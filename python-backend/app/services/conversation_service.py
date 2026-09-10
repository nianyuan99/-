"""
对话服务层

本节核心：多模型并排对比（Side-by-Side）。
Python 用 asyncio.Queue + asyncio.create_task 实现「多模型同时回答、谁先有数据谁先发」，
效果等价于 Java 版的 Flux.merge()。
"""

import asyncio
import logging
import time
import uuid
from decimal import Decimal
from typing import AsyncGenerator, List, Optional, Tuple

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import (
    CONVERSATION_TYPE_SIDE_BY_SIDE,
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_ROLE_USER,
    SIDE_BY_SIDE_MAX_MODELS,
    STREAM_MERGE_TIMEOUT,
    STREAM_SINGLE_CHUNK_TIMEOUT,
    STREAM_TOTAL_TIMEOUT,
)
from app.core.openrouter_config import OPENROUTER_EXTRA_HEADERS, get_async_openai_client
from app.db.session import AsyncSessionLocal
from app.exceptions import BusinessException, ErrorCode
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.model import Model
from app.schemas.conversation import (
    ConversationMessageVO,
    ConversationVO,
    SideBySideRequest,
    StreamChunkVO,
)
from app.utils.cost_calculator import CostCalculator

logger = logging.getLogger(__name__)

# 对话标题最大长度
TITLE_MAX_LENGTH = 30

# 历史消息最多带回的轮数，避免上下文无限膨胀
HISTORY_MAX_MESSAGES = 20

# 持有「取消后补写中断内容」的后台任务强引用。
# asyncio 官方提示：只 create_task 而不保留引用，任务可能被垃圾回收导致写库丢失。
_BACKGROUND_SAVE_TASKS: set[asyncio.Task] = set()


def _clean_reasoning(value: str) -> Optional[str]:
    """
    清洗思考过程文本

    个别模型（实测 nex-agi/nex-n2.5-mini:free）会在 reasoning 字段里返回
    只含换行 / 空格的伪内容，这种既展示不出东西、也不该算「有思考过程」，
    统一按「没有思考过程」处理，避免前端渲染出一个空的灰色折叠框。
    """
    return value if value and value.strip() else None


class ConversationService:
    """对话服务类"""

    def __init__(self, db: AsyncSession, redis_client=None):
        self.db = db
        self.redis = redis_client
        self.openai_client = get_async_openai_client()

    # ============ 对外方法：Side-by-Side 流式对比 ============

    async def side_by_side_stream(
        self, request: SideBySideRequest, user_id: int
    ) -> AsyncGenerator[str, None]:
        """
        Side-by-Side 多模型并排对比（SSE 流式响应）

        整体流程：参数校验 → 创建/获取对话记录 → 保存用户消息 → 为每个模型创建独立流
        → _merge_streams 合并 → 逐个 yield 给前端。

        Args:
            request: 对比请求
            user_id: 当前登录用户ID

        Yields:
            SSE 格式的字符串（data: {json}\n\n）
        """
        # ========== 1. 参数校验 ==========
        if not request.models or len(request.models) == 0:
            raise BusinessException(ErrorCode.PARAMS_ERROR, "模型列表不能为空")
        if len(request.models) > SIDE_BY_SIDE_MAX_MODELS:
            raise BusinessException(
                ErrorCode.PARAMS_ERROR, f"最多支持{SIDE_BY_SIDE_MAX_MODELS}个模型"
            )
        prompt = (request.prompt or "").strip()
        if not prompt:
            raise BusinessException(ErrorCode.PARAMS_ERROR, "提示词不能为空")

        # ========== 2. 创建或获取对话记录 ==========
        # 注意：整个方法体在流式响应开始后才真正执行，主请求的 db session 可能已被回收，
        # 因此这里统一使用独立的 AsyncSessionLocal。
        conversation_id = request.conversation_id
        async with AsyncSessionLocal() as independent_db:
            if conversation_id:
                result = await independent_db.execute(
                    select(Conversation).where(
                        Conversation.id == conversation_id,
                        Conversation.user_id == user_id,
                        Conversation.is_delete == 0,
                    )
                )
                conversation = result.scalar_one_or_none()
                if not conversation:
                    raise BusinessException(ErrorCode.NOT_FOUND_ERROR, "对话不存在")
            else:
                conversation_id = str(uuid.uuid4())
                independent_db.add(
                    Conversation(
                        id=conversation_id,
                        user_id=user_id,
                        title=self._generate_title(prompt),
                        conversation_type=CONVERSATION_TYPE_SIDE_BY_SIDE,
                        models=request.models,
                        code_preview_enabled=0,
                        total_tokens=0,
                        total_cost=Decimal("0"),
                        is_delete=0,
                    )
                )

            # ========== 3. 保存用户消息，获取 messageIndex ==========
            user_message_index = await self._save_user_message(
                independent_db, conversation_id, user_id, prompt
            )
            await independent_db.commit()

        assistant_message_index = user_message_index + 1

        # ========== 4. 为每个模型创建独立的流 ==========
        tasks = [
            self._stream_single_model(
                conversation_id=conversation_id,
                user_id=user_id,
                model_name=model_name,
                prompt=prompt,
                message_index=assistant_message_index,
                variant_index=None,
                image_urls=request.image_urls,
                web_search_enabled=bool(request.web_search_enabled),
            )
            for model_name in request.models
        ]

        # ========== 5. 合并所有流并返回 ==========
        async for event in self._merge_streams(tasks, request.models, conversation_id):
            yield event

    async def _stream_single_model(
        self,
        conversation_id: str,
        user_id: int,
        model_name: str,
        prompt: str,
        message_index: int,
        variant_index: Optional[int],
        image_urls: Optional[List[str]],
        web_search_enabled: bool,
        system_prompt: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        调用单个模型并流式返回结果

        Args:
            conversation_id: 对话ID
            user_id: 用户ID
            model_name: 模型名称
            prompt: 本轮用户提问
            message_index: 本轮 AI 回复的消息序号
            variant_index: 变体索引（Prompt Lab 场景使用，Side-by-Side 传 None）
            image_urls: 图片URL列表
            web_search_enabled: 是否启用联网搜索
            system_prompt: 系统提示词

        Yields:
            SSE 格式的字符串（data: {json}\n\n）
        """
        # ========== 第一步：初始化计数器 ==========
        start_time = time.time()
        accumulated_content = ""
        accumulated_reasoning = ""
        input_tokens = CostCalculator.estimate_tokens(prompt)
        output_tokens = 0
        thinking_start_time = None
        # 价格在第二步才加载，这里先兜底为 None：
        # 如果在加载完成前就被取消，中断落库仍能正常执行（成本按 0 计算）
        input_price: Optional[Decimal] = None
        output_price: Optional[Decimal] = None

        try:
            # ========== 第二步：加载历史消息与模型价格 ==========
            async with AsyncSessionLocal() as history_db:
                history_messages = await self._load_history_messages(
                    history_db, conversation_id, message_index
                )
                input_price, output_price = await self._load_model_prices(history_db, model_name)

            messages: List[dict] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            for role, content in history_messages:
                messages.append({"role": role, "content": content})

            # 添加当前用户消息（支持图片输入）
            if image_urls:
                current_content: List[dict] = [{"type": "text", "text": prompt}]
                for image_url in image_urls:
                    current_content.append({"type": "image_url", "image_url": {"url": image_url}})
                messages.append({"role": "user", "content": current_content})
            else:
                messages.append({"role": "user", "content": prompt})

            # ========== 第三步：流式调用 AI 模型 ==========
            stream = await self.openai_client.chat.completions.create(
                model=model_name,
                messages=messages,
                stream=True,
                temperature=0.7,
                timeout=60.0,
                extra_headers=OPENROUTER_EXTRA_HEADERS,
            )

            # ========== 第四步：处理流式数据 ==========
            stream_iter = stream.__aiter__()

            while True:
                # 超时保护：单次调用总时长不超过 120 秒
                if (time.time() - start_time) > STREAM_TOTAL_TIMEOUT:
                    logger.warning("模型 %s 达到总时长上限，提前结束", model_name)
                    break
                try:
                    # 单次读取超时 30 秒，避免某个模型卡死拖垮整轮对比
                    chunk = await asyncio.wait_for(
                        stream_iter.__anext__(), timeout=STREAM_SINGLE_CHUNK_TIMEOUT
                    )
                except StopAsyncIteration:
                    break

                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                # 提取思考内容（DeepSeek R1 等推理模型）——OpenAI SDK 原生支持 reasoning 属性
                if hasattr(delta, "reasoning") and delta.reasoning:
                    accumulated_reasoning += delta.reasoning
                    if thinking_start_time is None:
                        thinking_start_time = time.time()

                    # 只有拿到实质内容才推送，避免把空白字符当成思考过程展示
                    if _clean_reasoning(accumulated_reasoning):
                        reasoning_vo = StreamChunkVO(
                            conversation_id=conversation_id,
                            model_name=model_name,
                            message_index=message_index,
                            reasoning=accumulated_reasoning,
                            has_reasoning=True,
                            elapsed_ms=int((time.time() - start_time) * 1000),
                            done=False,
                            has_error=False,
                        )
                        yield f"data: {reasoning_vo.model_dump_json(by_alias=True, exclude_none=True)}\n\n"

                # 提取正文内容
                if delta.content:
                    content = delta.content
                    accumulated_content += content
                    output_tokens += CostCalculator.estimate_tokens(content)

                    chunk_vo = StreamChunkVO(
                        conversation_id=conversation_id,
                        model_name=model_name,
                        message_index=message_index,
                        content=content,
                        full_content=accumulated_content,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        elapsed_ms=int((time.time() - start_time) * 1000),
                        done=False,
                        has_error=False,
                    )
                    yield f"data: {chunk_vo.model_dump_json(by_alias=True, exclude_none=True)}\n\n"

            # ========== 第五步：流结束，落库并发送完成事件 ==========
            response_time_ms = int((time.time() - start_time) * 1000)
            cost = CostCalculator.calculate_cost(
                model_name, input_tokens, output_tokens, input_price, output_price
            )
            reasoning = _clean_reasoning(accumulated_reasoning)

            async with AsyncSessionLocal() as independent_db:
                await self._save_assistant_message(
                    independent_db,
                    conversation_id,
                    user_id,
                    message_index,
                    model_name,
                    variant_index,
                    accumulated_content,
                    input_tokens,
                    output_tokens,
                    cost,
                    response_time_ms,
                    reasoning,
                )

            done_vo = StreamChunkVO(
                conversation_id=conversation_id,
                model_name=model_name,
                message_index=message_index,
                full_content=accumulated_content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=float(cost) if cost is not None else None,
                response_time_ms=response_time_ms,
                done=True,
                has_error=False,
                reasoning=reasoning,
                has_reasoning=bool(reasoning),
                thinking_time=int(time.time() - thinking_start_time) if reasoning and thinking_start_time else None,
            )
            yield f"data: {done_vo.model_dump_json(by_alias=True, exclude_none=True)}\n\n"

        except asyncio.CancelledError:
            # 客户端中断（用户点了「停止生成」）时会走到这里，属于正常流程，不当作错误。
            # 但用户希望停止后在历史记录里还能看到已经生成的那半截回答，
            # 所以这里要把已累积的内容落库 —— 否则这轮 AI 回复在库里完全不存在，
            # 前端却仍显示评分按钮，评分就会指向一个不存在的消息序号（孤儿数据）。
            logger.info("模型 %s 的流被取消，保存已生成内容", model_name)
            await self._save_interrupted_message(
                conversation_id=conversation_id,
                user_id=user_id,
                message_index=message_index,
                model_name=model_name,
                content=accumulated_content,
                reasoning=accumulated_reasoning,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                input_price=input_price,
                output_price=output_price,
                start_time=start_time,
            )
            raise
        except Exception as e:
            # 错误隔离：一个模型出错不影响其他模型继续输出
            logger.exception("模型 %s 调用失败", model_name)
            error_vo = StreamChunkVO(
                conversation_id=conversation_id,
                model_name=model_name,
                message_index=message_index,
                error=f"{type(e).__name__}: {e}",
                has_error=True,
                done=True,
            )
            yield f"data: {error_vo.model_dump_json(by_alias=True, exclude_none=True)}\n\n"

    async def _merge_streams(
        self,
        tasks: List[AsyncGenerator[str, None]],
        model_names: List[str],
        conversation_id: str,
    ) -> AsyncGenerator[str, None]:
        """
        合并多个流式响应

        每个流一个队列，consume_stream 负责把事件放进队列，
        主循环轮询所有队列，谁先有数据谁先发，实现真正的并行推送。
        """
        queues = {i: asyncio.Queue() for i in range(len(tasks))}
        done_flags = {i: False for i in range(len(tasks))}

        async def consume_stream(idx: int, stream: AsyncGenerator[str, None], model_name: str):
            """消费单个流，把事件放入队列"""
            try:
                async for event in stream:
                    await queues[idx].put(event)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                # 兜底：单个流内部已做错误隔离，这里是最后一道防线
                logger.exception("消费模型 %s 的流时发生异常", model_name)
                error_vo = StreamChunkVO(
                    conversation_id=conversation_id,
                    model_name=model_name,
                    error=str(e),
                    has_error=True,
                    done=True,
                )
                await queues[idx].put(
                    f"data: {error_vo.model_dump_json(by_alias=True, exclude_none=True)}\n\n"
                )
            finally:
                done_flags[idx] = True
                await queues[idx].put(None)  # 结束标记

        # 启动所有消费任务（真正并行）
        consumers = [
            asyncio.create_task(consume_stream(i, task, model_names[i]))
            for i, task in enumerate(tasks)
        ]

        merge_deadline = time.time() + STREAM_MERGE_TIMEOUT

        try:
            while True:
                # 把各队列中已到达的事件一次性全部取完，谁先有数据谁先发
                for queue in queues.values():
                    while True:
                        try:
                            event = queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                        if event is not None:
                            yield event

                # 必须「所有流都结束」且「队列已排空」才能退出。
                # 只判断 done_flags 会在最后一个模型结束时立即退出，
                # 把它还排在队列里的事件（例如错误提示、最后一段内容）丢掉。
                if all(done_flags.values()) and all(queue.empty() for queue in queues.values()):
                    break

                if time.time() > merge_deadline:
                    logger.warning("多流合并达到总超时，取消未完成的流")
                    for i, consumer in enumerate(consumers):
                        if not done_flags[i]:
                            consumer.cancel()
                    break

                await asyncio.sleep(0.01)
        finally:
            # 客户端断开或提前退出时，取消仍在跑的任务，
            # 避免继续消耗模型调用（对应「停止生成」的语义）
            for i, consumer in enumerate(consumers):
                if not done_flags[i] and not consumer.done():
                    consumer.cancel()
            await asyncio.gather(*consumers, return_exceptions=True)

    # ============ 对外方法：历史记录查询 ============

    async def list_conversations(
        self,
        user_id: int,
        conversation_type: Optional[str] = None,
        current: int = 1,
        page_size: int = 10,
    ) -> dict:
        """
        分页查询当前用户的对话列表

        Returns:
            包含 records / total / current / pageSize 的分页结果
        """
        query = select(Conversation).where(
            Conversation.user_id == user_id, Conversation.is_delete == 0
        )
        if conversation_type:
            query = query.where(Conversation.conversation_type == conversation_type)

        count_result = await self.db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar() or 0

        query = (
            query.order_by(Conversation.update_time.desc())
            .offset((current - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(query)
        conversations = result.scalars().all()

        return {
            "records": [
                ConversationVO.model_validate(item).model_dump(by_alias=True, mode="json")
                for item in conversations
            ],
            "total": total,
            "current": current,
            "pageSize": page_size,
        }

    async def get_conversation_messages(
        self, conversation_id: str, user_id: int
    ) -> List[ConversationMessageVO]:
        """
        查询某个对话的全部消息（按 messageIndex 升序）

        同一轮会有多个模型的回复，它们的 messageIndex 相同，前端按 modelName 区分。
        """
        result = await self.db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
                Conversation.is_delete == 0,
            )
        )
        if not result.scalar_one_or_none():
            raise BusinessException(ErrorCode.NOT_FOUND_ERROR, "对话不存在")

        message_result = await self.db.execute(
            select(ConversationMessage)
            .where(
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.is_delete == 0,
            )
            .order_by(ConversationMessage.message_index.asc(), ConversationMessage.create_time.asc())
        )
        return [
            ConversationMessageVO.model_validate(message)
            for message in message_result.scalars().all()
        ]

    # ============ 内部方法：数据库操作 ============

    async def _save_user_message(
        self, db: AsyncSession, conversation_id: str, user_id: int, prompt: str
    ) -> int:
        """
        保存用户消息，返回本轮消息序号

        序号在当前对话最大 messageIndex 基础上 +1，保证多轮对话顺序递增。
        """
        result = await db.execute(
            select(func.max(ConversationMessage.message_index)).where(
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.is_delete == 0,
            )
        )
        max_index = result.scalar()
        user_message_index = (max_index + 1) if max_index is not None else 0

        db.add(
            ConversationMessage(
                id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                user_id=user_id,
                message_index=user_message_index,
                role=MESSAGE_ROLE_USER,
                content=prompt,
                is_delete=0,
            )
        )
        return user_message_index

    async def _save_assistant_message(
        self,
        db: AsyncSession,
        conversation_id: str,
        user_id: int,
        message_index: int,
        model_name: str,
        variant_index: Optional[int],
        content: str,
        input_tokens: int,
        output_tokens: int,
        cost: Decimal,
        response_time_ms: int,
        reasoning: Optional[str],
    ) -> None:
        """
        保存 AI 回复，并累加对话/模型的消耗统计

        variant_index 仅用于 Prompt Lab 场景定位变体，消息表没有对应列，因此不落库。
        """
        db.add(
            ConversationMessage(
                id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                user_id=user_id,
                message_index=message_index,
                role=MESSAGE_ROLE_ASSISTANT,
                model_name=model_name,
                content=content,
                response_time_ms=response_time_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                reasoning=reasoning,
                is_delete=0,
            )
        )

        total_tokens = (input_tokens or 0) + (output_tokens or 0)
        # 用 SQL 表达式自增，避免多模型并发写覆盖彼此的统计值
        await db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(
                total_tokens=Conversation.total_tokens + total_tokens,
                total_cost=Conversation.total_cost + cost,
            )
        )
        await db.execute(
            update(Model)
            .where(Model.id == model_name)
            .values(
                total_tokens=Model.total_tokens + total_tokens,
                total_cost=Model.total_cost + cost,
            )
        )
        await db.commit()

    async def _save_interrupted_message(
        self,
        conversation_id: str,
        user_id: int,
        message_index: int,
        model_name: str,
        content: str,
        reasoning: str,
        input_tokens: int,
        output_tokens: int,
        input_price: Optional[Decimal],
        output_price: Optional[Decimal],
        start_time: float,
    ) -> None:
        """
        用户中途停止生成时，把已经生成的部分内容落库

        难点在于「取消状态下的写库」：当前协程已经收到 CancelledError，
        如果直接 await 数据库操作，一旦外层再取消一次（合并逻辑收尾、服务关闭等），
        写库就可能写到一半被打断。所以把落库包成一个独立任务并用 asyncio.shield 保护：
        即使本协程再次被取消，写库任务也会继续在后台跑完。
        """
        if not content.strip() and not reasoning.strip():
            # 一个字都没生成出来，没必要留一条空消息（否则前端评分会指向无意义的记录）
            logger.info("模型 %s 被取消且未产生内容，跳过落库", model_name)
            return

        response_time_ms = int((time.time() - start_time) * 1000)
        cost = CostCalculator.calculate_cost(
            model_name, input_tokens, output_tokens, input_price, output_price
        )

        async def persist() -> None:
            async with AsyncSessionLocal() as independent_db:
                await self._save_assistant_message(
                    independent_db,
                    conversation_id,
                    user_id,
                    message_index,
                    model_name,
                    None,
                    content,
                    input_tokens,
                    output_tokens,
                    cost,
                    response_time_ms,
                    _clean_reasoning(reasoning),
                )

        persist_task = asyncio.create_task(persist())
        _BACKGROUND_SAVE_TASKS.add(persist_task)
        persist_task.add_done_callback(_BACKGROUND_SAVE_TASKS.discard)
        # 合并逻辑在收尾时会对这些消费任务再取消一次，
        # 这里先清掉当前任务的取消状态，让写库能一路 await 到提交完成，
        # 不会出现「响应都结束了、数据稍后才落库」的时间差。
        current_task = asyncio.current_task()
        if current_task is not None:
            current_task.uncancel()
        try:
            await asyncio.shield(persist_task)
        except asyncio.CancelledError:
            logger.info("保存模型 %s 的中断内容时再次被取消，写库已转入后台完成", model_name)
        except Exception:
            logger.exception("保存模型 %s 的中断内容失败", model_name)

    async def _load_history_messages(
        self, db: AsyncSession, conversation_id: str, before_index: int
    ) -> List[Tuple[str, str]]:
        """
        加载本轮之前的历史消息，用于构建多轮上下文

        Args:
            before_index: 只取 messageIndex 小于该值的消息（即本轮用户消息之前的内容）

        Returns:
            [(role, content), ...]
        """
        result = await db.execute(
            select(ConversationMessage.role, ConversationMessage.content)
            .where(
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.message_index < before_index,
                ConversationMessage.is_delete == 0,
            )
            .order_by(ConversationMessage.message_index.asc())
        )
        rows = result.all()
        # 只保留最近 N 条，避免上下文无限膨胀
        return [(row[0], row[1]) for row in rows[-HISTORY_MAX_MESSAGES:]]

    async def _load_model_prices(
        self, db: AsyncSession, model_name: str
    ) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        """加载模型的输入/输出价格，用于成本计算"""
        result = await db.execute(
            select(Model.input_price, Model.output_price).where(
                Model.id == model_name, Model.is_delete == 0
            )
        )
        row = result.first()
        if not row:
            return None, None
        return row[0], row[1]

    # ============ 内部方法：工具 ============

    @staticmethod
    def _generate_title(prompt: str) -> str:
        """用提问的前 N 个字符生成对话标题"""
        title = prompt.strip().replace("\n", " ")
        return title[:TITLE_MAX_LENGTH] if len(title) > TITLE_MAX_LENGTH else title
