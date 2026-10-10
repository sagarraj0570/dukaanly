import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ShopDetail } from './ShopDetail'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
  },
})

describe('ShopDetail', () => {
  it('renders shop details from API', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/shops/shop-1']}>
          <Routes>
            <Route path="/shops/:id" element={<ShopDetail />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('Test Shop Details')).toBeTruthy()
    })
    
    // Check that the product catalog fetches and renders products
    await waitFor(() => {
      expect(screen.getByText('Test Product')).toBeTruthy()
    })
  })
})
