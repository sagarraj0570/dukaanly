import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { DeliveryEtaCard } from './DeliveryEtaCard'
import type { DeliveryEtaResponse } from '@/hooks/useDeliveries'

describe('DeliveryEtaCard', () => {
  const mockEtaData: DeliveryEtaResponse = {
    delivery_id: 'del-101',
    status: 'out_for_delivery',
    eta: {
      earliest_at: new Date(Date.now() + 18 * 60 * 1000).toISOString(),
      latest_at: new Date(Date.now() + 25 * 60 * 1000).toISOString(),
      calculated_at: new Date().toISOString(),
      remaining_seconds: 1260,
      source: 'osrm',
      is_estimated: true,
    },
    update_reason: 'Rider en route',
    breakdown: {
      preparation_remaining_seconds: 0,
      assignment_wait_seconds: 0,
      pickup_travel_remaining_seconds: 0,
      pickup_buffer_seconds: 180,
      dropoff_travel_seconds: 720,
      handoff_buffer_seconds: 180,
    },
    delay_explanation: null,
  }

  it('renders arrival window and disclaimer correctly', () => {
    render(<DeliveryEtaCard etaData={mockEtaData} />)

    expect(screen.getByText('Smart Delivery ETA')).toBeTruthy()
    expect(screen.getByText('18–25 min')).toBeTruthy()
    expect(screen.getByText(/Estimated arrival • Not a guaranteed delivery time/i)).toBeTruthy()
    expect(screen.getByText(/Driving time is calculated from actual road routes/i)).toBeTruthy()
  })

  it('renders fallback banner when source is fallback_estimate', () => {
    const fallbackData: DeliveryEtaResponse = {
      ...mockEtaData,
      eta: {
        ...mockEtaData.eta,
        source: 'fallback_estimate',
      },
    }

    render(<DeliveryEtaCard etaData={fallbackData} />)
    expect(screen.getByText('Traffic Fallback Estimate')).toBeTruthy()
  })

  it('renders delay explanation banner when present', () => {
    const delayedData: DeliveryEtaResponse = {
      ...mockEtaData,
      delay_explanation: 'Shop preparation is taking longer than expected (+10 mins)',
    }

    render(<DeliveryEtaCard etaData={delayedData} />)
    expect(screen.getByText('Update on your order:')).toBeTruthy()
    expect(
      screen.getByText('Shop preparation is taking longer than expected (+10 mins)')
    ).toBeTruthy()
  })

  it('toggles breakdown details drawer with component breakdowns', () => {
    const detailedData: DeliveryEtaResponse = {
      ...mockEtaData,
      breakdown: {
        preparation_remaining_seconds: 300,
        assignment_wait_seconds: 180,
        pickup_travel_remaining_seconds: 240,
        dropoff_travel_seconds: 480,
        pickup_buffer_seconds: 180,
        handoff_buffer_seconds: 180,
      },
    }

    render(<DeliveryEtaCard etaData={detailedData} />)

    // Breakdown is hidden initially
    expect(screen.queryByText('ETA Component Breakdown')).toBeNull()

    // Click toggle button
    const toggleButton = screen.getByText('View breakdown')
    fireEvent.click(toggleButton)

    // Breakdown is now visible
    expect(screen.getByText('ETA Component Breakdown')).toBeTruthy()
    expect(screen.getByText('Remaining Prep')).toBeTruthy()
    expect(screen.getByText('~5 mins')).toBeTruthy()
    expect(screen.getByText('Rider Matching')).toBeTruthy()
    expect(screen.getByText('Rider to Shop')).toBeTruthy()
    expect(screen.getByText('Delivery Road Travel')).toBeTruthy()
    expect(screen.getByText('Doorstep Handoff')).toBeTruthy()

    // Click again to hide
    fireEvent.click(screen.getByText('Hide details'))
    expect(screen.queryByText('ETA Component Breakdown')).toBeNull()
  })

  it('renders terminal delivered state cleanly', () => {
    const deliveredData: DeliveryEtaResponse = {
      ...mockEtaData,
      status: 'delivered',
    }

    render(<DeliveryEtaCard etaData={deliveredData} />)
    expect(screen.getByText('Order Delivered')).toBeTruthy()
    expect(screen.getByText(/Delivered successfully/i)).toBeTruthy()
  })

  it('renders terminal cancelled state cleanly', () => {
    const cancelledData: DeliveryEtaResponse = {
      ...mockEtaData,
      status: 'cancelled',
    }

    render(<DeliveryEtaCard etaData={cancelledData} />)
    expect(screen.getByText('Delivery Cancelled')).toBeTruthy()
  })
})
