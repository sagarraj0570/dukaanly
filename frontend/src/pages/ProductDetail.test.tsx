import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ProductDetail } from './ProductDetail'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
  },
})

describe('ProductDetail', () => {
  it('renders product details from API', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/products/prod-1']}>
          <Routes>
            <Route path="/products/:id" element={<ProductDetail />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('Test Product Details')).toBeTruthy()
    })
    
    // Check price formatting
    expect(screen.getByText(/₹150.00/i)).toBeTruthy()
    expect(screen.getByText('Grocery')).toBeTruthy()
  })
})
