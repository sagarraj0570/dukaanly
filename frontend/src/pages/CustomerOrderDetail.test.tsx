import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CustomerOrderDetail } from './CustomerOrderDetail'

let queryClient: QueryClient

beforeEach(() => {
  queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })
})

describe('CustomerOrderDetail', () => {
  it('renders order detail and documents missing delivery gap', async () => {
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
      expect(screen.getByText('Order #order')).toBeTruthy()
      expect(screen.getByText('Test Product Details')).toBeTruthy()
    })
    
    // Ensure the tracking missing gap is documented in UI
    expect(screen.getByText('Tracking Unavailable')).toBeTruthy()
    expect(screen.getByText(/backend API does not currently expose the/)).toBeTruthy()
  })
})
