import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { DirectoryStoreModal } from './DirectoryStoreModal'

describe('DirectoryStoreModal Dynamic Departments by Shop Type', () => {
  const baseStore = {
    source: 'geoapify',
    source_id: 'place_123',
    address: 'Gola Road, Patna, Bihar',
    latitude: 25.61,
    longitude: 85.12,
    distance_meters: 1500,
    phone: null,
    website: null,
    opening_hours: null,
    is_directory_listing: true,
    is_dukaanly_merchant: false,
    is_orderable: false,
    is_delivery_eligible: false,
    attribution: 'Powered by Geoapify',
  }

  it('renders dynamic fashion departments and trial room notice for Zudio', () => {
    const store = {
      ...baseStore,
      name: 'Zudio',
      category: 'supermarket', // Raw upstream might say supermarket
    }

    render(
      <MemoryRouter>
        <DirectoryStoreModal isOpen={true} onClose={vi.fn()} store={store} />
      </MemoryRouter>
    )

    expect(screen.getByText('Fashion & Apparel')).toBeTruthy()
    expect(screen.getByText(/Men's Casual & Formal Wear/i)).toBeTruthy()
    expect(screen.getByText(/Women's Ethnic & Western Wear/i)).toBeTruthy()
    expect(screen.getByText(/Footwear & Casual Shoes/i)).toBeTruthy()
    expect(screen.getByText(/Trial rooms, seasonal fashion collections/i)).toBeTruthy()
  })

  it('renders dynamic nutrition departments and supplements notice for Active nutrition centtre', () => {
    const store = {
      ...baseStore,
      name: 'Active nutrition centtre',
      category: 'supermarket',
    }

    render(
      <MemoryRouter>
        <DirectoryStoreModal isOpen={true} onClose={vi.fn()} store={store} />
      </MemoryRouter>
    )

    expect(screen.getByText('Health & Sports Nutrition')).toBeTruthy()
    expect(screen.getByText(/Whey Protein & Isolates/i)).toBeTruthy()
    expect(screen.getByText(/Pre-Workouts & Amino Acids/i)).toBeTruthy()
    expect(screen.getByText(/Creatine & Muscle Builders/i)).toBeTruthy()
    expect(screen.getByText(/100% authentic sealed supplements/i)).toBeTruthy()
  })

  it('renders dynamic home living departments for Home town', () => {
    const store = {
      ...baseStore,
      name: 'Home town',
      category: 'supermarket',
    }

    render(
      <MemoryRouter>
        <DirectoryStoreModal isOpen={true} onClose={vi.fn()} store={store} />
      </MemoryRouter>
    )

    expect(screen.getByText('Home Living & Furniture')).toBeTruthy()
    expect(screen.getByText(/Living Room & Sofas/i)).toBeTruthy()
    expect(screen.getByText(/Bedroom & Mattresses/i)).toBeTruthy()
    expect(screen.getByText(/Dining & Kitchen Furniture/i)).toBeTruthy()
    expect(screen.getByText(/Showroom floor display/i)).toBeTruthy()
  })

  it('renders dynamic supermarket departments for TVS mart', () => {
    const store = {
      ...baseStore,
      name: 'TVS mart',
      category: 'supermarket',
    }

    render(
      <MemoryRouter>
        <DirectoryStoreModal isOpen={true} onClose={vi.fn()} store={store} />
      </MemoryRouter>
    )

    expect(screen.getByText('Supermarket & Provisions')).toBeTruthy()
    expect(screen.getByText(/Dairy & Cold Storage/i)).toBeTruthy()
    expect(screen.getByText(/Staples, Flours & Grains/i)).toBeTruthy()
    expect(screen.getByText(/Cooking Oils & Masalas/i)).toBeTruthy()
  })
})
