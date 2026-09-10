/**
 * SSE 客户端工具类
 * 用于处理 POST 请求的流式响应
 *
 * 浏览器原生的 EventSource 只支持 GET，而流式接口是 POST，
 * 因此这里用 fetch + ReadableStream 手动解析 SSE 协议。
 */

export interface SSEOptions {
  onMessage: (data: any) => void
  onError?: (error: Error) => void
  onComplete?: () => void
}

export interface SSEHandle {
  close: () => void
}

export async function createPostSSE(
  url: string,
  body: any,
  options: SSEOptions,
): Promise<SSEHandle> {
  // 用 AbortController 才能真正中断底层连接；
  // 只调用 reader.cancel() 时，服务端不一定能及时感知客户端已经离开
  const controller = new AbortController()

  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(body),
    signal: controller.signal,
  })

  // 后端异常时返回的是统一 BaseResponse 结构（HTTP 200），这里先兜底解析出错误信息
  // 后端异常时返回的是统一 BaseResponse 结构（HTTP 200 + JSON），
  // 如果不识别这种情况，业务错误（未登录、限流等）会被静默吞掉，这里先兜底抛错。
  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    const errorBody = await response.json().catch(() => null)
    const errorMessage = errorBody?.message || `请求失败（code=${errorBody?.code ?? 'unknown'}）`
    throw new Error(errorMessage)
  }

  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
  if (!response.body) throw new Error('Response body is null')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const processStream = async () => {
    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          options.onComplete?.()
          break
        }

        // stream: true 能处理跨 chunk 的多字节字符（如中文可能被拆到两个 chunk）
        buffer += decoder.decode(value, { stream: true })

        // SSE 格式：每个事件以 \n\n 分隔
        const parts = buffer.split('\n\n')
        // 最后一段可能是不完整的事件，留到下一个 chunk 再拼
        buffer = parts.pop() || ''

        for (const part of parts) {
          if (!part.trim()) continue
          const lines = part.split('\n')
          for (const line of lines) {
            const trimmed = line.trim()
            if (!trimmed.startsWith('data:')) continue

            const jsonStr = trimmed.substring(5).trim()
            if (!jsonStr) continue

            try {
              options.onMessage(JSON.parse(jsonStr))
            } catch {
              console.warn('JSON解析失败，等待更多数据')
            }
          }
        }
      }
    } catch (error: any) {
      // 主动调用 close() 时 reader.read() 会抛错，这种情况不再上报
      if (error?.name === 'AbortError') return
      options.onError?.(error)
    }
  }

  processStream()

  return {
    close: () => {
      // 先中断请求（让服务端尽快感知断开），再取消读取器
      controller.abort()
      reader.cancel().catch(() => {})
    },
  }
}
