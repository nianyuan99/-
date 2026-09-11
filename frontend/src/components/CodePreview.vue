<template>
  <div class="code-preview-container" :class="{ 'fill-height': fillHeight }">
    <!-- 多文件模式：顶部文件切换栏（HTML + CSS + JS 分开返回时用） -->
    <div v-if="isMultiFile" class="file-tabs">
      <button
        v-for="(block, index) in blocks"
        :key="`file-${index}`"
        class="file-tab"
        :class="{ active: activeFileIndex === index }"
        :title="block.language"
        @click="switchFile(index)"
      >
        {{ fileNameOf(block.language) }}
      </button>
    </div>

    <!-- HTML：默认显示预览，可切换到代码 -->
    <template v-if="isHtml">
      <!-- 预览视图 -->
      <div v-if="!showCode" class="preview-view">
        <div class="pane-header">
          <div class="header-left">
            <span class="pane-title">预览效果</span>
            <span v-if="isMultiFile" class="merged-tag" title="已把 CSS 注入 head、JS 注入 body 末尾后合并预览">
              已合并 {{ blocks.length }} 个代码块
            </span>
          </div>

          <div class="header-actions">
            <!-- 设备模拟（第六章扩展） -->
            <a-radio-group v-model:value="device" size="small" class="device-group">
              <a-radio-button value="desktop">桌面端</a-radio-button>
              <a-radio-button value="tablet">平板</a-radio-button>
              <a-radio-button value="mobile">手机</a-radio-button>
            </a-radio-group>

            <button class="action-btn" title="刷新预览" @click="refreshPreview">
              <ReloadOutlined />
            </button>
            <button class="action-btn" title="查看代码" @click="showCode = true">
              <CodeOutlined />
              <span>代码</span>
            </button>
            <button class="action-btn" title="复制代码" @click="copyCode">
              <CopyOutlined />
            </button>
            <button class="action-btn" title="全屏预览" @click="fullScreenPreview = true">
              <ExpandOutlined />
            </button>
          </div>
        </div>

        <div class="device-stage" :class="{ framed: device !== 'desktop' }">
          <iframe
            :key="previewKey"
            :srcdoc="previewHtml"
            sandbox="allow-scripts"
            class="preview-iframe"
            :style="deviceStyle"
            title="代码预览"
          ></iframe>
        </div>
      </div>

      <!-- 代码视图 -->
      <div v-else class="code-view">
        <div class="pane-header">
          <div class="header-left">
            <span class="language-tag">{{ displayLanguage }}</span>
            <span v-if="editable" class="edit-tag" title="修改代码后 500ms 自动刷新预览">
              <EditOutlined />
              可编辑
            </span>
          </div>
          <div class="header-actions">
            <button class="action-btn" title="返回预览" @click="showCode = false">
              <EyeOutlined />
              <span>预览</span>
            </button>
            <button class="action-btn" title="复制代码" @click="copyCode">
              <CopyOutlined />
            </button>
            <button class="action-btn" title="下载文件" @click="downloadCode">
              <DownloadOutlined />
            </button>
            <button v-if="editable" class="action-btn" title="还原为 AI 原始代码" @click="resetCode">
              <UndoOutlined />
            </button>
          </div>
        </div>
        <div
          ref="editorContainer"
          class="editor-container"
          :style="fillHeight ? undefined : { height: editorHeight }"
        ></div>
      </div>
    </template>

    <!-- 非 HTML 代码：只显示代码 -->
    <template v-else>
      <div class="code-view">
        <div class="pane-header">
          <div class="header-left">
            <span class="language-tag">{{ displayLanguage }}</span>
            <span v-if="editable" class="edit-tag">
              <EditOutlined />
              可编辑
            </span>
          </div>
          <div class="header-actions">
            <button class="action-btn" title="复制代码" @click="copyCode">
              <CopyOutlined />
            </button>
            <button class="action-btn" title="下载文件" @click="downloadCode">
              <DownloadOutlined />
            </button>
            <button v-if="editable" class="action-btn" title="还原为 AI 原始代码" @click="resetCode">
              <UndoOutlined />
            </button>
          </div>
        </div>
        <div
          ref="editorContainer"
          class="editor-container"
          :style="fillHeight ? undefined : { height: editorHeight }"
        ></div>
      </div>
    </template>

    <!-- 全屏预览模态框 -->
    <a-modal
      v-model:open="fullScreenPreview"
      title="全屏预览"
      width="95%"
      :footer="null"
      :destroy-on-close="true"
      wrap-class-name="code-preview-fullscreen-modal"
    >
      <iframe
        v-if="fullScreenPreview"
        :srcdoc="previewHtml"
        sandbox="allow-scripts"
        class="fullscreen-iframe"
        title="全屏代码预览"
      ></iframe>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import {
  CodeOutlined,
  CopyOutlined,
  DownloadOutlined,
  EditOutlined,
  ExpandOutlined,
  EyeOutlined,
  ReloadOutlined,
  UndoOutlined,
} from '@ant-design/icons-vue'
import type * as Monaco from 'monaco-editor'
import {
  EDITABLE_EDITOR_OPTIONS,
  READONLY_EDITOR_OPTIONS,
  SCRIPT_CLOSE_TAG,
  STYLE_CLOSE_TAG,
  debounce,
  downloadTextFile,
  getFileName,
  getMonacoLanguage,
  loadMonaco,
} from '@/utils/monacoEditor'

/** 一个代码块（与后端 code_extractor 的 dict 结构对应） */
export interface CodeBlock {
  language: string
  code: string
  sanitizedHtml?: string
}

interface Props {
  /** 单个代码块 */
  codeBlock?: CodeBlock
  /** 多个代码块（HTML/CSS/JS 分开返回时，合并预览；传了就优先用这个） */
  codeBlocks?: CodeBlock[]
  /** 代码模式：HTML 默认直接显示预览而不是代码 */
  isCodeMode?: boolean
  /** 是否允许编辑并实时刷新预览（第六章扩展） */
  editable?: boolean
  /**
   * 撑满父容器高度
   *
   * 代码模式页面的右侧预览栏需要卡片填满整列，否则底下会留一大块空白；
   * 而聊天流里的代码卡片必须用固定高度（否则会跟滚动容器互相拉扯）。
   */
  fillHeight?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  codeBlock: undefined,
  codeBlocks: undefined,
  isCodeMode: false,
  editable: false,
  fillHeight: false,
})

/** 归一化后的代码块列表：优先 codeBlocks，其次单个 codeBlock */
const blocks = computed<CodeBlock[]>(() => {
  if (props.codeBlocks && props.codeBlocks.length > 0) return props.codeBlocks
  if (props.codeBlock) return [props.codeBlock]
  return []
})

const isHtmlLanguage = (language?: string) => (language || '').toLowerCase() === 'html'
const isJsLanguage = (language?: string) =>
  ['javascript', 'js'].includes((language || '').toLowerCase())

/** 多文件时当前查看的代码块；单文件时就是唯一的那个 */
const activeFileIndex = ref(0)
const activeBlock = computed<CodeBlock | undefined>(
  () => blocks.value[activeFileIndex.value] ?? blocks.value[0],
)

const htmlBlock = computed(() => blocks.value.find((b) => isHtmlLanguage(b.language)))

/** 多文件模式：超过一个代码块，且其中至少有一个 html（否则没法合成页面） */
const isMultiFile = computed(() => blocks.value.length > 1 && !!htmlBlock.value)

/** 当前展示的代码块是不是 HTML（决定是否给预览视图） */
const isHtml = computed(() => isHtmlLanguage(activeBlock.value?.language))

const editorContainer = ref<HTMLElement>()
const fullScreenPreview = ref(false)

/** 代码视图默认是否展开：代码模式下 HTML 先给预览，其余情况直接看代码 */
const viewOverride = ref<boolean | null>(null)
const defaultShowCode = () => !(props.isCodeMode && isHtml.value)
const showCode = computed({
  get: () => viewOverride.value ?? defaultShowCode(),
  set: (value: boolean) => {
    viewOverride.value = value  },
})
const displayLanguage = ref((activeBlock.value?.language || 'text').toUpperCase())

/** 用户在编辑器里改过的内容（未改动时为 null，回退到原始代码） */
const editedCode = ref<string | null>(null)

/** 手动刷新预览时自增，作为 iframe 的 key 强制重建 */
const previewKey = ref(0)

let editor: Monaco.editor.IStandaloneCodeEditor | null = null
/** 持有 monaco 实例，切换文件时要靠它调 setModelLanguage */
let monacoRef: typeof Monaco | null = null
let editorDisposed = false

/* ==================== 预览 HTML 合成 ==================== */

/**
 * 多文件合并：把 CSS 注入 <head>，JS 注入到 body 末尾
 *
 * AI 有时会把 HTML/CSS/JS 拆成三个代码块返回，而 iframe 的 srcdoc 只能吃一份文档，
 * 所以这里在预览前做一次前端合并（教程第六章「多文件项目预览」）。
 */
const mergeCodeBlocks = (list: CodeBlock[]): string => {
  const html = list.find((b) => isHtmlLanguage(b.language))
  if (!html) return ''

  const css = list.filter((b) => b.language.toLowerCase() === 'css')
  const js = list.filter((b) => isJsLanguage(b.language))

  let merged = html.code

  if (css.length > 0) {
    const styleTag = `<style>\n${css.map((b) => b.code).join('\n')}\n${STYLE_CLOSE_TAG}`
    // 没有 </head> 的极简片段就退化为插到最前面
    merged = merged.includes('</head>')
      ? merged.replace('</head>', `${styleTag}\n</head>`)
      : `${styleTag}\n${merged}`
  }

  if (js.length > 0) {
    const scriptTag = `<script>\n${js.map((b) => b.code).join('\n')}\n${SCRIPT_CLOSE_TAG}`
    merged = merged.includes('</body>')
      ? merged.replace('</body>', `${scriptTag}\n</body>`)
      : `${merged}\n${scriptTag}`
  }

  return merged
}

/** 真正送进 iframe 的 HTML */
const previewHtml = computed(() => {
  if (editedCode.value !== null) return editedCode.value
  if (isMultiFile.value) return mergeCodeBlocks(blocks.value)
  const block = activeBlock.value
  // sanitizedHtml 后端目前是原样返回（安全由 iframe sandbox 保证），
  // 这里优先用 code，避免历史数据里 sanitizedHtml 为空时预览成白屏
  return block?.code || block?.sanitizedHtml || ''
})

/** 设备模拟预设（第六章扩展） */
const DEVICE_PRESETS: Record<string, { width: string; height: string; label: string }> = {
  desktop: { width: '100%', height: '100%', label: '桌面端' },
  tablet: { width: '768px', height: '1024px', label: '平板' },
  mobile: { width: '375px', height: '667px', label: '手机' },
}

const device = ref<'desktop' | 'tablet' | 'mobile'>('desktop')

const currentPreset = () => DEVICE_PRESETS[device.value] ?? DEVICE_PRESETS.desktop!

const deviceStyle = computed(() => {
  const preset = currentPreset()
  if (device.value === 'desktop') {
    return { width: '100%', height: '100%' }
  }
  return {
    width: preset.width,
    // 在小屏下用 70vh 封顶，避免平板/手机的固定高度撑破卡片
    height: `min(${preset.height}, 70vh)`,
    margin: '0 auto',
    border: '1px solid #e5e7eb',
    borderRadius: '12px',
    boxShadow: '0 6px 20px rgba(15, 23, 42, 0.08)',
  }
})

const refreshPreview = () => {
  previewKey.value += 1
  message.success('已刷新预览')
}

/* ==================== 编辑器 ==================== */

/** 编辑器每行高度 + 上下 padding，用于按内容行数估算合适高度 */
const EDITOR_LINE_HEIGHT = 19
const EDITOR_PADDING = 24
const EDITOR_MIN_HEIGHT = 130
const EDITOR_MAX_HEIGHT = 420

/**
 * 代码视图容器高度（仅在非撑满模式下生效）
 *
 * 聊天流里的代码卡片如果固定 380px，一段 3 行的 JS 也会占掉半屏；
 * 这里按行数估算高度并夹在 [130, 420] 之间，代码多的时候仍然可滚动查看。
 */
const editorHeight = computed(() => {
  const code = editedCode.value ?? activeBlock.value?.code ?? ''
  const lineCount = code ? code.split('\n').length : 1
  const estimate = lineCount * EDITOR_LINE_HEIGHT + EDITOR_PADDING
  return `${Math.min(EDITOR_MAX_HEIGHT, Math.max(EDITOR_MIN_HEIGHT, estimate))}px`
})

/** 编辑器当前应该展示的内容：用户改过的优先 */
const currentEditorValue = () => editedCode.value ?? activeBlock.value?.code ?? ''

/** 把当前代码块的内容与语言同步到已有编辑器实例（复用实例，不重建） */
const applyBlockToEditor = () => {
  if (!editor) return
  const block = activeBlock.value
  const nextValue = block?.code ?? ''
  if (editor.getValue() !== nextValue) {
    editor.setValue(nextValue)
  }
  const model = editor.getModel()
  if (monacoRef && model) {
    const languageId = getMonacoLanguage(block?.language)
    if (model.getLanguageId() !== languageId) {
      monacoRef.editor.setModelLanguage(model, languageId)
    }
  }
}

const initEditor = async () => {
  if (!editorContainer.value) return

  try {
    const monaco = await loadMonaco()
    monacoRef = monaco
    // await 期间组件可能已经卸载，或者被 watch 触发了第二次初始化
    if (editorDisposed || !editorContainer.value) return

    // 已有实例就复用（教程要求：切换代码时复用而不是重新创建），
    // 但容器必须还是同一个 DOM 节点 —— 代码/预览切换会让容器重新挂载。
    if (editor && editor.getDomNode() && !editorContainer.value.contains(editor.getDomNode())) {
      editor.dispose()
      editor = null
    }

    if (editor) {
      applyBlockToEditor()
      editor.layout()
      return
    }

    const block = activeBlock.value
    editor = monaco.editor.create(editorContainer.value, {
      ...(props.editable ? EDITABLE_EDITOR_OPTIONS : READONLY_EDITOR_OPTIONS),
      value: currentEditorValue(),
      language: getMonacoLanguage(block?.language),
    })

    if (props.editable) {
      editor.onDidChangeModelContent(() => {
        schedulePreviewUpdate()
      })
    }

    // 编辑器自己滚到边界时，把滚轮事件放行给外层页面，避免「滚不动」的割裂感
    const domNode = editor.getDomNode()
    if (domNode) {
      domNode.addEventListener(
        'wheel',
        (event: WheelEvent) => {
          if (!editor) return
          const scrollTop = editor.getScrollTop()
          const scrollHeight = editor.getScrollHeight()
          const clientHeight = domNode.clientHeight
          const atTop = scrollTop === 0 && event.deltaY < 0
          const atBottom = scrollTop + clientHeight >= scrollHeight - 1 && event.deltaY > 0
          if (atTop || atBottom) return
          event.stopPropagation()
        },
        { passive: true },
      )
    }
  } catch (error) {
    // 加载失败时不能让整条回答挂掉，给出可读提示即可
    console.error('Monaco Editor 初始化失败', error)
    message.error('代码编辑器加载失败，请刷新页面重试')
  }
}

/** 释放编辑器实例（代码视图被 v-if 移除时容器已经不存在，必须销毁避免内存泄漏） */
const disposeEditor = () => {
  if (editor) {
    editor.dispose()
    editor = null
  }
}

/**
 * 编辑后延迟刷新预览
 *
 * 用 500ms 防抖：既能「边改边看」，又不会每敲一个字符就重建 iframe 导致闪烁。
 */
const schedulePreviewUpdate = debounce(() => {
  if (!editor || !props.editable) return
  const value = editor.getValue()
  editedCode.value = value
  // 非 HTML（比如只改了 JS 代码块）时，合并预览也要跟着更新
  if (isHtml.value || isMultiFile.value) {
    previewKey.value += 1
  }
}, 500)

const resetCode = () => {
  editedCode.value = null
  schedulePreviewUpdate.cancel()
  if (editor) {
    editor.setValue(activeBlock.value?.code ?? '')
  }
  previewKey.value += 1
  message.info('已还原为 AI 原始代码')
}

/* ==================== 交互 ==================== */

const switchFile = (index: number) => {
  activeFileIndex.value = index
}

const copyCode = async () => {
  const text = editedCode.value ?? activeBlock.value?.code ?? ''
  try {
    await navigator.clipboard.writeText(text)
    message.success('代码已复制')
  } catch {
    message.error('复制失败，请手动选择内容')
  }
}

const downloadCode = () => {
  const block = activeBlock.value
  const text = editedCode.value ?? block?.code ?? ''
  const fileName = getFileName(block?.language)
  // HTML 下载时给 text/html，双击即可用浏览器打开
  const mime = isHtml.value ? 'text/html' : 'text/plain'
  downloadTextFile(text, fileName, mime)
  message.success(`已下载 ${fileName}`)
}

const fileNameOf = (language?: string) => getFileName(language)

/* ==================== 生命周期与响应式同步 ==================== */

// 代码块内容变化（流式追加、切换历史消息）时，同步语言标签、预览内容与编辑器。
// 注意：这里**不能**重置 editedCode —— 用户正在编辑时流式内容仍在追加，
// 一重置就会把用户刚敲的字符吞掉。
watch(
  () => [props.codeBlock, props.codeBlocks],
  () => {
    // codeBlocks 变短时把越界的下标拉回来
    if (activeFileIndex.value >= blocks.value.length) activeFileIndex.value = 0

    const block = activeBlock.value
    displayLanguage.value = (block?.language || 'text').toUpperCase()

    // 用户没手动改过代码时，编辑器跟着最新内容走
    if (editedCode.value === null) {
      applyBlockToEditor()
    }
  },
  { deep: true },
)

// 切换文件后要把编辑器的内容与语言一起换掉（只 setValue 不够，语言高亮也得跟着变）
watch(activeFileIndex, () => {
  const block = activeBlock.value
  displayLanguage.value = (block?.language || 'text').toUpperCase()
  editedCode.value = null
  // 换文件视为换了一个视图对象，之前的手动「代码/预览」选择不再适用，
  // 回到默认视图（HTML 给预览、其他语言给代码）
  viewOverride.value = null
  if (showCode.value) {
    nextTick(() => initEditor())
  }
})

watch(showCode, (visible) => {
  if (visible) {
    // 等 v-else 分支的容器渲染出来再初始化
    nextTick(() => initEditor())
  } else {
    // 切回预览时先把编辑内容落到预览里，避免「改了但没生效」的错觉
    if (props.editable && editor) {
      editedCode.value = editor.getValue()
      previewKey.value += 1
    }
    // 代码视图的容器已被 v-if 移除，编辑器 DOM 也跟着没了，必须销毁实例
    disposeEditor()
  }
})

onMounted(() => {
  displayLanguage.value = (activeBlock.value?.language || 'text').toUpperCase()
  if (showCode.value) {
    initEditor()
  }
})

onBeforeUnmount(() => {
  editorDisposed = true
  schedulePreviewUpdate.cancel()
  disposeEditor()
})
</script>

<style scoped>
.code-preview-container {
  border: 1px solid #e6e8eb;
  border-radius: 10px;
  overflow: hidden;
  background: #fff;
  margin: 10px 0;
}

/* ==================== 撑满父容器（代码模式右侧预览栏） ==================== */
.code-preview-container.fill-height {
  height: 100%;
  margin: 0;
  display: flex;
  flex-direction: column;
}

.fill-height .file-tabs,
.fill-height .pane-header {
  flex: 0 0 auto;
}

/* 预览 / 代码视图本身也要参与 flex 分配，否则 iframe 拿不到剩余高度 */
.fill-height .preview-view,
.fill-height .code-view {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.fill-height .device-stage {
  flex: 1 1 auto;
  min-height: 0;
  flex-direction: column;
}

.fill-height .editor-container {
  flex: 1 1 auto;
  min-height: 0;
  height: auto;
}

/* ==================== 多文件切换栏 ==================== */
.file-tabs {
  display: flex;
  gap: 2px;
  padding: 6px 8px 0;
  background: #f6f8fa;
  border-bottom: 1px solid #e6e8eb;
  overflow-x: auto;
}

.file-tab {
  padding: 5px 12px;
  border: none;
  border-radius: 6px 6px 0 0;
  background: transparent;
  color: #57606a;
  font-size: 12px;
  font-family: Consolas, Monaco, 'Courier New', monospace;
  cursor: pointer;
  white-space: nowrap;
}

.file-tab.active {
  background: #fff;
  color: #1f2328;
  font-weight: 600;
  box-shadow: inset 0 -2px 0 #1677ff;
}

/* ==================== 面板头 ==================== */
.pane-header {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 38px;
  padding: 0 10px;
  background: #f6f8fa;
  border-bottom: 1px solid #e6e8eb;
}

.preview-view .pane-header {
  background: #fafbfc;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.pane-title {
  font-size: 13px;
  color: #57606a;
}

.merged-tag {
  font-size: 11px;
  color: #1677ff;
  background: #e8f2ff;
  padding: 2px 6px;
  border-radius: 4px;
  white-space: nowrap;
}

.language-tag {
  font-size: 12px;
  font-weight: 600;
  color: #57606a;
  font-family: Consolas, Monaco, 'Courier New', monospace;
  letter-spacing: 0.3px;
}

.edit-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  color: #d46b08;
  background: #fff7e6;
  padding: 2px 6px;
  border-radius: 4px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
}

.device-group {
  margin-right: 4px;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 26px;
  padding: 0 8px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: #57606a;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.action-btn:hover {
  background: #eef1f4;
  color: #1f2328;
}

/* ==================== 预览 ==================== */
.device-stage {
  display: flex;
  justify-content: center;
  background: #fff;
}

.device-stage.framed {
  padding: 16px;
  background: #f2f4f7;
}

.preview-iframe {
  display: block;
  width: 100%;
  height: 420px;
  border: none;
  background: #fff;
}

/* 设备模拟（平板/手机）：高度交给内联样式（min(预设高度, 70vh)），不加额外边框
   —— 内联样式已经带了边框和阴影，再叠一层会变成双边框 */
.device-stage.framed .preview-iframe {
  height: auto;
  flex: 0 0 auto;
}

/* 撑满模式下桌面预览铺满 stage，不再用 420px 固定高度 */
.fill-height .device-stage:not(.framed) .preview-iframe {
  height: auto;
  flex: 1 1 auto;
  min-height: 0;
}

/* ==================== 代码 ==================== */
.editor-container {
  height: 380px;
  width: 100%;
}

/* 全屏预览的 iframe 撑满弹窗 */
.code-preview-fullscreen-modal :deep(.ant-modal-body) {
  padding: 0;
}

.fullscreen-iframe {
  display: block;
  width: 100%;
  height: 78vh;
  border: none;
  background: #fff;
}
</style>
