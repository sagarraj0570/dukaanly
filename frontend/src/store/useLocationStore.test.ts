import { describe, it, expect, beforeEach } from 'vitest'
import { useLocationStore, LOCATION_PRESETS } from './useLocationStore'

describe('useLocationStore', () => {
  beforeEach(() => {
    useLocationStore.getState().resetToDefault()
  })

  it('initializes with demo Boring Road coords, demo label, and 5000m radius', () => {
    const state = useLocationStore.getState()
    expect(state.radiusMeters).toBe(5000)
    expect(state.deliveryOnly).toBe(false)
    expect(state.coords).toEqual({ latitude: 25.6085, longitude: 85.1115 })
    expect(state.addressLabel).toBe('Boring Road, Patna (demo)')
    expect(state.isGps).toBe(false)
  })

  it('updates preset correctly', () => {
    useLocationStore.getState().setPreset('kankarbagh')
    const state = useLocationStore.getState()
    const kankarbagh = LOCATION_PRESETS.find((p) => p.id === 'kankarbagh')!
    expect(state.coords).toEqual(kankarbagh.coords)
    expect(state.addressLabel).toBe(kankarbagh.name)
    expect(state.isGps).toBe(false)
  })

  it('clamps radius correctly between 100m and 10000m', () => {
    useLocationStore.getState().setRadius(50)
    expect(useLocationStore.getState().radiusMeters).toBe(100)

    useLocationStore.getState().setRadius(30000)
    expect(useLocationStore.getState().radiusMeters).toBe(10000)

    useLocationStore.getState().setRadius(10000)
    expect(useLocationStore.getState().radiusMeters).toBe(10000)
  })

  it('toggles deliveryOnly boolean', () => {
    expect(useLocationStore.getState().deliveryOnly).toBe(false)
    useLocationStore.getState().toggleDeliveryOnly()
    expect(useLocationStore.getState().deliveryOnly).toBe(true)
    useLocationStore.getState().toggleDeliveryOnly()
    expect(useLocationStore.getState().deliveryOnly).toBe(false)
  })

  it('sets custom location', () => {
    useLocationStore.getState().setLocation({ latitude: 12.91, longitude: 77.62 }, 'Custom Spot', true)
    const state = useLocationStore.getState()
    expect(state.coords).toEqual({ latitude: 12.91, longitude: 77.62 })
    expect(state.addressLabel).toBe('Custom Spot')
    expect(state.isGps).toBe(true)
  })

  it('setManualCoords sets coords with isGps=false', () => {
    useLocationStore.getState().setManualCoords(25.6144, 85.1158, 'Custom Location')
    const state = useLocationStore.getState()
    expect(state.coords).toEqual({ latitude: 25.6144, longitude: 85.1158 })
    expect(state.addressLabel).toBe('Custom Location')
    expect(state.isGps).toBe(false)
  })

  it('rejects invalid coordinates without replacing the active location', () => {
    useLocationStore.getState().setManualCoords(25.6144, 85.1158, 'Valid Patna location')
    useLocationStore.getState().setLocation(
      { latitude: 95, longitude: 85.1158 },
      'Invalid location',
    )

    const state = useLocationStore.getState()
    expect(state.coords).toEqual({ latitude: 25.6144, longitude: 85.1158 })
    expect(state.locationError).toContain('valid latitude and longitude')
  })

  it('resetToDefault resets to demo Boring Road coords and demo label', () => {
    useLocationStore.getState().setPreset('kankarbagh')
    useLocationStore.getState().resetToDefault()
    const state = useLocationStore.getState()
    expect(state.coords).toEqual({ latitude: 25.6085, longitude: 85.1115 })
    expect(state.addressLabel).toBe('Boring Road, Patna (demo)')
    expect(state.radiusMeters).toBe(5000)
    expect(state.deliveryOnly).toBe(false)
    expect(state.isGps).toBe(false)
    expect(state.locationError).toBeNull()
  })

  it('rejects requestGpsLocation when not in a secure context (HTTPS requirement)', async () => {
    const originalSecureContext = window.isSecureContext
    try {
      Object.defineProperty(window, 'isSecureContext', {
        value: false,
        writable: true,
        configurable: true,
      })

      const success = await useLocationStore.getState().requestGpsLocation()
      expect(success).toBe(false)
      expect(useLocationStore.getState().locationError).toContain('secure HTTPS connection')
      expect(useLocationStore.getState().isLocating).toBe(false)
    } finally {
      Object.defineProperty(window, 'isSecureContext', {
        value: originalSecureContext ?? true,
        writable: true,
        configurable: true,
      })
    }
  })

  it('handles GPS permission denied error gracefully', async () => {
    Object.defineProperty(window, 'isSecureContext', {
      value: true,
      writable: true,
      configurable: true,
    })

    const mockGeolocation = {
      getCurrentPosition: (
        _success: (pos: any) => void,
        error: (err: any) => void
      ) => {
        error({ code: 1, PERMISSION_DENIED: 1, message: 'User denied geolocation' })
      },
    }
    Object.defineProperty(navigator, 'geolocation', {
      value: mockGeolocation,
      writable: true,
      configurable: true,
    })

    const success = await useLocationStore.getState().requestGpsLocation()
    expect(success).toBe(false)
    expect(useLocationStore.getState().locationError).toContain('Location permission was denied')
  })
})
