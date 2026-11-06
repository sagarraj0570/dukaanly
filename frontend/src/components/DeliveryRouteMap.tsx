import React, { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { DeliveryRoute } from '@/hooks/useDeliveries'
import { Navigation, Compass, Info, CheckCircle2, AlertTriangle, RotateCw } from 'lucide-react'
import { StatusStamp } from '@/components/ui/StatusStamp'

interface DeliveryRouteMapProps {
  route: DeliveryRoute | null | undefined
  liveRiderLocation?: { latitude: number; longitude: number } | null
  fallbackCustomerLocation?: { latitude: number; longitude: number; name?: string } | null
  fallbackShopLocation?: { latitude: number; longitude: number; name?: string } | null
  className?: string
  isLoading?: boolean
  isError?: boolean
  errorMessage?: string
  onRetry?: () => void
  isTerminal?: boolean
  terminalStatus?: 'delivered' | 'cancelled' | null
}

const sanitizeRouteErrorMessage = (msg?: string): string => {
  if (!msg) {
    return 'Road route navigation temporarily unavailable. Real-time direct tracking remains active.'
  }
  const lower = msg.toLowerCase()
  if (
    lower.includes('status code') ||
    lower.includes('504') ||
    lower.includes('502') ||
    lower.includes('500') ||
    lower.includes('network error') ||
    lower.includes('axioserror')
  ) {
    return 'Road route navigation temporarily unavailable. Real-time direct tracking remains active.'
  }
  return msg
}

export const DeliveryRouteMap: React.FC<DeliveryRouteMapProps> = ({
  route,
  liveRiderLocation,
  fallbackCustomerLocation,
  fallbackShopLocation,
  className = '',
  isLoading = false,
  isError = false,
  errorMessage,
  onRetry,
  isTerminal = false,
  terminalStatus = null,
}) => {
  const isTerminalResolved =
    isTerminal ||
    terminalStatus === 'cancelled' ||
    terminalStatus === 'delivered' ||
    route?.status === 'cancelled' ||
    route?.status === 'delivered'
  const resolvedTerminalStatus: 'delivered' | 'cancelled' | null =
    terminalStatus ||
    (route?.status === 'cancelled' ? 'cancelled' : route?.status === 'delivered' ? 'delivered' : null)

  const mapContainerRef = useRef<HTMLDivElement | null>(null)
  const mapInstanceRef = useRef<L.Map | null>(null)
  const riderMarkerRef = useRef<L.Marker | null>(null)
  const layerGroupRef = useRef<L.LayerGroup | null>(null)

  // Initialize Map Instance once container is mounted
  useEffect(() => {
    if (!mapContainerRef.current) return

    if (!mapInstanceRef.current) {
      const initialLat =
        route?.shop_location?.latitude ??
        fallbackShopLocation?.latitude ??
        liveRiderLocation?.latitude ??
        fallbackCustomerLocation?.latitude ??
        25.6144
      const initialLng =
        route?.shop_location?.longitude ??
        fallbackShopLocation?.longitude ??
        liveRiderLocation?.longitude ??
        fallbackCustomerLocation?.longitude ??
        85.1158

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
      }, 100)
      setTimeout(() => {
        map.invalidateSize()
      }, 300)

      let resizeObserver: ResizeObserver | null = null
      if (typeof ResizeObserver !== 'undefined' && mapContainerRef.current) {
        resizeObserver = new ResizeObserver(() => {
          map.invalidateSize()
        })
        resizeObserver.observe(mapContainerRef.current)
      }

      return () => {
        if (resizeObserver) {
          resizeObserver.disconnect()
        }
        if (mapInstanceRef.current) {
          mapInstanceRef.current.remove()
          mapInstanceRef.current = null
          layerGroupRef.current = null
          riderMarkerRef.current = null
        }
      }
    }
  }, [])

  // Draw Route, Legs, and Markers when route data arrives or changes
  useEffect(() => {
    const map = mapInstanceRef.current
    const layerGroup = layerGroupRef.current
    if (!map || !layerGroup) return

    layerGroup.clearLayers()
    riderMarkerRef.current = null

    const allPoints: [number, number][] = []

    // 1. Shop Marker (if available)
    const activeShopLoc = route?.shop_location ?? fallbackShopLocation
    if (activeShopLoc) {
      const shopLat = activeShopLoc.latitude
      const shopLng = activeShopLoc.longitude
      allPoints.push([shopLat, shopLng])

      const shopIcon = L.divIcon({
        className: 'bg-transparent border-0',
        html: `
          <div class="h-9 w-9 rounded-full bg-primary-900 text-white flex items-center justify-center shadow-lg border-2 border-white ring-2 ring-primary-900/30">
            <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M3 3h18l-2 13H5L3 3z"/><path d="M16 16v5a1 1 0 01-1 1H9a1 1 0 01-1-1v-5"/></svg>
          </div>
        `,
        iconSize: [36, 36],
        iconAnchor: [18, 18],
      })

      L.marker([shopLat, shopLng], { icon: shopIcon })
        .bindPopup(`<b>${activeShopLoc.name || 'Merchant Store'}</b><br/><span class="text-xs text-gray-500">Merchant Store</span>`)
        .addTo(layerGroup)
    }

    // 2. Customer Destination Marker (if available)
    const activeCustLoc = route?.customer_location ?? fallbackCustomerLocation
    if (activeCustLoc) {
      const custLat = activeCustLoc.latitude
      const custLng = activeCustLoc.longitude
      allPoints.push([custLat, custLng])

      const customerIcon = L.divIcon({
        className: 'bg-transparent border-0',
        html: `
          <div class="h-9 w-9 rounded-full bg-red-600 text-white flex items-center justify-center shadow-lg border-2 border-white ring-2 ring-red-500/30">
            <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M12 21s-8-7.5-8-12a8 8 0 1116 0c0 4.5-8 12-8 12z"/><circle cx="12" cy="9" r="3" fill="currentColor"/></svg>
          </div>
        `,
        iconSize: [36, 36],
        iconAnchor: [18, 36],
      })

      L.marker([custLat, custLng], { icon: customerIcon })
        .bindPopup(`<b>${activeCustLoc.name || 'Delivery Dropoff'}</b><br/><span class="text-xs text-gray-500">Delivery Dropoff</span>`)
        .addTo(layerGroup)
    }

    // 3. Rider Marker
    const activeRiderLoc = liveRiderLocation ?? route?.rider_location
    if (activeRiderLoc) {
      const riderLat = activeRiderLoc.latitude
      const riderLng = activeRiderLoc.longitude
      allPoints.push([riderLat, riderLng])

      const riderIcon = L.divIcon({
        className: 'bg-transparent border-0',
        html: `
          <div class="relative flex items-center justify-center">
            <div class="animate-ping absolute h-8 w-8 rounded-full bg-blue-500 opacity-60"></div>
            <div class="relative h-9 w-9 rounded-full bg-blue-600 text-white flex items-center justify-center shadow-lg border-2 border-white ring-2 ring-blue-500/40">
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
            </div>
          </div>
        `,
        iconSize: [36, 36],
        iconAnchor: [18, 18],
      })

      const marker = L.marker([riderLat, riderLng], { icon: riderIcon, zIndexOffset: 1000 })
        .bindPopup(`<b>Delivery Partner</b><br/><span class="text-xs text-blue-600">On the move</span>`)
        .addTo(layerGroup)

      riderMarkerRef.current = marker
    }

    // 4. Draw Polylines for each Leg
    if (route && route.legs && route.legs.length > 0) {
      route.legs.forEach((leg, index) => {
        // Leg 1 (Pickup: Rider to Shop): dashed blue
        // Leg 2 (Dropoff: Shop to Customer): solid emerald
        const isLeg1Pickup = leg.from_name === 'Rider' || (index === 0 && route.legs.length > 1)
        const legColor = isLeg1Pickup ? '#2B7A9B' : '#1F9D61'
        const isDashed = isLeg1Pickup

        const polyline = L.polyline(leg.geometry, {
          color: legColor,
          weight: 5,
          opacity: 0.9,
          dashArray: isDashed ? '8, 8' : undefined,
          lineCap: 'round',
          lineJoin: 'round',
        })

        polyline.bindTooltip(
          `${leg.from_name} &rarr; ${leg.to_name}: ${(leg.distance_meters / 1000).toFixed(1)} km (~${Math.round(leg.duration_minutes)} min)`,
          { sticky: true }
        )
        polyline.addTo(layerGroup)

        leg.geometry.forEach((pt) => allPoints.push(pt))
      })
    } else if (route && route.combined_geometry && route.combined_geometry.length > 0) {
      L.polyline(route.combined_geometry, {
        color: '#1F9D61',
        weight: 6,
        opacity: 0.9,
        lineCap: 'round',
      }).addTo(layerGroup)

      route.combined_geometry.forEach((pt) => allPoints.push(pt))
    }

    // 5. Fit Map Bounds
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
  }, [route, fallbackCustomerLocation, fallbackShopLocation])

  // Smoothly update Rider Marker position when live location changes
  useEffect(() => {
    if (liveRiderLocation && riderMarkerRef.current) {
      riderMarkerRef.current.setLatLng([liveRiderLocation.latitude, liveRiderLocation.longitude])
    }
  }, [liveRiderLocation])

  const distanceKm = route ? (route.total_distance_meters / 1000).toFixed(1) : '--'
  const durationMin = route ? Math.round(route.total_duration_minutes) : '--'

  return (
    <div className={`overflow-hidden rounded-[14px] border border-border bg-surface shadow-none ${className}`}>
      {/* Route Telemetry HUD Banner */}
      <div className="bg-sand border-b border-border p-3.5 sm:p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className={`h-9 w-9 rounded-xl border flex items-center justify-center shrink-0 ${
              isTerminalResolved
                ? resolvedTerminalStatus === 'cancelled'
                  ? 'bg-brick-tint text-brick-ink border-brick-ink/30'
                  : 'bg-sage-tint text-leaf border-leaf/30'
                : 'bg-surface text-ink-soft border-border'
            }`}>
              <Navigation className="h-4 w-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-ink-soft">
                  {isTerminalResolved
                    ? resolvedTerminalStatus === 'cancelled'
                      ? 'Delivery Cancelled'
                      : 'Delivery Completed'
                    : 'Road Route (OSRM)'}
                </span>
                {isTerminalResolved ? (
                  <StatusStamp tone={resolvedTerminalStatus === 'cancelled' ? 'danger' : 'success'}>
                    {resolvedTerminalStatus === 'cancelled' ? 'Cancelled' : 'Delivered'}
                  </StatusStamp>
                ) : (
                  <>
                    {route && (
                      <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-surface text-ink border border-border">
                        {route.cached ? 'OSRM Cached (5m)' : 'Live OSRM Routing'}
                      </span>
                    )}
                    {isError && (
                      <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-turmeric-tint text-turmeric-ink border border-turmeric-ink/30">
                        Route Unavailable
                      </span>
                    )}
                  </>
                )}
              </div>
              <p className="text-sm font-semibold text-ink">
                {isTerminalResolved ? (
                  <span className="text-xs text-ink-soft font-normal">
                    {resolvedTerminalStatus === 'cancelled'
                      ? 'Delivery was cancelled. Active route tracking ended.'
                      : 'Order delivered to destination.'}
                  </span>
                ) : route ? (
                  <>
                    <span className="num">{distanceKm} km</span>{' '}
                    <span className="text-ink-soft font-normal text-xs sm:text-sm">
                      ({durationMin} mins driving time)
                    </span>
                  </>
                ) : isError ? (
                  <span className="text-xs text-turmeric-ink font-medium">Direct tracking active (OSRM route unavailable)</span>
                ) : (
                  <span className="text-xs text-ink-soft font-medium">Calculating road travel time...</span>
                )}
              </p>
            </div>
          </div>

          {/* Leg Status Pills or Retry Button */}
          {!isTerminalResolved && route && route.legs && route.legs.length > 0 ? (
            <div className="flex items-center gap-2 text-xs">
              {route.legs.map((leg, idx) => {
                const isActive = route.active_leg_index === idx
                const isPast = idx < route.active_leg_index
                return (
                  <div
                    key={idx}
                    className={`px-2.5 py-1 rounded-lg border font-medium flex items-center gap-1.5 ${
                      isActive
                        ? 'bg-sage-tint border-leaf/40 text-leaf'
                        : isPast
                        ? 'bg-sand border-border text-ink-soft line-through'
                        : 'bg-surface border-border text-ink'
                    }`}
                  >
                    {isPast ? (
                      <CheckCircle2 className="h-3 w-3 text-leaf" />
                    ) : (
                      <span className={`h-2 w-2 rounded-full ${isActive ? 'bg-leaf animate-pulse' : 'bg-border-strong'}`} />
                    )}
                    <span>{leg.from_name} &rarr; {leg.to_name}</span>
                  </div>
                )
              })}
            </div>
          ) : !isTerminalResolved && isError && onRetry ? (
            <button
              onClick={onRetry}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-surface border border-border text-ink hover:bg-sand transition cursor-pointer"
            >
              <RotateCw className="h-3 w-3 text-ink-soft" />
              <span>Retry Route</span>
            </button>
          ) : null}
        </div>
      </div>

      {/* Map Container with Overlay States */}
      <div className="relative">
        <div
          ref={mapContainerRef}
          className="h-64 sm:h-80 w-full z-0 bg-border"
          style={{ minHeight: '280px' }}
        />

        {/* Loading Overlay */}
        {!isTerminalResolved && isLoading && !route && (
          <div className="absolute inset-0 bg-sand/95 flex flex-col items-center justify-center p-6 text-center z-10">
            <Compass className="h-8 w-8 text-leaf animate-spin mb-2" />
            <p className="text-xs sm:text-sm font-semibold text-ink">Calculating road route and driving ETA via OSRM...</p>
            <p className="text-xs text-ink-soft mt-1">Connecting road network between merchant, rider, and dropoff</p>
          </div>
        )}

        {/* Error / Route Unavailable Banner Overlay */}
        {!isTerminalResolved && isError && !route && (
          <div className="absolute inset-x-3 bottom-3 bg-surface border border-turmeric rounded-[12px] p-3 shadow-none z-10 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <AlertTriangle className="h-4 w-4 text-turmeric-ink shrink-0" />
              <p className="text-xs text-ink">
                {sanitizeRouteErrorMessage(errorMessage)}
              </p>
            </div>
            {onRetry && (
              <button
                onClick={onRetry}
                className="shrink-0 px-2.5 py-1 text-xs font-bold text-ink bg-sand hover:bg-border rounded-md transition cursor-pointer"
              >
                Retry
              </button>
            )}
          </div>
        )}
      </div>

      {/* Map Legend & Attribution */}
      <div className="p-3 bg-surface border-t border-border flex flex-wrap items-center justify-between gap-2 text-[11px] text-ink-soft">
        <div className="flex items-center gap-4 flex-wrap">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-ink" />
            <span>Store ({route?.shop_location?.name || 'Merchant'})</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-brick-ink" />
            <span>Dropoff</span>
          </span>
          {!isTerminalResolved && (route?.rider_location || liveRiderLocation) && (
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-2.5 w-2.5 rounded-full bg-ink-soft" />
              <span>Rider (Blue dashed = Pickup route)</span>
            </span>
          )}
          {!isTerminalResolved && (
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-1.5 w-4 rounded bg-leaf" />
              <span>Delivery Route</span>
            </span>
          )}
        </div>

        <div className="flex items-center gap-1 text-[10px] text-ink-soft">
          <Info className="h-3 w-3" />
          <span>{route?.attribution || 'Route data © OpenStreetMap contributors, powered by OSRM'}</span>
        </div>
      </div>
    </div>
  )
}
