import { describe, it, expect } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { NearbyDiscoverySection, ExternalStoreCard } from './NearbyDiscoverySection'
import { useLocationStore } from '@/store/useLocationStore'
import { server } from '@/setupTests'
import { http, HttpResponse } from 'msw'

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

describe('NearbyDiscoverySection', () => {
  it('renders prompt when customer location is not set', () => {
    useLocationStore.setState({ coords: null })

    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <NearbyDiscoverySection />
      </QueryClientProvider>
    )

    expect(screen.getByText('Set your delivery location above to discover nearby shops.')).toBeTruthy()
  })

  it('does not violate rules of hooks when transitioning from null coords to populated coords', async () => {
    useLocationStore.setState({ coords: null })

    const queryClient = createTestQueryClient()
    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <NearbyDiscoverySection />
      </QueryClientProvider>
    )

    expect(screen.getByText('Set your delivery location above to discover nearby shops.')).toBeTruthy()

    // Transition coords from null to populated
    useLocationStore.setState({
      coords: { latitude: 12.9716, longitude: 77.5946 },
      addressLabel: 'Indiranagar, Bengaluru',
      radiusMeters: 3000,
    })

    rerender(
      <QueryClientProvider client={queryClient}>
        <NearbyDiscoverySection />
      </QueryClientProvider>
    )

    expect(screen.getByText('More Stores in Your Neighbourhood')).toBeTruthy()
  })

  it('renders external directory listings with strict two-tier in-store badges and attribution', async () => {
    useLocationStore.setState({
      coords: { latitude: 12.9716, longitude: 77.5946 },
      addressLabel: 'Indiranagar, Bengaluru',
      radiusMeters: 3000,
    })

    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <NearbyDiscoverySection />
      </QueryClientProvider>
    )

    expect(screen.getByText('More Stores in Your Neighbourhood')).toBeTruthy()

    await waitFor(() => {
      expect(screen.getByText('City Supermarket')).toBeTruthy()
      expect(screen.getByText('Apollo Pharmacy')).toBeTruthy()
    })

    // Strict two-tier badge verification
    const badges = screen.getAllByText(/Directory Listing · In-store Only/)
    expect(badges.length).toBe(2)

    // Verify distance formatting
    expect(screen.getByText('450 m')).toBeTruthy()
    expect(screen.getByText('750 m')).toBeTruthy()

    // Verify mandatory provider attribution
    expect(
      screen.getByText(/Powered by Geoapify \| © OpenStreetMap contributors/)
    ).toBeTruthy()

    // Verify in-store purchase notice exists
    const notices = screen.getAllByText('In-store purchase')
    expect(notices.length).toBe(2)
  })

  it('renders graceful error state with retry button when upstream provider fails', async () => {
    useLocationStore.setState({
      coords: { latitude: 12.9716, longitude: 77.5946 },
      addressLabel: 'Indiranagar, Bengaluru',
      radiusMeters: 3000,
    })

    // Override handler to return 503
    server.use(
      http.get('http://localhost:8000/api/v1/discovery/nearby', () => {
        return HttpResponse.json(
          { detail: 'External directory provider authentication failed.' },
          { status: 503 }
        )
      })
    )

    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <NearbyDiscoverySection />
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('nearby-discovery-error')).toBeTruthy()
      expect(screen.getByText('Unable to load external places')).toBeTruthy()
      expect(screen.getByText('Retry Discovery')).toBeTruthy()
    })
  })

  it('renders empty state when no external stores are returned in radius', async () => {
    useLocationStore.setState({
      coords: { latitude: 12.9716, longitude: 77.5946 },
      addressLabel: 'Indiranagar, Bengaluru',
      radiusMeters: 3000,
    })

    server.use(
      http.get('http://localhost:8000/api/v1/discovery/nearby', () => {
        return HttpResponse.json({
          items: [],
          total: 0,
          latitude: 12.9716,
          longitude: 77.5946,
          radius_meters: 3000,
          cached: false,
          attribution: 'Powered by Geoapify | © OpenStreetMap contributors',
        })
      })
    )

    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <NearbyDiscoverySection />
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('nearby-discovery-empty')).toBeTruthy()
      expect(
        screen.getByText('No physical stores found in this radius')
      ).toBeTruthy()
    })
  })

  it('renders Open in Maps directions links, view mode toggle, and distance sorting', async () => {
    useLocationStore.setState({
      coords: { latitude: 12.9716, longitude: 77.5946 },
      addressLabel: 'Indiranagar, Bengaluru',
      radiusMeters: 3000,
    })

    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <NearbyDiscoverySection />
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('City Supermarket')).toBeTruthy()
    })

    // 1. Verify "Open in Maps" links prioritize encoded business name and address
    const mapLinks = screen.getAllByTestId('open-in-maps-link')
    expect(mapLinks.length).toBe(2)
    expect(mapLinks[0].getAttribute('href')).toContain('google.com/maps')
    expect(mapLinks[0].getAttribute('href')).toContain(
      encodeURIComponent('City Supermarket, Main Road, Sector 4')
    )
    expect(mapLinks[1].getAttribute('href')).toContain(
      encodeURIComponent('Apollo Pharmacy, Boring Road Cross, Patna')
    )

    // 2. Test toggling to Map View
    const mapToggle = screen.getByTestId('toggle-map-view')
    mapToggle.click()

    await waitFor(() => {
      expect(screen.getByTestId('discovery-map-view')).toBeTruthy()
      expect(screen.getByText('Spatial Directory Map')).toBeTruthy()
      expect(screen.getByText('You are here')).toBeTruthy()
    })

    // 3. Test toggling back to List View
    const listToggle = screen.getByTestId('toggle-list-view')
    listToggle.click()

    await waitFor(() => {
      expect(screen.queryByTestId('discovery-map-view')).toBeNull()
      expect(screen.getByText('City Supermarket')).toBeTruthy()
    })
  })

  it('ExternalStoreCard falls back to verified coordinates when business name is unavailable', () => {
    const listingWithoutName = {
      source: 'geoapify',
      source_id: 'geo-unnamed-1',
      name: '',
      category: 'general',
      address: '',
      latitude: 25.6126,
      longitude: 85.114,
      distance_meters: 320,
      phone: null,
      website: null,
      opening_hours: null,
      is_directory_listing: true,
      is_dukaanly_merchant: false,
      is_orderable: false,
      is_delivery_eligible: false,
      attribution: 'Powered by Geoapify',
    }

    render(<ExternalStoreCard item={listingWithoutName} />)
    const mapLink = screen.getByTestId('open-in-maps-link')
    expect(mapLink.getAttribute('href')).toContain('google.com/maps')
    expect(mapLink.getAttribute('href')).toContain('25.6126%2C85.114')
  })

  it('ExternalStoreCard renders dynamic shop type badge based on store identity', () => {
    const zudioStore = {
      source: 'geoapify',
      source_id: 'geo-zudio-1',
      name: 'Zudio',
      category: 'supermarket',
      address: 'NH922, Priyadarshi Nagar, Patna',
      latitude: 25.6126,
      longitude: 85.114,
      distance_meters: 2100,
      phone: null,
      website: null,
      opening_hours: null,
      is_directory_listing: true,
      is_dukaanly_merchant: false,
      is_orderable: false,
      is_delivery_eligible: false,
      attribution: 'Powered by Geoapify',
    }

    const { rerender } = render(<ExternalStoreCard item={zudioStore} />)
    expect(screen.getByText('Fashion & Apparel')).toBeTruthy()

    const nutritionStore = {
      ...zudioStore,
      name: 'Active nutrition centtre',
    }
    rerender(<ExternalStoreCard item={nutritionStore} />)
    expect(screen.getByText('Health & Sports Nutrition')).toBeTruthy()

    const homeTownStore = {
      ...zudioStore,
      name: 'Home town',
    }
    rerender(<ExternalStoreCard item={homeTownStore} />)
    expect(screen.getByText('Home Living & Furniture')).toBeTruthy()
  })

  it('opens DirectoryStoreModal with full storefront details and department guide when clicking Open Store button', async () => {
    useLocationStore.setState({
      coords: { latitude: 12.9716, longitude: 77.5946 },
      addressLabel: 'Indiranagar, Bengaluru',
      radiusMeters: 3000,
    })

    render(
      <MemoryRouter>
        <QueryClientProvider client={createTestQueryClient()}>
          <NearbyDiscoverySection />
        </QueryClientProvider>
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(screen.getByText('City Supermarket')).toBeTruthy()
    })

    // Find Open Store buttons on external store cards
    const openStoreButtons = screen.getAllByTestId('open-store-btn')
    expect(openStoreButtons.length).toBeGreaterThan(0)

    // Click the first Open Store button
    fireEvent.click(openStoreButtons[0])

    // Verify modal opened with store information
    await waitFor(() => {
      const modal = screen.getByTestId('directory-store-modal')
      expect(modal).toBeTruthy()
      expect(within(modal).getByRole('heading', { name: 'City Supermarket' })).toBeTruthy()
      expect(within(modal).getByText('In-Store Departments & Aisles')).toBeTruthy()
      expect(within(modal).getByText('Dairy & Cold Storage')).toBeTruthy()
      expect(within(modal).getByText('Staples, Flours & Grains')).toBeTruthy()
      expect(within(modal).getByTestId('modal-open-in-maps-btn')).toBeTruthy()
    })

    // Click Close button
    const closeBtn = screen.getByRole('button', { name: 'Close' })
    fireEvent.click(closeBtn)

    await waitFor(() => {
      expect(screen.queryByTestId('directory-store-modal')).toBeNull()
    })
  })
})
