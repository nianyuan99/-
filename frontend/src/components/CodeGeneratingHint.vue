<template>
  <div class="code-generating-hint">
    <div class="generating-header">
      <div class="file-icon-wrapper">
        <FileTextOutlined class="file-icon" />
      </div>
      <div class="generating-info">
        <div class="file-name">
          <span>{{ fileName }}</span>
          <div class="loading-dots"><span /><span /><span /></div>
        </div>
        <div class="generating-status">正在生成代码...</div>
      </div>
    </div>
    <div class="progress-bar">
      <div class="progress-fill" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { FileTextOutlined } from '@ant-design/icons-vue'

/**
 * 代码生成中的加载提示
 *
 * 模仿 VS Code 里「正在写入文件」的观感：一个文件名 + 流动的进度条，
 * 让用户在漫长的流式生成过程中明确知道「AI 正在写代码」，而不是以为页面卡住了。
 */
const props = defineProps<{
  language?: string
}>()

const FILE_NAMES: Record<string, string> = {
  html: 'index.html',
  javascript: 'script.js',
  js: 'script.js',
  typescript: 'index.ts',
  ts: 'index.ts',
  python: 'script.py',
  java: 'Main.java',
  cpp: 'main.cpp',
  'c++': 'main.cpp',
  go: 'main.go',
  rust: 'main.rs',
  rs: 'main.rs',
  css: 'styles.css',
  json: 'data.json',
  xml: 'data.xml',
  sql: 'query.sql',
  bash: 'script.sh',
  shell: 'script.sh',
  sh: 'script.sh',
  markdown: 'README.md',
  md: 'README.md',
}

const fileName = computed(() => {
  const lang = (props.language || 'html').toLowerCase()
  return FILE_NAMES[lang] || `code.${lang}`
})
</script>

<style scoped>
.code-generating-hint {
  border: 1px solid #e6e8eb;
  border-radius: 10px;
  background: #fff;
  overflow: hidden;
  margin: 10px 0;
}

.generating-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
}

.file-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: #e8f2ff;
  flex: 0 0 auto;
}

.file-icon {
  font-size: 16px;
  color: #1677ff;
}

.generating-info {
  min-width: 0;
}

.file-name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #1f2328;
  font-family: Consolas, Monaco, 'Courier New', monospace;
}

.generating-status {
  margin-top: 2px;
  font-size: 12px;
  color: #8b949e;
}

/* 三个呼吸的小圆点，暗示「还在产出」 */
.loading-dots {
  display: inline-flex;
  gap: 3px;
}

.loading-dots span {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: #1677ff;
  animation: dot-bounce 1.2s infinite ease-in-out;
}

.loading-dots span:nth-child(2) {
  animation-delay: 0.15s;
}

.loading-dots span:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes dot-bounce {
  0%,
  60%,
  100% {
    opacity: 0.25;
    transform: translateY(0);
  }
  30% {
    opacity: 1;
    transform: translateY(-3px);
  }
}

/* 不确定进度的流动条：无法预知代码长度，所以用往复动画而不是真实百分比 */
.progress-bar {
  height: 2px;
  background: #eef1f4;
  overflow: hidden;
}

.progress-fill {
  width: 40%;
  height: 100%;
  background: linear-gradient(90deg, #91caff, #1677ff, #91caff);
  animation: progress-slide 1.6s infinite ease-in-out;
}

@keyframes progress-slide {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(350%);
  }
}
</style>
