import axios from 'axios'
import { message } from 'ant-design-vue'
import { API_BASE_URL } from '@/config/env'

// 创建 Axios 实例
const myAxios = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
  withCredentials: true,
})

// 全局请求拦截器
myAxios.interceptors.request.use(
  function (config) {
    // Do something before request is sent
    return config
  },
  function (error) {
    // Do something with request error
    return Promise.reject(error)
  },
)

// 全局响应拦截器
myAxios.interceptors.response.use(
  function (response) {
    const { data } = response
    // 未登录
    if (data.code === 40100) {
      // 不是获取用户信息的请求，并且用户目前不是已经在用户登录页面，则跳转到登录页面
      if (
        !response.request.responseURL.includes('user/get/login') &&
        !window.location.pathname.includes('/user/login')
      ) {
        message.warning('请先登录')
        window.location.href = `/user/login?redirect=${window.location.href}`
      }
    }
    return response
  },
  function (error) {
    // Any status codes that falls outside the range of 2xx cause this function to trigger
    // Do something with request error
    // 处理 FastAPI 参数校验错误（422），给用户友好提示
    if (error.response?.status === 422) {
      const detail = error.response.data?.detail
      let msg = '请求参数错误'
      if (Array.isArray(detail) && detail.length > 0) {
        const first = detail[0]
        const field = first.loc?.[first.loc.length - 1] ?? ''
        msg = `${field}: ${first.msg}`
      } else if (typeof detail === 'string') {
        msg = detail
      }
      message.error(msg)
    } else if (!error.response) {
      message.error('网络异常，请检查后端服务是否启动')
    }
    return Promise.reject(error)
  },
)

export default myAxios
