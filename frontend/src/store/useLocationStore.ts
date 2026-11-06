import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface Coordinates {
  latitude: number
  longitude: number
}

export const DEFAULT_DELIVERY_RADIUS_METERS = 5000
export const DELIVERY_LIMIT_METERS = 5000
export const DELIVERY_LIMIT_KM = 5

export const PATNA_BOUNDING_BOX = {
  minLat: 25.50,
  maxLat: 25.70,
  minLon: 85.00,
  maxLon: 85.25,
}

export const isInPatnaBoundingBox = (coords: Coordinates | null): boolean => {
  if (!coords) return false
  return (
    coords.latitude >= PATNA_BOUNDING_BOX.minLat &&
    coords.latitude <= PATNA_BOUNDING_BOX.maxLat &&
    coords.longitude >= PATNA_BOUNDING_BOX.minLon &&
    coords.longitude <= PATNA_BOUNDING_BOX.maxLon
  )
}

export const DEMO_PATNA_LOCATION: { coords: Coordinates; label: string } = {
  coords: { latitude: 25.6085, longitude: 85.1115 },
  label: 'Boring Road, Patna (demo)',
}

export const isValidCoordinates = (coords: Coordinates): boolean =>
  Number.isFinite(coords.latitude) &&
  Number.isFinite(coords.longitude) &&
  coords.latitude >= -90 &&
  coords.latitude <= 90 &&
  coords.longitude >= -180 &&
  coords.longitude <= 180

export const haversineDistanceKm = (
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number
): number => {
  const R = 6371
  const dLat = ((lat2 - lat1) * Math.PI) / 180
  const dLon = ((lon2 - lon1) * Math.PI) / 180
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2)
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
  return R * c
}

export interface LocationPreset {
  id: string
  name: string
  area: string
  coords: Coordinates
}

export const LOCATION_PRESETS: LocationPreset[] = [
  {
    id: 'boring-road',
    name: 'Boring Road, Patna (demo)',
    area: 'Central Patna',
    coords: { latitude: 25.6085, longitude: 85.1115 },
  },
  {
    id: 'kankarbagh',
    name: 'Kankarbagh Main Road',
    area: 'South Patna',
    coords: { latitude: 25.5947, longitude: 85.1588 },
  },
  {
    id: 'rajendra-nagar',
    name: 'Rajendra Nagar Market',
    area: 'East Patna',
    coords: { latitude: 25.6022, longitude: 85.1633 },
  },
  {
    id: 'bailey-road',
    name: 'Bailey Road / Raja Bazar',
    area: 'West Patna',
    coords: { latitude: 25.6083, longitude: 85.0892 },
  },
]

interface LocationState {
  coords: Coordinates | null
  addressLabel: string
  radiusMeters: number
  deliveryOnly: boolean
  isGps: boolean
  isGpsDenied: boolean
  isLocating: boolean
  locationError: string | null

  setLocation: (coords: Coordinates, label: string, isGps?: boolean) => void
  setManualCoords: (lat: number, lon: number, label: string) => void
  setPreset: (presetId: string) => void
  setDemoPatnaLocation: () => void
  setRadius: (meters: number) => void
  setDeliveryOnly: (only: boolean) => void
  toggleDeliveryOnly: () => void
  requestGpsLocation: () => Promise<boolean>
  clearError: () => void
  resetToDefault: () => void
}

export const useLocationStore = create<LocationState>()(
  persist(
    (set) => ({
      coords: DEMO_PATNA_LOCATION.coords,
      addressLabel: DEMO_PATNA_LOCATION.label,
      radiusMeters: DEFAULT_DELIVERY_RADIUS_METERS,
      deliveryOnly: false,
      isGps: false,
      isGpsDenied: false,
      isLocating: false,
      locationError: null,

      setLocation: (coords, label, isGps = false) => {
        if (!isValidCoordinates(coords)) {
          set({
            locationError: 'Please provide valid latitude and longitude coordinates.',
            isLocating: false,
          })
          return
        }
        set({ coords, addressLabel: label, isGps, isGpsDenied: false, locationError: null })
      },

      setManualCoords: (lat, lon, label) => {
        const coords = { latitude: lat, longitude: lon }
        if (!isValidCoordinates(coords)) {
          set({ locationError: 'Please provide valid latitude and longitude coordinates.' })
          return
        }
        set({ coords, addressLabel: label, isGps: false, isGpsDenied: false, locationError: null })
      },

      setPreset: (presetId) => {
        const found = LOCATION_PRESETS.find((p) => p.id === presetId)
        if (found) {
          set({
            coords: found.coords,
            addressLabel: found.name,
            isGps: false,
            isGpsDenied: false,
            locationError: null,
          })
        }
      },

      setDemoPatnaLocation: () => {
        set({
          coords: DEMO_PATNA_LOCATION.coords,
          addressLabel: DEMO_PATNA_LOCATION.label,
          isGps: false,
          isGpsDenied: false,
          locationError: null,
        })
      },

      setRadius: (meters) => set({ radiusMeters: Math.max(100, Math.min(meters, 10000)) }),

      setDeliveryOnly: (deliveryOnly) => set({ deliveryOnly }),

      toggleDeliveryOnly: () => set((state) => ({ deliveryOnly: !state.deliveryOnly })),

      clearError: () => set({ locationError: null, isGpsDenied: false }),

      resetToDefault: () =>
        set({
          coords: DEMO_PATNA_LOCATION.coords,
          addressLabel: DEMO_PATNA_LOCATION.label,
          radiusMeters: DEFAULT_DELIVERY_RADIUS_METERS,
          deliveryOnly: false,
          isGps: false,
          isGpsDenied: false,
          locationError: null,
        }),

      requestGpsLocation: async () => {
        if (typeof window !== 'undefined' && window.isSecureContext === false) {
          set({
            locationError:
              'Geolocation requires a secure HTTPS connection. Please access Dukaanly via HTTPS or select a location manually.',
            isLocating: false,
            isGpsDenied: true,
          })
          return false
        }

        if (!navigator.geolocation) {
          set({
            locationError: 'Geolocation is not supported by your browser.',
            isLocating: false,
            isGpsDenied: true,
          })
          return false
        }

        set({ isLocating: true, locationError: null })

        return new Promise<boolean>((resolve) => {
          navigator.geolocation.getCurrentPosition(
            (position) => {
              const newCoords: Coordinates = {
                latitude: Number(position.coords.latitude.toFixed(6)),
                longitude: Number(position.coords.longitude.toFixed(6)),
              }
              if (!isValidCoordinates(newCoords)) {
                set({
                  locationError: 'Your device returned invalid location coordinates.',
                  isLocating: false,
                })
                resolve(false)
                return
              }

              const inPatna = isInPatnaBoundingBox(newCoords)
              set({
                coords: newCoords,
                addressLabel: inPatna ? 'My GPS Location (Patna)' : 'My GPS Location (Outside Patna)',
                isGps: true,
                isGpsDenied: false,
                isLocating: false,
                locationError: inPatna
                  ? null
                  : 'You are outside our Patna delivery service area. Switch to our demo location to explore partner stores and ordering.',
              })
              resolve(true)
            },
            (err) => {
              const denied = err.code === err.PERMISSION_DENIED
              let msg = 'Unable to fetch your device location.'
              if (denied) {
                msg =
                  typeof window !== 'undefined' && window.isSecureContext === false
                    ? 'Geolocation requires a secure HTTPS connection.'
                    : 'Location permission was denied. Explore Dukaanly with a Patna demo location.'
              } else if (err.code === err.POSITION_UNAVAILABLE) {
                msg = 'Location information is unavailable on this device.'
              } else if (err.code === err.TIMEOUT) {
                msg = 'GPS location request timed out.'
              }
              set({
                locationError: msg,
                isLocating: false,
                isGpsDenied: denied,
              })
              resolve(false)
            },
            {
              enableHighAccuracy: true,
              timeout: 10000,
              maximumAge: 60000,
            }
          )
        })
      },
    }),
    {
      name: 'dukaanly-customer-location',
      partialize: (state) => ({
        coords: state.coords,
        addressLabel: state.addressLabel,
        radiusMeters: state.radiusMeters,
        deliveryOnly: state.deliveryOnly,
        isGps: state.isGps,
      }),
      onRehydrateStorage: () => (state) => {
        if (!state?.coords || !state?.addressLabel) {
          state?.setDemoPatnaLocation()
        }
      },
    }
  )
)
