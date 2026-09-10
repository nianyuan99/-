<template>
  <div class="sb-root">
    <!-- ==================== 左侧：会话历史 ==================== -->
    <aside class="sb-sidebar">
      <RouterLink to="/" class="sb-brand" title="返回首页">
        <img class="sb-brand-logo" src="@/assets/logo.svg" alt="Logo" />
        <span class="sb-brand-title">大模型评测平台</span>
      </RouterLink>

      <button class="sb-new-chat" :disabled="isLoading" @click="startNewConversation">
        <EditOutlined />
        <span>新对话</span>
      </button>

      <div class="sb-history">
        <div class="sb-history-label">更早</div>
        <div
          v-for="conv in conversations"
          :key="conv.id"
          class="sb-conv"
          :class="{ active: conv.id === currentConversationId }"
          :title="conv.title || '未命名对话'"
          @click="loadConversation(conv.id)"
        >
          <span class="sb-conv-icons">
            <span
              v-for="(model, i) in (conv.models || []).slice(0, 2)"
              :key="i"
              class="sb-conv-icon"
              :style="{ background: getProviderColor(model) }"
            >
              {{ getProviderLabel(model).charAt(0).toUpperCase() }}
            </span>
          </span>
          <span class="sb-conv-title">{{ conv.title || '未命名对话' }}</span>
        </div>
        <div v-if="historyLoading" class="sb-history-tip">加载中…</div>
        <div v-else-if="conversations.length === 0" class="sb-history-tip">还没有历史对话</div>
      </div>

      <a-dropdown placement="topLeft" :trigger="['click']">
        <div class="sb-user">
          <a-avatar :size="26" :src="loginUserStore.loginUser.userAvatar" />
          <span class="sb-user-name">{{ loginUserStore.loginUser.userName ?? '未登录' }}</span>
        </div>
        <template #overlay>
          <a-menu>
            <a-menu-item key="home" @click="router.push('/')">
              <HomeOutlined />
              返回首页
            </a-menu-item>
            <a-menu-item key="logout" @click="doLogout">
              <LogoutOutlined />
              退出登录
            </a-menu-item>
          </a-menu>
        </template>
      </a-dropdown>
    </aside>

    <!-- ==================== 右侧：主区域 ==================== -->
    <main class="sb-main">
      <!-- 顶部：模式 + 模型选择 -->
      <header class="sb-topbar">
        <div class="mode-wrap">
          <SwapOutlined class="mode-icon" />
          <a-select
            v-model:value="mode"
            :options="modeOptions"
            :disabled="isLoading"
            class="mode-select"
          />
        </div>

        <template v-if="mode === 'compare'">
          <a-select
            v-model:value="modelA"
            :options="optionsForA"
            :loading="modelLoading"
            :disabled="isLoading"
            :filter-option="filterModelOption"
            popup-class-name="sb-select-popup"
            :virtual="false"
            show-search
            class="sb-select"
            placeholder="选择第一个模型"
          />
          <span class="sb-vs">vs</span>
          <a-select
            v-model:value="modelB"
            :options="optionsForB"
            :loading="modelLoading"
            :disabled="isLoading"
            :filter-option="filterModelOption"
            popup-class-name="sb-select-popup"
            :virtual="false"
            show-search
            class="sb-select"
            placeholder="选择第二个模型"
          />
        </template>
        <a-select
          v-else
          v-model:value="modelA"
          :options="modelOptions"
          :loading="modelLoading"
          :disabled="isLoading"
          :filter-option="filterModelOption"
          popup-class-name="sb-select-popup"
          :virtual="false"
          show-search
          class="sb-select wide"
          placeholder="选择一个模型"
        />

        <span class="sb-topbar-spacer" />

        <a-tooltip title="隐藏模型名称，评分后才揭晓，避免「看到牌子就觉得好」的品牌偏见">
          <div class="sb-blind">
            <EyeInvisibleOutlined />
            <span>盲测</span>
            <a-switch v-model:checked="blindMode" size="small" :disabled="isLoading" />
          </div>
        </a-tooltip>
      </header>

      <!-- 中间：消息列表 -->
      <div class="sb-messages-wrap">
        <div ref="listRef" class="sb-messages" @scroll="onScroll">
          <div v-if="messages.length === 0" class="sb-empty">
            <div class="sb-empty-title">选择模型，开始对比</div>
            <div class="sb-empty-desc">
              同一个问题让多个模型同时作答，横向对比响应速度、Token 消耗与回答质量
            </div>
          </div>

          <div v-for="(msg, idx) in messages" :key="idx" class="sb-row">
            <!-- 用户提问 -->
            <div v-if="msg.type === 'user'" class="sb-user-line">
              <div class="sb-user-bubble">{{ msg.content }}</div>
            </div>

            <!-- AI 并排回答 -->
            <template v-else>
              <div
                v-if="msg.responses"
                class="sb-grid"
                :style="{ gridTemplateColumns: gridColumns(msg) }"
              >
                <div
                  v-for="(resp, respIndex) in msg.responses"
                  :key="`${resp.modelName}-${respIndex}`"
                  class="sb-card"
                >
                  <!-- 卡片头：模型名 + 实时指标 + 操作 -->
                  <div class="sb-card-head">
                    <span
                      class="sb-avatar"
                      :style="{ background: isBlind(msg) ? '#c9ced6' : getProviderColor(resp.modelName) }"
                    >
                      {{
                        isBlind(msg)
                          ? getBlindCode(respIndex)
                          : getProviderLabel(resp.modelName).charAt(0).toUpperCase()
                      }}
                    </span>
                    <span class="sb-model-name" :title="isBlind(msg) ? '' : resp.modelName">
                      {{ isBlind(msg) ? getBlindLabel(respIndex) : getModelName(resp.modelName) }}
                    </span>

                    <span class="sb-head-spacer" />

                    <span v-if="resp.elapsedMs" class="sb-metric">
                      <ClockCircleOutlined />
                      {{ (resp.elapsedMs / 1000).toFixed(2) }}s
                    </span>
                    <span v-if="totalTokens(resp)" class="sb-metric">
                      <BarChartOutlined />
                      {{ totalTokens(resp) }}t
                    </span>
                    <span v-if="resp.cost != null" class="sb-metric">
                      <DollarOutlined />
                      {{ resp.cost.toFixed(4) }}
                    </span>
                    <button
                      class="sb-icon-btn"
                      title="复制回答"
                      :disabled="!resp.fullContent"
                      @click="copyResponse(resp)"
                    >
                      <CopyOutlined />
                    </button>
                    <button
                      class="sb-icon-btn"
                      title="查看完整回答"
                      :disabled="!resp.fullContent"
                      @click="openExpand(resp)"
                    >
                      <ExpandOutlined />
                    </button>
                  </div>

                  <!-- 错误提示 -->
                  <a-alert
                    v-if="resp.hasError"
                    type="error"
                    :message="resp.error || '该模型调用失败'"
                    show-icon
                    class="sb-alert"
                  />

                  <!-- 思考过程（推理模型） -->
                  <div v-if="hasReasoning(resp)" class="sb-reasoning">
                    <div class="sb-reasoning-head" @click="toggleReasoning(idx, respIndex)">
                      <DownOutlined
                        class="sb-caret"
                        :class="{ collapsed: isReasoningCollapsed(idx, respIndex) }"
                      />
                      <span>
                        {{ resp.thinkingTime ? `思考了 ${resp.thinkingTime} 秒` : '思考过程' }}
                      </span>
                    </div>
                    <div
                      v-show="!isReasoningCollapsed(idx, respIndex)"
                      class="sb-reasoning-body"
                    >
                      <MarkdownRenderer :content="resp.reasoning" />
                    </div>
                  </div>

                  <!-- 最终回答 -->
                  <MarkdownRenderer :content="resp.fullContent || ''" />

                  <!-- 生成中 -->
                  <div v-if="!resp.done && !resp.hasError" class="sb-dots">
                    <span></span><span></span><span></span>
                  </div>

                  <!-- 被用户停止 -->
                  <div v-if="resp.stopped" class="sb-stopped-tip">
                    已停止生成 · 以上为已生成的内容，已保存到历史记录
                  </div>
                </div>
              </div>

              <!-- 底部：评分 + 导出 -->
              <div v-if="canRate(msg)" class="sb-footer">
                <div class="sb-rating">
                  <button
                    v-for="(resp, respIndex) in msg.responses"
                    :key="`better-${respIndex}`"
                    class="sb-rating-btn"
                    :class="{ selected: isModelSelected(msg, resp.modelName) }"
                    @click="handleRating(idx, 'model_better', resp.modelName)"
                  >
                    {{ isBlind(msg) ? getBlindLabel(respIndex) : getModelName(resp.modelName) }} 更好
                  </button>
                  <button
                    class="sb-rating-btn"
                    :class="{ selected: msg.rating?.ratingType === 'tie' }"
                    @click="handleRating(idx, 'tie')"
                  >
                    平局 😐
                  </button>
                  <button
                    class="sb-rating-btn"
                    :class="{ selected: msg.rating?.ratingType === 'both_bad' }"
                    @click="handleRating(idx, 'both_bad')"
                  >
                    都不好 👎
                  </button>
                </div>
                <button class="sb-export" title="导出本轮对比为 Markdown" @click="exportComparison(idx)">
                  <DownloadOutlined />
                </button>
              </div>
              <div v-else-if="isBlind(msg) && (msg.responses?.length ?? 0) >= 2" class="sb-footer">
                <span class="sb-blind-hint">评分后揭晓真实模型</span>
              </div>
            </template>
          </div>
        </div>

        <button v-if="!atBottom" class="sb-scroll-btn" title="回到最新" @click="scrollToBottom(true)">
          <DownOutlined />
        </button>
      </div>

      <!-- 底部：输入区 -->
      <div class="sb-composer-wrap">
        <div class="sb-composer">
          <textarea
            ref="inputRef"
            v-model="userInput"
            class="sb-textarea"
            placeholder="输入你的问题..."
            :disabled="isLoading"
            @keydown.ctrl.enter.prevent="sendMessage"
            @keydown.meta.enter.prevent="sendMessage"
          />
          <div class="sb-composer-bar">
            <button class="sb-icon-btn lg" title="聚焦输入框" @click="focusInput">
              <SearchOutlined />
            </button>
            <button v-if="isLoading" class="sb-send stop" title="停止生成" @click="stopGeneration">
              <StopOutlined />
            </button>
            <button
              v-else
              class="sb-send"
              :disabled="!canSend"
              title="发送（Ctrl + Enter）"
              @click="sendMessage"
            >
              <ArrowUpOutlined />
            </button>
          </div>
        </div>
      </div>
    </main>

    <!-- 完整回答查看 -->
    <a-modal v-model:open="expandOpen" :title="expandTarget?.title" :footer="null" width="820px">
      <div class="sb-expand-body">
        <div v-if="expandTarget?.reasoning" class="sb-reasoning">
          <div class="sb-reasoning-head">
            <DownOutlined class="sb-caret" />
            <span>思考过程</span>
          </div>
          <div class="sb-reasoning-body">
            <MarkdownRenderer :content="expandTarget.reasoning" />
          </div>
        </div>
        <MarkdownRenderer :content="expandTarget?.content || ''" />
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  ArrowUpOutlined,
  BarChartOutlined,
  ClockCircleOutlined,
  CopyOutlined,
  DollarOutlined,
  DownloadOutlined,
  DownOutlined,
  EditOutlined,
  ExpandOutlined,
  EyeInvisibleOutlined,
  HomeOutlined,
  LogoutOutlined,
  SearchOutlined,
  StopOutlined,
  SwapOutlined,
} from '@ant-design/icons-vue'
import { API_BASE_URL } from '@/config/env'
import { userLogout } from '@/api/user'
import { useLoginUserStore } from '@/stores/loginUser'
import {
  addRating,
  listConversationMessages,
  listConversationVoByPage,
  listRatings,
  type ConversationVO,
  type RatingVO,
  type StreamChunkVO,
} from '@/api/conversation'
import { listModels, type ModelVO } from '@/api/model'
import { createPostSSE, type SSEHandle } from '@/utils/sseClient'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'

/** 页面模式：模型对比（两个模型 vs）/ 单模型 */
type Mode = 'compare' | 'single'

/** 距离底部多少像素内算「贴着底部」，此时新内容自动跟随滚动 */
const AUTO_SCROLL_THRESHOLD = 80

/** 侧栏一次拉取的历史会话条数 */
const HISTORY_PAGE_SIZE = 30

/** 单个模型的回答状态 */
interface ModelResponse {
  modelName: string
  fullContent: string
  reasoning?: string
  done: boolean
  hasError: boolean
  error?: string
  elapsedMs?: number
  responseTimeMs?: number
  inputTokens?: number
  outputTokens?: number
  cost?: number
  hasReasoning?: boolean
  thinkingTime?: number
  /** 是否被用户主动停止生成（区别于调用失败） */
  stopped?: boolean
}

/** 页面中的一条消息 */
interface ChatMessage {
  type: 'user' | 'assistant'
  content?: string
  conversationId?: string
  messageIndex?: number
  responses?: ModelResponse[]
  rating?: { ratingType: string; winnerModel?: string }
}

const router = useRouter()
const loginUserStore = useLoginUserStore()

// ---------- 模型 ----------
const modelList = ref<ModelVO[]>([])
const modelLoading = ref(false)
const mode = ref<Mode>('compare')
const modelA = ref<string>()
const modelB = ref<string>()

const modeOptions = [
  { value: 'compare', label: '模型对比' },
  { value: 'single', label: '单模型' },
]

// ---------- 会话 ----------
const messages = ref<ChatMessage[]>([])
const userInput = ref('')
const isLoading = ref(false)
const blindMode = ref(false)
const currentConversationId = ref<string | null>(null)
const conversations = ref<ConversationVO[]>([])
const historyLoading = ref(false)

// ---------- 视图状态 ----------
const listRef = ref<HTMLElement>()
const inputRef = ref<HTMLTextAreaElement>()
const atBottom = ref(true)
const collapsedReasoning = ref<Set<string>>(new Set())
const expandOpen = ref(false)
const expandTarget = ref<{ title: string; content: string; reasoning?: string }>()
const sse = ref<SSEHandle | null>(null)

/** 下拉里的一个叶子选项 */
interface ModelOption {
  value: string
  label: string
  name?: string
}

/** 下拉里的一个分组（厂商） */
interface ModelOptionGroup {
  label: string
  options: ModelOption[]
}

/** 免费模型的分组标题 */
const FREE_GROUP_LABEL = '免费'

/** OpenRouter 免费变体：模型 ID 以 `:free` 结尾 */
const isFreeModel = (model: ModelVO) => model.id.endsWith(':free')

/** 展示名去掉「厂商: 」前缀 —— 分组标题已经写了厂商，二级菜单里再重复一遍太啰嗦 */
const shortModelName = (model: ModelVO) => {
  const name = model.name || model.id
  const sep = name.indexOf(': ')
  return sep > 0 ? name.slice(sep + 2) : name
}

/** 厂商展示名：优先取展示名的前缀，取不到再退回 provider 字段 */
const vendorLabel = (model: ModelVO) => {
  const name = model.name || ''
  const sep = name.indexOf(': ')
  if (sep > 0) return name.slice(0, sep)
  return model.provider || '其他'
}

/**
 * 模型下拉选项（分组结构）：第一组是免费模型，其余按厂商分组
 *
 * 排序：先整体按「发布时间由新到旧」（取 OpenRouter 的 created），
 * 因此组内是新的在前、厂商分组也按各自最新模型的时间从新到旧排；
 * 拿不到发布时间的模型排在最后。
 * 免费变体不挂在各自厂商下面，而是单独抽成一个分组放在最前面，
 * 没充值时打开就能直接挑一个能用的（付费模型会 402）。
 */
const modelOptions = computed(() => {
  const sorted = [...modelList.value].sort((a, b) => (b.created ?? 0) - (a.created ?? 0))
  const free: ModelOption[] = []
  const vendors = new Map<string, ModelOption[]>()
  for (const model of sorted) {
    const option: ModelOption = {
      value: model.id,
      label: shortModelName(model),
      name: model.name,
    }
    if (isFreeModel(model)) {
      free.push(option)
      continue
    }
    const vendor = vendorLabel(model)
    const group = vendors.get(vendor)
    if (group) group.push(option)
    else vendors.set(vendor, [option])
  }

  const groups: ModelOptionGroup[] = []
  if (free.length) groups.push({ label: FREE_GROUP_LABEL, options: free })
  for (const [label, options] of vendors) groups.push({ label, options })
  return groups
})

/** 分组内摘掉某个模型（对比模式下两个下拉互斥）；摘空了的分组直接隐藏 */
const excludeModel = (groups: ModelOptionGroup[], excluded?: string) =>
  groups
    .map((group) => ({ ...group, options: group.options.filter((opt) => opt.value !== excluded) }))
    .filter((group) => group.options.length > 0)

const optionsForA = computed(() => excludeModel(modelOptions.value, modelB.value))
const optionsForB = computed(() => excludeModel(modelOptions.value, modelA.value))

/** 下拉搜索：模型 ID、完整展示名、去前缀的名字都能命中 */
const filterModelOption = (input: string, option: ModelOption) => {
  const keyword = input.trim().toLowerCase()
  if (!keyword) return true
  return (
    String(option.value).toLowerCase().includes(keyword) ||
    String(option.name || '').toLowerCase().includes(keyword) ||
    String(option.label || '').toLowerCase().includes(keyword)
  )
}

/** 本次要请求的模型列表 */
const selectedModels = computed(() => {
  if (mode.value === 'single') return modelA.value ? [modelA.value] : []
  return [modelA.value, modelB.value].filter((item): item is string => !!item)
})

const canSend = computed(() => {
  const need = mode.value === 'compare' ? 2 : 1
  return !!userInput.value.trim() && selectedModels.value.length === need && !isLoading.value
})

onMounted(async () => {
  if (!loginUserStore.loginUser.id) {
    loginUserStore.fetchLoginUser().catch(() => {})
  }
  await Promise.all([loadModels(), loadConversations()])
})

// 组件销毁时关闭 SSE 连接，防止连接泄漏
onBeforeUnmount(() => {
  closeSSE()
})

/* ==================== 模型与历史数据 ==================== */

/**
 * 首次打开页面默认选中的模型
 *
 * 必须是免费模型：账号没充值时付费模型一律返回 402，默认就选付费的话
 * 用户一进来直接发送必然失败。这里写死两个实测可用的免费模型，
 * 不跟着后端排序走（排序规则一改，默认值就会被悄悄换掉）。
 */
const DEFAULT_MODEL_IDS = ['nex-agi/nex-n2.5-mini:free', 'nvidia/nemotron-3-ultra-550b-a55b:free']

/** 挑默认模型：显式指定的免费模型 → 任意免费模型 → 策展推荐 → 全部兜底 */
const pickDefaultModels = () => {
  const available = modelList.value.map((model) => model.id)
  const pool = [
    ...DEFAULT_MODEL_IDS.filter((id) => available.includes(id)),
    ...modelList.value.filter(isFreeModel).map((model) => model.id),
    ...modelList.value.filter((model) => model.recommended === 1).map((model) => model.id),
    ...available,
  ]
  const unique = [...new Set(pool)]
  return [unique[0], unique[1]] as [string | undefined, string | undefined]
}

/** 加载模型列表（后端已按「国内优先 → 推荐优先」排序） */
const loadModels = async () => {
  modelLoading.value = true
  try {
    const res = await listModels()
    if (res.data.code === 0) {
      modelList.value = res.data.data || []
      if (!modelA.value) {
        const [first, second] = pickDefaultModels()
        modelA.value = first
        modelB.value = second
      }
    } else {
      message.error('加载模型列表失败：' + res.data.message)
    }
  } catch (error) {
    message.error('加载模型列表失败：' + (error as Error).message)
  } finally {
    modelLoading.value = false
  }
}

/** 加载侧栏历史会话 */
const loadConversations = async () => {
  historyLoading.value = true
  try {
    const res = await listConversationVoByPage({ current: 1, pageSize: HISTORY_PAGE_SIZE })
    if (res.data.code === 0) {
      conversations.value = res.data.data?.records || []
    }
  } catch {
    // 侧栏属于辅助信息，加载失败不打断主流程
  } finally {
    historyLoading.value = false
  }
}

/** 点击侧栏会话：拉取消息与评分并还原到主区域 */
const loadConversation = async (conversationId: string) => {
  if (isLoading.value) {
    message.warning('正在生成回答，请先停止再切换会话')
    return
  }
  if (conversationId === currentConversationId.value && messages.value.length > 0) return

  try {
    const [msgRes, ratingRes] = await Promise.all([
      listConversationMessages(conversationId),
      listRatings(conversationId),
    ])
    if (msgRes.data.code !== 0) {
      message.error('加载对话失败：' + msgRes.data.message)
      return
    }

    const conv = conversations.value.find((item) => item.id === conversationId)
    const usedModels = conv?.models || []
    if (usedModels.length === 1) {
      mode.value = 'single'
      modelA.value = usedModels[0]
    } else if (usedModels.length >= 2) {
      mode.value = 'compare'
      modelA.value = usedModels[0]
      modelB.value = usedModels[1]
    }

    const ratingMap = new Map<number, RatingVO>()
    if (ratingRes.data.code === 0) {
      for (const rating of ratingRes.data.data || []) {
        ratingMap.set(rating.messageIndex, rating)
      }
    }

    // 按 messageIndex 归组：user 消息是一条，同一轮的多个 assistant 消息聚成一组
    const rows = msgRes.data.data || []
    const built: ChatMessage[] = []
    const roundMap = new Map<number, ChatMessage>()
    for (const row of rows) {
      if (row.role === 'user') {
        built.push({
          type: 'user',
          content: row.content,
          conversationId,
          messageIndex: row.messageIndex,
        })
        continue
      }

      let round = roundMap.get(row.messageIndex)
      if (!round) {
        round = {
          type: 'assistant',
          conversationId,
          messageIndex: row.messageIndex,
          responses: [],
        }
        roundMap.set(row.messageIndex, round)
        built.push(round)
      }
      if (!round.responses) round.responses = []
      round.responses.push({
        modelName: row.modelName || '',
        fullContent: row.content,
        reasoning: row.reasoning,
        done: true,
        hasError: false,
        responseTimeMs: row.responseTimeMs,
        elapsedMs: row.responseTimeMs,
        inputTokens: row.inputTokens,
        outputTokens: row.outputTokens,
        cost: row.cost,
        hasReasoning: !!row.reasoning,
      })
    }

    // 回填评分状态，让评分按钮显示为已选中
    for (const item of built) {
      if (item.type !== 'assistant' || item.messageIndex === undefined) continue
      const rating = ratingMap.get(item.messageIndex)
      if (rating) {
        item.rating = { ratingType: rating.ratingType, winnerModel: rating.winnerModel }
      }
    }

    messages.value = built
    currentConversationId.value = conversationId
    // 历史记录的思考过程默认折叠，避免一屏都是灰色文本
    const collapsed = new Set<string>()
    built.forEach((item, msgIdx) => {
      ;(item.responses || []).forEach((resp, respIdx) => {
        if (resp.hasReasoning) collapsed.add(reasoningKey(msgIdx, respIdx))
      })
    })
    collapsedReasoning.value = collapsed
    scrollToBottom(true)
  } catch (error) {
    message.error('加载对话失败：' + (error as Error).message)
  }
}

/** 开启一个新对话（保留当前的模型与模式选择） */
const startNewConversation = () => {
  if (isLoading.value) return
  closeSSE()
  messages.value = []
  currentConversationId.value = null
  collapsedReasoning.value = new Set()
  scrollToBottom(true)
}

/* ==================== 展示辅助 ==================== */

/** 并排卡片列数：最多两列，单模型模式就是整行 */
const gridColumns = (msg: ChatMessage) =>
  `repeat(${Math.min(msg.responses?.length || 1, 2)}, minmax(0, 1fr))`

const totalTokens = (resp: ModelResponse) => (resp.inputTokens || 0) + (resp.outputTokens || 0)

/** 模型 ID → 展示名称 */
const getModelName = (modelName?: string) => {
  if (!modelName) return '未知模型'
  return modelList.value.find((model) => model.id === modelName)?.name || modelName
}

/** 模型 ID → 提供商名称 */
const getProviderLabel = (modelName?: string) => {
  if (!modelName) return '?'
  return modelName.split('/')[0] || modelName
}

/** 提供商首字母头像的配色，按名称做一次简单散列 */
const getProviderColor = (modelName?: string) => {
  const label = getProviderLabel(modelName)
  let hash = 0
  for (let i = 0; i < label.length; i++) {
    hash = (hash * 31 + label.charCodeAt(i)) % 360
  }
  return `hsl(${hash}, 62%, 46%)`
}

/**
 * 某一条 AI 回答当前是否处于「盲测未揭晓」状态
 *
 * 盲测模式下评分即揭晓：一旦用户提交了评分，这一轮的真实模型名就显示出来。
 */
const isBlind = (msg: ChatMessage) => blindMode.value && !msg.rating

/** 盲测代号：0 → A，1 → B，2 → C ... */
const getBlindCode = (index: number) => String.fromCharCode(65 + index)

/** 盲测展示名：模型 A、模型 B ... */
const getBlindLabel = (index: number) => `模型 ${getBlindCode(index)}`

/**
 * 是否展示思考过程
 *
 * 个别模型会在 reasoning 字段里返回只含换行/空格的伪内容（后端已清洗，
 * 这里再兜一层），否则会渲染出一个空的灰色折叠框。
 */
const hasReasoning = (resp: ModelResponse) => !!resp.hasReasoning && !!(resp.reasoning || '').trim()

/**
 * 本轮是否允许评分
 *
 * 必须所有模型都已结束、且至少有一个模型真的产出了内容：
 * 如果全都没内容（例如刚发出去就停止），库里不会有对应的 assistant 消息，
 * 此时提交评分就会变成指向不存在消息的孤儿数据。
 */
const canRate = (msg: ChatMessage) => {
  const responses = msg.responses
  if (!responses || responses.length < 2) return false
  if (!responses.every((resp) => resp.done)) return false
  return responses.some((resp) => (resp.fullContent || '').length > 0)
}

/** 判断某个模型是否被选为优胜者 */
const isModelSelected = (msg: ChatMessage, modelName?: string) =>
  msg.rating?.ratingType === 'model_better' && msg.rating?.winnerModel === modelName

const reasoningKey = (msgIndex: number, respIndex: number) => `${msgIndex}-${respIndex}`

const isReasoningCollapsed = (msgIndex: number, respIndex: number) =>
  collapsedReasoning.value.has(reasoningKey(msgIndex, respIndex))

const toggleReasoning = (msgIndex: number, respIndex: number) => {
  const next = new Set(collapsedReasoning.value)
  const key = reasoningKey(msgIndex, respIndex)
  if (next.has(key)) {
    next.delete(key)
  } else {
    next.add(key)
  }
  collapsedReasoning.value = next
}

/* ==================== 滚动 ==================== */

/** 只有用户本来就贴着底部时才自动跟随新内容，避免打断向上翻看的操作 */
const scrollToBottom = (force = false) => {
  if (!force && !atBottom.value) return
  nextTick(() => {
    const el = listRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

const onScroll = () => {
  const el = listRef.value
  if (!el) return
  atBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < AUTO_SCROLL_THRESHOLD
}

const focusInput = () => inputRef.value?.focus()

/* ==================== 发送与流式接收 ==================== */

const closeSSE = () => {
  if (sse.value) {
    sse.value.close()
    sse.value = null
  }
}

/** 发送消息并接收多模型流式响应 */
const sendMessage = async () => {
  if (!canSend.value) return

  const text = userInput.value.trim()
  const validModels = [...selectedModels.value]
  userInput.value = ''
  isLoading.value = true

  messages.value.push({ type: 'user', content: text })

  // 为每个模型预创建空的响应占位，SSE 数据到达后按 modelName 匹配填充
  const assistantMsgIndex = messages.value.length
  messages.value.push({
    type: 'assistant',
    conversationId: currentConversationId.value ?? undefined,
    responses: validModels.map((model) => ({
      modelName: model,
      fullContent: '',
      done: false,
      hasError: false,
    })),
  })
  scrollToBottom(true)

  try {
    sse.value = await createPostSSE(
      `${API_BASE_URL}/conversation/side-by-side/stream`,
      {
        // 带上 conversationId 即可实现多轮对话，为空时后端会新建对话
        conversationId: currentConversationId.value || undefined,
        models: validModels,
        prompt: text,
      },
      {
        onMessage: (chunk: StreamChunkVO) => {
          const msg = messages.value[assistantMsgIndex]
          if (!msg?.responses) return

          // 记录对话ID与消息序号，供下一轮对话和评分使用
          if (chunk.conversationId) {
            currentConversationId.value = chunk.conversationId
            msg.conversationId = chunk.conversationId
          }
          if (chunk.messageIndex !== undefined) {
            msg.messageIndex = chunk.messageIndex
          }

          const idx = msg.responses.findIndex((resp) => resp.modelName === chunk.modelName)
          if (idx >= 0) {
            // 后端用 exclude_none 序列化，未提供的字段不会出现在 JSON 中，
            // 因此这里的展开不会用 undefined 覆盖掉已有内容
            msg.responses[idx] = { ...msg.responses[idx], ...chunk } as ModelResponse
            // 强制触发 Vue 响应式更新
            messages.value = [...messages.value]
          }

          scrollToBottom()

          if (chunk.done && msg.responses.every((resp) => resp.done)) {
            isLoading.value = false
            loadConversations()
          }
        },
        onError: (err) => {
          isLoading.value = false
          markResponsesFailed(assistantMsgIndex, err.message)
          message.error('请求失败：' + err.message)
        },
        onComplete: () => {
          isLoading.value = false
          markResponsesFailed(assistantMsgIndex, '连接已中断')
        },
      },
    )
  } catch (error) {
    isLoading.value = false
    markResponsesFailed(assistantMsgIndex, (error as Error).message)
    message.error('请求失败：' + (error as Error).message)
  }
}

/** 把仍然停留在「生成中」的模型标记为失败，避免页面一直转圈 */
const markResponsesFailed = (msgIndex: number, reason: string) => {
  const msg = messages.value[msgIndex]
  if (!msg?.responses) return
  let changed = false
  msg.responses.forEach((resp) => {
    if (!resp.done) {
      resp.done = true
      resp.hasError = true
      resp.error = reason
      changed = true
    }
  })
  if (changed) {
    messages.value = [...messages.value]
  }
}

/**
 * 中途停止生成
 *
 * 关闭 SSE 连接后，服务端会在下一次推送前检测到客户端断开并取消仍未完成的模型调用，
 * 因此不会继续消耗 API 额度。
 * 后端同时会把各个模型「已经生成的内容」落库，所以历史记录里能看到这半截回答，
 * 本轮也可以正常评分。
 */
const stopGeneration = () => {
  closeSSE()
  isLoading.value = false

  const lastMsg = messages.value[messages.value.length - 1]
  if (lastMsg?.responses) {
    lastMsg.responses.forEach((resp) => {
      if (!resp.done) {
        resp.done = true
        resp.stopped = true
      }
    })
    messages.value = [...messages.value]
  }
  message.info('已停止生成，已生成的内容已保存')
  loadConversations()
}

/* ==================== 评分 / 复制 / 导出 ==================== */

/** 提交或修改评分 */
const handleRating = async (msgIndex: number, ratingType: string, winnerModel?: string) => {
  const msg = messages.value[msgIndex]
  if (!msg?.conversationId || msg.messageIndex === undefined) {
    message.warning('本轮对话尚未保存完成，请稍后再试')
    return
  }

  try {
    const res = await addRating({
      conversationId: msg.conversationId,
      messageIndex: msg.messageIndex,
      ratingType: ratingType as 'model_better' | 'tie' | 'both_bad',
      winnerModel,
    })
    if (res.data.code === 0) {
      msg.rating = { ratingType, winnerModel }
      messages.value = [...messages.value]
      message.success('评分已提交，感谢反馈')
    } else {
      message.error('评分失败：' + res.data.message)
    }
  } catch (error) {
    message.error('评分失败：' + (error as Error).message)
  }
}

/** 复制某个模型的完整回答 */
const copyResponse = async (resp: ModelResponse) => {
  try {
    await navigator.clipboard.writeText(resp.fullContent || '')
    message.success('已复制到剪贴板')
  } catch {
    message.error('复制失败，请手动选择内容')
  }
}

/** 打开完整回答弹窗 */
const openExpand = (resp: ModelResponse) => {
  expandTarget.value = {
    title: getModelName(resp.modelName),
    content: resp.fullContent || '',
    reasoning: hasReasoning(resp) ? resp.reasoning : undefined,
  }
  expandOpen.value = true
}

/** 把本轮的对比结果导出为 Markdown 文件 */
const exportComparison = (msgIndex: number) => {
  const msg = messages.value[msgIndex]
  if (!msg?.responses?.length) return

  // 用户提问在 AI 回答的前一条消息里
  const question = messages.value[msgIndex - 1]?.content || '(未记录)'

  const lines: string[] = []
  lines.push('# AI 模型对比结果\n')
  lines.push(`> 导出时间：${new Date().toLocaleString()}\n`)
  lines.push(`**问题**：${question}\n`)

  msg.responses.forEach((resp) => {
    lines.push(`## ${getModelName(resp.modelName)}\n`)
    lines.push(`- 模型 ID：\`${resp.modelName}\``)
    if (resp.hasError) {
      lines.push(`- 状态：调用失败（${resp.error || '未知错误'}）`)
    } else if (resp.stopped) {
      lines.push('- 状态：用户手动停止生成')
    } else {
      lines.push('- 状态：正常完成')
    }
    lines.push(
      `- 响应时间：${resp.responseTimeMs ? `${(resp.responseTimeMs / 1000).toFixed(2)} s` : '—'}`,
    )
    lines.push(
      `- Token 消耗：${totalTokens(resp)}（输入 ${resp.inputTokens || 0} / 输出 ${resp.outputTokens || 0}）`,
    )
    lines.push(`- 成本：$${(resp.cost ?? 0).toFixed(6)}\n`)

    if (resp.reasoning) {
      lines.push('<details>\n<summary>思考过程</summary>\n')
      lines.push(resp.reasoning)
      lines.push('\n</details>\n')
    }

    lines.push(resp.fullContent || '（无内容）')
    lines.push('\n---\n')
  })

  const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `ai-comparison-${new Date().toISOString().slice(0, 10)}.md`
  link.click()
  URL.revokeObjectURL(url)
  message.success('对比结果已导出')
}

/* ==================== 用户 ==================== */

const doLogout = async () => {
  const res = await userLogout()
  if (res.data.code === 0) {
    loginUserStore.setLoginUser({ userName: '未登录' })
    message.success('退出登录成功')
    router.push('/user/login')
  } else {
    message.error('退出登录失败，' + res.data.message)
  }
}
</script>

<style scoped>
/* ==================== 整体布局 ==================== */
.sb-root {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: #fff;
  color: #1f2328;
  font-size: 14px;
}

/* ==================== 左侧会话栏 ==================== */
.sb-sidebar {
  flex: 0 0 232px;
  width: 232px;
  display: flex;
  flex-direction: column;
  padding: 12px 12px 10px;
  box-sizing: border-box;
  border-right: 1px solid #ececec;
  background: #fff;
}

.sb-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px 16px;
  text-decoration: none;
}

.sb-brand-logo {
  height: 26px;
}

.sb-brand-title {
  font-size: 15px;
  font-weight: 700;
  color: #1f2328;
  white-space: nowrap;
}

.sb-new-chat {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 40px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #fff;
  color: #1f2328;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.sb-new-chat:hover:not(:disabled) {
  background: #f7f8fa;
  border-color: #d7dbe0;
}

.sb-new-chat:disabled {
  color: #b9c0ca;
  cursor: not-allowed;
}

.sb-history {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  margin-top: 18px;
}

.sb-history-label {
  padding: 0 8px 6px;
  font-size: 12px;
  color: #9aa1ac;
}

.sb-conv {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 8px;
  border-radius: 8px;
  color: #4b5563;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s;
}

.sb-conv:hover {
  background: #f5f6f8;
}

.sb-conv.active {
  background: #eef4ff;
  color: #1677ff;
}

.sb-conv-icons {
  display: inline-flex;
  flex: 0 0 auto;
}

.sb-conv-icon {
  width: 16px;
  height: 16px;
  margin-right: -5px;
  border-radius: 50%;
  border: 1px solid #fff;
  color: #fff;
  font-size: 9px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.sb-conv-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sb-history-tip {
  padding: 6px 8px;
  font-size: 12px;
  color: #b0b6bf;
}

.sb-user {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding: 10px 8px 6px;
  border-top: 1px solid #f0f1f3;
  border-radius: 8px;
  cursor: pointer;
}

.sb-user:hover {
  background: #f5f6f8;
}

.sb-user-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  color: #1f2328;
}

/* ==================== 主区域 ==================== */
.sb-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.sb-topbar {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 10px;
  height: 64px;
  padding: 0 20px;
  border-bottom: 1px solid #eef0f2;
}

.sb-topbar-spacer {
  flex: 1;
}

.mode-wrap {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.mode-icon {
  position: absolute;
  left: 11px;
  z-index: 2;
  font-size: 14px;
  color: #6b7280;
  pointer-events: none;
}

.mode-select {
  width: 150px;
}

.mode-select :deep(.ant-select-selector) {
  padding-left: 30px !important;
}

.sb-select {
  width: 262px;
}

.sb-select.wide {
  width: 340px;
}

.sb-select :deep(.ant-select-selector),
.mode-select :deep(.ant-select-selector) {
  height: 36px !important;
  border-radius: 8px !important;
  border-color: #e3e6ea !important;
}

.sb-select :deep(.ant-select-selection-item),
.mode-select :deep(.ant-select-selection-item) {
  line-height: 34px !important;
}

/* ---------- 模型下拉的分组标题（厂商 / 免费） ---------- */

/* 弹层挂在 body 上，scoped 选择器够不到，所以用 :global + 弹层类名限定范围 */
:global(.sb-select-popup .ant-select-item-group) {
  position: sticky;
  top: 0;
  z-index: 1;
  padding: 7px 12px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: #8a93a0;
  background: #f6f7f9;
  border-top: 1px solid #eceff3;
}

:global(.sb-select-popup .ant-select-item-group:first-child) {
  border-top: none;
}

/* 二级菜单：展示名缩进一档，视觉上从属于上面的厂商标题 */
:global(.sb-select-popup .ant-select-item-option) {
  padding-left: 22px;
}

:global(.sb-select-popup .ant-select-item-option-selected) {
  font-weight: 600;
}

.sb-vs {
  padding: 0 2px;
  font-size: 13px;
  color: #9aa1ac;
}

.sb-blind {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #6b7280;
  white-space: nowrap;
  cursor: pointer;
}

/* ==================== 消息区 ==================== */
.sb-messages-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
}

.sb-messages {
  flex: 1;
  overflow-y: auto;
  padding: 28px 40px 16px;
}

.sb-empty {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  text-align: center;
}

.sb-empty-title {
  font-size: 16px;
  font-weight: 600;
  color: #4b5563;
}

.sb-empty-desc {
  max-width: 460px;
  font-size: 13px;
  line-height: 1.8;
  color: #9aa1ac;
}

.sb-row {
  margin-bottom: 26px;
}

.sb-user-line {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 22px;
}

.sb-user-bubble {
  max-width: 62%;
  padding: 10px 16px;
  border-radius: 12px;
  background: #f2f3f5;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.sb-grid {
  display: grid;
  gap: 22px;
  align-items: start;
}

.sb-card {
  min-width: 0;
  padding: 16px 20px 18px;
  border: 1px solid #ececec;
  border-radius: 12px;
  background: #fff;
}

.sb-card-head {
  display: flex;
  align-items: center;
  gap: 7px;
  padding-bottom: 12px;
  margin-bottom: 14px;
  border-bottom: 1px solid #f2f3f5;
  font-size: 12px;
  color: #9aa1ac;
}

.sb-head-spacer {
  flex: 1;
}

.sb-avatar {
  flex: 0 0 auto;
  width: 18px;
  height: 18px;
  border-radius: 4px;
  color: #fff;
  font-size: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.sb-model-name {
  max-width: 190px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 600;
  color: #1f2328;
}

.sb-metric {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-left: 8px;
  white-space: nowrap;
}

.sb-icon-btn {
  width: 24px;
  height: 24px;
  margin-left: 4px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #9aa1ac;
  font-size: 13px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.sb-icon-btn:hover:not(:disabled) {
  background: #f4f5f7;
  color: #1677ff;
}

.sb-icon-btn:disabled {
  color: #d8dce1;
  cursor: not-allowed;
}

.sb-icon-btn.lg {
  width: 30px;
  height: 30px;
  font-size: 15px;
  margin-left: 0;
}

.sb-alert {
  margin-bottom: 12px;
}

.sb-reasoning {
  padding: 10px 12px;
  margin-bottom: 14px;
  border-radius: 8px;
  background: #f7f8fa;
}

.sb-reasoning-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #6b7280;
  cursor: pointer;
  user-select: none;
}

.sb-caret {
  font-size: 10px;
  transition: transform 0.2s;
}

.sb-caret.collapsed {
  transform: rotate(-90deg);
}

.sb-reasoning-body {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.75;
  color: #6b7280;
}

.sb-dots {
  display: inline-flex;
  gap: 4px;
  padding-top: 6px;
}

.sb-dots span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #bfbfbf;
  animation: sb-dot-blink 1.2s infinite ease-in-out;
}

.sb-dots span:nth-child(2) {
  animation-delay: 0.2s;
}

.sb-dots span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes sb-dot-blink {
  0%,
  80%,
  100% {
    opacity: 0.3;
  }
  40% {
    opacity: 1;
  }
}

.sb-stopped-tip {
  margin-top: 10px;
  font-size: 12px;
  color: #fa8c16;
}

/* ==================== 评分区 ==================== */
.sb-footer {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 20px;
}

.sb-rating {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border: 1px solid #ececec;
  border-radius: 12px;
  background: #fff;
}

.sb-rating-btn {
  padding: 8px 20px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #fff;
  color: #1f2328;
  font-size: 13px;
  white-space: nowrap;
  cursor: pointer;
  transition: all 0.2s;
}

.sb-rating-btn:hover {
  border-color: #1677ff;
  color: #1677ff;
}

.sb-rating-btn.selected {
  border-color: #1677ff;
  background: #e6f4ff;
  color: #1677ff;
}

.sb-export {
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 30px;
  height: 30px;
  padding: 0;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #9aa1ac;
  font-size: 14px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.sb-export:hover {
  background: #f4f5f7;
  color: #1677ff;
}

.sb-blind-hint {
  font-size: 12px;
  color: #fa8c16;
}

.sb-scroll-btn {
  position: absolute;
  left: 50%;
  bottom: 10px;
  transform: translateX(-50%);
  width: 30px;
  height: 30px;
  padding: 0;
  border: 1px solid #ececec;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  color: #6b7280;
  font-size: 12px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

/* ==================== 输入区 ==================== */
.sb-composer-wrap {
  flex: 0 0 auto;
  padding: 8px 40px 22px;
}

.sb-composer {
  padding: 12px 14px 10px;
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  background: #fff;
  transition:
    border-color 0.2s,
    box-shadow 0.2s;
}

.sb-composer:focus-within {
  border-color: #1677ff;
  box-shadow: 0 0 0 3px rgba(22, 119, 255, 0.08);
}

.sb-textarea {
  display: block;
  width: 100%;
  min-height: 56px;
  max-height: 160px;
  border: none;
  outline: none;
  resize: none;
  background: transparent;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.7;
  color: #1f2328;
}

.sb-textarea::placeholder {
  color: #b0b6bf;
}

.sb-textarea:disabled {
  color: #b0b6bf;
}

.sb-composer-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 6px;
}

.sb-send {
  width: 34px;
  height: 34px;
  padding: 0;
  border: none;
  border-radius: 10px;
  background: #1677ff;
  color: #fff;
  font-size: 15px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.sb-send:hover:not(:disabled) {
  background: #4096ff;
}

.sb-send:disabled {
  background: #eef1f5;
  color: #b9c0ca;
  cursor: not-allowed;
}

.sb-send.stop {
  background: #ff4d4f;
}

.sb-send.stop:hover {
  background: #ff7875;
}

/* ==================== 完整回答弹窗 ==================== */
.sb-expand-body {
  max-height: 62vh;
  overflow-y: auto;
}
</style>
