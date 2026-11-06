import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ShoppingAssistantModal } from './ShoppingAssistantModal'
import { useLocationStore } from '@/store/useLocationStore'
import { server } from '@/setupTests'
import { http, HttpResponse } from 'msw'

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

describe('ShoppingAssistantModal', () => {
  beforeEach(() => {
    useLocationStore.setState({
      coords: { latitude: 25.6144, longitude: 85.1158 },
      addressLabel: 'Boring Road / Boring Canal Rd',
      radiusMeters: 5000,
    })
  })

  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <MemoryRouter>
        <QueryClientProvider client={createTestQueryClient()}>
          <ShoppingAssistantModal isOpen={false} onClose={vi.fn()} />
        </QueryClientProvider>
      </MemoryRouter>
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders welcome screen and suggestions when open', () => {
    render(
      <MemoryRouter>
        <QueryClientProvider client={createTestQueryClient()}>
          <ShoppingAssistantModal isOpen={true} onClose={vi.fn()} />
        </QueryClientProvider>
      </MemoryRouter>
    )

    expect(screen.getByText('Dukaanly AI Assistant')).toBeTruthy()
    expect(screen.getByText('What can I help you find today?')).toBeTruthy()
    expect(screen.getByText('Need 1L milk and bread for breakfast')).toBeTruthy()
  })

  it('sends shopping query, renders matched products and authoritative proposed cart', async () => {
    render(
      <MemoryRouter>
        <QueryClientProvider client={createTestQueryClient()}>
          <ShoppingAssistantModal isOpen={true} onClose={vi.fn()} />
        </QueryClientProvider>
      </MemoryRouter>
    )

    const input = screen.getByPlaceholderText(/Ask for groceries/i)
    fireEvent.change(input, { target: { value: 'Need milk' } })
    fireEvent.submit(input.closest('form')!)

    // Verify assistant response rendered
    await waitFor(() => {
      expect(
        screen.getByText('I found fresh items for your breakfast from Boring Road Mart.')
      ).toBeTruthy()
    })

    // Verify matched product rendered
    expect(screen.getAllByText('Amul Fresh Milk 1L').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('₹66.00').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('10 in stock')).toBeTruthy()

    // Verify proposed cart
    expect(screen.getByText('Proposed Cart Review')).toBeTruthy()
    expect(screen.getAllByText('Boring Road Mart').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Add Items to Cart')).toBeTruthy()
  })

  it('allows quantity editing and recomputes authoritative total', async () => {
    render(
      <MemoryRouter>
        <QueryClientProvider client={createTestQueryClient()}>
          <ShoppingAssistantModal isOpen={true} onClose={vi.fn()} />
        </QueryClientProvider>
      </MemoryRouter>
    )

    const suggestionBtn = screen.getByText('Need 1L milk and bread for breakfast')
    fireEvent.click(suggestionBtn)

    await waitFor(() => {
      expect(screen.getByText('Proposed Cart Review')).toBeTruthy()
    })

    // Initial quantity is 1 -> total is ₹66.00
    expect(screen.getAllByText('₹66.00').length).toBeGreaterThanOrEqual(1)

    // Click (+) button to increase quantity to 2
    const plusBtn = screen.getByLabelText(/Increase quantity for Amul Fresh Milk 1L/i)
    fireEvent.click(plusBtn)

    // Total should authoritatively recalculate: 2 * 66.00 = 132.00
    await waitFor(() => {
      expect(screen.getAllByText('₹132.00').length).toBeGreaterThanOrEqual(1)
    })
  })

  it('clicking Add Items to Cart applies items and shows success state', async () => {
    render(
      <MemoryRouter>
        <QueryClientProvider client={createTestQueryClient()}>
          <ShoppingAssistantModal isOpen={true} onClose={vi.fn()} />
        </QueryClientProvider>
      </MemoryRouter>
    )

    const input = screen.getByPlaceholderText(/Ask for groceries/i)
    fireEvent.change(input, { target: { value: 'Need milk' } })
    fireEvent.submit(input.closest('form')!)

    await waitFor(() => {
      expect(screen.getByText('Add Items to Cart')).toBeTruthy()
    })

    const addBtn = screen.getByText('Add Items to Cart')
    fireEvent.click(addBtn)

    await waitFor(() => {
      expect(screen.getByText(/Added to cart/i)).toBeTruthy()
      expect(screen.getByText('Go to Cart')).toBeTruthy()
    })
  })

  it('displays graceful fallback when AI service is disabled (503)', async () => {
    server.use(
      http.post('http://localhost:8000/api/v1/ai/assistant/chat', () => {
        return HttpResponse.json(
          { detail: 'AI feature shopping_assistant is currently disabled.' },
          { status: 503 }
        )
      })
    )

    render(
      <MemoryRouter>
        <QueryClientProvider client={createTestQueryClient()}>
          <ShoppingAssistantModal isOpen={true} onClose={vi.fn()} />
        </QueryClientProvider>
      </MemoryRouter>
    )

    const input = screen.getByPlaceholderText(/Ask for groceries/i)
    fireEvent.change(input, { target: { value: 'Need milk' } })
    fireEvent.submit(input.closest('form')!)

    await waitFor(() => {
      expect(screen.getByText(/The AI Shopping Assistant is currently offline/i)).toBeTruthy()
      expect(screen.getByText('Browse Partner Shops')).toBeTruthy()
    })
  })
})
