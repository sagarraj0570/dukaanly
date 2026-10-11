import axios from 'axios'
import { useAuthStore } from '@/store/useAuthStore'

const rawBaseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
const normalizedBaseUrl = rawBaseUrl.endsWith('/api/v1')
  ? rawBaseUrl
  : `${rawBaseUrl.replace(/\/+$/, '')}/api/v1`;

export const api = axios.create({
  baseURL: normalizedBaseUrl,
})

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout()
    }
    return Promise.reject(error)
  }
)
