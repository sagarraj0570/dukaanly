import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { EmptyState3D } from './EmptyState3D'

describe('EmptyState3D', () => {
  it('renders fallback icon without crashing when WebGL is unavailable in test environment', () => {
    const { container } = render(<EmptyState3D type="cart" className="custom-test-class" />)
    expect(container.firstChild).toBeTruthy()
    expect(container.querySelector('.custom-test-class')).toBeTruthy()
  })

  it('renders correctly for different empty state types', () => {
    const types = ['cart', 'search', 'orders', 'inventory', 'store'] as const
    types.forEach((type) => {
      const { container } = render(<EmptyState3D type={type} />)
      expect(container.querySelector('svg')).toBeTruthy()
    })
  })
})
