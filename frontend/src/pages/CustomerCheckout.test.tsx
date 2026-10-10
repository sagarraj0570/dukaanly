import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CustomerCheckout } from './CustomerCheckout'
import { http, HttpResponse } from 'msw'
import { server } from '../setupTests'

let queryClient: QueryClient

beforeEach(() => {
  queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })
})

describe('CustomerCheckout', () => {
  it('renders checkout page correctly with populated cart', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/customer/checkout']}>
          <Routes>
            <Route path="/customer/checkout" element={<CustomerCheckout />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('Review your order')).toBeTruthy()
    })
    
    // Check that items and total amount render
    const amounts = screen.getAllByText(/₹300.00/i)
    expect(amounts.length).toBeGreaterThan(0)
  })

  it('prevents checkout and shows empty state when cart is empty', async () => {
    // Override MSW for this test
    server.use(
      http.get('http://localhost:8000/api/v1/cart', () => {
        return HttpResponse.json({
          id: 'cart-1',
          customer_id: 'cust-1',
          shop_id: 'shop-1',
          items: [],
          total_amount: 0.00
        })
      })
    )

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/customer/checkout']}>
          <Routes>
            <Route path="/customer/checkout" element={<CustomerCheckout />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('Cart is empty')).toBeTruthy()
      expect(screen.getByText('You cannot checkout an empty cart.')).toBeTruthy()
    })
  })

  it('allows clicking Confirm Order and processes checkout', async () => {
    // Revert to populated cart implicitly by not using `server.use` in this block
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/customer/checkout']}>
          <Routes>
            <Route path="/customer/checkout" element={<CustomerCheckout />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('Confirm Order')).toBeTruthy()
    })
    
    const btn = screen.getByText('Confirm Order')
    btn.click()
    
    await waitFor(() => {
      expect(screen.getByText('Processing...')).toBeTruthy()
    })
  })
})
