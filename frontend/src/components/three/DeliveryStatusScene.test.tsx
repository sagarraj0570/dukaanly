import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DeliveryStatusScene } from './DeliveryStatusScene'

describe('DeliveryStatusScene', () => {
  it('renders fallback representation with status label when WebGL is unavailable', () => {
    render(<DeliveryStatusScene status="out_for_delivery" className="custom-delivery-class" />)
    expect(screen.getByText('out for delivery')).toBeTruthy()
  })

  it('renders appropriate fallback icons and labels for all delivery statuses', () => {
    const statuses = ['pending', 'assigned', 'picked_up', 'out_for_delivery', 'delivered']
    statuses.forEach((status) => {
      const { unmount } = render(<DeliveryStatusScene status={status} />)
      expect(screen.getByText(status.replace(/_/g, ' '))).toBeTruthy()
      unmount()
    })
  })
})
