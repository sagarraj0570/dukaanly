import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CustomerOrderHistory } from './CustomerOrderHistory'

let queryClient: QueryClient

beforeEach(() => {
  queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })
})

describe('CustomerOrderHistory', () => {
  it('renders order history', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/customer/orders']}>
          <Routes>
            <Route path="/customer/orders" element={<CustomerOrderHistory />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('Order History')).toBeTruthy()
      expect(screen.getByText(/Order #order/)).toBeTruthy()
      expect(screen.getByText('pending')).toBeTruthy()
    })
  })
})
