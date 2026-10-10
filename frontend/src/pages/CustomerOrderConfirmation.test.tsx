import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CustomerOrderConfirmation } from './CustomerOrderConfirmation'

let queryClient: QueryClient

beforeEach(() => {
  queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })
})

describe('CustomerOrderConfirmation', () => {
  it('renders order confirmation correctly', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/customer/orders/order-1/confirmation']}>
          <Routes>
            <Route path="/customer/orders/:id/confirmation" element={<CustomerOrderConfirmation />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('Payment Pending')).toBeTruthy()
    })
    
    // Total amounts
    const amounts = screen.getAllByText(/₹300.00/i)
    expect(amounts.length).toBeGreaterThan(0)
  })
})
