/**
 * WebSocket 客户端工具类
 *
 * 与后端约定：连接 `${backendBaseUrl}/ws`（SockJS 端点），
 * 在其上跑 STOMP 协议订阅 `/topic/task/{taskId}` 接收批量测试进度。
 * 后端没有部署 spring-websocket，SockJS + STOMP 协议由 Python 侧手写实现，
 * 但协议一致，所以这里用的还是标准写法：sockjs-client + @stomp/stompjs。
 *
 * 注意：SockJS 的握手请求需要带上会话 Cookie（跨端口同站，浏览器会自动带），
 * 因此后端能识别当前登录用户，只把进度推给任务的归属者。
 *
 * ⚠️ 为什么不用 `new SockJS(...) as any` 直接交给 stompjs（踩过的坑）：
 * SockJS 是「消息级」协议，它会先把 WebSocket 帧解析掉，只把消息体交给 onmessage；
 * 而 stompjs 拿到 onmessage 的消息后是直接丢给 STOMP 解析器的。
 * 于是 stompjs 收到的是 `["CONNECTED\nversion:1.2\n\n\u0000"]` 这样的 SockJS 帧，
 * 解析不出来 → CONNECTED 永远处理不到 → onConnect 不触发 → 订阅静默失败
 * （表现：进度条一直靠轮询兜底，WebSocket 白连）。
 * 正确的做法是把 SockJS 底层那条 WebSocket 透明代理给 stompjs：
 * 出站按 SockJS 规范包成 JSON 数组，入站把数组拆回单条 STOMP 帧。
 */

import { Client, type IMessage, type StompSubscription } from '@stomp/stompjs'
import SockJS from 'sockjs-client'
import { BACKEND_BASE_URL } from '@/config/env'

export interface WebSocketClientOptions {
  /** 连接成功回调（此时才能安全订阅） */
  onConnect?: () => void
  /** 收到订阅消息回调 */
  onMessage?: (topic: string, message: unknown) => void
  /** 连接断开回调 */
  onDisconnect?: () => void
  /** STOMP 协议层错误回调 */
  onError?: (error: string) => void
}

/**
 * stompjs 对 WebSocket 的最小要求
 *
 * 只要 onopen / onmessage / onclose / onerror 能挂上回调、send / close 可用就够。
 * 这里刻意不实现完整 WebSocket 接口（那些接口有几十个只读字段），
 * 因此用这个精简类型来表达代理对象，而不是硬凑成 DOM 的 WebSocket 类型。
 */
interface StompSocketLike {
  onopen: ((event: Event) => void) | null
  onmessage: ((event: { data: string }) => void) | null
  onclose: ((event: { code: number; reason: string; wasClean: boolean }) => void) | null
  onerror: ((event: Event) => void) | null
  send(data: string): void
  close(): void
}

/**
 * 构造一个「SockJS 门面 ↔ STOMP」的 WebSocket 代理
 *
 * 为什么不直接把 SockJS 实例当 WebSocket 交给 stompjs：
 * SockJS 是「消息级」协议，它把 `["CONNECTED\n…\u0000"]` 这样的帧解析后，
 * 只把 STOMP 帧文本交给 onmessage；而 stompjs 拿到消息体后会直接丢给 STOMP 解析器。
 * 这样其实能跑通 STOMP 语义，但 stompjs 还会去读写 readyState / url 等字段，
 * 且 SockJS 的 'o'（连接打开）、'h'（心跳）帧会被误当成 STOMP 数据。
 *
 * 所以这里做一层薄代理：把 STOMP 帧透传给 SockJS 发送（SockJS 会自动按协议分包），
 * 入站时把 SockJS 的控制帧过滤掉，只把 STOMP 帧交给 stompjs。
 * 连接建立（收到 SockJS 的 'o' 帧）后才触发 onopen，保证 stompjs 发出 CONNECT 时链路已就绪。
 */
/**
 * 构造一个「SockJS 门面 ↔ STOMP」的 WebSocket 代理（同步返回）
 *
 * 为什么要这层代理：
 * SockJS 是「消息级」协议，会把 `["CONNECTED\n…\u0000"]` 这种帧解析后只把消息体交给 onmessage，
 * 同时还会推 'o'（连接打开）与 'h'（心跳）这类控制帧；而 stompjs 期望拿到的是
 * 标准 WebSocket，直接吃 SockJS 实例会把控制帧当成 STOMP 数据。
 *
 * 关键点：stompjs 的 webSocketFactory **不会 await 返回值**，
 * 所以这里必须同步把代理对象交出去，再由代理在 SockJS 真正打开后回调 onopen。
 * 在 onopen 之前到达的 SockJS 控制帧会被忽略（'o' / 'h' 本来也不是 STOMP 数据）。
 */
function createSockJsWebSocketProxy(sockjs: SockJS): StompSocketLike {
  const proxy: StompSocketLike = {
    onopen: null,
    onmessage: null,
    onclose: null,
    onerror: null,
    send(data: string) {
      // STOMP 帧交给 SockJS 门面发送：sockjs-client 负责按传输协议打包（WebSocket 下是 JSON 数组）
      sockjs.send(data)
    },
    close() {
      sockjs.close()
    },
  }

  let opened = false
  const notifyOpen = () => {
    if (opened) {
      return
    }
    opened = true
    proxy.onopen?.(new Event('open'))
  }

  sockjs.onmessage = (event: { data: string }) => {
    const payload = typeof event.data === 'string' ? event.data : ''
    if (!payload) {
      return
    }
    // 'o'：SockJS 连接打开帧；'h'：心跳帧；'c[…]'：关闭帧 —— 都不是 STOMP 数据
    if (payload === 'o') {
      notifyOpen()
      return
    }
    if (payload === 'h' || payload.startsWith('c[')) {
      return
    }
    if (!opened) {
      // 还没通知 onopen（STOMP 尚未开始握手），此时不应有业务消息
      return
    }
    try {
      proxy.onmessage?.({ data: payload })
    } catch (error) {
      console.error('STOMP 帧处理异常', error)
    }
  }

  sockjs.onopen = () => {
    // SockJS 的 onopen 早于 'o' 帧到达；真正的就绪信号统一由 notifyOpen 发出
  }

  sockjs.onclose = (event: { code: number; reason: string }) => {
    proxy.onclose?.({
      code: event.code,
      reason: event.reason,
      // SockJS 的关闭事件里没有标准 WebSocket 的 wasClean 字段，
      // 正常关闭码 1000 即视作干净关闭
      wasClean: event.code === 1000,
    })
  }

  // 兜底：个别实现可能不发 'o' 帧，用轮询确认 SockJS 已打开后补一次通知
  const openWatcher = window.setInterval(() => {
    if (sockjs.readyState === SockJS.OPEN) {
      notifyOpen()
      window.clearInterval(openWatcher)
    }
  }, 50)

  return proxy
}

export class WebSocketClient {
  private client: Client | null = null

  private subscriptions = new Map<string, StompSubscription>()

  /** 待订阅的主题：连接尚未建立时先缓存，连接成功后统一订阅 */
  private pendingTopics = new Set<string>()

  private readonly baseUrl: string

  private readonly options: WebSocketClientOptions

  constructor(baseUrl: string = BACKEND_BASE_URL, options: WebSocketClientOptions = {}) {
    this.baseUrl = baseUrl
    this.options = options
  }

  /** 是否已连接 */
  get connected(): boolean {
    return Boolean(this.client?.connected)
  }

  /**
   * 建立连接
   *
   * reconnectDelay 交给 stompjs 自己做断线重连：
   * 批量测试可能跑几分钟，网络抖动或后端重启后能自动恢复订阅。
   */
  connect(): void {
    if (this.client) {
      return
    }

    this.client = new Client({
      // stompjs 不会 await webSocketFactory 的返回值，所以这里同步建立 SockJS 连接并返回代理，
      // 由代理在链路真正就绪后回调 onopen，STOMP 才会发出 CONNECT
      webSocketFactory: () => {
        const sockjs = new SockJS(`${this.baseUrl}/ws`)
        return createSockJsWebSocketProxy(sockjs) as unknown as WebSocket
      },
      reconnectDelay: 5000,
      heartbeatIncoming: 10000,
      heartbeatOutgoing: 10000,
      onConnect: () => {
        // 断线重连后需要重新订阅（stompjs 不会自动恢复）
        this.subscriptions.clear()
        const topics = Array.from(this.pendingTopics)
        this.pendingTopics.clear()
        topics.forEach((topic) => this.subscribe(topic))
        this.options.onConnect?.()
      },
      onStompError: (frame) => {
        const errorText = frame.headers['message'] ?? 'STOMP 协议错误'
        console.error('STOMP 错误:', errorText, frame.body)
        this.options.onError?.(errorText)
      },
      onWebSocketClose: () => {
        this.options.onDisconnect?.()
      },
    })

    this.client.activate()
  }

  /**
   * 订阅主题
   *
   * 连接还没建立时先把主题记下来，等 onConnect 里再真正订阅，
   * 避免调用方必须先判断 connected 才能订阅（很容易漏掉首次订阅）。
   */
  subscribe(topic: string): void {
    this.pendingTopics.add(topic)

    if (!this.client || !this.client.connected) {
      return
    }
    if (this.subscriptions.has(topic)) {
      return
    }

    const subscription = this.client.subscribe(topic, (message: IMessage) => {
      let parsed: unknown = message.body
      try {
        parsed = JSON.parse(message.body)
      } catch {
        // 非 JSON 消息（例如心跳）原样透传
      }
      this.options.onMessage?.(topic, parsed)
    })
    this.subscriptions.set(topic, subscription)
  }

  /** 取消订阅某个主题 */
  unsubscribe(topic: string): void {
    this.pendingTopics.delete(topic)
    const subscription = this.subscriptions.get(topic)
    if (subscription) {
      subscription.unsubscribe()
      this.subscriptions.delete(topic)
    }
  }

  /** 断开连接并清空所有订阅（页面卸载时调用） */
  disconnect(): void {
    this.pendingTopics.clear()
    this.subscriptions.clear()
    this.client?.deactivate()
    this.client = null
  }
}

