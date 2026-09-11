import type * as echarts from 'echarts'

declare module 'vue' {
  interface ComponentCustomProperties {
    /** 全局注册的 ECharts 实例（见 main.ts） */
    $echarts: typeof echarts
  }
}

export {}
