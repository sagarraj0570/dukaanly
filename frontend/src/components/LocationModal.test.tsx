import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { LocationModal } from './LocationModal'
import { useLocationStore } from '@/store/useLocationStore'

describe('LocationModal', () => {
  beforeEach(() => {
    useLocationStore.getState().resetToDefault()
  })

  it('renders search by place input and initial places list when open', () => {
    render(<LocationModal isOpen={true} onClose={() => {}} />)

    expect(screen.getByRole('dialog')).toBeTruthy()
    expect(screen.getByText('Set Delivery Location')).toBeTruthy()
    expect(screen.getByText('Search by Place or Neighbourhood')).toBeTruthy()

    const searchInput = screen.getByPlaceholderText(
      /Search area \(e\.g\. Boring Road, Kankarbagh, Danapur, AIIMS\)\.\.\./i
    )
    expect(searchInput).toBeTruthy()

    // Verifies common Patna places are shown
    expect(screen.getByText('Boring Road / Boring Canal Rd')).toBeTruthy()
    expect(screen.getByText('Kankarbagh Main Road')).toBeTruthy()
  })

  it('filters places in real time as user types', () => {
    render(<LocationModal isOpen={true} onClose={() => {}} />)

    const searchInput = screen.getByPlaceholderText(
      /Search area \(e\.g\. Boring Road, Kankarbagh, Danapur, AIIMS\)\.\.\./i
    )

    // Type "Danapur"
    fireEvent.change(searchInput, { target: { value: 'Danapur' } })

    expect(screen.getByText('Danapur Cantt & Danapur Station')).toBeTruthy()
    expect(screen.getByText('Saguna More / Danapur Road')).toBeTruthy()
    expect(screen.queryByText('Kankarbagh Main Road')).toBeNull()
  })

  it('selects a place and updates store coordinates and address label', () => {
    render(<LocationModal isOpen={true} onClose={() => {}} />)

    const searchInput = screen.getByPlaceholderText(
      /Search area \(e\.g\. Boring Road, Kankarbagh, Danapur, AIIMS\)\.\.\./i
    )
    fireEvent.change(searchInput, { target: { value: 'AIIMS' } })

    const aiimsButton = screen.getByText('AIIMS Patna (Phulwari Sharif)')
    fireEvent.click(aiimsButton)

    const state = useLocationStore.getState()
    expect(state.addressLabel).toBe('AIIMS Patna (Phulwari Sharif)')
    expect(state.coords?.latitude).toBe(25.561)
    expect(state.coords?.longitude).toBe(85.042)
  })

  it('shows empty state when search finds no matching places', () => {
    render(<LocationModal isOpen={true} onClose={() => {}} />)

    const searchInput = screen.getByPlaceholderText(
      /Search area \(e\.g\. Boring Road, Kankarbagh, Danapur, AIIMS\)\.\.\./i
    )
    fireEvent.change(searchInput, { target: { value: 'NonexistentPlace123' } })

    expect(screen.getByText(/No neighbourhood found for "NonexistentPlace123"/i)).toBeTruthy()
    expect(screen.getByText(/Clear search & view all places/i)).toBeTruthy()
  })

  it('renders nothing when isOpen is false', () => {
    const { container } = render(<LocationModal isOpen={false} onClose={() => {}} />)
    expect(container.firstChild).toBeNull()
  })
})
