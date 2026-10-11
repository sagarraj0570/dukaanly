import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CustomerOrderDetail } from './CustomerOrderDetail'
import { useAuthStore } from '@/store/useAuthStore'
import { http, HttpResponse } from 'msw'
import { server } from '../setupTests'

let queryClient: QueryClient

class MockWebSocket {
  static instances: MockWebSocket[] = []
  url: string
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  readyState = 1
  closed = false

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
    setTimeout(() => {
      if (!this.closed && this.onopen) {
        this.onopen()
      }
    }, 10)
  }

  send() {}

  close() {
    this.closed = true
    if (this.onclose) {
      this.onclose()
    }
  }

  emitMessage(data: unknown) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(data) })
    }
  }
}

beforeEach(() => {
  queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })

  useAuthStore.setState({
    token: 'mock-customer-token',
    user: {
      id: 'cust-1',
      name: 'Customer One',
      email: 'customer@example.com',
      role: 'customer'
    }
  })

  MockWebSocket.instances = []
  vi.stubGlobal('WebSocket', MockWebSocket)
})

afterEach(() => {
  MockWebSocket.instances.forEach(ws => ws.close())
  MockWebSocket.instances = []
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe('CustomerOrderDetail and Live Tracking', () => {
  it('renders order detail and displays live delivery tracking with WebSocket connection', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/customer/orders/order-1']}>
          <Routes>
            <Route path="/customer/orders/:id" element={<CustomerOrderDetail />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    // Order items and header
    await waitFor(() => {
      expect(screen.getByText('Order #order')).toBeTruthy()
      expect(screen.getByText('Test Product Details')).toBeTruthy()
    })

    // Delivery tracking container
    await waitFor(() => {
      expect(screen.getByText('Live Delivery Tracking')).toBeTruthy()
      expect(screen.getByText(/Delivery ID: delivery-1/)).toBeTruthy()
    })

    // Verify WebSocket connected with token
    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBeGreaterThan(0)
      expect(MockWebSocket.instances[0].url).toContain('ws/deliveries/delivery-1?token=mock-customer-token')
    })

    // Verify live status stages
    expect(screen.getByText('Rider Assigned')).toBeTruthy()
    expect(screen.getByText('Out for Delivery')).toBeTruthy()
  })

  it('updates live status and coordinates when WebSocket receives connection.ready and location_updated', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/customer/orders/order-1']}>
          <Routes>
            <Route path="/customer/orders/:id" element={<CustomerOrderDetail />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBeGreaterThan(0)
    })

    const ws = MockWebSocket.instances[0]

    // Send connection.ready event
    act(() => {
      ws.emitMessage({
        event: 'connection.ready',
        version: 1,
        delivery_id: 'delivery-1',
        data: {
          delivery_status: 'out_for_delivery',
          rider_id: 'rider-1',
          rider_location: {
            latitude: 12.97159,
            longitude: 77.59456,
            updated_at: new Date().toISOString()
          }
        }
      })
    })

    await waitFor(() => {
      expect(screen.getByText('12.97159')).toBeTruthy()
      expect(screen.getByText('77.59456')).toBeTruthy()
      expect(screen.getByText('Active Signal')).toBeTruthy()
    })

    // Send location_updated event
    act(() => {
      ws.emitMessage({
        event: 'delivery.location_updated',
        version: 1,
        delivery_id: 'delivery-1',
        rider_id: 'rider-1',
        timestamp: new Date().toISOString(),
        data: {
          latitude: 12.98001,
          longitude: 77.60002
        }
      })
    })

    await waitFor(() => {
      expect(screen.getByText('12.98001')).toBeTruthy()
      expect(screen.getByText('77.60002')).toBeTruthy()
    })
  })

  it('handles stale location data appropriately', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/customer/orders/order-1']}>
          <Routes>
            <Route path="/customer/orders/:id" element={<CustomerOrderDetail />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBeGreaterThan(0)
    })

    const ws = MockWebSocket.instances[0]
    // 25 minutes ago (exceeds 15-minute freshness window)
    const staleTime = new Date(Date.now() - 25 * 60 * 1000).toISOString()

    act(() => {
      ws.emitMessage({
        event: 'connection.ready',
        version: 1,
        delivery_id: 'delivery-1',
        data: {
          delivery_status: 'assigned',
          rider_id: 'rider-1',
          rider_location: {
            latitude: 12.91234,
            longitude: 77.56789,
            updated_at: staleTime
          }
        }
      })
    })

    await waitFor(() => {
      expect(screen.getByText('Last Known (Stale)')).toBeTruthy()
      expect(screen.getByText('12.91234')).toBeTruthy()
    })
  })

  it('renders waiting state when order has no delivery assigned yet', async () => {
    server.use(
      http.get('http://localhost:8000/api/v1/orders/:id', () => {
        return HttpResponse.json({
          id: 'order-no-delivery',
          customer_id: 'cust-1',
          shop_id: 'shop-1',
          status: 'confirmed',
          total_amount: 300.00,
          items: [
            {
              id: 'orderitem-1',
              product_id: 'prod-1',
              product_name: 'Test Product Details',
              unit_price: 150.00,
              quantity: 2,
              line_total: 300.00
            }
          ],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          delivery: null
        })
      })
    )

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/customer/orders/order-no-delivery']}>
          <Routes>
            <Route path="/customer/orders/:id" element={<CustomerOrderDetail />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('Waiting for Delivery Assignment')).toBeTruthy()
      expect(screen.getByText(/Your order is currently being prepared by the shop/)).toBeTruthy()
    })

    // No WebSocket connection should be initiated when delivery is null
    expect(MockWebSocket.instances.length).toBe(0)
  })

  it('cleans up WebSocket on component unmount', async () => {
    const { unmount } = render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/customer/orders/order-1']}>
          <Routes>
            <Route path="/customer/orders/:id" element={<CustomerOrderDetail />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1)
    })

    const ws = MockWebSocket.instances[0]
    expect(ws.closed).toBe(false)

    unmount()

    expect(ws.closed).toBe(true)
  })
})
