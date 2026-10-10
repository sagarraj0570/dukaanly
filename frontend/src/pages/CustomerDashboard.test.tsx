import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CustomerDashboard } from './CustomerDashboard'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false, // Turn off retries for tests
    },
  },
})

describe('CustomerDashboard', () => {
  it('renders loading state initially', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <CustomerDashboard />
        </MemoryRouter>
      </QueryClientProvider>
    )
    
    expect(screen.getByText('Shops in your area')).toBeTruthy()
  })

  it('renders shops from API', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <CustomerDashboard />
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('Test Shop')).toBeTruthy()
    })
  })
})
