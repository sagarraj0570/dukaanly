import '@testing-library/jest-dom'
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { DeliveryRouteMap } from './DeliveryRouteMap'
import type { DeliveryRoute } from '@/hooks/useDeliveries'

const mockRoute: DeliveryRoute = {
  delivery_id: 'del-123',
  status: 'assigned',
  rider_location: { latitude: 25.61, longitude: 85.11, name: 'Delivery Partner' },
  shop_location: { latitude: 25.6144, longitude: 85.1158, name: 'Patna Kirana' },
  customer_location: { latitude: 25.62, longitude: 85.12, name: 'Customer Home' },
  legs: [
    {
      from_name: 'Rider',
      to_name: 'Shop',
      from_latitude: 25.61,
      from_longitude: 85.11,
      to_latitude: 25.6144,
      to_longitude: 85.1158,
      distance_meters: 1200.0,
      duration_seconds: 240.0,
      duration_minutes: 4.0,
      geometry: [[25.61, 85.11], [25.6144, 85.1158]],
      is_fallback: false,
      cached: true,
    },
    {
      from_name: 'Shop',
      to_name: 'Customer',
      from_latitude: 25.6144,
      from_longitude: 85.1158,
      to_latitude: 25.62,
      to_longitude: 85.12,
      distance_meters: 2500.0,
      duration_seconds: 480.0,
      duration_minutes: 8.0,
      geometry: [[25.6144, 85.1158], [25.62, 85.12]],
      is_fallback: false,
      cached: true,
    },
  ],
  total_distance_meters: 3700.0,
  total_duration_seconds: 720.0,
  total_duration_minutes: 12.0,
  combined_geometry: [[25.61, 85.11], [25.6144, 85.1158], [25.62, 85.12]],
  active_leg_index: 0,
  is_fallback: false,
  cached: true,
  attribution: 'Route data © OpenStreetMap contributors, powered by OSRM',
}

describe('DeliveryRouteMap', () => {
  it('renders road distance and driving ETA in telemetry HUD', () => {
    render(<DeliveryRouteMap route={mockRoute} />)

    expect(screen.getByText(/Road Route \(OSRM\)/i)).toBeDefined()
    // 3700m -> 3.7 km
    expect(screen.getByText(/3.7 km/i)).toBeDefined()
    expect(screen.getByText(/12 mins driving time/i)).toBeDefined()
    expect(screen.getByText(/OSRM Cached \(5m\)/i)).toBeDefined()
  })

  it('renders distinct pickup and dropoff navigation leg pills', () => {
    render(<DeliveryRouteMap route={mockRoute} />)

    expect(screen.getByText(/Rider → Shop/i)).toBeDefined()
    expect(screen.getByText(/Shop → Customer/i)).toBeDefined()
  })

  it('displays loading state with spinner overlay when route is calculating', () => {
    render(<DeliveryRouteMap route={null} isLoading={true} />)

    expect(screen.getByText(/Calculating road route and driving ETA via OSRM.../i)).toBeDefined()
  })

  it('displays error / unavailable state and handles retry click', () => {
    const handleRetry = vi.fn()
    render(
      <DeliveryRouteMap
        route={null}
        isError={true}
        errorMessage="OSRM connection timed out"
        onRetry={handleRetry}
      />
    )

    expect(screen.getAllByText(/Route Unavailable/i).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/OSRM connection timed out/i)).toBeDefined()

    const retryBtns = screen.getAllByRole('button', { name: /retry/i })
    fireEvent.click(retryBtns[0])
    expect(handleRetry).toHaveBeenCalledTimes(1)
  })

  it('renders OpenStreetMap and OSRM attribution link', () => {
    render(<DeliveryRouteMap route={mockRoute} />)

    expect(
      screen.getByText(/Route data © OpenStreetMap contributors, powered by OSRM/i)
    ).toBeDefined()
  })

  it('renders calm terminal HUD and suppresses error overlays when delivery is cancelled', () => {
    render(
      <DeliveryRouteMap
        route={null}
        isError={true}
        errorMessage="Request failed with status code 504"
        isTerminal={true}
        terminalStatus="cancelled"
      />
    )

    expect(screen.getByText(/Delivery Cancelled/i)).toBeDefined()
    expect(screen.getByText(/Delivery was cancelled. Active route tracking ended./i)).toBeDefined()
    expect(screen.queryByText(/Route Unavailable/i)).toBeNull()
    expect(screen.queryByText(/Request failed with status code 504/i)).toBeNull()
    expect(screen.queryByRole('button', { name: /retry/i })).toBeNull()
  })
})
