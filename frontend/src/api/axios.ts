import axios, { type AxiosRequestConfig } from 'axios'
import { useAuthStore } from '@/store/useAuthStore'

const rawBaseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'
export const normalizedBaseUrl = rawBaseUrl.endsWith('/api/v1')
  ? rawBaseUrl
  : `${rawBaseUrl.replace(/\/+$/, '')}/api/v1`

export const api = axios.create({
  baseURL: normalizedBaseUrl,
  withCredentials: true,
})

// Concurrency queue for handling multiple simultaneous 401s
let isRefreshing = false
let failedQueue: Array<{
  resolve: (token: string) => void
  reject: (err: unknown) => void
}> = []

export const processQueue = (error: unknown, token: string | null = null) => {
  failedQueue.forEach((promise) => {
    if (error) {
      promise.reject(error)
    } else if (token) {
      promise.resolve(token)
    }
  })
  failedQueue = []
}

export const resetRefreshQueue = () => {
  isRefreshing = false
  failedQueue = []
}

// Request interceptor: attach short-lived access token
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Custom interface to track retry state
interface RetryConfig extends AxiosRequestConfig {
  _retry?: boolean
}

// Response interceptor: queue concurrent 401s, rotate token once, and retry
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config as RetryConfig

    // Reject non-401 errors or requests missing config immediately
    if (!originalRequest || !error.response || error.response.status !== 401) {
      return Promise.reject(error)
    }

    const requestUrl = originalRequest.url || ''

    // Do not attempt token refresh for authentication lifecycle routes
    if (
      requestUrl.includes('/auth/login') ||
      requestUrl.includes('/auth/register') ||
      requestUrl.includes('/auth/refresh')
    ) {
      return Promise.reject(error)
    }

    // Single retry limit: prevent infinite retry loops on revoked/invalid credentials
    if (originalRequest._retry) {
      useAuthStore.getState().logout()
      return Promise.reject(error)
    }

    // If a refresh is already in flight, queue this request to wait for the shared new token
    if (isRefreshing) {
      return new Promise<string>((resolve, reject) => {
        failedQueue.push({ resolve, reject })
      })
        .then((newToken) => {
          originalRequest.headers = originalRequest.headers || {}
          originalRequest.headers.Authorization = `Bearer ${newToken}`
          originalRequest._retry = true
          return api(originalRequest)
        })
        .catch((err) => Promise.reject(err))
    }

    // First 401 encountered: initiate the shared refresh operation
    originalRequest._retry = true
    isRefreshing = true

    try {
      // Use clean standalone axios instance to prevent interceptor loops
      const refreshResponse = await axios.post(
        `${normalizedBaseUrl}/auth/refresh`,
        {},
        { withCredentials: true }
      )

      const { access_token } = refreshResponse.data
      if (!access_token) {
        throw new Error('Missing access_token in refresh response')
      }

      // Update store with rotated access token
      useAuthStore.getState().setToken(access_token)

      // Notify and resume all queued requests with the new token
      processQueue(null, access_token)

      // Retry the original request that triggered the refresh
      originalRequest.headers = originalRequest.headers || {}
      originalRequest.headers.Authorization = `Bearer ${access_token}`
      return api(originalRequest)
    } catch (refreshError) {
      // Refresh failed: reject all queued requests and clear client auth state
      processQueue(refreshError, null)
      useAuthStore.getState().logout()

      if (typeof window !== 'undefined' && window.location && window.location.pathname !== '/login') {
        window.location.href = '/login'
      }

      return Promise.reject(refreshError)
    } finally {
      isRefreshing = false
    }
  }
)
