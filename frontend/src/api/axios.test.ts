import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '@/setupTests'
import { api, resetRefreshQueue } from './axios'
import { useAuthStore } from '@/store/useAuthStore'

describe('Frontend API Client & Token Refresh Interceptors', () => {
  const mockUser = {
    id: 'user-123',
    name: 'Test Customer',
    email: 'customer@dukaanly.test',
    role: 'customer' as const,
  }

  beforeEach(() => {
    resetRefreshQueue()
    useAuthStore.setState({
      token: 'initial-expired-token',
      user: mockUser,
    })
  })

  afterEach(() => {
    resetRefreshQueue()
    useAuthStore.setState({ token: null, user: null })
  })

  it('attaches the active Bearer token to outgoing requests', async () => {
    useAuthStore.setState({ token: 'active-valid-token' })

    server.use(
      http.get('http://localhost:8000/api/v1/test-headers', ({ request }) => {
        return HttpResponse.json({
          authHeader: request.headers.get('authorization'),
        })
      })
    )

    const response = await api.get('/test-headers')
    expect(response.status).toBe(200)
    expect(response.data.authHeader).toBe('Bearer active-valid-token')
  })

  it('triggers a single refresh and retries the original request on 401', async () => {
    let attempts = 0
    let refreshCalls = 0

    server.use(
      http.post('http://localhost:8000/api/v1/auth/refresh', () => {
        refreshCalls++
        return HttpResponse.json({
          access_token: 'fresh-rotated-token',
          refresh_token: 'new-refresh-token',
          token_type: 'bearer',
        })
      }),
      http.get('http://localhost:8000/api/v1/test-protected', ({ request }) => {
        attempts++
        if (attempts === 1) {
          return HttpResponse.json({ detail: 'Token expired' }, { status: 401 })
        }
        return HttpResponse.json({
          success: true,
          authHeader: request.headers.get('authorization'),
        })
      })
    )

    const result = await api.get('/test-protected')

    expect(refreshCalls).toBe(1)
    expect(attempts).toBe(2)
    expect(result.status).toBe(200)
    expect(result.data.success).toBe(true)
    expect(result.data.authHeader).toBe('Bearer fresh-rotated-token')
    expect(useAuthStore.getState().token).toBe('fresh-rotated-token')
  })

  it('queues concurrent 401 requests and executes exactly ONE refresh operation', async () => {
    let refreshCount = 0
    let c1Attempts = 0
    let c2Attempts = 0
    let c3Attempts = 0

    server.use(
      http.post('http://localhost:8000/api/v1/auth/refresh', async () => {
        refreshCount++
        // Small delay to simulate network latency
        await new Promise((res) => setTimeout(res, 30))
        return HttpResponse.json({
          access_token: 'shared-rotated-token',
          refresh_token: 'new-shared-refresh',
          token_type: 'bearer',
        })
      }),
      http.get('http://localhost:8000/api/v1/test-queue-1', ({ request }) => {
        c1Attempts++
        if (c1Attempts === 1) {
          return HttpResponse.json({ detail: 'Expired' }, { status: 401 })
        }
        return HttpResponse.json({ endpoint: 1, auth: request.headers.get('authorization') })
      }),
      http.get('http://localhost:8000/api/v1/test-queue-2', ({ request }) => {
        c2Attempts++
        if (c2Attempts === 1) {
          return HttpResponse.json({ detail: 'Expired' }, { status: 401 })
        }
        return HttpResponse.json({ endpoint: 2, auth: request.headers.get('authorization') })
      }),
      http.get('http://localhost:8000/api/v1/test-queue-3', ({ request }) => {
        c3Attempts++
        if (c3Attempts === 1) {
          return HttpResponse.json({ detail: 'Expired' }, { status: 401 })
        }
        return HttpResponse.json({ endpoint: 3, auth: request.headers.get('authorization') })
      })
    )

    // Fire 3 simultaneous requests that all hit 401 initially
    const [res1, res2, res3] = await Promise.all([
      api.get('/test-queue-1'),
      api.get('/test-queue-2'),
      api.get('/test-queue-3'),
    ])

    // Exactly one refresh was called across all concurrent requests
    expect(refreshCount).toBe(1)

    // All 3 requests were retried and succeeded with the shared new token
    expect(res1.status).toBe(200)
    expect(res2.status).toBe(200)
    expect(res3.status).toBe(200)
    expect(res1.data.auth).toBe('Bearer shared-rotated-token')
    expect(res2.data.auth).toBe('Bearer shared-rotated-token')
    expect(res3.data.auth).toBe('Bearer shared-rotated-token')
  })

  it('clears state and rejects queued requests on refresh failure', async () => {
    let refreshAttempts = 0

    server.use(
      http.post('http://localhost:8000/api/v1/auth/refresh', () => {
        refreshAttempts++
        return HttpResponse.json({ detail: 'Refresh token revoked' }, { status: 401 })
      }),
      http.get('http://localhost:8000/api/v1/test-fail-1', () => {
        return HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 })
      }),
      http.get('http://localhost:8000/api/v1/test-fail-2', () => {
        return HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 })
      })
    )

    const p1 = api.get('/test-fail-1')
    const p2 = api.get('/test-fail-2')

    await expect(p1).rejects.toThrow()
    await expect(p2).rejects.toThrow()

    // Refresh was attempted once
    expect(refreshAttempts).toBe(1)

    // Auth state was wiped clean
    expect(useAuthStore.getState().token).toBeNull()
    expect(useAuthStore.getState().user).toBeNull()
  })

  it('prevents infinite retry loops by rejecting requests already marked _retry', async () => {
    let refreshCalls = 0

    server.use(
      http.post('http://localhost:8000/api/v1/auth/refresh', () => {
        refreshCalls++
        return HttpResponse.json({
          access_token: 'new-token-that-is-still-rejected',
          refresh_token: 'next-refresh',
        })
      }),
      // Endpoint stubbornly returns 401 even after retry
      http.get('http://localhost:8000/api/v1/test-stubborn', () => {
        return HttpResponse.json({ detail: 'Forbidden permanently' }, { status: 401 })
      })
    )

    await expect(api.get('/test-stubborn')).rejects.toThrow()

    // Refresh called once on initial 401, but NOT on retried 401
    expect(refreshCalls).toBe(1)
    expect(useAuthStore.getState().token).toBeNull()
  })

  it('never attempts refresh on auth lifecycle routes (/auth/login, /auth/register, /auth/refresh)', async () => {
    let refreshCalls = 0

    server.use(
      http.post('http://localhost:8000/api/v1/auth/refresh', () => {
        refreshCalls++
        return HttpResponse.json({ access_token: 'abc' })
      }),
      http.post('http://localhost:8000/api/v1/auth/login', () => {
        return HttpResponse.json({ detail: 'Invalid credentials' }, { status: 401 })
      }),
      http.post('http://localhost:8000/api/v1/auth/register', () => {
        return HttpResponse.json({ detail: 'Unauthorized registration' }, { status: 401 })
      })
    )

    await expect(api.post('/auth/login', { email: 'test@dukaanly.test', password: 'bad' })).rejects.toThrow()
    await expect(api.post('/auth/register', { email: 'new@dukaanly.test' })).rejects.toThrow()

    expect(refreshCalls).toBe(0)
  })
})
