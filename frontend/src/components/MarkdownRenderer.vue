<template>
  <div class="markdown-renderer">
    <!-- 混合渲染：普通文本段和代码块交替显示，代码块用可预览的卡片而不是纯 <pre> -->
    <template v-for="(segment, index) in segments" :key="index">
      <div
        v-if="segment.type === 'text'"
        class="markdown-body"
        :class="{ 'markdown-body-streaming': segment.streaming }"
        v-html="segment.html"
      ></div>
      <CodePreview
        v-else
        :code-block="segment.block"
        :code-blocks="segment.blocks"
        :is-code-mode="codeMode"
        :editable="editableCode"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import CodePreview, { type CodeBlock } from '@/components/CodePreview.vue'

/**
 * Markdown 渲染组件
 *
 * 用于展示模型返回的富文本内容（代码块、列表、表格等）。
 *
 * 与「整个丢给 marked」的朴素做法不同，这里先把内容按 ``` 代码块切成
 * 文本段 / 代码段两类：
 *   - 文本段仍然交给 marked 转 HTML；
 *   - 代码段交给 CodePreview（Monaco 高亮 + iframe 沙箱预览 + 复制/下载）。
 *
 * 分段只在 content 变化时重算一次（computed 缓存），流式追加时逐段渲染，
 * 不会因为重渲染把已经存在的代码块推翻重建 —— 否则 Monaco 会不停闪。
 */
interface Props {
  content?: string
  /** 代码模式：HTML 代码块默认直接展示预览效果 */
  codeMode?: boolean
  /** 代码块允许编辑并实时刷新预览（第六章扩展） */
  editableCode?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  content: '',
  codeMode: false,
  editableCode: false,
})

/** 未闭合代码块最多当文本渲染的字符数，超过就折叠，避免流式把半截代码刷屏 */
const MAX_UNCLOSED_PREVIEW = 2000

/** 已闭合的 Markdown 代码块，或到文本结尾仍未闭合的代码块 */
const CODE_BLOCK_PATTERN = /```([^\n`]*)\n([\s\S]*?)(?:```|$)/g

/** 看起来像 HTML 的片段：用于给「没写语言标记」却明显是 HTML 的代码块补上语言 */
const HTML_HINT_PATTERN = /<!DOCTYPE\s+html|<html[\s>]|<head[\s>]|<body[\s>]|<div[\s>]|<script[\s>]|<style[\s>]/i

interface TextSegment {
  type: 'text'
  html: string
  /** 是否为「流式未完成」的尾巴（用于淡化样式） */
  streaming: boolean
}

interface CodeSegment {
  type: 'code'
  block: CodeBlock
  /** 多代码块合并预览用（暂未使用，保留给 MarkdownRenderer 级别的合并） */
  blocks?: CodeBlock[]
}

type Segment = TextSegment | CodeSegment

const looksLikeHtml = (code: string) => HTML_HINT_PATTERN.test(code)

const renderText = (text: string) => {
  if (!text.trim()) return ''
  return marked.parse(text, { async: false }) as string
}

const segments = computed<Segment[]>(() => {
  const content = props.content
  if (!content) return []

  // 正则带 g 标志，是有状态对象，每次重算都要重置 lastIndex
  CODE_BLOCK_PATTERN.lastIndex = 0

  const result: Segment[] = []
  let cursor = 0
  let match: RegExpExecArray | null

  const pushText = (text: string, streaming = false) => {
    if (!text) return
    const html = renderText(text)
    if (!html) return
    result.push({ type: 'text', html, streaming })
  }

  while ((match = CODE_BLOCK_PATTERN.exec(content)) !== null) {
    const full = match[0]
    const rawLanguage = match[1] ?? ''
    const code = match[2] ?? ''
    // 正则的收尾 ``` 是可选分支（用于兜住流式中未闭合的代码块），
    // 所以这里要判断「匹配是否真的以收尾反引号结束」，而不是看代码正文：
    // 正文本身以 ``` 结尾的情况（比如 AI 在教写 Markdown）不能被误判成已闭合。
    const closed = full.endsWith('```') && full.length > code.length + 3

    // 代码块之前的正文
    pushText(content.slice(cursor, match.index))

    if (!closed) {
      // 流式生成到一半、还没出现收尾反引号：
      // 这一轮先按普通文本渲染，等闭合后再切成代码卡片，避免半截代码用 Monaco 反复重建
      const preview =
        code.length > MAX_UNCLOSED_PREVIEW
          ? `${code.slice(0, MAX_UNCLOSED_PREVIEW)}\n…（代码仍在生成中）`
          : code
      const tail = `\`\`\`${rawLanguage}\n${preview}`
      pushText(tail, true)
      cursor = content.length
      break
    }

    const language = (rawLanguage || '').trim().toLowerCase()
    const block: CodeBlock = {
      language: language || (looksLikeHtml(code) ? 'html' : 'text'),
      code,
    }
    if (block.language === 'html') {
      // 后端 sanitize 目前是原样返回；这里保持一致，安全由 iframe sandbox 负责
      block.sanitizedHtml = code
    }
    result.push({ type: 'code', block })

    cursor = match.index + full.length
  }

  // 最后一个代码块之后的正文
  pushText(content.slice(cursor))

  return result
})
</script>

<style scoped>
.markdown-renderer {
  font-size: 14px;
  color: #1f2328;
}

.markdown-body {
  line-height: 1.7;
  word-break: break-word;
}

.markdown-body :deep(p) {
  margin: 0 0 10px;
}

.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(pre) {
  background: #f6f8fa;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  font-size: 13px;
}

.markdown-body :deep(code) {
  background: #f6f8fa;
  padding: 2px 5px;
  border-radius: 4px;
  font-size: 13px;
  font-family: Consolas, Monaco, 'Courier New', monospace;
}

.markdown-body :deep(pre code) {
  background: transparent;
  padding: 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 22px;
  margin: 0 0 10px;
}

.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin-bottom: 10px;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid #d0d7de;
  padding: 6px 10px;
  text-align: left;
}

.markdown-body :deep(th) {
  background: #f6f8fa;
}

.markdown-body :deep(blockquote) {
  margin: 0 0 10px;
  padding-left: 12px;
  border-left: 3px solid #d0d7de;
  color: #656d76;
}

/* 未闭合（流式中）的代码块：淡化一点，和已完成的内容区分开 */
.markdown-body-streaming {
  color: #6b7280;
}
</style>
