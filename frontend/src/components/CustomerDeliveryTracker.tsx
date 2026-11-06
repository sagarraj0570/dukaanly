import { useState, useEffect, useRef } from 'react'
import type { OrderDeliverySummary, DeliveryStatus } from '@/hooks/useOrders'
import { useAuthStore } from '@/store/useAuthStore'
import { getDeliveryWsUrl } from '@/lib/utils'
import { useDeliveryRoute, useDeliveryEta } from '@/hooks/useDeliveries'
import { DeliveryRouteMap } from '@/components/DeliveryRouteMap'
import { DeliveryEtaCard } from '@/components/DeliveryEtaCard'
import { StatusStamp, orderStatusTone } from '@/components/ui/StatusStamp'
import {
  MapPin,
  CheckCircle2,
  Clock,
  Truck,
  AlertCircle,
  Wifi,
  WifiOff,
  RotateCw,
  Navigation,
} from 'lucide-react'

interface CustomerDeliveryTrackerProps {
  delivery: OrderDeliverySummary | null | undefined
  orderStatus: string
  onRefreshOrder?: () => void
}

interface RiderLocationState {
  latitude: number
  longitude: number
  updatedAt: string | null
}

function calculateDistanceMeters(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371000
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

export const CustomerDeliveryTracker = ({
  delivery,
  orderStatus,
  onRefreshOrder,
}: CustomerDeliveryTrackerProps) => {
  const token = useAuthStore((state) => state.token)
  const onRefreshOrderRef = useRef(onRefreshOrder)
  const lastRerouteRef = useRef<{ lat: number; lng: number; time: number } | null>(null)

  useEffect(() => {
    onRefreshOrderRef.current = onRefreshOrder
  }, [onRefreshOrder])

  const [connectionStatus, setConnectionStatus] = useState<
    'connecting' | 'connected' | 'reconnecting' | 'disconnected'
  >('disconnected')
  const [wsDeliveryStatus, setWsDeliveryStatus] = useState<DeliveryStatus | null>(null)

  const isCancelledBase =
    orderStatus === 'cancelled' ||
    delivery?.status === 'cancelled' ||
    wsDeliveryStatus === 'cancelled'
  const isDeliveredBase =
    orderStatus === 'delivered' ||
    orderStatus === 'completed' ||
    delivery?.status === 'delivered' ||
    wsDeliveryStatus === 'delivered'

  const isTerminalInitial = isCancelledBase || isDeliveredBase

  const [riderLocation, setRiderLocation] = useState<RiderLocationState | null>(null)
  const [currentTime, setCurrentTime] = useState(() => Date.now())
  const [retryTrigger, setRetryTrigger] = useState(0)

  const {
    data: route,
    isLoading: isRouteLoading,
    isError: isRouteError,
    error: routeError,
    refetch: refetchRoute,
  } = useDeliveryRoute(delivery?.id, !!delivery?.id && !isTerminalInitial)

  const {
    data: etaData,
    isLoading: isEtaLoading,
    refetch: refetchEta,
  } = useDeliveryEta(delivery?.id, !!delivery?.id && !isTerminalInitial)

  const isCancelled =
    isCancelledBase ||
    etaData?.status === 'cancelled' ||
    route?.status === 'cancelled'

  const isDelivered =
    isDeliveredBase ||
    etaData?.status === 'delivered' ||
    route?.status === 'delivered'

  const liveStatus: DeliveryStatus = isCancelled
    ? 'cancelled'
    : isDelivered
    ? 'delivered'
    : wsDeliveryStatus ?? delivery?.status ?? etaData?.status ?? route?.status ?? 'pending'

  const isTerminal = isCancelled || isDelivered

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(Date.now()), 30000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    if (!delivery?.id || isTerminal) {
      setConnectionStatus('disconnected')
      return
    }

    let ws: WebSocket | null = null
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null
    let isUnmounted = false
    let reconnectAttempts = 0

    const connect = () => {
      if (isUnmounted) return
      if (!token) {
        setConnectionStatus('disconnected')
        return
      }

      setConnectionStatus(reconnectAttempts > 0 ? 'reconnecting' : 'connecting')

      try {
        const url = getDeliveryWsUrl(delivery.id, token)
        ws = new WebSocket(url)

        ws.onopen = () => {
          if (isUnmounted) {
            ws?.close()
            return
          }
          const wasReconnecting = reconnectAttempts > 0
          setConnectionStatus('connected')
          reconnectAttempts = 0

          if (wasReconnecting && onRefreshOrderRef.current) {
            onRefreshOrderRef.current()
          }
        }

        ws.onmessage = (event) => {
          if (isUnmounted) return
          try {
            const payload = JSON.parse(event.data)
            if (!payload || typeof payload !== 'object') return

            if (payload.event === 'connection.ready' && payload.data) {
              if (payload.data.delivery_status) {
                setWsDeliveryStatus(payload.data.delivery_status)
              }
              if (
                payload.data.rider_location &&
                typeof payload.data.rider_location.latitude === 'number'
              ) {
                setRiderLocation({
                  latitude: payload.data.rider_location.latitude,
                  longitude: payload.data.rider_location.longitude,
                  updatedAt:
                    payload.data.rider_location.updated_at || new Date().toISOString(),
                })
              }
            } else if (payload.event === 'delivery.location_updated' && payload.data) {
              if (
                typeof payload.data.latitude === 'number' &&
                typeof payload.data.longitude === 'number'
              ) {
                const newLat = payload.data.latitude
                const newLng = payload.data.longitude
                setRiderLocation({
                  latitude: newLat,
                  longitude: newLng,
                  updatedAt: payload.timestamp || new Date().toISOString(),
                })

                // Throttle rerouting requests when rider coordinates update frequently (>50m / 30s)
                const now = Date.now()
                if (!lastRerouteRef.current) {
                  lastRerouteRef.current = { lat: newLat, lng: newLng, time: now }
                } else {
                  const elapsedMs = now - lastRerouteRef.current.time
                  const deltaMeters = calculateDistanceMeters(
                    lastRerouteRef.current.lat,
                    lastRerouteRef.current.lng,
                    newLat,
                    newLng
                  )
                  if (deltaMeters >= 50 && elapsedMs >= 30000) {
                    lastRerouteRef.current = { lat: newLat, lng: newLng, time: now }
                    refetchRoute()
                  }
                }
              }
            } else if (payload.event === 'delivery.status_changed' && payload.data) {
              if (payload.data.status) {
                setWsDeliveryStatus(payload.data.status)
                onRefreshOrderRef.current?.()
                refetchEta()
              }
            } else if (payload.event === 'delivery.eta_updated') {
              refetchEta()
            }
          } catch {
            // Ignore malformed payloads safely
          }
        }

        ws.onclose = () => {
          if (isUnmounted) return
          setConnectionStatus('disconnected')
          if (!isTerminal && reconnectAttempts < 8) {
            reconnectAttempts++
            setConnectionStatus('reconnecting')
            // Exponential backoff capped at 15 seconds
            const backoffMs = Math.min(1000 * Math.pow(1.5, reconnectAttempts), 15000)
            reconnectTimeout = setTimeout(() => {
              if (!isUnmounted) {
                connect()
              }
            }, backoffMs)
          }
        }

        ws.onerror = () => {
          // Triggers onclose
        }
      } catch {
        setConnectionStatus('disconnected')
      }
    }

    connect()

    // Mobile resilience: Reconnect immediately when mobile device wakes up or network recovers
    const handleVisibilityOrOnline = () => {
      if (document.visibilityState === 'visible' && !isTerminal) {
        if (!ws || ws.readyState === WebSocket.CLOSING || ws.readyState === WebSocket.CLOSED) {
          reconnectAttempts = 0
          connect()
        }
      }
    }

    window.addEventListener('visibilitychange', handleVisibilityOrOnline)
    window.addEventListener('online', handleVisibilityOrOnline)

    return () => {
      isUnmounted = true
      if (reconnectTimeout) clearTimeout(reconnectTimeout)
      window.removeEventListener('visibilitychange', handleVisibilityOrOnline)
      window.removeEventListener('online', handleVisibilityOrOnline)
      if (ws) {
        ws.close()
      }
    }
  }, [delivery?.id, delivery?.status, isTerminal, token, retryTrigger])

  // 15-minute freshness check matching backend settings
  const isStale = (updatedAt: string | null): boolean => {
    if (!updatedAt) return true
    const ageMs = currentTime - new Date(updatedAt).getTime()
    return ageMs > 15 * 60 * 1000
  }

  // State: No delivery assigned yet
  if (!delivery) {
    return (
      <div className="rounded-[14px] border border-border bg-surface p-5 sm:p-6 shadow-none space-y-4">
        <div className="flex items-center justify-between border-b border-border pb-3">
          <h2 className="font-display text-base sm:text-lg font-semibold text-ink flex items-center gap-2">
            <Truck className="h-5 w-5 text-ink-soft" /> Delivery Tracking
          </h2>
          <StatusStamp tone="neutral">Unassigned</StatusStamp>
        </div>

        <div className="p-5 bg-sand border border-border rounded-xl flex flex-col sm:flex-row items-start gap-4">
          <div className="h-10 w-10 rounded-full bg-surface border border-border flex items-center justify-center shrink-0 text-ink-soft">
            <Clock className="h-5 w-5" />
          </div>
          <div>
            <h3 className="font-semibold text-sm text-ink mb-1">
              Waiting for Delivery Assignment
            </h3>
            <p className="text-xs sm:text-sm text-ink-soft leading-relaxed">
              {orderStatus === 'pending'
                ? 'Your order payment is pending. Once payment is confirmed, the shop will prepare your order and assign a delivery partner.'
                : orderStatus === 'cancelled'
                ? 'This order has been cancelled. No delivery will be dispatched.'
                : 'Your order is currently being prepared by the shop. A nearby delivery rider will be assigned shortly.'}
            </p>
          </div>
        </div>
      </div>
    )
  }

  // Delivery Stages: Preparing -> Rider assigned -> Out for Delivery -> Handover
  const stages = [
    {
      key: 'preparing',
      label: 'Preparing',
      sub: 'Shop is preparing your items',
      time: null,
    },
    {
      key: 'assigned',
      label: 'Rider Assigned',
      sub: 'Delivery partner matched with order',
      time: delivery.assigned_at,
    },
    {
      key: 'out_for_delivery',
      label: 'Out for Delivery',
      sub: 'Rider is on the way to your delivery address',
      time: delivery.picked_up_at,
    },
    {
      key: 'delivered',
      label: 'Handover',
      sub: 'Order handed over successfully',
      time: delivery.delivered_at,
    },
  ]

  const getStageStatus = (key: string): 'completed' | 'current' | 'upcoming' => {
    if (liveStatus === 'delivered') return 'completed'
    if (liveStatus === 'cancelled') return 'upcoming'

    if (key === 'preparing') {
      if (['assigned', 'picked_up', 'out_for_delivery', 'delivered'].includes(liveStatus)) {
        return 'completed'
      }
      return 'current'
    }

    if (key === 'assigned') {
      if (['picked_up', 'out_for_delivery', 'delivered'].includes(liveStatus)) {
        return 'completed'
      }
      if (liveStatus === 'assigned') return 'current'
      return 'upcoming'
    }

    if (key === 'out_for_delivery') {
      if (['picked_up', 'out_for_delivery'].includes(liveStatus)) return 'current'
      return 'upcoming'
    }

    if (key === 'delivered') {
      return 'upcoming'
    }

    return 'upcoming'
  }

  return (
    <div className="rounded-[14px] border border-border bg-surface p-5 sm:p-6 shadow-none space-y-6">
      {/* Header & Connection Indicator */}
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-3 border-b border-border pb-4">
        <div>
          <h2 className="font-display text-lg sm:text-xl font-semibold text-ink flex items-center gap-2">
            <Truck className="h-5 w-5 text-ink-soft" aria-hidden="true" /> Live Delivery Tracking
          </h2>
          <p className="text-xs text-ink-soft font-mono mt-0.5 break-all">
            Delivery ID: {delivery.id}
          </p>
          <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
            Delivery status is {liveStatus.replace(/_/g, ' ')}.
            {connectionStatus !== 'connected' && ` Connection status is ${connectionStatus}.`}
          </div>
        </div>

        {/* Live Status & Connection Pill */}
        <div className="flex items-center gap-2.5 flex-wrap">
          {connectionStatus === 'connected' && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-sage-tint text-leaf border border-leaf/30">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-leaf opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-leaf" />
              </span>
              Live Connected
            </span>
          )}

          {connectionStatus === 'reconnecting' && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-turmeric-tint text-turmeric-ink border border-turmeric-ink/30">
              <RotateCw className="h-3 w-3 animate-spin text-turmeric-ink" />
              Reconnecting...
            </span>
          )}

          {connectionStatus === 'connecting' && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-sand text-ink-soft border border-border">
              <Wifi className="h-3 w-3 animate-pulse text-ink-soft" />
              Connecting...
            </span>
          )}

          {connectionStatus === 'disconnected' && !isTerminal && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-sand text-ink-soft border border-border">
              <WifiOff className="h-3 w-3 text-ink-soft" />
              Offline
            </span>
          )}

          {connectionStatus === 'disconnected' && !isTerminal && (
            <button
              type="button"
              onClick={() => setRetryTrigger((prev) => prev + 1)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-surface hover:bg-sand text-ink border border-border transition-colors cursor-pointer"
              title="Retry WebSocket connection"
            >
              <RotateCw className="h-3 w-3 text-ink-soft" />
              Reconnect
            </button>
          )}

          <StatusStamp tone={orderStatusTone(liveStatus)}>
            {liveStatus.replace(/_/g, ' ')}
          </StatusStamp>
        </div>
      </div>

      {/* Main Grid: Leaflet Map first on Mobile; side-by-side (5 cols ETA, 7 cols Map) on Desktop */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left column (Desktop: 5 cols, Mobile: Below map) */}
        <div className="order-2 lg:order-1 lg:col-span-5 space-y-5">
          {/* Smart Delivery ETA Card */}
          <DeliveryEtaCard etaData={etaData} isLoading={isEtaLoading} />

          {/* Vertical Order-Stage Timeline */}
          <div className="rounded-[14px] border border-border bg-surface p-4 sm:p-5">
            <h3 className="text-xs font-semibold text-ink-soft uppercase tracking-wider mb-4">
              Delivery Progress
            </h3>

            <div className="relative pl-6 sm:pl-7 space-y-5 before:absolute before:left-3 before:top-2 before:bottom-2 before:w-0.5 before:bg-border">
              {stages.map((stage) => {
                const status = getStageStatus(stage.key)
                const isCompleted = status === 'completed'
                const isCurrent = status === 'current'

                return (
                  <div key={stage.key} className="relative flex items-start gap-3">
                    {/* Stage marker */}
                    <div
                      className={`absolute -left-6 sm:-left-7 top-0.5 h-6 w-6 rounded-full flex items-center justify-center ring-4 ring-surface ${
                        isCompleted
                          ? 'bg-sage-tint text-leaf border border-leaf/40'
                          : isCurrent
                          ? 'bg-surface border-2 border-leaf text-leaf ring-sage-tint'
                          : 'bg-surface border-2 border-border text-ink-soft'
                      }`}
                    >
                      {isCompleted ? (
                        <CheckCircle2 className="h-3.5 w-3.5" />
                      ) : isCurrent ? (
                        <Navigation className="h-3 w-3 animate-pulse" />
                      ) : (
                        <span className="h-1.5 w-1.5 rounded-full bg-border-strong" />
                      )}
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <p
                          className={`text-sm font-semibold ${
                            isCompleted || isCurrent ? 'text-ink' : 'text-ink-soft'
                          }`}
                        >
                          <span>{stage.label}</span>
                          {stage.key === 'out_for_delivery' && (
                            <span className="text-xs font-normal text-ink-soft ml-1">· On the way</span>
                          )}
                        </p>
                        {stage.time && (
                          <span className="text-xs font-mono text-ink-soft">
                            {new Date(stage.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-ink-soft mt-0.5">
                        {stage.sub}
                      </p>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Rider Location Display & Honest GPS Radar Card */}
          <div className="rounded-[14px] border border-border bg-sand p-4 sm:p-5 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-ink flex items-center gap-2">
                <MapPin className="h-4 w-4 text-ink-soft" /> Rider Coordinates & Signal
              </h3>
              {riderLocation && (
                <span
                  className={`px-2.5 py-0.5 rounded-full text-[11px] font-semibold ${
                    isStale(riderLocation.updatedAt)
                      ? 'bg-turmeric-tint text-turmeric-ink border border-turmeric-ink/30'
                      : 'bg-sage-tint text-leaf border border-leaf/30'
                  }`}
                >
                  {isStale(riderLocation.updatedAt) ? 'Last Known (Stale)' : 'Active Signal'}
                </span>
              )}
            </div>

            {riderLocation ? (
              <div className="bg-surface p-3.5 rounded-xl border border-border text-sm space-y-2">
                <div className="flex justify-between items-center text-ink">
                  <span className="text-xs text-ink-soft">Latitude:</span>
                  <span className="font-mono text-xs font-semibold text-ink num">
                    {riderLocation.latitude.toFixed(5)}
                  </span>
                </div>
                <div className="flex justify-between items-center text-ink">
                  <span className="text-xs text-ink-soft">Longitude:</span>
                  <span className="font-mono text-xs font-semibold text-ink num">
                    {riderLocation.longitude.toFixed(5)}
                  </span>
                </div>
                {riderLocation.updatedAt && (
                  <div className="flex justify-between items-center text-ink-soft text-[11px] pt-1.5 border-t border-border">
                    <span>Last Updated:</span>
                    <span>{new Date(riderLocation.updatedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                  </div>
                )}
              </div>
            ) : (
              <div className="p-3.5 bg-surface border border-border rounded-xl text-xs text-ink-soft flex items-center gap-2">
                <AlertCircle className="h-4 w-4 text-ink-soft shrink-0" />
                <span>
                  {liveStatus === 'cancelled'
                    ? 'Delivery cancelled. Live tracking closed.'
                    : liveStatus === 'delivered'
                    ? 'Delivery completed. Live location tracking closed.'
                    : 'Location coordinates unavailable. Rider has not yet initiated GPS tracking.'}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Leaflet Map: First on mobile (order-1), right column on desktop (order-2) */}
        <div className="order-1 lg:order-2 lg:col-span-7">
          <DeliveryRouteMap
            route={route}
            liveRiderLocation={
              !isTerminal && riderLocation
                ? { latitude: riderLocation.latitude, longitude: riderLocation.longitude }
                : null
            }
            fallbackShopLocation={
              (delivery as any)?.order?.shop?.location
                ? {
                    latitude: (delivery as any).order.shop.location.latitude,
                    longitude: (delivery as any).order.shop.location.longitude,
                    name: (delivery as any).order.shop.name,
                  }
                : null
            }
            fallbackCustomerLocation={
              (delivery as any)?.destination_latitude && (delivery as any)?.destination_longitude
                ? {
                    latitude: (delivery as any).destination_latitude,
                    longitude: (delivery as any).destination_longitude,
                    name: 'Delivery Dropoff',
                  }
                : null
            }
            isLoading={!isTerminal && isRouteLoading}
            isError={!isTerminal && isRouteError}
            errorMessage={
              (routeError as any)?.response?.data?.detail ||
              (routeError instanceof Error ? routeError.message : undefined)
            }
            onRetry={() => refetchRoute()}
            isTerminal={isTerminal}
            terminalStatus={isCancelled ? 'cancelled' : isDelivered ? 'delivered' : null}
          />
        </div>
      </div>
    </div>
  )
}
