<template>
  <div class="chat-test-page">
    <a-card title="Chat 功能测试" :bordered="false">
      <a-form layout="vertical">
        <a-form-item label="选择模型">
          <a-select
            v-model:value="formData.model"
            placeholder="请选择模型"
            style="width: 100%"
            :options="modelOptions"
            show-search
          />
        </a-form-item>
        <a-form-item label="输入消息">
          <a-textarea
            v-model:value="formData.message"
            placeholder="请输入您的消息..."
            :rows="4"
            @keydown.ctrl.enter="sendMessage"
          />
        </a-form-item>
        <a-form-item>
          <a-space>
            <a-button
              type="primary"
              :loading="isStreaming"
              @click="sendMessage"
              :disabled="!formData.model || !formData.message"
            >
              {{ isStreaming ? '生成中...' : '发送消息 (Ctrl+Enter)' }}
            </a-button>
            <a-button @click="clearChat" :disabled="isStreaming">清空对话</a-button>
          </a-space>
        </a-form-item>
      </a-form>
      <a-divider>对话记录</a-divider>
      <div class="chat-messages" ref="messagesContainer">
        <div v-for="(msg, index) in messages" :key="index" class="message-item" :class="msg.role">
          <div class="message-header">
            <span class="role-tag">{{ msg.role === 'user' ? '👤 用户' : '🤖 AI' }}</span>
            <span class="model-tag" v-if="msg.model">{{ msg.model }}</span>
          </div>
          <div class="message-content">
            <div v-if="msg.role === 'assistant'" v-html="renderMarkdown(msg.content)"></div>
            <div v-else>{{ msg.content }}</div>
          </div>
          <div class="message-meta" v-if="msg.tokens || msg.cost || msg.time">
            <span v-if="msg.tokens">Tokens: {{ msg.tokens }}</span>
            <span v-if="msg.cost">Cost: ${{ msg.cost.toFixed(6) }}</span>
            <span v-if="msg.time">Time: {{ msg.time }}ms</span>
          </div>
        </div>
        <div v-if="isStreaming" class="streaming-indicator">
          <a-spin size="small" /> 生成中...
        </div>
        <a-empty v-if="messages.length === 0 && !isStreaming" description="暂无对话记录" />
      </div>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { message as antMessage } from 'ant-design-vue'
import { marked } from 'marked'
import { API_BASE_URL } from '@/config/env'

interface Message {
  role: 'user' | 'assistant'
  content: string
  model?: string
  tokens?: number
  cost?: number
  time?: number
}

const formData = ref({
  model: 'deepseek/deepseek-chat',
  message: '',
})

// 模型选项（与后端 SUPPORTED_MODELS 保持一致，另含实测可用的免费模型）
const modelOptions = [
  { value: 'deepseek/deepseek-chat', label: 'DeepSeek Chat' },
  { value: 'openai/gpt-4o', label: 'OpenAI GPT-4o' },
  { value: 'openai/gpt-4o-mini', label: 'OpenAI GPT-4o Mini' },
  { value: 'anthropic/claude-3.5-sonnet', label: 'Claude 3.5 Sonnet' },
  { value: 'anthropic/claude-3-opus', label: 'Claude 3 Opus' },
  { value: 'google/gemini-pro-1.5', label: 'Gemini Pro 1.5' },
  { value: 'meta-llama/llama-3.1-70b-instruct', label: 'Llama 3.1 70B' },
  { value: 'qwen/qwen-2.5-72b-instruct', label: '通义千问 Qwen 2.5 72B' },
  { value: 'nvidia/nemotron-3.5-lightning:free', label: 'NVIDIA Nemotron 3.5 (免费可用)' },
]

const messages = ref<Message[]>([])
const isStreaming = ref(false)
const messagesContainer = ref<HTMLElement>()
const currentConversationId = ref<string | null>(null)

// 渲染 Markdown
const renderMarkdown = (content: string) => {
  return marked(content)
}

// 滚动到底部
const scrollToBottom = () => {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

// 发送消息
const sendMessage = async () => {
  if (!formData.value.model || !formData.value.message || isStreaming.value) {
    return
  }

  const userMessage = formData.value.message
  const model = formData.value.model

  // 添加用户消息
  messages.value.push({ role: 'user', content: userMessage })
  formData.value.message = ''
  scrollToBottom()
  isStreaming.value = true

  // 创建 AI 消息占位符
  const aiMessage: Message = { role: 'assistant', content: '', model: model }
  messages.value.push(aiMessage)

  try {
    // 调用 SSE 接口
    const urlParams = new URLSearchParams({ prompt: userMessage, model: model })
    const response = await fetch(`${API_BASE_URL}/test/ai/stream?${urlParams}`, {
      method: 'POST',
      credentials: 'include',
    })

    if (!response.ok || !response.body) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.trim() || !line.startsWith('data:')) continue
        const jsonStr = line.substring(5).trim()
        if (jsonStr === '[DONE]' || !jsonStr) continue

        try {
          const data = JSON.parse(jsonStr)
          if (data.fullContent !== undefined && data.fullContent !== '') {
            const lastMsg = messages.value[messages.value.length - 1]
            if (lastMsg && lastMsg.role === 'assistant') {
              lastMsg.content = data.fullContent
            }
            scrollToBottom()
          }
          if (data.done) {
            const lastMsg = messages.value[messages.value.length - 1]
            if (lastMsg && lastMsg.role === 'assistant') {
              lastMsg.tokens = (data.inputTokens || 0) + (data.outputTokens || 0)
              lastMsg.cost = data.cost || 0
              lastMsg.time = data.responseTimeMs || 0
            }
          }
        } catch (e) {
          console.error('解析 SSE 数据失败:', jsonStr, e)
        }
      }
    }
    antMessage.success('消息发送成功')
  } catch (error) {
    console.error('发送消息失败:', error)
    antMessage.error('发送消息失败: ' + (error as Error).message)
    messages.value.pop()
  } finally {
    isStreaming.value = false
  }
}

// 清空对话
const clearChat = () => {
  messages.value = []
  currentConversationId.value = null
  antMessage.success('对话已清空')
}
</script>

<style scoped>
.chat-test-page {
  max-width: 900px;
  margin: 0 auto;
}

.chat-messages {
  max-height: 600px;
  overflow-y: auto;
  padding: 8px;
}

.message-item {
  margin-bottom: 16px;
  padding: 12px;
  border-radius: 8px;
  background: #f5f5f5;
}

.message-item.user {
  background: #e6f4ff;
}

.message-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.role-tag {
  font-weight: bold;
}

.model-tag {
  font-size: 12px;
  color: #888;
  background: #fff;
  padding: 2px 8px;
  border-radius: 4px;
}

.message-content {
  line-height: 1.6;
  word-break: break-word;
}

.message-meta {
  margin-top: 8px;
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #999;
}

.streaming-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #999;
  padding: 8px;
}
</style>
