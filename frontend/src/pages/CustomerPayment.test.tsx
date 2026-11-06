import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { server } from '@/setupTests'
import { http, HttpResponse } from 'msw'
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

  it('renders synchronized inventory reservation banner from authoritative server duration', async () => {
    server.use(
      http.get('http://localhost:8000/api/v1/orders/:id/reservation', () => {
        return HttpResponse.json({
          order_id: 'order-1',
          status: 'active',
          expires_at: new Date(Date.now() + 600 * 1000).toISOString(),
          seconds_remaining: 600,
          server_time: new Date().toISOString(),
          is_expired: false,
          items: [],
        })
      })
    )

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
      expect(screen.getByText('Inventory Reserved')).toBeTruthy()
      expect(screen.getByText('10:00')).toBeTruthy()
    })
  })

  it('does not declare stock released when countdown reaches 00:00; displays server verification indicator', async () => {
    server.use(
      http.get('http://localhost:8000/api/v1/orders/:id/reservation', () => {
        return HttpResponse.json({
          order_id: 'order-1',
          status: 'active',
          expires_at: new Date().toISOString(),
          seconds_remaining: 0,
          server_time: new Date().toISOString(),
          is_expired: false,
          items: [],
        })
      })
    )

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/customer/payment/order-1']}>
          <Routes>
            <Route path="/customer/payment/:id" element={<CustomerPayment />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    // When seconds_remaining reaches 0 locally while status is still 'active',
    // the UI must NOT unilaterally claim stock is restored to inventory.
    // Instead, it must show the verification banner.
    await waitFor(() => {
      expect(screen.getByText('Verifying Reservation Status')).toBeTruthy()
      expect(screen.getByText(/Reservation window reached 00:00. Syncing with server.../i)).toBeTruthy()
    })
    expect(screen.queryByText(/items have been safely restored to inventory/i)).toBeNull()
  })

  it('renders authoritative stock released notice only when confirmed by backend status', async () => {
    server.use(
      http.get('http://localhost:8000/api/v1/orders/:id/reservation', () => {
        return HttpResponse.json({
          order_id: 'order-1',
          status: 'expired',
          expires_at: new Date().toISOString(),
          seconds_remaining: 0,
          server_time: new Date().toISOString(),
          is_expired: true,
          items: [],
        })
      })
    )

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
      expect(screen.getByText('Reservation Expired')).toBeTruthy()
      expect(screen.getByText(/items have been safely restored to inventory by the server/i)).toBeTruthy()
      expect(screen.getByText('Return to Cart & Re-order')).toBeTruthy()
    })
  })

  it('allows retrying payment initiation when provider initiation initially fails', async () => {
    let attempt = 0
    server.use(
      http.post('http://localhost:8000/api/v1/orders/:id/payment', () => {
        attempt++
        if (attempt === 1) {
          return HttpResponse.json({ detail: 'Payment gateway timeout' }, { status: 504 })
        }
        return HttpResponse.json({
          payment_id: 'pay_init-retry',
          order_id: 'order-1',
          provider: 'razorpay',
          provider_order_id: 'order_mock_retry',
          amount: 300.00,
          currency: 'INR',
          key_id: 'mock_key_id',
          mock_payment_id: 'pay_mock_retry',
          mock_signature: 'sig_mock_retry',
        })
      })
    )

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
      expect(screen.getByText('Failed to initialize payment')).toBeTruthy()
      expect(screen.getByText('Payment gateway timeout')).toBeTruthy()
      expect(screen.getByRole('button', { name: /retry/i })).toBeTruthy()
    })

    // Click retry
    fireEvent.click(screen.getByRole('button', { name: /retry/i }))

    await waitFor(() => {
      expect(screen.queryByText('Failed to initialize payment')).toBeNull()
      expect(screen.getByText('Simulate Success')).toBeTruthy()
    })
  })

  it('allows re-attempting payment when verification fails while reservation remains active', async () => {
    server.use(
      http.post('http://localhost:8000/api/v1/payments/verify', () => {
        return HttpResponse.json({ detail: 'Signature mismatch' }, { status: 400 })
      })
    )

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
      expect(screen.getByText('Simulate Failure')).toBeTruthy()
    })

    fireEvent.click(screen.getByText('Simulate Failure'))

    await waitFor(() => {
      expect(screen.getByText('Verification Failed')).toBeTruthy()
      expect(screen.getByText('Signature mismatch')).toBeTruthy()
      expect(screen.getByText(/You can re-attempt payment before your reservation timer expires/i)).toBeTruthy()
      // Buttons remain available to re-attempt
      expect(screen.getByText('Simulate Success').closest('button')?.hasAttribute('disabled')).toBe(false)
    })
  })

  it('prevents duplicate payment submission while processing', async () => {
    let verifyCallCount = 0
    server.use(
      http.post('http://localhost:8000/api/v1/payments/verify', async () => {
        verifyCallCount++
        await new Promise((resolve) => setTimeout(resolve, 200))
        return HttpResponse.json({ id: 'pay-1', order_id: 'order-1', status: 'captured' })
      })
    )

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
      expect(screen.getByText('Simulate Success')).toBeTruthy()
    })

    const successBtn = screen.getByText('Simulate Success').closest('button')!
    expect(successBtn.hasAttribute('disabled')).toBe(false)

    // First click initiates verification
    fireEvent.click(successBtn)

    // Button should transition to Processing... and be disabled
    await waitFor(() => {
      expect(screen.getByText('Processing...')).toBeTruthy()
      expect(screen.getByText('Processing...').closest('button')?.hasAttribute('disabled')).toBe(true)
    })

    // Second click during in-flight processing should be blocked
    fireEvent.click(screen.getByText('Processing...'))

    await waitFor(() => {
      expect(verifyCallCount).toBe(1)
    })
  })

  it('restores reservation and order state on page load', async () => {
    server.use(
      http.get('http://localhost:8000/api/v1/orders/:id', () => {
        return HttpResponse.json({
          id: 'order-1',
          customer_id: 'cust-1',
          shop_id: 'shop-1',
          status: 'pending',
          total_amount: 450.0,
          items: [{ id: 'item-1', product_name: 'Atta 5kg', quantity: 1, unit_price: 450.0 }],
          created_at: new Date().toISOString(),
        })
      }),
      http.get('http://localhost:8000/api/v1/orders/:id/reservation', () => {
        return HttpResponse.json({
          order_id: 'order-1',
          status: 'active',
          expires_at: new Date(Date.now() + 450 * 1000).toISOString(),
          seconds_remaining: 450,
          server_time: new Date().toISOString(),
          is_expired: false,
          items: [],
        })
      })
    )

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/customer/payment/order-1']}>
          <Routes>
            <Route path="/customer/payment/:id" element={<CustomerPayment />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    // Verify order and reservation state restored from server queries
    await waitFor(() => {
      expect(screen.getByText('Inventory Reserved')).toBeTruthy()
      expect(screen.getByText('07:30')).toBeTruthy()
      expect(screen.getByText(/₹450.00/i)).toBeTruthy()
      expect(screen.getByText('Simulate Success')).toBeTruthy()
    })
  })
})
