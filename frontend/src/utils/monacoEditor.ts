/**
 * Monaco Editor 公共配置
 *
 * Monaco 体积大（约 2MB），因此这个模块只导出「函数」，不在这里顶层 import，
 * 真正的 `import('monaco-editor')` 放在 loadMonaco() 里，等组件第一次需要编辑器时才加载。
 * 这样纯文本回答（没有代码块）的页面完全不会拉取 Monaco 的 chunk。
 */

import type * as Monaco from 'monaco-editor'

/** 简写 / 别名 → Monaco 内置语言 ID */
const LANGUAGE_MAP: Record<string, string> = {
  js: 'javascript',
  mjs: 'javascript',
  cjs: 'javascript',
  ts: 'typescript',
  py: 'python',
  sh: 'shell',
  bash: 'shell',
  zsh: 'shell',
  yml: 'yaml',
  dockerfile: 'dockerfile',
  md: 'markdown',
  html5: 'html',
  vue: 'html',
  jsx: 'javascript',
  tsx: 'typescript',
  'c++': 'cpp',
  rs: 'rust',
  golang: 'go',
}

/** 把代码块里的语言标记映射成 Monaco 认识的语言 ID */
export const getMonacoLanguage = (lang?: string): string => {
  const key = (lang || '').toLowerCase().trim()
  if (!key) return 'plaintext'
  return LANGUAGE_MAP[key] || key
}

/** 编辑器统一的只读展示样式 */
export const READONLY_EDITOR_OPTIONS: Monaco.editor.IStandaloneEditorConstructionOptions = {
  theme: 'vs',
  readOnly: true,
  domReadOnly: true,
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
  automaticLayout: true,
  fontSize: 13,
  lineNumbers: 'on',
  roundedSelection: false,
  fontFamily: "'SF Mono', Consolas, Monaco, 'Courier New', monospace",
  renderWhitespace: 'selection',
  scrollbar: {
    verticalScrollbarSize: 8,
    horizontalScrollbarSize: 8,
    // 让鼠标滚轮在编辑器滚到边界时把滚动事件交还给外层页面，
    // 否则回答很长时代码块会「吃掉」滚轮，用户没法继续往下翻
    alwaysConsumeMouseWheel: false,
  },
  overviewRulerLanes: 0,
  wordWrap: 'off',
  padding: { top: 10, bottom: 10 },
}

/** 可编辑模式下的样式（第六章扩展：在线编辑 + 实时预览） */
export const EDITABLE_EDITOR_OPTIONS: Monaco.editor.IStandaloneEditorConstructionOptions = {
  ...READONLY_EDITOR_OPTIONS,
  readOnly: false,
  domReadOnly: false,
}

let monacoPromise: Promise<typeof Monaco> | null = null

/**
 * 懒加载 monaco-editor
 *
 * 返回的 Promise 会被复用（同一个 chunk 只加载一次）。
 * 加载失败时清空缓存，让下一次调用可以重试。
 */
export const loadMonaco = (): Promise<typeof Monaco> => {
  if (!monacoPromise) {
    monacoPromise = import('monaco-editor').catch((error) => {
      monacoPromise = null
      throw error
    })
  }
  return monacoPromise
}

/** 语言 → 下载文件扩展名 */
const EXTENSION_MAP: Record<string, string> = {
  html: 'html',
  css: 'css',
  javascript: 'js',
  js: 'js',
  typescript: 'ts',
  ts: 'ts',
  python: 'py',
  py: 'py',
  java: 'java',
  cpp: 'cpp',
  c: 'c',
  go: 'go',
  rust: 'rs',
  rs: 'rs',
  json: 'json',
  xml: 'xml',
  yaml: 'yaml',
  yml: 'yml',
  markdown: 'md',
  md: 'md',
  sql: 'sql',
  shell: 'sh',
  bash: 'sh',
  sh: 'sh',
}

export const getFileExtension = (language?: string): string =>
  EXTENSION_MAP[(language || '').toLowerCase()] || 'txt'

/** 语言 → 下载文件名（HTML 统一叫 index.html，更有「网页工程」的感觉） */
export const getFileName = (language?: string): string => {
  const lang = (language || '').toLowerCase()
  if (lang === 'html') return 'index.html'
  if (lang === 'css') return 'styles.css'
  if (lang === 'javascript' || lang === 'js') return 'script.js'
  if (lang === 'typescript' || lang === 'ts') return 'index.ts'
  if (lang === 'python' || lang === 'py') return 'script.py'
  if (lang === 'markdown' || lang === 'md') return 'README.md'
  return `code.${getFileExtension(lang)}`
}

/**
 * 多文件合并时用到的 HTML 标签片段
 *
 * 为什么用数组 join 而不是模板字符串：.vue 的 <script setup> 块是靠「源码文本里
 * 出现收尾 tag」来定位边界的，源码里直接写出完整标签会让 SFC 编译器提前收尾，
 * 整个组件解析失败（表现为一堆莫名其妙的 TS1005 语法错误）。
 * 这里拼出来的是运行时值，源码文本里不含该序列。
 */
export const SCRIPT_CLOSE_TAG = ['<', '/', 'script', '>'].join('')
export const STYLE_CLOSE_TAG = ['<', '/', 'style', '>'].join('')

/**
 * 触发浏览器下载（纯前端实现，不需要后端接口）
 *
 * 用 Blob + 临时 a 标签：createObjectURL 产生的地址必须 revokeObjectURL 释放，
 * 否则每次下载都会泄漏一份内存。
 */
export const downloadTextFile = (content: string, fileName: string, mime = 'text/plain') => {
  const blob = new Blob([content], { type: `${mime};charset=utf-8` })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

/** 简单防抖：用于「编辑代码 → 延迟刷新预览」，避免每敲一个字就重建 iframe */
export const debounce = <T extends (...args: never[]) => void>(fn: T, wait = 500) => {
  let timer: ReturnType<typeof setTimeout> | null = null
  const wrapped = (...args: Parameters<T>) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      timer = null
      fn(...args)
    }, wait)
  }
  wrapped.cancel = () => {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
  }
  return wrapped as T & { cancel: () => void }
}
