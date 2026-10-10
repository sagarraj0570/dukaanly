import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RiderDeliveryDetail } from './RiderDeliveryDetail'
import { http, HttpResponse } from 'msw'
import { server } from '../setupTests'

let queryClient: QueryClient

beforeEach(() => {
  queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })
  
  // Mock geolocation
  const mockGeolocation = {
    watchPosition: vi.fn().mockReturnValue(123),
    clearWatch: vi.fn(),
    getCurrentPosition: vi.fn()
  }
  Object.defineProperty(globalThis, 'navigator', {
    value: { geolocation: mockGeolocation },
    configurable: true
  })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('RiderDeliveryDetail', () => {
  it('renders out_for_delivery state with location tracking', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/rider/deliveries/delivery-1']}>
          <Routes>
            <Route path="/rider/deliveries/:id" element={<RiderDeliveryDetail />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('out for delivery')).toBeTruthy() // The default MSW mock sets this
      expect(screen.getByText('Mark as Delivered')).toBeTruthy()
    })
    
    // Auto-starts tracking if out for delivery
    await waitFor(() => {
      expect(navigator.geolocation.watchPosition).toHaveBeenCalled()
      expect(screen.getByText('Live Location Sharing Active')).toBeTruthy()
    })
  })

  it('renders assigned state correctly and does not track location', async () => {
    server.use(
      http.get('http://localhost:8000/api/v1/deliveries/:id', ({ params }) => {
        return HttpResponse.json({
          id: params.id,
          order_id: 'order-1',
          rider_id: 'rider-1',
          status: 'assigned', // Changing state
          destination_latitude: 12.972,
          destination_longitude: 77.595,
          assigned_at: new Date().toISOString(),
          picked_up_at: null,
          delivered_at: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        })
      })
    )

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/rider/deliveries/delivery-1']}>
          <Routes>
            <Route path="/rider/deliveries/:id" element={<RiderDeliveryDetail />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('assigned')).toBeTruthy()
      expect(screen.getByText('Mark as Picked Up')).toBeTruthy()
    })
    
    // Should NOT have started tracking
    expect(navigator.geolocation.watchPosition).not.toHaveBeenCalled()
  })
})
