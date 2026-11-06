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

  it('renders directory listing notice for unverified discovered shops', async () => {
    const { server } = await import('@/setupTests')
    const { http, HttpResponse } = await import('msw')

    server.use(
      http.get('http://localhost:8000/api/v1/shops/:id', () => {
        return HttpResponse.json({
          id: 'shop-unverified',
          owner_id: null,
          name: 'Patna Candidate Kirana',
          description: 'A neighbourhood OSM listing',
          address: 'Boring Road, Patna',
          phone: '+91 612 254 1102',
          is_active: true,
          is_orderable: false,
          verification_status: 'discovered',
          source_attribution: '© OpenStreetMap contributors, ODbL',
          location: { latitude: 25.6144, longitude: 85.1158 },
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        })
      })
    )

    const unverifiedQueryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={unverifiedQueryClient}>
        <MemoryRouter initialEntries={['/shops/shop-unverified']}>
          <Routes>
            <Route path="/shops/:id" element={<ShopDetail />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('Patna Candidate Kirana')).toBeTruthy()
      expect(screen.getByText(/Neighbourhood Directory Listing/i)).toBeTruthy()
      expect(screen.getByText(/In-Store Shopping Only/i)).toBeTruthy()
      expect(screen.getByText(/Claim this business/i)).toBeTruthy()
    })
  })
})
