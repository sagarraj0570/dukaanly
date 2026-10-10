import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CustomerPayment } from './CustomerPayment'

let queryClient: QueryClient

beforeEach(() => {
  queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })
})

describe('CustomerPayment', () => {
  it('renders payment page and initiates payment automatically', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/customer/payment/order-1']}>
          <Routes>
            <Route path="/customer/payment/:id" element={<CustomerPayment />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('Complete Payment')).toBeTruthy()
    })
    
    // Check that amount renders
    expect(screen.getByText(/₹300.00/i)).toBeTruthy()

    // Wait for automatic initiation to finish (buttons should become active)
    await waitFor(() => {
      expect(screen.getByText('Simulate Success')).toBeTruthy()
    })
  })
})
