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

# 流式响应超时（秒）
STREAM_SINGLE_CHUNK_TIMEOUT = 30
STREAM_TOTAL_TIMEOUT = 120
STREAM_MERGE_TIMEOUT = 130
