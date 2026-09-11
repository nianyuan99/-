/**
 * sockjs-client 类型声明
 *
 * sockjs-client 自身不带类型定义，官方维护的 @types/sockjs-client 又和
 * 当前 TS 版本配合不佳，这里只声明本项目实际用到的部分，保持最小面积。
 */
declare module 'sockjs-client' {
  type SockJSReadyState = 0 | 1 | 2 | 3

  class SockJS {
    constructor(url: string, protocols?: string | string[], options?: Record<string, unknown>)

    static readonly CONNECTING: 0
    static readonly OPEN: 1
    static readonly CLOSING: 2
    static readonly CLOSED: 3

    readonly readyState: SockJSReadyState
    readonly url: string
    readonly protocol: string
    readonly transport: string

    onopen: (() => void) | null
    onmessage: ((event: { data: string }) => void) | null
    onclose: ((event: { code: number; reason: string; wasClean: boolean }) => void) | null

    send(data: string): void
    close(code?: number, reason?: string): void
  }

  export default SockJS
}
