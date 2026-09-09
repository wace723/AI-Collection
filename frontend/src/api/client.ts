import axios from 'axios'
import { message } from 'antd'
import { getToken, clearToken } from '../utils/auth'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE ?? '/api',
  timeout: 10000,
})

// 请求拦截器：注入 JWT
client.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：401 跳登录，其他错误统一提示
client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      clearToken()
      // 跳登录页（避免在登录页循环跳转）
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    } else {
      const msg = error.response?.data?.detail || error.message || '请求失败'
      message.error(msg)
    }
    return Promise.reject(error)
  },
)

export default client
