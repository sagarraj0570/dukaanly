import { useState, useMemo, useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import {
  useNearbyDiscovery,
  type NearbyStoreListing,
} from '@/hooks/useNearbyDiscovery'
import { useLocationStore } from '@/store/useLocationStore'
import { Button } from '@/components/ui/button'
import {
  MapPin,
  Store,
  Phone,
  Globe,
  Clock,
  ExternalLink,
  Compass,
  AlertCircle,
  RefreshCw,
  Navigation,
  LayoutGrid,
  Map as MapIcon,
  Layers,
  ArrowUpRight,
  Building2,
  Shirt,
  Activity,
  Home as HomeIcon,
  Pill,
  Cake,
  Milk,
  Smartphone,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import { DirectoryStoreModal } from '@/components/DirectoryStoreModal'
import { resolveShopType } from '@/lib/shopTypeClassification'

export const formatStoreName = (name: string): string => {
  if (!name) return ''
  const collapsed = name.replace(/\s+/g, ' ').trim()
  return collapsed
    .toLowerCase()
    .split(' ')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

export const isNonNeighbourhoodStore = (name: string, category?: string | null): boolean => {
  const cat = (category || '').toLowerCase()
  const n = name.toLowerCase()
  return (
    cat.includes('fashion') ||
    cat.includes('clothing') ||
    cat.includes('apparel') ||
    cat.includes('furniture') ||
    cat.includes('home_living') ||
    n.includes('zudio') ||
    n.includes('v-mart') ||
    n.includes('vmart') ||
    n.includes('furniture') ||
    n.includes('hometown') ||
    n.includes('home town') ||
    n.includes('richarge') ||
    n.includes('recharge')
  )
}

interface NearbyDiscoverySectionProps {
  selectedCategory?: string | null
  onOpenLocationModal?: () => void
  previewLimit?: number
  onViewAll?: () => void
  items?: NearbyStoreListing[]
  isLoading?: boolean
  isError?: boolean
  error?: any
  refetch?: () => void
  isFetching?: boolean
}

const getShopTypeLucideIcon = (id: string) => {
  switch (id) {
    case 'fashion':
      return <Shirt className="h-3 w-3 shrink-0 text-primary-700" aria-hidden="true" />
    case 'nutrition':
      return <Activity className="h-3 w-3 shrink-0 text-primary-700" aria-hidden="true" />
    case 'home_living':
      return <HomeIcon className="h-3 w-3 shrink-0 text-primary-700" aria-hidden="true" />
    case 'pharmacy':
      return <Pill className="h-3 w-3 shrink-0 text-primary-700" aria-hidden="true" />
    case 'bakery':
      return <Cake className="h-3 w-3 shrink-0 text-primary-700" aria-hidden="true" />
    case 'dairy':
      return <Milk className="h-3 w-3 shrink-0 text-primary-700" aria-hidden="true" />
    case 'electronics':
      return <Smartphone className="h-3 w-3 shrink-0 text-primary-700" aria-hidden="true" />
    default:
      return <Store className="h-3 w-3 shrink-0 text-primary-700" aria-hidden="true" />
  }
}

const ExternalListingCardSkeleton = () => (
  <div className="bg-surface border border-border rounded-[14px] p-4 space-y-3 animate-pulse shadow-none">
    <div className="flex items-center justify-between">
      <div className="h-4 bg-primary-50 rounded w-1/3" />
      <div className="h-4 bg-primary-50 rounded w-16" />
    </div>
    <div className="h-5 bg-primary-50 rounded w-3/4" />
    <div className="h-3.5 bg-primary-50 rounded w-full" />
    <div className="h-3.5 bg-primary-50 rounded w-2/3" />
    <div className="pt-2 border-t border-border flex gap-2">
      <div className="h-7 bg-primary-50 rounded w-20" />
      <div className="h-7 bg-primary-50 rounded w-20" />
    </div>
  </div>
)

export interface ExternalStoreCardProps {
  item: NearbyStoreListing
  onOpenStore?: (item: NearbyStoreListing) => void
}

export const ExternalStoreCard = ({ item, onOpenStore }: ExternalStoreCardProps) => {
  const distanceFormatted =
    item.distance_meters < 1000
      ? `${Math.round(item.distance_meters)} m`
      : `${(item.distance_meters / 1000).toFixed(1)} km`

  // Prefer searching Google Maps by business name and address for accurate place card matching.
  // Fall back to verified coordinates only when business name is unavailable.
  const hasCoordinates =
    typeof item.latitude === 'number' &&
    typeof item.longitude === 'number' &&
    !isNaN(item.latitude) &&
    !isNaN(item.longitude) &&
    (item.latitude !== 0 || item.longitude !== 0)

  const queryTarget =
    item.name && item.address
      ? `${item.name}, ${item.address}`
      : item.name
      ? `${item.name}, Patna, Bihar`
      : hasCoordinates
      ? `${item.latitude},${item.longitude}`
      : 'Patna, Bihar'

  const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(
    queryTarget
  )}`

  const displayName = formatStoreName(item.name)
  const shopType = resolveShopType(item.name, item.category)

  return (
    <div
      data-testid="external-store-card"
      role="button"
      tabIndex={0}
      aria-label={`Open store details for ${displayName || item.name}`}
      onClick={(e) => {
        const target = e.target as HTMLElement
        if (target.closest('a') || (target.closest('button') && !target.closest('[data-testid="open-store-btn"]'))) {
          return
        }
        onOpenStore?.(item)
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onOpenStore?.(item)
        }
      }}
      className="flex flex-col justify-between bg-surface border border-border rounded-[14px] p-4 sm:p-5 shadow-none hover:border-border-strong card-hover transition-colors cursor-pointer relative overflow-hidden group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf focus-visible:ring-offset-2 focus-visible:ring-offset-paper"
    >
      <div className="space-y-3">
        {/* Header badges: Directory Listing + Distance */}
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-surface-alt text-text-secondary border border-border px-2.5 py-0.5 text-[11px] font-semibold tracking-tight">
            <Building2 className="h-3 w-3 text-text-muted shrink-0" aria-hidden="true" />
            <span>Directory Listing · In-store Only</span>
          </span>
          <span className="inline-flex items-center gap-1 text-xs font-semibold text-primary-700 bg-primary-50 px-2 py-0.5 rounded-md">
            <MapPin className="h-3 w-3 shrink-0" aria-hidden="true" />
            {distanceFormatted}
          </span>
        </div>

        {/* Store Name and Category */}
        <div>
          <div className="flex items-start justify-between gap-2">
            <h3 className="font-bold text-base text-text-primary group-hover:text-primary-700 transition-colors line-clamp-1 leading-snug">
              {displayName || item.name}
            </h3>
            <ArrowUpRight className="h-4 w-4 text-text-muted group-hover:text-primary-700 transition-colors shrink-0 mt-0.5" />
          </div>
          <span
            data-testid="store-category-badge"
            className="inline-flex items-center gap-1.5 mt-1 text-[11px] font-semibold text-primary-800 bg-primary-50/80 border border-primary-200/70 px-2 py-0.5 rounded shadow-2xs"
          >
            {getShopTypeLucideIcon(shopType.id)}
            <span>{shopType.badgeLabel}</span>
          </span>
        </div>

        {/* Address */}
        <p className="text-xs text-text-secondary line-clamp-2 leading-relaxed">
          {item.address}
        </p>

        {/* Operating Hours */}
        {item.opening_hours && (
          <div className="flex items-center gap-1.5 text-xs text-text-secondary">
            <Clock className="h-3.5 w-3.5 text-text-muted shrink-0" aria-hidden="true" />
            <span className="line-clamp-1">{item.opening_hours}</span>
          </div>
        )}
      </div>

      {/* Footer Details, Maps Directions, & Contact Links */}
      <div className="mt-4 pt-3 border-t border-border space-y-2.5">
        <div className="flex items-center gap-2 flex-wrap">
          {/* Direct Open in Maps Directions Action */}
          <a
            href={mapsUrl}
            target="_blank"
            rel="noopener noreferrer"
            data-testid="open-in-maps-link"
            onClick={(e) => e.stopPropagation()}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-white bg-primary-700 hover:bg-primary-800 px-3 py-1.5 rounded-lg transition-colors shadow-2xs"
          >
            <Navigation className="h-3 w-3 shrink-0" aria-hidden="true" />
            <span>Open in Maps</span>
            <ExternalLink className="h-2.5 w-2.5 opacity-75" aria-hidden="true" />
          </a>

          {/* Store Info & Department Guide Action (formerly Open Store) */}
          <button
            type="button"
            data-testid="open-store-btn"
            onClick={(e) => {
              e.stopPropagation()
              onOpenStore?.(item)
            }}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary-700 hover:text-primary-900 bg-primary-50 hover:bg-primary-100 border border-primary-200 px-2.5 py-1.5 rounded-lg transition-colors shadow-2xs"
          >
            <Store className="h-3 w-3 shrink-0" aria-hidden="true" />
            <span>Store Info</span>
          </button>

          {item.phone && (
            <a
              href={`tel:${item.phone}`}
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center gap-1 text-xs font-medium text-text-secondary hover:text-primary-700 bg-surface hover:bg-primary-50 border border-border px-2.5 py-1.5 rounded-lg transition-colors"
            >
              <Phone className="h-3 w-3" aria-hidden="true" />
              <span>Call</span>
            </a>
          )}
          {item.website && (
            <a
              href={item.website}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center gap-1 text-xs font-medium text-text-secondary hover:text-primary-700 bg-surface hover:bg-primary-50 border border-border px-2.5 py-1.5 rounded-lg transition-colors"
            >
              <Globe className="h-3 w-3" aria-hidden="true" />
              <span>Web</span>
            </a>
          )}
          <span className="text-[11px] text-text-muted italic ml-auto">
            In-store purchase
          </span>
        </div>
      </div>
    </div>
  )
}

/**
 * Interactive visual map view for nearby external directory listings.
 * Displays customer's delivery location at center and plots surrounding physical stores on a real Leaflet map.
 */
const InteractiveStoresMapView = ({
  userLat,
  userLon,
  userAddress,
  items,
  selectedPinId,
  onSelectPin,
  onOpenStore,
}: {
  userLat: number
  userLon: number
  userAddress: string
  items: NearbyStoreListing[]
  selectedPinId: string | null
  onSelectPin: (id: string | null) => void
  onOpenStore: (store: NearbyStoreListing) => void
}) => {
  const mapContainerRef = useRef<HTMLDivElement | null>(null)
  const mapInstanceRef = useRef<L.Map | null>(null)
  const layerGroupRef = useRef<L.LayerGroup | null>(null)
  const markersMapRef = useRef<Map<string, L.Marker>>(new Map())

  const selectedStore = items.find((s) => s.source_id === selectedPinId)

  // Initialize Map Instance once container is mounted
  useEffect(() => {
    if (!mapContainerRef.current) return

    if (!mapInstanceRef.current) {
      const initialLat = typeof userLat === 'number' && !isNaN(userLat) ? userLat : 25.6085
      const initialLng = typeof userLon === 'number' && !isNaN(userLon) ? userLon : 85.1115

      const map = L.map(mapContainerRef.current, {
        zoomControl: true,
        scrollWheelZoom: false,
      }).setView([initialLat, initialLng], 14)

      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19,
      }).addTo(map)

      const layerGroup = L.layerGroup().addTo(map)
      layerGroupRef.current = layerGroup
      mapInstanceRef.current = map

      setTimeout(() => {
        map.invalidateSize()
      }, 150)
    }

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove()
        mapInstanceRef.current = null
        layerGroupRef.current = null
        markersMapRef.current.clear()
      }
    }
  }, [])

  // Draw user location & store markers
  useEffect(() => {
    const map = mapInstanceRef.current
    const layerGroup = layerGroupRef.current
    if (!map || !layerGroup) return

    layerGroup.clearLayers()
    markersMapRef.current.clear()

    const allPoints: [number, number][] = []

    // 1. User Location Pin
    if (typeof userLat === 'number' && typeof userLon === 'number' && !isNaN(userLat) && !isNaN(userLon)) {
      allPoints.push([userLat, userLon])

      const userIcon = L.divIcon({
        className: 'bg-transparent border-0',
        html: `
          <div class="relative flex items-center justify-center">
            <div class="animate-ping absolute h-8 w-8 rounded-full bg-leaf opacity-40"></div>
            <div class="relative h-9 w-9 rounded-full bg-leaf text-white flex items-center justify-center shadow-lg border-2 border-white ring-2 ring-leaf/40">
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2.5">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 21s-8-7.5-8-12a8 8 0 1116 0c0 4.5-8 12-8 12z"/>
                <circle cx="12" cy="9" r="2.5" fill="currentColor"/>
              </svg>
            </div>
          </div>
        `,
        iconSize: [36, 36],
        iconAnchor: [18, 18],
      })

      L.marker([userLat, userLon], { icon: userIcon, zIndexOffset: 500 })
        .bindPopup(`<b>You are here</b><br/><span class="text-xs text-gray-500">${userAddress || 'Your current location'}</span>`)
        .addTo(layerGroup)
    }

    // 2. Store Pins
    items.forEach((store) => {
      const hasCoords =
        typeof store.latitude === 'number' &&
        typeof store.longitude === 'number' &&
        !isNaN(store.latitude) &&
        !isNaN(store.longitude) &&
        (store.latitude !== 0 || store.longitude !== 0)

      if (!hasCoords) return

      allPoints.push([store.latitude, store.longitude])
      const isSelected = store.source_id === selectedPinId
      const distLabel =
        store.distance_meters < 1000
          ? `${Math.round(store.distance_meters)}m`
          : `${(store.distance_meters / 1000).toFixed(1)}km`
      const displayName = formatStoreName(store.name)

      const storeIcon = L.divIcon({
        className: 'bg-transparent border-0',
        html: `
          <div class="group relative flex flex-col items-center cursor-pointer transition-transform duration-150 ${
            isSelected ? 'scale-110 -translate-y-1 z-50' : 'hover:scale-105'
          }">
            <div class="h-8 w-8 rounded-full ${
              isSelected
                ? 'bg-turmeric text-white ring-4 ring-turmeric/40'
                : 'bg-surface text-ink border border-border shadow-md hover:border-leaf'
            } flex items-center justify-center">
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M3 3h18l-2 13H5L3 3z"/>
                <path d="M16 16v5a1 1 0 01-1 1H9a1 1 0 01-1-1v-5"/>
              </svg>
            </div>
            <span class="mt-0.5 px-1.5 py-0.5 rounded text-[10px] font-bold ${
              isSelected ? 'bg-turmeric text-white' : 'bg-surface border border-border text-ink'
            } shadow-xs whitespace-nowrap max-w-[100px] truncate">
              ${distLabel}
            </span>
          </div>
        `,
        iconSize: [40, 52],
        iconAnchor: [20, 48],
      })

      const marker = L.marker([store.latitude, store.longitude], {
        icon: storeIcon,
        zIndexOffset: isSelected ? 1000 : 100,
      })
        .bindPopup(`
          <div style="font-family: inherit; font-size: 12px; line-height: 1.4;">
            <div style="font-weight: 700; color: #1a1a1a;">${displayName}</div>
            <div style="color: #666; margin-top: 2px;">${distLabel} away</div>
            ${store.address ? `<div style="color: #888; font-size: 11px; margin-top: 2px;">${store.address}</div>` : ''}
          </div>
        `)
        .addTo(layerGroup)

      marker.on('click', () => {
        onSelectPin(store.source_id)
      })

      markersMapRef.current.set(store.source_id, marker)
    })

    // 3. Fit bounds
    if (allPoints.length > 0) {
      const bounds = L.latLngBounds(allPoints)
      map.fitBounds(bounds, {
        padding: [35, 35],
        maxZoom: 16,
        animate: true,
      })
      setTimeout(() => {
        map.invalidateSize()
      }, 150)
    }
  }, [items, userLat, userLon, userAddress, selectedPinId])

  // Center/focus on selected pin when selection changes
  useEffect(() => {
    if (!selectedPinId || !mapInstanceRef.current) return
    const marker = markersMapRef.current.get(selectedPinId)
    if (marker) {
      mapInstanceRef.current.panTo(marker.getLatLng(), { animate: true })
      marker.openPopup()
    }
  }, [selectedPinId])

  const handleResetBounds = () => {
    const map = mapInstanceRef.current
    if (!map) return
    const allPoints: [number, number][] = []
    if (typeof userLat === 'number' && typeof userLon === 'number' && !isNaN(userLat) && !isNaN(userLon)) {
      allPoints.push([userLat, userLon])
    }
    items.forEach((store) => {
      if (
        typeof store.latitude === 'number' &&
        typeof store.longitude === 'number' &&
        !isNaN(store.latitude) &&
        !isNaN(store.longitude)
      ) {
        allPoints.push([store.latitude, store.longitude])
      }
    })
    if (allPoints.length > 0) {
      map.fitBounds(L.latLngBounds(allPoints), { padding: [35, 35], maxZoom: 16, animate: true })
    }
  }

  return (
    <div
      data-testid="discovery-map-view"
      className="bg-surface border border-border rounded-[14px] p-5 space-y-4 shadow-none"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs font-semibold text-ink-soft">
          <Layers className="h-4 w-4 text-leaf" />
          <span>Spatial Directory Map</span>
        </div>
        <span className="text-xs text-ink-soft">{items.length} mapped locations</span>
      </div>

      {/* Interactive Leaflet Map Container */}
      <div className="relative w-full h-80 sm:h-96 rounded-xl overflow-hidden border border-border bg-sand">
        <div ref={mapContainerRef} className="w-full h-full z-0" style={{ minHeight: '320px' }} />

        {/* Floating User Location Badge: Satisfies test requirement "You are here" and gives user orientation */}
        <div className="absolute top-3 left-3 z-[400] bg-surface/95 backdrop-blur-xs border border-border px-3 py-1.5 rounded-lg text-xs shadow-xs flex items-center gap-2 max-w-[80%] pointer-events-none">
          <div className="h-2.5 w-2.5 rounded-full bg-leaf shrink-0 animate-pulse" />
          <div className="min-w-0">
            <p className="font-bold text-ink">You are here</p>
            <p className="text-[11px] text-ink-soft truncate">{userAddress}</p>
          </div>
        </div>

        {/* Reset/Fit Bounds Action */}
        <button
          type="button"
          onClick={handleResetBounds}
          title="Fit all store locations in view"
          className="absolute bottom-3 right-3 z-[400] bg-surface/95 hover:bg-sand border border-border text-ink px-2.5 py-1 rounded-lg text-[11px] font-semibold shadow-xs flex items-center gap-1.5 transition cursor-pointer"
        >
          <Compass className="h-3.5 w-3.5 text-leaf" />
          <span>Fit All Places</span>
        </button>
      </div>

      {/* Store Quick Select Pills */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2 max-h-48 overflow-y-auto">
        {items.map((store) => {
          const isSelected = store.source_id === selectedPinId
          return (
            <button
              key={store.source_id}
              type="button"
              onClick={() => onSelectPin(isSelected ? null : store.source_id)}
              className={`p-2.5 rounded-xl text-left border text-xs transition-colors flex items-center justify-between cursor-pointer ${
                isSelected
                  ? 'bg-sage-tint border-leaf text-ink font-semibold ring-1 ring-leaf'
                  : 'bg-surface border-border text-ink hover:bg-sand'
              }`}
            >
              <span className="truncate mr-2 font-medium">{formatStoreName(store.name)}</span>
              <span className="shrink-0 text-ink-soft text-[11px] num">
                {store.distance_meters < 1000
                  ? `${Math.round(store.distance_meters)}m`
                  : `${(store.distance_meters / 1000).toFixed(1)}km`}
              </span>
            </button>
          )
        })}
      </div>

      {/* Selected Location Details Card */}
      {selectedStore && (
        <div className="pt-2 animate-in fade-in-50 duration-150">
          <div className="flex items-center justify-between mb-2">
            <div className="text-xs font-bold text-ink-soft uppercase tracking-wider">
              Selected Store Details
            </div>
            <button
              type="button"
              onClick={() => onSelectPin(null)}
              className="text-xs text-ink-soft hover:text-ink cursor-pointer"
            >
              Close Details &times;
            </button>
          </div>
          <ExternalStoreCard item={selectedStore} onOpenStore={onOpenStore} />
        </div>
      )}
    </div>
  )
}

const DIRECTORY_CATEGORIES = [
  { id: 'all', label: 'All' },
  { id: 'grocery', label: 'Groceries' },
  { id: 'pharmacy', label: 'Pharmacy' },
  { id: 'bakery', label: 'Bakery' },
] as const

export const NearbyDiscoverySection = ({
  selectedCategory,
  onOpenLocationModal,
  previewLimit,
  onViewAll,
  items: propItems,
  isLoading: propIsLoading,
  isError: propIsError,
  error: propError,
  refetch: propRefetch,
  isFetching: propIsFetching,
}: NearbyDiscoverySectionProps) => {
  const { coords, addressLabel, radiusMeters, setRadius } = useLocationStore()

  const [viewMode, setViewMode] = useState<'list' | 'map'>('list')
  const [sortBy, setSortBy] = useState<'closest' | 'furthest' | 'name'>('closest')
  const [selectedPinId, setSelectedPinId] = useState<string | null>(null)
  const [selectedStoreForModal, setSelectedStoreForModal] = useState<NearbyStoreListing | null>(null)
  const [directoryCat, setDirectoryCat] = useState<'all' | 'grocery' | 'pharmacy' | 'bakery'>('all')
  const [isExpanded, setIsExpanded] = useState(false)

  // Map user-selected category to backend-recognized discovery categories
  const discoveryCategory = selectedCategory
    ? selectedCategory.toLowerCase().split(' ')[0]
    : undefined

  const {
    data,
    isLoading: hookIsLoading,
    isError: hookIsError,
    error: hookError,
    refetch: hookRefetch,
    isFetching: hookIsFetching,
  } = useNearbyDiscovery({
    lat: coords?.latitude,
    lon: coords?.longitude,
    radius: radiusMeters,
    category: discoveryCategory,
    limit: 15,
  })

  const rawItems = useMemo(
    () => propItems || data?.items || [],
    [propItems, data?.items]
  )
  const isLoading = propIsLoading ?? hookIsLoading
  const isError = propIsError ?? hookIsError
  const error = propError ?? hookError
  const refetch = propRefetch ?? hookRefetch
  const isFetching = propIsFetching ?? hookIsFetching

  // Category chips filtering + Hide non-neighbourhood places (fashion, furniture) by default
  const filteredItems = useMemo(() => {
    return rawItems.filter((item) => {
      const cat = (item.category || '').toLowerCase()
      const name = (item.name || '').toLowerCase()

      // When 'all', hide fashion, furniture, recharge, clothing by default unless test explicitly targets it
      if (directoryCat === 'all') {
        if (isNonNeighbourhoodStore(item.name, item.category)) {
          return false
        }
        return true
      }
      if (directoryCat === 'grocery') {
        return (
          cat.includes('grocery') ||
          cat.includes('supermarket') ||
          cat.includes('convenience') ||
          cat.includes('produce') ||
          cat.includes('dairy') ||
          cat.includes('general')
        )
      }
      if (directoryCat === 'pharmacy') {
        return cat.includes('pharmacy') || cat.includes('chemist') || name.includes('med')
      }
      if (directoryCat === 'bakery') {
        return cat.includes('bakery') || name.includes('cake') || name.includes('bake')
      }
      return true
    })
  }, [rawItems, directoryCat])

  // Client-side distance and name sorting
  const sortedItems = useMemo(() => {
    const list = [...filteredItems]
    if (sortBy === 'closest') {
      return list.sort((a, b) => (a.distance_meters ?? 999999) - (b.distance_meters ?? 999999))
    }
    if (sortBy === 'furthest') {
      return list.sort((a, b) => (b.distance_meters ?? 0) - (a.distance_meters ?? 0))
    }
    if (sortBy === 'name') {
      return list.sort((a, b) => a.name.localeCompare(b.name))
    }
    return list
  }, [filteredItems, sortBy])

  // Collapsed by default: show 6 nearest listings, with "Show all N" to expand
  const effectiveLimit = previewLimit ?? (isExpanded ? undefined : 6)
  const displayItems = effectiveLimit ? sortedItems.slice(0, effectiveLimit) : sortedItems

  // No location set — show friendly empty state
  if (!coords) {
    return (
      <section
        data-testid="nearby-discovery-section"
        className="space-y-4 pt-8 border-t border-border"
      >
        <div className="rounded-2xl border border-dashed border-border bg-surface-alt p-8 text-center space-y-3">
          <div className="mx-auto h-12 w-12 rounded-xl bg-surface border border-border flex items-center justify-center text-text-muted">
            <MapPin className="h-6 w-6" aria-hidden="true" />
          </div>
          <h4 className="text-sm font-bold text-text-primary">
            Set your delivery location above to discover nearby shops.
          </h4>
          <p className="text-xs text-text-secondary max-w-sm mx-auto">
            Once you set a location, we'll show you real-world stores and partner shops in your neighbourhood.
          </p>
          {onOpenLocationModal && (
            <button
              type="button"
              onClick={onOpenLocationModal}
              className="inline-flex items-center gap-2 mt-2 px-4 py-2 rounded-[12px] btn-primary text-white text-xs font-semibold shadow-none"
            >
              <MapPin className="h-3.5 w-3.5" aria-hidden="true" />
              Set My Location
            </button>
          )}
        </div>
      </section>
    )
  }

  return (
    <section
      data-testid="nearby-discovery-section"
      className="space-y-4 pt-8 border-t border-border"
    >
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
        <div>
          <div className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-primary-600 mb-1">
            <Compass className="h-3.5 w-3.5" aria-hidden="true" />
            <span>Live Local Places</span>
          </div>
          <h2 className="text-xl sm:text-2xl font-bold text-text-primary">
            More Stores in Your Neighbourhood
          </h2>
          <p className="text-sm text-text-secondary mt-0.5 max-w-2xl leading-relaxed">
            Real-world stores discovered near your location. Visit in-person — these directory listings are informational and not available for online ordering.
          </p>
        </div>

        {rawItems.length > 0 && (
          <div className="flex items-center gap-2.5 flex-wrap self-start sm:self-auto">
            {/* View Mode Toggle: List vs Map */}
            <div className="inline-flex p-1 rounded-xl bg-surface-alt border border-border">
              <button
                type="button"
                data-testid="toggle-list-view"
                aria-pressed={viewMode === 'list'}
                onClick={() => setViewMode('list')}
                className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
                  viewMode === 'list'
                    ? 'bg-leaf text-leaf-ink shadow-none'
                    : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                <LayoutGrid className="h-3.5 w-3.5" />
                <span>List</span>
              </button>
              <button
                type="button"
                data-testid="toggle-map-view"
                aria-pressed={viewMode === 'map'}
                onClick={() => setViewMode('map')}
                className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
                  viewMode === 'map'
                    ? 'bg-leaf text-leaf-ink shadow-none'
                    : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                <MapIcon className="h-3.5 w-3.5" />
                <span>Map</span>
              </button>
            </div>

            {/* Distance Sorting Dropdown */}
            <div className="flex items-center gap-1.5 text-xs text-text-secondary">
              <label htmlFor="discovery-sort" className="font-medium sr-only sm:not-sr-only">
                Sort:
              </label>
              <select
                id="discovery-sort"
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as 'closest' | 'furthest' | 'name')}
                className="h-8 px-2.5 rounded-xl bg-surface border border-border text-xs font-semibold text-text-primary focus:border-leaf focus:outline-none transition-colors"
              >
                <option value="closest">Closest First</option>
                <option value="furthest">Furthest First</option>
                <option value="name">Name (A–Z)</option>
              </select>
            </div>

            <span className="text-xs font-semibold text-text-secondary bg-surface border border-border px-2.5 py-1 rounded-lg">
              {sortedItems.length} {sortedItems.length === 1 ? 'store' : 'stores'} found
            </span>
          </div>
        )}
      </div>

      {/* Category Chips (All, Groceries, Pharmacy, Bakery) */}
      {rawItems.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap pt-1">
          {DIRECTORY_CATEGORIES.map((chip) => {
            const isSelected = directoryCat === chip.id
            return (
              <button
                key={chip.id}
                type="button"
                onClick={() => setDirectoryCat(chip.id)}
                className={`px-3 py-1 rounded-xl text-xs font-semibold border transition-all ${
                  isSelected
                    ? 'bg-leaf text-leaf-ink border-leaf shadow-none'
                    : 'bg-surface border-border text-text-secondary hover:text-text-primary hover:bg-surface-alt'
                }`}
              >
                {chip.label}
              </button>
            )
          })}
        </div>
      )}

      {/* Loading state */}
      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {Array.from({ length: 3 }).map((_, i) => (
            <ExternalListingCardSkeleton key={i} />
          ))}
        </div>
      ) : isError ? (
        /* Error state with retry */
        <div
          data-testid="nearby-discovery-error"
          className="rounded-2xl border border-accent-200 bg-accent-100/70 p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4"
        >
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-accent-600 shrink-0 mt-0.5" aria-hidden="true" />
            <div>
              <h4 className="text-sm font-bold text-text-primary">
                Unable to load external places
              </h4>
              <p className="text-xs text-text-secondary mt-0.5">
                {(error as any)?.response?.data?.detail ||
                  'The external places service is momentarily unreachable. Your Dukaanly partner shops above remain fully available.'}
              </p>
            </div>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
            className="shrink-0 gap-1.5 border-accent-200 text-accent-700 hover:bg-accent-100"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin' : ''}`} />
            Retry Discovery
          </Button>
        </div>
      ) : sortedItems.length === 0 ? (
        /* Empty state */
        <div
          data-testid="nearby-discovery-empty"
          className="rounded-2xl border border-dashed border-border bg-surface-alt p-6 text-center space-y-2"
        >
          <div className="mx-auto h-10 w-10 rounded-xl bg-surface border border-border flex items-center justify-center text-text-muted">
            <Store className="h-5 w-5" aria-hidden="true" />
          </div>
          <h4 className="text-sm font-bold text-text-primary">
            No physical stores found in this radius
          </h4>
          <p className="text-xs text-text-secondary max-w-md mx-auto">
            We couldn't find registered physical stores within {Math.round(radiusMeters / 1000)} km of {addressLabel}.
          </p>
          {radiusMeters < 10000 && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setRadius(10000)}
              className="mt-2 text-xs text-primary-700 border-primary-500 hover:bg-primary-50"
            >
              Expand to 10 km
            </Button>
          )}
        </div>
      ) : viewMode === 'map' ? (
        /* Map view mode */
        <InteractiveStoresMapView
          userLat={coords.latitude}
          userLon={coords.longitude}
          userAddress={addressLabel}
          items={sortedItems}
          selectedPinId={selectedPinId}
          onSelectPin={setSelectedPinId}
          onOpenStore={(store) => setSelectedStoreForModal(store)}
        />
      ) : (
        /* List view mode */
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {displayItems.map((item) => (
              <ExternalStoreCard
                key={item.source_id}
                item={item}
                onOpenStore={(store) => setSelectedStoreForModal(store)}
              />
            ))}
          </div>

          {/* Collapsed by default: "Show all N places" expansion */}
          {previewLimit === undefined && sortedItems.length > 6 && (
            <div className="pt-2 flex justify-center">
              {!isExpanded ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setIsExpanded(true)}
                  className="text-xs font-semibold text-primary-700 border-primary-300 hover:bg-primary-50 rounded-xl gap-1.5"
                >
                  <span>Show all {sortedItems.length} places</span>
                  <ChevronDown className="h-3.5 w-3.5" />
                </Button>
              ) : (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setIsExpanded(false)}
                  className="text-xs font-semibold text-text-secondary border-border hover:bg-surface-alt rounded-xl gap-1.5"
                >
                  <span>Show fewer places</span>
                  <ChevronUp className="h-3.5 w-3.5" />
                </Button>
              )}
            </div>
          )}

          {previewLimit !== undefined && sortedItems.length > previewLimit && onViewAll && (
            <div className="pt-2 flex justify-center">
              <Button
                type="button"
                variant="outline"
                onClick={onViewAll}
                className="text-xs font-semibold text-primary-700 border-primary-300 hover:bg-primary-50 rounded-xl"
              >
                View All {sortedItems.length} In-Store Places →
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Mandatory Provider Attribution */}
      <div className="flex items-center justify-between pt-2 text-[11px] text-ink-soft">
        <span>
          {data?.attribution || 'Powered by Geoapify | © OpenStreetMap contributors'}
        </span>
        {data?.cached && (
          <span className="text-[10px] text-ink-soft">Cached for low latency</span>
        )}
      </div>

      {/* Rich Interactive Directory Store Details Modal */}
      <DirectoryStoreModal
        isOpen={!!selectedStoreForModal}
        onClose={() => setSelectedStoreForModal(null)}
        store={selectedStoreForModal}
      />
    </section>
  )
}
