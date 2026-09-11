<template>
  <div class="cm-root">
    <!-- ==================== 左侧：会话历史 ==================== -->
    <aside class="cm-sidebar">
      <RouterLink to="/" class="cm-brand" title="返回首页">
        <img class="cm-brand-logo" src="@/assets/logo.svg" alt="Logo" />
        <span class="cm-brand-title">大模型评测平台</span>
      </RouterLink>

      <button class="cm-new-chat" :disabled="isStreaming" @click="startNewConversation">
        <EditOutlined />
        <span>新对话</span>
      </button>

      <div class="cm-history">
        <div class="cm-history-label">更早</div>
        <div
          v-for="conv in conversations"
          :key="conv.id"
          class="cm-conv"
          :class="{ active: conv.id === currentConversationId }"
          :title="conv.title || '未命名对话'"
          @click="loadConversation(conv.id)"
        >
          <span class="cm-conv-icon"><CodeOutlined /></span>
          <span class="cm-conv-title">{{ conv.title || '未命名对话' }}</span>
        </div>
        <div v-if="historyLoading" class="cm-history-tip">加载中…</div>
        <div v-else-if="conversations.length === 0" class="cm-history-tip">还没有代码会话</div>
      </div>

      <a-dropdown placement="topLeft" :trigger="['click']">
        <div class="cm-user">
          <a-avatar :size="26" :src="loginUserStore.loginUser.userAvatar" />
          <span class="cm-user-name">{{ loginUserStore.loginUser.userName ?? '未登录' }}</span>
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

    <!-- ==================== 中间：对话交互区 ==================== -->
    <section class="cm-chat">
      <header class="cm-topbar">
        <div class="mode-wrap">
          <SwapOutlined class="mode-icon" />
          <a-select
            v-model:value="mode"
            :options="MODE_OPTIONS"
            :disabled="isStreaming"
            class="mode-select"
            @change="onModeChange"
          />
        </div>

        <!-- 模型对比：选多个模型 -->
        <template v-if="currentMode === 'model-compare'">
          <a-select
            v-model:value="selectedModels"
            mode="multiple"
            :options="modelOptions"
            :loading="modelLoading"
            :disabled="isStreaming"
            :filter-option="filterModelOption"
            popup-class-name="cm-select-popup"
            :virtual="false"
            show-search
            :max-tag-count="2"
            class="cm-select wide"
            placeholder="选择 1-8 个模型"
          />
        </template>
        <!-- 提示词实验：只选一个模型 -->
        <template v-else>
          <a-select
            v-model:value="labModel"
            :options="modelOptions"
            :loading="modelLoading"
            :disabled="isStreaming"
            :filter-option="filterModelOption"
            popup-class-name="cm-select-popup"
            :virtual="false"
            show-search
            class="cm-select wide"
            placeholder="选择一个模型"
          />
        </template>

        <span class="cm-topbar-spacer" />
        <span class="cm-topbar-hint">AI 写代码 · 右侧实时预览运行效果</span>
      </header>

      <!-- 对话记录 -->
      <div ref="listRef" class="cm-messages" @scroll="onScroll">
        <div v-if="messages.length === 0" class="cm-empty">
          <CodeOutlined class="cm-empty-icon" />
          <div class="cm-empty-title">描述你想要的网页，AI 直接写出来</div>
          <div class="cm-empty-desc">
            比如「一个 iOS 风格的计算器」「一家日料店的菜单页」，
            多个模型同时生成，右侧可以逐个预览、对比谁的实现更好
          </div>
        </div>

        <div v-for="(msg, idx) in messages" :key="idx" class="cm-row">
          <!-- 用户提问 / 提示词变体 -->
          <div v-if="msg.type === 'user'" class="cm-user-line">
            <div v-if="msg.variants" class="cm-variant-list">
              <div v-for="(variant, vi) in msg.variants" :key="vi" class="cm-user-bubble">
                <span class="cm-user-tag">变体 {{ vi + 1 }}</span>
                <span class="cm-user-text">{{ variant }}</span>
              </div>
            </div>
            <div v-else class="cm-user-bubble">{{ msg.content }}</div>
          </div>

          <!-- AI 生成结果 -->
          <template v-else>
            <div v-if="msg.responses" class="cm-response-list">
              <div
                v-for="(resp, respIndex) in msg.responses"
                :key="`${resp.modelName}-${respIndex}`"
                class="cm-card"
              >
                <div class="cm-card-head">
                  <span
                    class="cm-avatar"
                    :style="{ background: getProviderColor(resp.modelName) }"
                  >
                    {{ getProviderLabel(resp.modelName).charAt(0).toUpperCase() }}
                  </span>
                  <span class="cm-model-name">
                    {{ getModelName(resp.modelName) }}
                    <span v-if="msg.runCount && msg.runCount > 1" class="cm-run-tag">
                      第 {{ (resp.runIndex ?? 0) + 1 }} 次
                    </span>
                  </span>
                  <span class="cm-head-spacer" />
                  <span v-if="resp.responseTimeMs" class="cm-metric">
                    <ClockCircleOutlined />
                    {{ (resp.responseTimeMs / 1000).toFixed(2) }}s
                  </span>
                  <span v-if="totalTokens(resp)" class="cm-metric">
                    <BarChartOutlined />
                    {{ totalTokens(resp) }}t
                  </span>
                  <span v-if="resp.cost != null" class="cm-metric">
                    <DollarOutlined />
                    {{ resp.cost.toFixed(4) }}
                  </span>
                  <button
                    class="cm-icon-btn"
                    title="复制回答"
                    :disabled="!resp.fullContent"
                    @click="copyResponse(resp)"
                  >
                    <CopyOutlined />
                  </button>
                </div>

                <a-alert
                  v-if="resp.hasError"
                  type="error"
                  :message="resp.error || '该模型调用失败'"
                  show-icon
                  class="cm-alert"
                />

                <template v-else>
                  <!-- 思考过程（推理模型） -->
                  <div v-if="hasReasoning(resp)" class="cm-reasoning">
                    <div class="cm-reasoning-head" @click="toggleReasoning(idx, respIndex)">
                      <DownOutlined
                        class="cm-caret"
                        :class="{ collapsed: isReasoningCollapsed(idx, respIndex) }"
                      />
                      <span>
                        {{ resp.thinkingTime ? `思考了 ${resp.thinkingTime} 秒` : '思考过程' }}
                      </span>
                    </div>
                    <div
                      v-show="!isReasoningCollapsed(idx, respIndex)"
                      class="cm-reasoning-body"
                    >
                      <MarkdownRenderer :content="resp.reasoning || ''" />
                    </div>
                  </div>

                  <!-- 正文：代码块会渲染成带预览的卡片 -->
                  <MarkdownRenderer
                    v-if="resp.fullContent"
                    :content="resp.fullContent"
                    :editable-code="true"
                  />

                  <!-- 正在生成：给一个「AI 正在写文件」的提示 -->
                  <CodeGeneratingHint v-else-if="!resp.done" :language="''" />
                </template>

                <div v-if="resp.stopped" class="cm-stopped-tip">
                  已停止生成 · 以上为已生成的内容，已保存到历史记录
                </div>
              </div>
            </div>
          </template>
        </div>

        <button v-if="!atBottom" class="cm-scroll-btn" title="回到最新" @click="scrollToBottom(true)">
          <DownOutlined />
        </button>
      </div>

      <!-- 底部输入区 -->
      <div class="cm-input-wrap">
        <!-- 页内工作模式切换：模型对比（多模型 + 一个提示词）/ 提示词实验（单模型 + 多变体） -->
        <div class="cm-workmode-row">
          <div class="cm-workmode-switch">
            <button
              class="cm-workmode-btn"
              :class="{ active: currentMode === 'model-compare' }"
              :disabled="isStreaming"
              @click="switchWorkMode('model-compare')"
            >
              <AppstoreOutlined />
              模型对比
            </button>
            <button
              class="cm-workmode-btn"
              :class="{ active: currentMode === 'prompt-experiment' }"
              :disabled="isStreaming"
              @click="switchWorkMode('prompt-experiment')"
            >
              <ExperimentOutlined />
              提示词实验
            </button>
          </div>
          <span class="cm-workmode-hint">
            {{
              currentMode === 'model-compare'
                ? '同一个需求，多个模型同时写代码'
                : '同一个模型，多种问法分别写代码'
            }}
          </span>
        </div>

        <!-- 提示词实验：多变体输入 -->
        <div v-if="currentMode === 'prompt-experiment'" class="cm-variants-panel">
          <div class="cm-panel-header">
            <span class="cm-panel-title">提示词变体 ({{ variants.length }}/{{ MAX_VARIANTS }})</span>
            <div class="cm-header-actions">
              <a-button
                size="small"
                type="dashed"
                :disabled="variants.length >= MAX_VARIANTS || isStreaming"
                @click="addVariant"
              >
                + 添加变体
              </a-button>
              <a-button
                v-if="variants.length > MIN_VARIANTS"
                size="small"
                type="dashed"
                danger
                :disabled="isStreaming"
                @click="removeVariant(variants.length - 1)"
              >
                - 移除
              </a-button>
            </div>
          </div>
          <div class="cm-variants-horizontal">
            <div v-for="(variant, vi) in variants" :key="vi" class="cm-variant-card">
              <div class="cm-variant-label">变体 {{ vi + 1 }}</div>
              <textarea
                v-model="variants[vi]"
                class="cm-variant-input"
                rows="3"
                placeholder="例如：用 Tailwind 风格写一个待办清单页面..."
                :disabled="isStreaming"
              ></textarea>
            </div>
          </div>
        </div>

        <!-- 模型对比：单输入框 -->
        <div v-else class="cm-prompt-panel">
          <textarea
            v-model="prompt"
            class="cm-prompt-input"
            rows="3"
            placeholder="描述你想要的网页，例如：帮我写一个计算器网页，要有 iOS 风格的按钮和深色模式..."
            :disabled="isStreaming"
            @keydown.enter.exact.prevent="handleSubmit"
          ></textarea>
        </div>

        <div class="cm-submit-row">
          <span class="cm-submit-hint">
            生成的是完整单文件 HTML，右侧可实时预览、复制与下载
          </span>
          <button v-if="isStreaming" class="cm-submit-btn stop" @click="stopGeneration">
            停止生成
          </button>
          <button v-else class="cm-submit-btn" :disabled="!canSubmit" @click="handleSubmit">
            开始生成
          </button>
        </div>
      </div>
    </section>

    <!-- ==================== 右侧：实时预览区（可收起） ==================== -->
    <!-- is-collapsed 由外层做宽度动画，v-show 只负责显示/隐藏，两者配合才有折叠动效 -->
    <section class="cm-preview" :class="{ 'is-collapsed': previewCollapsed }">
      <div v-show="!previewCollapsed" class="cm-preview-inner">
        <!-- 预览目标切换：模型 tab / 变体 tab -->
        <div class="cm-preview-tabs">
          <div class="cm-tabs-left">
            <template v-if="currentMode === 'model-compare'">
              <button
                v-for="(model, index) in selectedModels"
                :key="`tab-${model}-${index}`"
                class="cm-tab-item"
                :class="{ active: activePreviewTab === index }"
                :title="getModelName(model)"
                @click="activePreviewTab = index"
              >
                <span class="cm-tab-icon" :style="{ background: getProviderColor(model) }">
                  {{ getProviderLabel(model).charAt(0).toUpperCase() }}
                </span>
                <span class="cm-tab-name">{{ getModelName(model) }}</span>
              </button>
            </template>
            <template v-else>
              <button
                v-for="(_, index) in variants"
                :key="`tab-variant-${index}`"
                class="cm-tab-item"
                :class="{ active: activePreviewTab === index }"
                @click="activePreviewTab = index"
              >
                <span class="cm-tab-name">变体 {{ index + 1 }}</span>
              </button>
            </template>
            <div v-if="previewTabsEmpty" class="cm-tabs-empty">还没有可预览的内容</div>
          </div>

          <div class="cm-tabs-actions">
            <a-button
              v-if="currentPreviewBlocks.length"
              type="primary"
              size="small"
              class="cm-download-btn"
              @click="downloadHtml"
            >
              <template #icon><DownloadOutlined /></template>
              下载 HTML
            </a-button>
            <a-tooltip title="收起预览区，把空间让给对话" placement="bottomRight">
              <button
                class="cm-icon-btn cm-collapse-btn"
                aria-label="收起预览区"
                @click="onPreviewCollapsedChange(true)"
              >
                <RightOutlined />
              </button>
            </a-tooltip>
          </div>
        </div>

        <div class="cm-preview-content">
          <!-- 拿不到代码块但还在生成：显示生成提示 -->
          <div v-if="!currentPreviewBlocks.length && isStreaming" class="cm-preview-generating">
            <CodeGeneratingHint language="html" />
          </div>

          <!-- 有代码块：交给 CodePreview（含 Monaco 代码视图、全屏、设备模拟） -->
          <div v-else-if="currentPreviewBlocks.length" class="cm-preview-wrapper">
            <CodePreview
              :code-blocks="currentPreviewBlocks"
              is-code-mode
              editable
              fill-height
              class="cm-preview-card"
            />
          </div>

          <!-- 空状态 -->
          <div v-else class="cm-preview-empty">
            <CodeOutlined class="cm-preview-empty-icon" />
            <p class="cm-preview-empty-title">生成 HTML 代码后，预览将显示在这里</p>
            <p class="cm-preview-empty-desc">请在左侧输入框描述你想要的网页</p>
          </div>
        </div>
      </div>

      <!-- 收起状态下的竖排展开条：贴在右边缘，不占用对话区空间 -->
      <button
        v-show="previewCollapsed"
        class="cm-preview-expand-rail"
        title="展开预览区"
        @click="onPreviewCollapsedChange(false)"
      >
        <LeftOutlined class="cm-rail-caret" />
        <span class="cm-rail-text">预览</span>
        <span
          v-if="currentPreviewBlocks.length"
          class="cm-rail-dot"
          title="已有可预览的内容"
        ></span>
      </button>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  AppstoreOutlined,
  BarChartOutlined,
  ClockCircleOutlined,
  CodeOutlined,
  CopyOutlined,
  DollarOutlined,
  DownOutlined,
  DownloadOutlined,
  EditOutlined,
  ExperimentOutlined,
  HomeOutlined,
  LeftOutlined,
  LogoutOutlined,
  RightOutlined,
  SwapOutlined,
} from '@ant-design/icons-vue'
import { API_BASE_URL } from '@/config/env'
import { userLogout } from '@/api/user'
import { useLoginUserStore } from '@/stores/loginUser'
import {
  listConversationMessages,
  listConversationVoByPage,
  type CodeBlockVO,
  type ConversationMessageVO,
  type ConversationVO,
  type StreamChunkVO,
} from '@/api/conversation'
import { listModels, type ModelVO } from '@/api/model'
import { createPostSSE, type SSEHandle } from '@/utils/sseClient'
import { SCRIPT_CLOSE_TAG, STYLE_CLOSE_TAG } from '@/utils/monacoEditor'
import { MODE_CODE, MODE_OPTIONS, resolveModeNavigation } from '@/constants/mode'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import CodePreview from '@/components/CodePreview.vue'
import CodeGeneratingHint from '@/components/CodeGeneratingHint.vue'

/** 页面内的两种工作模式 */
type CodeMode = 'model-compare' | 'prompt-experiment'

/** 变体数量约束，与后端 constants 保持一致 */
const MIN_VARIANTS = 2
const MAX_VARIANTS = 5

/** 本页承载的大模式（用于模式下拉的跳转判断） */
const CURRENT_PAGE_MODE = MODE_CODE

/** 距离底部多少像素内算「贴着底部」，此时新内容自动跟随滚动 */
const AUTO_SCROLL_THRESHOLD = 80

/** 侧栏一次拉取的历史会话条数 */
const HISTORY_PAGE_SIZE = 30

/** 首次打开页面默认选中的模型（免费模型：账号没充值时付费模型一律 402） */
const DEFAULT_MODEL_IDS = ['nex-agi/nex-n2.5-mini:free', 'nvidia/nemotron-3-ultra-550b-a55b:free']

/** 单个模型的生成结果 */
interface ModelResponse {
  modelName: string
  /** 变体模式下的变体序号 */
  variantIndex?: number
  /** 多次生成时的序号（本页只在变体模式下用 0） */
  runIndex?: number
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
  stopped?: boolean
  /** 本轮从回答里解析出的代码块（done 事件带回） */
  codeBlocks?: CodeBlockVO[]
}

/** 会话中的一条消息 */
interface ChatMessage {
  type: 'user' | 'assistant'
  content?: string
  /** 提示词实验模式：本轮提交的多个变体 */
  variants?: string[]
  conversationId?: string
  messageIndex?: number
  responses?: ModelResponse[]
  runCount?: number
}

const router = useRouter()
const route = useRoute()
const loginUserStore = useLoginUserStore()

// ---------- 模型 ----------
const modelList = ref<ModelVO[]>([])
const modelLoading = ref(false)
const mode = ref<string>(MODE_CODE)
const currentMode = ref<CodeMode>('model-compare')
const selectedModels = ref<string[]>([])
const labModel = ref<string>()

// ---------- 会话状态 ----------
const messages = ref<ChatMessage[]>([])
const prompt = ref('')
const variants = ref<string[]>(['', ''])
const isStreaming = ref(false)
const currentConversationId = ref<string | null>(null)
const conversations = ref<ConversationVO[]>([])
const historyLoading = ref(false)

// ---------- 视图状态 ----------
const listRef = ref<HTMLElement>()
const atBottom = ref(true)
const collapsedReasoning = ref<Set<string>>(new Set())
const activePreviewTab = ref(0)
const sseHandles = ref<(SSEHandle | null)[]>([])

/** 右侧预览区收起状态的 localStorage key（记住用户的选择，刷新后保持） */
const PREVIEW_COLLAPSED_KEY = 'codeMode.previewCollapsed'

/**
 * 右侧预览区是否收起
 *
 * 初始值从 localStorage 恢复：用户点过一次「收起」就说明他更想专心看对话，
 * 刷新页面又弹回来会很烦。
 */
const previewCollapsed = ref(false)
try {
  previewCollapsed.value = localStorage.getItem(PREVIEW_COLLAPSED_KEY) === '1'
} catch {
  // 隐私模式等场景下 localStorage 可能不可用，忽略即可（退化为不记忆）
}

const onPreviewCollapsedChange = (collapsed: boolean) => {
  previewCollapsed.value = collapsed
  try {
    localStorage.setItem(PREVIEW_COLLAPSED_KEY, collapsed ? '1' : '0')
  } catch {
    // 存不进去不影响功能
  }
}

/* ==================== 模型下拉 ==================== */

interface ModelOption {
  value: string
  label: string
  name?: string
}

interface ModelOptionGroup {
  label: string
  options: ModelOption[]
}

const FREE_GROUP_LABEL = '免费'

const isFreeModel = (model: ModelVO) => model.id.endsWith(':free')

/** 展示名去掉「厂商: 」前缀 —— 分组标题已经写了厂商 */
const shortModelName = (model: ModelVO) => {
  const name = model.name || model.id
  const sep = name.indexOf(': ')
  return sep > 0 ? name.slice(sep + 2) : name
}

const vendorLabel = (model: ModelVO) => {
  const name = model.name || ''
  const sep = name.indexOf(': ')
  if (sep > 0) return name.slice(0, sep)
  return model.provider || '其他'
}

/** 模型下拉（按厂商分组，免费模型单独置顶 —— 账号没充值时付费模型会 402） */
const modelOptions = computed(() => {
  const sorted = [...modelList.value].sort((a, b) => (b.created ?? 0) - (a.created ?? 0))
  const free: ModelOption[] = []
  const vendors = new Map<string, ModelOption[]>()
  for (const model of sorted) {
    const option: ModelOption = { value: model.id, label: shortModelName(model), name: model.name }
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

const filterModelOption = (input: string, option: ModelOption) => {
  const keyword = input.trim().toLowerCase()
  if (!keyword) return true
  return (
    String(option.value).toLowerCase().includes(keyword) ||
    String(option.name || '').toLowerCase().includes(keyword) ||
    String(option.label || '').toLowerCase().includes(keyword)
  )
}

/** 模型显示名（去掉厂商前缀，卡片头上已用色块标了厂商） */
const getModelName = (modelId?: string) => {
  if (!modelId) return '未知模型'
  const model = modelList.value.find((m) => m.id === modelId)
  return model ? shortModelName(model) : modelId
}

/** 厂商名：优先取展示名前缀，取不到再退回 provider 字段 */
const getProviderLabel = (modelId?: string) => {
  if (!modelId) return '?'
  const model = modelList.value.find((m) => m.id === modelId)
  if (!model) return modelId.split('/')[0] || '?'
  return vendorLabel(model)
}

/** 厂商色块颜色：按厂商名做稳定哈希，保证同一厂商每次都是同一个色 */
const PROVIDER_COLORS = [
  '#1677ff',
  '#52c41a',
  '#fa8c16',
  '#eb2f96',
  '#722ed1',
  '#13c2c2',
  '#f5222d',
  '#a0d911',
]

const getProviderColor = (modelId?: string) => {
  const label = getProviderLabel(modelId)
  let hash = 0
  for (let i = 0; i < label.length; i++) {
    hash = (hash * 31 + label.charCodeAt(i)) % 100000
  }
  return PROVIDER_COLORS[hash % PROVIDER_COLORS.length]
}

const pickDefaultModel = () => {
  const available = modelList.value.map((model) => model.id)
  const pool = [
    ...DEFAULT_MODEL_IDS.filter((id) => available.includes(id)),
    ...modelList.value.filter(isFreeModel).map((model) => model.id),
    ...modelList.value.filter((model) => model.recommended === 1).map((model) => model.id),
    ...available,
  ]
  return [...new Set(pool)][0]
}

/* ==================== 右侧预览 ==================== */

/** 当前 tab 对应的模型回复 */
const currentPreviewResponse = computed<ModelResponse | undefined>(() => {
  // 从最后一条 assistant 消息里找，保证预览永远是「最新一轮」的结果
  for (let i = messages.value.length - 1; i >= 0; i--) {
    const msg = messages.value[i]
    if (!msg || msg.type !== 'assistant' || !msg.responses) continue

    if (currentMode.value === 'model-compare') {
      const modelId = selectedModels.value[activePreviewTab.value]
      if (!modelId) return undefined
      return msg.responses.find((r) => r.modelName === modelId)
    }

    return msg.responses.find((r) => r.variantIndex === activePreviewTab.value)
  }
  return undefined
})

/**
 * 当前预览要渲染的代码块
 *
 * 优先用 done 事件带回的 codeBlocks；没有就现场从 Markdown 里解析一遍
 * （覆盖「正在流式生成、还没收到 done」以及历史数据缺字段的情况）。
 *
 * 多代码块全部返回：CodePreview 会自动把 CSS 注入 head、JS 注入 body 后合并预览
 * （教程第六章「多文件项目预览」）。
 */
const currentPreviewBlocks = computed<CodeBlockVO[]>(() => {
  const response = currentPreviewResponse.value
  if (!response) return []

  if (response.codeBlocks && response.codeBlocks.length > 0) return response.codeBlocks
  return parseCodeBlocks(response.fullContent || '')
})

/** Markdown → 代码块（与后端 code_extractor 的逻辑保持一致） */
const parseCodeBlocks = (content: string): CodeBlockVO[] => {
  if (!content) return []
  const result: CodeBlockVO[] = []
  const pattern = /```([^\n`]*)\n([\s\S]*?)```/g
  let match: RegExpExecArray | null
  while ((match = pattern.exec(content)) !== null) {
    const language = (match[1] || 'text').trim().toLowerCase() || 'text'
    const code = match[2] ?? ''
    const block: CodeBlockVO = { language, code }
    if (language === 'html') block.sanitizedHtml = code
    result.push(block)
  }
  return result
}

/** 预览 tab 区是否为空（一个选中项都没有） */
const previewTabsEmpty = computed(() =>
  currentMode.value === 'model-compare' ? selectedModels.value.length === 0 : variants.value.length === 0,
)

/** 下载当前预览的 HTML（多代码块先合并成单文件） */
const downloadHtml = () => {
  const blocks = currentPreviewBlocks.value
  const first = blocks[0]
  if (!first) return

  const htmlBlock = blocks.find((b) => b.language.toLowerCase() === 'html')
  const merged = htmlBlock ? mergeBlocks(blocks) : first.code
  const blob = new Blob([merged], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'index.html'
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
  message.success('已下载 index.html')
}

/** 把 HTML/CSS/JS 代码块合成一份完整文档（与 CodePreview 内的实现保持一致） */
const mergeBlocks = (blocks: CodeBlockVO[]): string => {
  const html = blocks.find((b) => b.language.toLowerCase() === 'html')
  if (!html) return blocks[0]?.code ?? ''

  const css = blocks.filter((b) => b.language.toLowerCase() === 'css')
  const js = blocks.filter((b) => ['javascript', 'js'].includes(b.language.toLowerCase()))
  let merged = html.code

  if (css.length) {
    const styleTag = `<style>\n${css.map((b) => b.code).join('\n')}\n${STYLE_CLOSE_TAG}`
    merged = merged.includes('</head>')
      ? merged.replace('</head>', `${styleTag}\n</head>`)
      : `${styleTag}\n${merged}`
  }
  if (js.length) {
    const scriptTag = `<script>\n${js.map((b) => b.code).join('\n')}\n${SCRIPT_CLOSE_TAG}`
    merged = merged.includes('</body>')
      ? merged.replace('</body>', `${scriptTag}\n</body>`)
      : `${merged}\n${scriptTag}`
  }
  return merged
}

/* ==================== 生命周期 ==================== */

onMounted(async () => {
  if (!loginUserStore.loginUser.id) {
    loginUserStore.fetchLoginUser().catch(() => {})
  }
  await Promise.all([loadModels(), loadConversations()])
  const queryId = route.query.conversationId as string | undefined
  if (queryId) {
    await loadConversation(queryId)
  }
})

onBeforeUnmount(() => {
  closeSSE()
})

/* ==================== 模式切换 ==================== */

const onModeChange = (value: string) => {
  if (value === MODE_CODE) return
  const target = resolveModeNavigation(value, CURRENT_PAGE_MODE)
  if (target) {
    router.push(target)
  }
  // 下拉值立刻回弹到本页模式，避免显示成用户刚点走的那个（跳转可能被取消）
  mode.value = MODE_CODE
}

/** 页内模式切换（模型对比 / 提示词实验） */
const switchWorkMode = (next: CodeMode) => {
  if (currentMode.value === next) return
  if (isStreaming.value) {
    message.warning('正在生成中，请先停止再切换')
    return
  }
  currentMode.value = next
  activePreviewTab.value = 0
  // 切换工作模式等于换了一套上下文，直接开一个新会话更清晰
  startNewConversation()
}

watch(currentMode, () => {
  activePreviewTab.value = 0
})

/**
 * URL 上的 conversationId 变化时重新加载会话
 *
 * 场景：已经在 /code-mode 页面时，点击侧栏另一条历史、或直接改地址栏的 ?conversationId=——
 * 这两种情况只是 query 变化，组件不会重新挂载，onMounted 里的加载逻辑不会再跑，
 * 没有这个 watch 就会出现「点了别的会话但内容没变」。
 * loadConversation 内部有「同一条且已有消息就跳过」的判断，syncQuery 触发的同值变化不会重复请求。
 */
watch(
  () => route.query.conversationId as string | undefined,
  (next, prev) => {
    if (!next || next === prev) return
    loadConversation(next)
  },
)

/* ==================== 数据加载 ==================== */

const loadModels = async () => {
  modelLoading.value = true
  try {
    const res = await listModels()
    if (res.data.code === 0) {
      modelList.value = res.data.data || []
      const fallback = pickDefaultModel()
      if (!labModel.value) labModel.value = fallback
      if (selectedModels.value.length === 0 && fallback) {
        // 默认选中两个模型，直接就能对比（只有一个模型时只选一个）
        const second = modelList.value.find(
          (m) => m.id !== fallback && isFreeModel(m) && m.id !== fallback,
        )
        selectedModels.value = second ? [fallback, second.id] : [fallback]
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

/** 侧栏历史：只取代码预览相关的会话（codePreviewEnabled=true） */
const loadConversations = async () => {
  historyLoading.value = true
  try {
    const res = await listConversationVoByPage({
      codePreviewEnabled: true,
      current: 1,
      pageSize: HISTORY_PAGE_SIZE,
    })
    if (res.data.code === 0) {
      conversations.value = res.data.data?.records || []
    }
  } catch {
    // 侧栏属于辅助信息，加载失败不打断主流程
  } finally {
    historyLoading.value = false
  }
}

/** 加载历史代码会话，按 messageIndex 归组还原多轮结构 */
const loadConversation = async (conversationId: string) => {
  if (isStreaming.value) {
    message.warning('正在生成中，请先停止再切换')
    return
  }
  if (conversationId === currentConversationId.value && messages.value.length > 0) return

  try {
    const res = await listConversationMessages(conversationId)
    if (res.data.code !== 0) {
      message.error('加载会话失败：' + res.data.message)
      return
    }

    const rows = res.data.data || []
    const conv = conversations.value.find((item) => item.id === conversationId)

    const groupMap = new Map<
      number,
      { userRows: ConversationMessageVO[]; aiRows: ConversationMessageVO[] }
    >()
    for (const row of rows) {
      let group = groupMap.get(row.messageIndex)
      if (!group) {
        group = { userRows: [], aiRows: [] }
        groupMap.set(row.messageIndex, group)
      }
      if (row.role === 'user') group.userRows.push(row)
      else group.aiRows.push(row)
    }

    const built: ChatMessage[] = []
    const indexes = [...groupMap.keys()].sort((a, b) => a - b)

    for (const index of indexes) {
      const group = groupMap.get(index)!

      if (group.userRows.length) {
        const sorted = [...group.userRows].sort(
          (a, b) => (a.variantIndex ?? 0) - (b.variantIndex ?? 0),
        )
        // 有 variantIndex 的是提示词实验，否则是模型对比的单条提问
        const isLabRound = sorted.some((row) => row.variantIndex != null)
        if (isLabRound) {
          built.push({
            type: 'user',
            variants: sorted.map((row) => row.content),
            conversationId,
            messageIndex: index,
          })
        } else {
          built.push({
            type: 'user',
            content: sorted.map((row) => row.content).join('\n'),
            conversationId,
            messageIndex: index,
          })
        }
      }

      if (group.aiRows.length) {
        const isLabRound = group.aiRows.some((row) => row.variantIndex != null)
        const responses: ModelResponse[] = group.aiRows.map((row, i) => ({
          modelName: row.modelName || '',
          variantIndex: isLabRound ? (row.variantIndex ?? i) : undefined,
          runIndex: 0,
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
          codeBlocks: row.codeBlocks,
        }))
        built.push({
          type: 'assistant',
          conversationId,
          messageIndex: index,
          responses,
          runCount: 1,
        })
      }
    }

    messages.value = built
    currentConversationId.value = conversationId
    // 把 URL 同步成当前会话，否则从侧栏切了会话之后刷新页面会回到上一个会话
    // （syncQuery 内部有同值判断，watch 也有「同一条就跳过」的守卫，不会形成循环）
    syncQuery(conversationId)

    // 按历史内容推断工作模式与模型选择
    const firstAi = rows.find((row) => row.role === 'assistant')
    if (firstAi) {
      const isLab = rows.some((row) => row.role === 'assistant' && row.variantIndex != null)
      currentMode.value = isLab ? 'prompt-experiment' : 'model-compare'
      if (isLab) {
        if (firstAi.modelName) labModel.value = firstAi.modelName
        const variantRows = rows.filter((row) => row.role === 'user' && row.variantIndex != null)
        variants.value = [...variantRows]
          .sort((a, b) => (a.variantIndex ?? 0) - (b.variantIndex ?? 0))
          .map((row) => row.content)
        if (variants.value.length < MIN_VARIANTS) variants.value = ['', '']
      } else if (conv?.models?.length) {
        selectedModels.value = [...conv.models]
      }
    }

    // 历史记录的思考过程默认折叠
    const collapsed = new Set<string>()
    built.forEach((item, msgIdx) => {
      ;(item.responses || []).forEach((resp, rIdx) => {
        if (hasReasoning(resp)) collapsed.add(reasoningKey(msgIdx, rIdx))
      })
    })
    collapsedReasoning.value = collapsed
    scrollToBottom(true)
  } catch (error) {
    message.error('加载会话失败：' + (error as Error).message)
  }
}

const startNewConversation = () => {
  if (isStreaming.value) return
  closeSSE()
  messages.value = []
  currentConversationId.value = null
  prompt.value = ''
  variants.value = ['', '']
  collapsedReasoning.value = new Set()
  activePreviewTab.value = 0
  if (route.query.conversationId) router.replace({ path: '/code-mode' })
  scrollToBottom(true)
}

/* ==================== 变体管理 ==================== */

const addVariant = () => {
  if (variants.value.length < MAX_VARIANTS) variants.value.push('')
}

const removeVariant = (index: number) => {
  if (variants.value.length > MIN_VARIANTS) variants.value.splice(index, 1)
}

const filledVariants = computed(() => variants.value.map((v) => v.trim()).filter((v) => v !== ''))

const canSubmit = computed(() => {
  if (isStreaming.value) return false
  if (currentMode.value === 'model-compare') {
    return selectedModels.value.length > 0 && !!prompt.value.trim()
  }
  return (
    !!labModel.value &&
    filledVariants.value.length >= MIN_VARIANTS &&
    filledVariants.value.length <= MAX_VARIANTS
  )
})

/* ==================== 展示辅助 ==================== */

const totalTokens = (resp: ModelResponse) => (resp.inputTokens || 0) + (resp.outputTokens || 0)

const hasReasoning = (resp: ModelResponse) =>
  !!resp.hasReasoning && !!(resp.reasoning || '').trim()

const reasoningKey = (msgIndex: number, respIndex: number) => `${msgIndex}-${respIndex}`

const isReasoningCollapsed = (msgIndex: number, respIndex: number) =>
  collapsedReasoning.value.has(reasoningKey(msgIndex, respIndex))

const toggleReasoning = (msgIndex: number, respIndex: number) => {
  const next = new Set(collapsedReasoning.value)
  const key = reasoningKey(msgIndex, respIndex)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  collapsedReasoning.value = next
}

const copyResponse = async (resp: ModelResponse) => {
  try {
    await navigator.clipboard.writeText(resp.fullContent || '')
    message.success('已复制到剪贴板')
  } catch {
    message.error('复制失败，请手动选择内容')
  }
}

/* ==================== 滚动 ==================== */

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

/* ==================== 提交与流式接收 ==================== */

const closeSSE = () => {
  for (const handle of sseHandles.value) {
    handle?.close()
  }
  // 直接换一个新数组而不是置空长度：正在 await createPostSSE 的调用拿到结果后
  // 会往「它捕获的那个数组引用」里 push，用新数组可以避免把已关闭的 handle 又塞回来
  sseHandles.value = []
}

/** 记录新建的 SSE 连接句柄（连上之后才能中断，所以要在拿到 handle 后补存一次） */
const trackSSE = (handle: SSEHandle) => {
  sseHandles.value = [...sseHandles.value.filter((item) => item && item !== handle), handle]
}

/** 流已自然结束：关掉连接并把它从「可中断」列表里摘掉，避免句柄越积越多 */
const releaseSSE = (handlePromise: Promise<SSEHandle>) => {
  void handlePromise
    .then((handle) => {
      handle.close()
      sseHandles.value = sseHandles.value.filter((item) => item !== handle)
    })
    .catch(() => {
      // createPostSSE 在建立连接阶段就失败时走 onError，这里无需额外处理
    })
}

const syncQuery = (conversationId: string) => {
  if (route.query.conversationId === conversationId) return
  router.replace({ path: '/code-mode', query: { conversationId } })
}

const handleSubmit = async () => {
  if (!canSubmit.value) return

  isStreaming.value = true
  const assistantMsgIndex = messages.value.length + 1

  if (currentMode.value === 'model-compare') {
    const promptText = prompt.value.trim()
    const models = [...selectedModels.value]
    messages.value.push({ type: 'user', content: promptText })
    messages.value.push({
      type: 'assistant',
      conversationId: currentConversationId.value ?? undefined,
      responses: models.map((modelName) => ({
        modelName,
        fullContent: '',
        done: false,
        hasError: false,
      })),
      runCount: 1,
    })
    scrollToBottom(true)

    try {
      await runModelCompareRound(assistantMsgIndex, models, promptText)
    } finally {
      isStreaming.value = false
      closeSSE()
      loadConversations()
    }
    return
  }

  // 提示词实验：同一模型并行跑所有变体
  const promptVariants = [...filledVariants.value]
  messages.value.push({ type: 'user', variants: promptVariants })
  messages.value.push({
    type: 'assistant',
    conversationId: currentConversationId.value ?? undefined,
    responses: promptVariants.map((_, index) => ({
      modelName: labModel.value || '',
      variantIndex: index,
      runIndex: 0,
      fullContent: '',
      done: false,
      hasError: false,
    })),
    runCount: 1,
  })
  scrollToBottom(true)

  try {
    await runPromptLabRound(assistantMsgIndex, promptVariants)
  } finally {
    isStreaming.value = false
    closeSSE()
    loadConversations()
  }
}

/** 模型对比模式：一个请求里后端已经并行跑了多个模型，前端按 modelName 归位 */
const runModelCompareRound = (
  assistantMsgIndex: number,
  models: string[],
  promptText: string,
): Promise<void> =>
  new Promise((resolve) => {
    let settled = false
    const settle = () => {
      if (settled) return
      settled = true
      resolve()
    }

    // 本轮所有回复都结束时，主动断开 SSE：
    // 后端在 done 事件之后还会走一段 merge 收尾，早点断开能省掉一次无谓的等待。
    const finishIfAllDone = (responses: ModelResponse[]) => {
      if (responses.every((r) => r.done)) {
        releaseSSE(sse)
        settle()
      }
    }

    const sse = createPostSSE(
      `${API_BASE_URL}/conversation/code-mode/stream`,
      {
        conversationId: currentConversationId.value ?? undefined,
        models,
        prompt: promptText,
      },
      {
        onMessage: (chunk: StreamChunkVO) => {
          const msg = messages.value[assistantMsgIndex]
          if (!msg?.responses) return

          if (chunk.conversationId && !currentConversationId.value) {
            currentConversationId.value = chunk.conversationId
            msg.conversationId = chunk.conversationId
            syncQuery(chunk.conversationId)
          }

          const target = msg.responses.find((r) => r.modelName === chunk.modelName)
          if (!target) return

          applyChunk(target, chunk)
          messages.value = [...messages.value]
          scrollToBottom()

          finishIfAllDone(msg.responses)
        },
        onError: (err) => {
          releaseSSE(sse)
          markResponsesFailed(assistantMsgIndex, err.message)
          settle()
        },
        onComplete: () => {
          releaseSSE(sse)
          markResponsesFailed(assistantMsgIndex, '连接已中断')
          settle()
        },
      },
    )

    // createPostSSE 是同步返回 Promise 的，句柄在下一个微任务才可用；
    // 这里不 await，等 handle 到位再登记，避免「停止生成」时漏关连接。
    void sse.then(trackSSE)
  })

/** 提示词实验模式：按 variantIndex 归位 */
const runPromptLabRound = (assistantMsgIndex: number, promptVariants: string[]): Promise<void> =>
  new Promise((resolve) => {
    let settled = false
    const settle = () => {
      if (settled) return
      settled = true
      resolve()
    }

    const finishIfAllDone = (responses: ModelResponse[]) => {
      if (responses.every((r) => r.done)) {
        releaseSSE(sse)
        settle()
      }
    }

    const sse = createPostSSE(
      `${API_BASE_URL}/conversation/code-mode/prompt-lab/stream`,
      {
        conversationId: currentConversationId.value ?? undefined,
        model: labModel.value,
        promptVariants,
      },
      {
        onMessage: (chunk: StreamChunkVO) => {
          const msg = messages.value[assistantMsgIndex]
          if (!msg?.responses) return

          if (chunk.conversationId && !currentConversationId.value) {
            currentConversationId.value = chunk.conversationId
            msg.conversationId = chunk.conversationId
            syncQuery(chunk.conversationId)
          }

          const index = chunk.variantIndex
          if (index === undefined) return
          const target = msg.responses.find((r) => r.variantIndex === index)
          if (!target) return

          applyChunk(target, chunk)
          messages.value = [...messages.value]
          scrollToBottom()

          finishIfAllDone(msg.responses)
        },
        onError: (err) => {
          releaseSSE(sse)
          markResponsesFailed(assistantMsgIndex, err.message)
          settle()
        },
        onComplete: () => {
          releaseSSE(sse)
          markResponsesFailed(assistantMsgIndex, '连接已中断')
          settle()
        },
      },
    )

    void sse.then(trackSSE)
  })

/** 把一个 SSE 数据块合并进某个回复对象 */
const applyChunk = (target: ModelResponse, chunk: StreamChunkVO) => {
  if (chunk.fullContent !== undefined) target.fullContent = chunk.fullContent
  if (chunk.reasoning !== undefined) target.reasoning = chunk.reasoning
  if (chunk.hasReasoning !== undefined) target.hasReasoning = chunk.hasReasoning
  if (chunk.thinkingTime !== undefined) target.thinkingTime = chunk.thinkingTime
  if (chunk.elapsedMs !== undefined) target.elapsedMs = chunk.elapsedMs
  if (chunk.responseTimeMs !== undefined) target.responseTimeMs = chunk.responseTimeMs
  if (chunk.inputTokens !== undefined) target.inputTokens = chunk.inputTokens
  if (chunk.outputTokens !== undefined) target.outputTokens = chunk.outputTokens
  if (chunk.cost !== undefined) target.cost = chunk.cost
  if (chunk.hasError) {
    target.hasError = true
    target.error = chunk.error
    target.done = true
    return
  }
  if (chunk.done) {
    target.done = true
    if (chunk.codeBlocks) target.codeBlocks = chunk.codeBlocks
  }
}

/** 把还停留在「生成中」的回复标记为失败，避免页面一直转圈 */
const markResponsesFailed = (msgIndex: number, reason: string) => {
  const msg = messages.value[msgIndex]
  if (!msg?.responses) return
  let changed = false
  for (const resp of msg.responses) {
    if (!resp.done) {
      resp.done = true
      resp.hasError = true
      resp.error = reason
      changed = true
    }
  }
  if (changed) messages.value = [...messages.value]
}

/** 中途停止生成：断开 SSE 后服务端会取消在途的模型调用 */
const stopGeneration = () => {
  closeSSE()
  isStreaming.value = false

  const lastMsg = messages.value[messages.value.length - 1]
  if (lastMsg?.responses) {
    for (const resp of lastMsg.responses) {
      if (!resp.done) {
        resp.done = true
        resp.stopped = true
      }
    }
    messages.value = [...messages.value]
  }
  message.info('已停止生成，已生成的内容已保存')
  loadConversations()
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
/* ==================== 整体布局：左栏 + 中栏 + 右侧预览 ==================== */
.cm-root {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: #fff;
  color: #1f2328;
  font-size: 14px;
}

/* ==================== 左侧会话栏 ==================== */
.cm-sidebar {
  flex: 0 0 220px;
  width: 220px;
  display: flex;
  flex-direction: column;
  padding: 12px 12px 10px;
  box-sizing: border-box;
  border-right: 1px solid #ececec;
  background: #fff;
}

.cm-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px 16px;
  text-decoration: none;
}

.cm-brand-logo {
  height: 26px;
}

.cm-brand-title {
  font-size: 15px;
  font-weight: 700;
  color: #1f2328;
  white-space: nowrap;
}

.cm-new-chat {
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

.cm-new-chat:hover:not(:disabled) {
  background: #f7f8fa;
  border-color: #d7dbe0;
}

.cm-new-chat:disabled {
  color: #b9c0ca;
  cursor: not-allowed;
}

.cm-history {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  margin-top: 18px;
}

.cm-history-label {
  padding: 0 8px 6px;
  font-size: 12px;
  color: #9aa1ac;
}

.cm-conv {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 8px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}

.cm-conv:hover {
  background: #f7f8fa;
}

.cm-conv.active {
  background: #eef4ff;
}

.cm-conv-icon {
  display: inline-flex;
  color: #8b949e;
  flex: 0 0 auto;
}

.cm-conv.active .cm-conv-icon {
  color: #1677ff;
}

.cm-conv-title {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: #3d4451;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cm-history-tip {
  padding: 6px 8px;
  font-size: 12px;
  color: #b0b7c3;
}

.cm-user {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 6px 2px;
  border-top: 1px solid #f0f1f3;
  cursor: pointer;
}

.cm-user-name {
  font-size: 13px;
  color: #3d4451;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ==================== 中间对话区 ==================== */
.cm-chat {
  flex: 1 1 40%;
  min-width: 340px;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #ececec;
  background: #fff;
}

.cm-topbar {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 56px;
  padding: 0 16px;
  border-bottom: 1px solid #ececec;
  flex: 0 0 auto;
}

.mode-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
}

.mode-icon {
  color: #8b949e;
}

.mode-select {
  width: 118px;
}

.cm-select {
  min-width: 170px;
}

.cm-select.wide {
  flex: 1 1 auto;
  max-width: 420px;
}

.cm-topbar-spacer {
  flex: 1 1 auto;
}

.cm-topbar-hint {
  font-size: 12px;
  color: #9aa1ac;
  white-space: nowrap;
}

.cm-messages {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 20px 20px 8px;
  position: relative;
}

.cm-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  padding: 0 24px;
}

.cm-empty-icon {
  font-size: 40px;
  color: #d1d5db;
  margin-bottom: 14px;
}

.cm-empty-title {
  font-size: 15px;
  font-weight: 600;
  color: #3d4451;
  margin-bottom: 8px;
}

.cm-empty-desc {
  font-size: 13px;
  color: #8b949e;
  line-height: 1.7;
  max-width: 420px;
}

.cm-row {
  margin-bottom: 18px;
}

.cm-user-line {
  display: flex;
  justify-content: flex-end;
}

.cm-user-bubble {
  max-width: 88%;
  padding: 10px 14px;
  border-radius: 12px 12px 2px 12px;
  background: #eef4ff;
  color: #1f2328;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.cm-variant-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  align-items: flex-end;
}

.cm-user-tag {
  display: inline-block;
  margin-right: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  background: #d6e4ff;
  color: #1677ff;
  font-size: 11px;
  font-weight: 600;
}

.cm-user-text {
  word-break: break-word;
}

.cm-response-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.cm-card {
  border: 1px solid #e6e8eb;
  border-radius: 12px;
  padding: 12px 14px 14px;
  background: #fff;
}

.cm-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.cm-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  flex: 0 0 auto;
}

.cm-model-name {
  font-size: 13px;
  font-weight: 600;
  color: #1f2328;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.cm-run-tag {
  padding: 1px 5px;
  border-radius: 4px;
  background: #f0f1f3;
  color: #6b7280;
  font-size: 11px;
  font-weight: 500;
}

.cm-head-spacer {
  flex: 1 1 auto;
}

.cm-metric {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  color: #8b949e;
  white-space: nowrap;
}

.cm-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #8b949e;
  cursor: pointer;
  transition: all 0.15s;
}

.cm-icon-btn:hover:not(:disabled) {
  background: #f0f1f3;
  color: #1f2328;
}

.cm-icon-btn:disabled {
  color: #d1d5db;
  cursor: not-allowed;
}

.cm-alert {
  margin-top: 4px;
}

.cm-reasoning {
  margin-bottom: 10px;
  border-left: 3px solid #e5e7eb;
  padding-left: 10px;
}

.cm-reasoning-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #8b949e;
  cursor: pointer;
  user-select: none;
}

.cm-caret {
  transition: transform 0.2s;
}

.cm-caret.collapsed {
  transform: rotate(-90deg);
}

.cm-reasoning-body {
  margin-top: 6px;
  font-size: 13px;
  color: #6b7280;
}

.cm-stopped-tip {
  margin-top: 8px;
  font-size: 12px;
  color: #b07d00;
  background: #fffbe6;
  border-radius: 6px;
  padding: 6px 10px;
}

.cm-scroll-btn {
  position: sticky;
  bottom: 8px;
  left: 50%;
  transform: translateX(-50%);
  width: 30px;
  height: 30px;
  border: 1px solid #e5e7eb;
  border-radius: 50%;
  background: #fff;
  color: #6b7280;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.1);
}

/* ==================== 底部输入区 ==================== */
.cm-input-wrap {
  flex: 0 0 auto;
  border-top: 1px solid #ececec;
  padding: 12px 16px 14px;
  background: #fff;
}

.cm-workmode-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.cm-workmode-switch {
  display: inline-flex;
  gap: 2px;
  padding: 2px;
  border-radius: 8px;
  background: #f2f4f7;
  flex: 0 0 auto;
}

.cm-workmode-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  padding: 0 12px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #6b7280;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.cm-workmode-btn:hover:not(:disabled) {
  color: #1f2328;
}

.cm-workmode-btn.active {
  background: #fff;
  color: #1677ff;
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.1);
}

.cm-workmode-btn:disabled {
  color: #b9c0ca;
  cursor: not-allowed;
}

.cm-workmode-hint {
  font-size: 12px;
  color: #9aa1ac;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cm-prompt-input {
  width: 100%;
  box-sizing: border-box;
  padding: 10px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  font-size: 14px;
  font-family: inherit;
  line-height: 1.6;
  resize: vertical;
  outline: none;
  transition: border-color 0.15s;
}

.cm-prompt-input:focus {
  border-color: #1677ff;
}

.cm-variants-panel {
  border: 1px solid #ececec;
  border-radius: 10px;
  padding: 10px;
}

.cm-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.cm-panel-title {
  font-size: 13px;
  font-weight: 600;
  color: #3d4451;
}

.cm-header-actions {
  display: flex;
  gap: 8px;
}

.cm-variants-horizontal {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  padding-bottom: 4px;
}

.cm-variant-card {
  flex: 0 0 220px;
  border: 1px solid #ececec;
  border-radius: 8px;
  padding: 8px;
  background: #fafbfc;
}

.cm-variant-label {
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 6px;
}

.cm-variant-input {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 13px;
  font-family: inherit;
  line-height: 1.5;
  resize: vertical;
  outline: none;
  background: #fff;
}

.cm-variant-input:focus {
  border-color: #1677ff;
}

.cm-submit-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
}

.cm-submit-hint {
  flex: 1 1 auto;
  font-size: 12px;
  color: #9aa1ac;
}

.cm-submit-btn {
  height: 36px;
  padding: 0 22px;
  border: none;
  border-radius: 8px;
  background: #1677ff;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}

.cm-submit-btn:hover:not(:disabled) {
  background: #4096ff;
}

.cm-submit-btn:disabled {
  background: #c8d6e5;
  cursor: not-allowed;
}

.cm-submit-btn.stop {
  background: #fff;
  color: #f5222d;
  border: 1px solid #ffccc7;
}

.cm-submit-btn.stop:hover {
  background: #fff1f0;
}

/* ==================== 右侧预览区（可收起） ==================== */
.cm-preview {
  flex: 0 0 56%;
  min-width: 420px;
  display: flex;
  flex-direction: column;
  background: #fafbfc;
  /* 宽度/最小宽度一起过渡，收起时才有「抽屉推回去」的效果 */
  transition:
    flex-basis 0.24s ease,
    min-width 0.24s ease;
}

/* 收起：让出全部宽度给对话区，只留右侧一条竖排展开条 */
.cm-preview.is-collapsed {
  flex: 0 0 44px;
  min-width: 44px;
  background: #fff;
  border-left: 1px solid #ececec;
}

.cm-preview-inner {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.cm-collapse-btn {
  color: #6b7280;
}

.cm-collapse-btn:hover {
  background: #eef1f4;
  color: #1f2328;
}

/* 右侧竖排展开条 */
.cm-preview-expand-rail {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 16px 0;
  border: none;
  background: #fff;
  color: #6b7280;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.cm-preview-expand-rail:hover {
  background: #f7f8fa;
  color: #1677ff;
}

.cm-rail-caret {
  font-size: 12px;
}

.cm-rail-text {
  /* 竖排文字：让「预览」两个字纵向排列，窄条里也读得出来 */
  writing-mode: vertical-rl;
  letter-spacing: 2px;
}

/* 收起时如果已经有可预览的代码，给个提示点 */
.cm-rail-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #52c41a;
  box-shadow: 0 0 0 3px rgba(82, 196, 26, 0.15);
}

/* 窄屏：对话区已经没什么空间再让预览区撑着 420px 了，
   直接收窄下限，配合「收起」按钮用户就能把预览完全让出去 */
@media (max-width: 1440px) {
  .cm-preview {
    min-width: 340px;
  }

  .cm-chat {
    min-width: 300px;
  }
}

.cm-preview-tabs {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 8px;
  height: 56px;
  padding: 0 14px;
  border-bottom: 1px solid #ececec;
  background: #fff;
  overflow-x: auto;
}

.cm-tabs-left {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 1 1 auto;
  min-width: 0;
}

.cm-tab-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: #6b7280;
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
}

.cm-tab-item:hover {
  background: #f7f8fa;
}

.cm-tab-item.active {
  background: #eef4ff;
  border-color: #bedaff;
  color: #1677ff;
  font-weight: 600;
}

.cm-tab-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
}

.cm-tab-name {
  max-width: 130px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cm-tabs-empty {
  font-size: 12px;
  color: #b0b7c3;
}

.cm-tabs-actions {
  flex: 0 0 auto;
}

.cm-download-btn {
  white-space: nowrap;
}

.cm-preview-content {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
}

.cm-preview-wrapper {
  flex: 1 1 auto;
  min-height: 0;
}

/* 右侧预览里的 CodePreview 撑满可用高度（内部用 flex 分配 iframe 的剩余空间） */
.cm-preview-card {
  margin: 0;
}

.cm-preview-generating {
  max-width: 520px;
  margin: 40px auto 0;
}

.cm-preview-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
}

.cm-preview-empty-icon {
  font-size: 48px;
  color: #d1d5db;
  margin-bottom: 16px;
}

.cm-preview-empty-title {
  font-size: 14px;
  color: #6b7280;
  margin: 0;
}

.cm-preview-empty-desc {
  font-size: 12px;
  color: #9ca3af;
  margin: 8px 0 0;
}
</style>
