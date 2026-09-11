import './assets/main.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'

import '@/access'

import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'

// ECharts：测试报告页的雷达图 / 柱状图使用，注册到全局属性便于任意组件取用
import * as echarts from 'echarts'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(Antd)

app.config.globalProperties.$echarts = echarts

app.mount('#app')
