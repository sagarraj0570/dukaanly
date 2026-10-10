import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CustomerCart } from './CustomerCart'
import { CustomerLayout } from '../layouts/CustomerLayout'
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

describe('CustomerCart', () => {
  it('renders cart details correctly', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/cart']}>
          <Routes>
            <Route path="/cart" element={<CustomerCart />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('Test Product Details')).toBeTruthy()
    })
    
    // Check that items and total amount render
    const amounts = screen.getAllByText(/₹300.00/i)
    expect(amounts.length).toBeGreaterThan(0)
  })

  it('handles empty cart state', async () => {
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
        <MemoryRouter initialEntries={['/cart']}>
          <Routes>
            <Route path="/cart" element={<CustomerCart />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('Your cart is empty')).toBeTruthy()
    })
  })

  it('renders cart badge in CustomerLayout', async () => {
    // Revert to populated cart
    server.use(
      http.get('http://localhost:8000/api/v1/cart', () => {
        return HttpResponse.json({
          id: 'cart-1',
          customer_id: 'cust-1',
          shop_id: 'shop-1',
          items: [
            {
              id: 'item-1',
              product_id: 'prod-1',
              quantity: 2,
              product_name: 'Test Product Details',
              product_price: 150.00,
              item_total: 300.00
            }
          ],
          total_amount: 300.00
        })
      })
    )

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/customer']}>
          <Routes>
            <Route path="/customer" element={<CustomerLayout />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('2')).toBeTruthy() // The badge with quantity 2
    })
  })
})
