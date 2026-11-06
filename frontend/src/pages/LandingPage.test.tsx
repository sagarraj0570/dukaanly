import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { LandingPage } from './LandingPage'

// Mock 3D HeroScene to avoid WebGL context requirements in jsdom
vi.mock('@/components/three/HeroScene', () => ({
  default: () => <div data-testid="mock-hero-scene">3D Scene</div>,
  HeroScene: () => <div data-testid="mock-hero-scene">3D Scene</div>,
}))

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('LandingPage', () => {
  it('renders hero title, navigation and desktop experience elements', async () => {
    render(<LandingPage />, { wrapper: createWrapper() })

    // Hero headline
    expect(
      screen.getByRole('heading', { name: /your neighbourhood shops, delivered to your door/i })
    ).toBeTruthy()

    // Primary CTA
    const startShoppingLinks = screen.getAllByRole('link', { name: /start shopping/i })
    expect(startShoppingLinks.length).toBeGreaterThan(0)
    expect(startShoppingLinks[0].getAttribute('href')).toBe('/login')

    // Navigation branding
    const dukaanlyLogos = screen.getAllByText(/dukaan/i)
    expect(dukaanlyLogos.length).toBeGreaterThan(0)

    // Category Discovery section
    expect(screen.getByText(/shop by category/i)).toBeTruthy()
    expect(screen.getByText(/groceries/i)).toBeTruthy()
    expect(screen.getByText(/medicines/i)).toBeTruthy()

    // How It Works section
    expect(screen.getByText(/how it works/i)).toBeTruthy()
    expect(screen.getByText(/browse local shops/i)).toBeTruthy()
    expect(screen.getByText(/place your order/i)).toBeTruthy()
    expect(screen.getByText(/rider delivery/i)).toBeTruthy()

    // Brand section
    expect(screen.getByText(/built for your neighbourhood/i)).toBeTruthy()

    // Desktop notice for mobile viewports
    expect(screen.getByText(/dukaanly desktop experience/i)).toBeTruthy()
  })
})
