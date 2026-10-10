import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RiderDashboard } from './RiderDashboard'

let queryClient: QueryClient

beforeEach(() => {
  queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })
})

describe('RiderDashboard', () => {
  it('renders rider profile and deliveries', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/rider']}>
          <Routes>
            <Route path="/rider" element={<RiderDashboard />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('Available')).toBeTruthy()
      expect(screen.getByText('Go Offline')).toBeTruthy()
    })
    
    // Check that deliveries are loaded (1 active, 1 past mock)
    await waitFor(() => {
      expect(screen.getByText(/Active Deliveries \(1\)/)).toBeTruthy()
      expect(screen.getByText('assigned')).toBeTruthy()
      expect(screen.getByText('delivered')).toBeTruthy()
    })
  })
})
