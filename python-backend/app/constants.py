"""
通用常量定义
"""

# 用户登录态在 Session 中的 key
USER_LOGIN_STATE = "user_login_state"

# 用户角色
DEFAULT_ROLE = "user"
ADMIN_ROLE = "admin"

# 对话类型
CONVERSATION_TYPE_SIDE_BY_SIDE = "side_by_side"
CONVERSATION_TYPE_PROMPT_LAB = "prompt_lab"
CONVERSATION_TYPE_BATTLE = "battle"

# 消息角色
MESSAGE_ROLE_USER = "user"
MESSAGE_ROLE_ASSISTANT = "assistant"

# 评分类型
RATING_TYPE_MODEL_BETTER = "model_better"
RATING_TYPE_TIE = "tie"
RATING_TYPE_BOTH_BAD = "both_bad"
RATING_TYPES = (RATING_TYPE_MODEL_BETTER, RATING_TYPE_TIE, RATING_TYPE_BOTH_BAD)

# Prompt Lab 的变体评分类型前缀：variant_0、variant_1 ...
# 不走 RATING_TYPES 白名单，由 rating_service 按前缀 + 数字单独校验
RATING_TYPE_VARIANT_PREFIX = "variant_"

# 国内模型提供商关键字（用于同步时标记 isChina）
CHINA_MODEL_PROVIDERS = [
    "qwen",
    "alibaba",
    "baidu",
    "tencent",
    "zhipu",
    "deepseek",
    "moonshot",
    "bytedance",
    "minimax",
    "01-ai",
    "ernie",
    "glm",
]

# 同步时排除的模型变体后缀
# OpenRouter 上带这些后缀的模型走的是另一套接入方式，不适合本平台的实时对话场景：
# - batch：批处理接口，异步提交、最长 24 小时才返回，走实时流式必然失败
# - extended：扩展上下文变体，价格与行为都和标准模型不同
EXCLUDED_MODEL_SUFFIXES = ("batch", "extended")

# 人工策展的推荐模型（同步时按这个列表设置 recommended 标记）
#
# 挑选原则：主流厂商、活跃维护、确定支持实时流式对话，并覆盖国内外各若干家，
# 方便用户打开页面就有可靠的默认对比组合。
# 注意：这里写的是精确的模型 ID，上游下线或改名后需要同步维护；
# 同步时会打印出本次未命中的条目，便于发现失效项。
RECOMMENDED_MODEL_IDS = [
    # 国内模型（访问速度更快，前端排序优先展示）
    "deepseek/deepseek-chat",
    "deepseek/deepseek-r1",
    "qwen/qwen3-235b-a22b",
    "moonshotai/kimi-k2",
    "z-ai/glm-4.6",
    "minimax/minimax-m2",
    # 海外模型
    "openai/gpt-5.2",
    "anthropic/claude-sonnet-4.5",
    "google/gemini-2.5-pro",
    "x-ai/grok-4.5",
    "meta-llama/llama-4-maverick",
    "mistralai/mistral-large-2512",
]

# Side-by-Side 并发约束
SIDE_BY_SIDE_MAX_MODELS = 8

# Prompt Lab 变体数量约束（教程：2-5 个）
MIN_PROMPT_VARIANTS_COUNT = 2
MAX_PROMPT_VARIANTS_COUNT = 5

# 流式响应超时（秒）
STREAM_SINGLE_CHUNK_TIMEOUT = 30
STREAM_TOTAL_TIMEOUT = 120
STREAM_MERGE_TIMEOUT = 130

# ============ 场景化批量测试 ============

# 预设场景的提示词归属用户ID：预设场景没有创建者，统一用 0 表示「系统内置」
PRESET_PROMPT_USER_ID = 0

# 场景提示词难度
PROMPT_DIFFICULTY_EASY = "easy"
PROMPT_DIFFICULTY_MEDIUM = "medium"
PROMPT_DIFFICULTY_HARD = "hard"
PROMPT_DIFFICULTIES = (PROMPT_DIFFICULTY_EASY, PROMPT_DIFFICULTY_MEDIUM, PROMPT_DIFFICULTY_HARD)

# 批量测试任务状态
TASK_STATUS_PENDING = "pending"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"
TASK_STATUS_CANCELLED = "cancelled"
TASK_STATUSES = (
    TASK_STATUS_PENDING,
    TASK_STATUS_RUNNING,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_CANCELLED,
)

# 批量测试并发与规模约束
# MAX_CONCURRENT_SUBTASKS 对应 asyncio.Semaphore 的令牌数：最多同时发起 N 次模型调用
MAX_CONCURRENT_SUBTASKS = 5
MAX_BATCH_TEST_MODELS = 8
MAX_BATCH_TEST_SUBTASKS = 60

# 单次子任务调用参数约束
BATCH_TEST_TEMPERATURE_MIN = 0.0
BATCH_TEST_TEMPERATURE_MAX = 2.0
BATCH_TEST_DEFAULT_TEMPERATURE = 0.7
BATCH_TEST_MAX_TOKENS_MIN = 128
BATCH_TEST_MAX_TOKENS_MAX = 8192
BATCH_TEST_DEFAULT_MAX_TOKENS = 2000
BATCH_TEST_TIMEOUT_SECONDS = 60

# 进度推送策略：每完成 N 个子任务推送一次（50 个任务推 50 次太频繁），
# 任务开始 / 结束 / 失败时无条件推送
PROGRESS_PUSH_INTERVAL = 10

# 用户评分范围
USER_RATING_MIN = 1
USER_RATING_MAX = 5

# 进度推送的 Redis Pub/Sub 频道前缀（多进程部署时的备用通道）
PROGRESS_CHANNEL_PREFIX = "task:progress:"

# 任务进度 WebSocket 订阅目的地前缀（与前端 /topic/task/{taskId} 对应）
TASK_TOPIC_PREFIX = "/topic/task/"
