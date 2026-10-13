import { useState, useEffect, useRef } from 'react'
import type { OrderDeliverySummary, DeliveryStatus } from '@/hooks/useOrders'
import { useAuthStore } from '@/store/useAuthStore'
import { getDeliveryWsUrl } from '@/lib/utils'
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

export const CustomerDeliveryTracker = ({
  delivery,
  orderStatus,
  onRefreshOrder,
}: CustomerDeliveryTrackerProps) => {
  const token = useAuthStore((state) => state.token)
  const onRefreshOrderRef = useRef(onRefreshOrder)

  useEffect(() => {
    onRefreshOrderRef.current = onRefreshOrder
  }, [onRefreshOrder])

  const [connectionStatus, setConnectionStatus] = useState<
    'connecting' | 'connected' | 'reconnecting' | 'disconnected'
  >('disconnected')
  const [wsDeliveryStatus, setWsDeliveryStatus] = useState<DeliveryStatus | null>(null)
  const liveStatus: DeliveryStatus = wsDeliveryStatus ?? delivery?.status ?? 'pending'
  const [riderLocation, setRiderLocation] = useState<RiderLocationState | null>(null)
  const [currentTime, setCurrentTime] = useState(() => Date.now())

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(Date.now()), 30000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    if (!delivery?.id) {
      return
    }

    const isTerminal = delivery.status === 'delivered' || delivery.status === 'cancelled'
    if (isTerminal) {
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
                setRiderLocation({
                  latitude: payload.data.latitude,
                  longitude: payload.data.longitude,
                  updatedAt: payload.timestamp || new Date().toISOString(),
                })
              }
            } else if (payload.event === 'delivery.status_changed' && payload.data) {
              if (payload.data.status) {
                setWsDeliveryStatus(payload.data.status)
                onRefreshOrderRef.current?.()
              }
            }
          } catch {
            // Ignore malformed payloads safely
          }
        }

        ws.onclose = () => {
          if (isUnmounted) return
          setConnectionStatus('disconnected')
          if (!isTerminal && reconnectAttempts < 5) {
            reconnectAttempts++
            setConnectionStatus('reconnecting')
            reconnectTimeout = setTimeout(() => {
              if (!isUnmounted) {
                connect()
              }
            }, 2000)
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

    return () => {
      isUnmounted = true
      if (reconnectTimeout) clearTimeout(reconnectTimeout)
      if (ws) {
        ws.close()
      }
    }
  }, [delivery?.id, delivery?.status, token])

  // 15-minute freshness check matching backend settings
  const isStale = (updatedAt: string | null): boolean => {
    if (!updatedAt) return true
    const ageMs = currentTime - new Date(updatedAt).getTime()
    return ageMs > 15 * 60 * 1000
  }

  // State: No delivery assigned yet
  if (!delivery) {
    return (
      <div className="bg-white border border-[#E5E9E4] rounded-2xl p-5 sm:p-6 shadow-soft space-y-4">
        <div className="flex items-center justify-between border-b border-[#E5E9E4] pb-3">
          <h2 className="text-base font-bold text-[#202923] flex items-center gap-2">
            <Truck className="h-5 w-5 text-[#176B45]" /> Delivery Tracking
          </h2>
          <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-gray-100 text-[#69736C]">
            Unassigned
          </span>
        </div>

        <div className="p-5 bg-[#EDF5EE] border border-[#A8D5B5]/60 rounded-xl flex items-start gap-3">
          <Clock className="h-5 w-5 text-[#176B45] mt-0.5 shrink-0" />
          <div>
            <h3 className="font-bold text-sm text-[#104B32] mb-1">
              Waiting for Delivery Assignment
            </h3>
            <p className="text-xs sm:text-sm text-[#202923]/80 leading-relaxed">
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

  // Delivery Stages
  const stages = [
    { key: 'assigned', label: 'Rider Assigned', time: delivery.assigned_at },
    { key: 'picked_up', label: 'Picked Up', time: delivery.picked_up_at },
    { key: 'out_for_delivery', label: 'Out for Delivery', time: null },
    { key: 'delivered', label: 'Delivered', time: delivery.delivered_at },
  ]

  const stageOrder = ['pending', 'assigned', 'picked_up', 'out_for_delivery', 'delivered']
  const currentIndex = stageOrder.indexOf(liveStatus)

  return (
    <div className="bg-white border border-[#E5E9E4] rounded-2xl p-5 sm:p-6 shadow-soft space-y-6">
      {/* Header & Connection Indicator */}
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-3 border-b border-[#E5E9E4] pb-4">
        <div>
          <h2 className="text-base sm:text-lg font-bold text-[#202923] flex items-center gap-2">
            <Truck className="h-5 w-5 text-[#176B45]" aria-hidden="true" /> Live Delivery Tracking
          </h2>
          <p className="text-xs text-[#69736C] font-mono mt-0.5 break-all">
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
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-[#EDF5EE] text-[#176B45] border border-[#A8D5B5]">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#176B45] opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-[#176B45]" />
              </span>
              Live Connected
            </span>
          )}

          {connectionStatus === 'reconnecting' && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-800 border border-amber-200">
              <RotateCw className="h-3 w-3 animate-spin text-amber-600" />
              Reconnecting...
            </span>
          )}

          {connectionStatus === 'connecting' && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
              <Wifi className="h-3 w-3 animate-pulse text-blue-600" />
              Connecting...
            </span>
          )}

          {connectionStatus === 'disconnected' && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-gray-100 text-[#69736C] border border-[#E5E9E4]">
              <WifiOff className="h-3 w-3 text-[#69736C]" />
              {['delivered', 'cancelled'].includes(liveStatus) ? 'Completed' : 'Offline'}
            </span>
          )}

          <span
            className={`px-2.5 py-1 rounded-full text-xs font-bold capitalize ${
              liveStatus === 'delivered'
                ? 'bg-[#EDF5EE] text-[#176B45] border border-[#A8D5B5]'
                : liveStatus === 'cancelled'
                ? 'bg-red-50 text-red-700 border border-red-200'
                : 'bg-blue-50 text-blue-700 border border-blue-200'
            }`}
          >
            {liveStatus.replace(/_/g, ' ')}
          </span>
        </div>
      </div>

      {/* Vertical Order-Stage Timeline */}
      <div className="py-2">
        <h3 className="text-xs font-bold text-[#69736C] uppercase tracking-wider mb-4">
          Delivery Progress
        </h3>

        <div className="relative pl-6 sm:pl-8 space-y-6 before:absolute before:left-3 before:top-2 before:bottom-2 before:w-0.5 before:bg-[#E5E9E4]">
          {stages.map((stage, idx) => {
            const isCompleted = currentIndex > idx + 1 || liveStatus === 'delivered'
            const isCurrent = stageOrder[currentIndex] === stage.key && liveStatus !== 'delivered'

            return (
              <div key={stage.key} className="relative flex items-start gap-3">
                {/* Stage marker dot */}
                <div
                  className={`absolute -left-6 sm:-left-8 top-0.5 h-6 w-6 rounded-full flex items-center justify-center ring-4 ring-white ${
                    isCompleted
                      ? 'bg-[#176B45] text-white shadow-sm'
                      : isCurrent
                      ? 'bg-[#176B45] text-white animate-pulse'
                      : 'bg-white border-2 border-[#E5E9E4] text-[#69736C]'
                  }`}
                >
                  {isCompleted ? (
                    <CheckCircle2 className="h-3.5 w-3.5" />
                  ) : isCurrent ? (
                    <Navigation className="h-3 w-3" />
                  ) : (
                    <span className="h-1.5 w-1.5 rounded-full bg-[#E5E9E4]" />
                  )}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <p
                      className={`text-sm font-bold ${
                        isCompleted || isCurrent ? 'text-[#202923]' : 'text-[#69736C]'
                      }`}
                    >
                      {stage.label}
                    </p>
                    {stage.time && (
                      <span className="text-xs font-mono text-[#69736C]">
                        {new Date(stage.time).toLocaleTimeString()}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-[#69736C] mt-0.5">
                    {stage.key === 'assigned'
                      ? 'Delivery partner matched with order'
                      : stage.key === 'picked_up'
                      ? 'Order collected from the merchant'
                      : stage.key === 'out_for_delivery'
                      ? 'Rider is on the way to your delivery address'
                      : 'Order handed over successfully'}
                  </p>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Rider Location Display & Honest GPS Radar Card */}
      <div className="bg-[#FAF9F6] border border-[#E5E9E4] rounded-2xl p-4 sm:p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-[#202923] flex items-center gap-2">
            <MapPin className="h-4 w-4 text-[#176B45]" /> Rider Coordinates & Signal
          </h3>
          {riderLocation && (
            <span
              className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold ${
                isStale(riderLocation.updatedAt)
                  ? 'bg-amber-100 text-amber-800'
                  : 'bg-[#EDF5EE] text-[#176B45] border border-[#A8D5B5]'
              }`}
            >
              {isStale(riderLocation.updatedAt) ? 'Last Known (Stale)' : 'Active Signal'}
            </span>
          )}
        </div>

        {riderLocation ? (
          <div className="bg-white p-4 rounded-xl border border-[#E5E9E4] text-sm space-y-2">
            <div className="flex justify-between items-center text-[#202923]">
              <span className="text-xs text-[#69736C]">Latitude:</span>
              <span className="font-mono text-xs font-semibold">
                {riderLocation.latitude.toFixed(5)}
              </span>
            </div>
            <div className="flex justify-between items-center text-[#202923]">
              <span className="text-xs text-[#69736C]">Longitude:</span>
              <span className="font-mono text-xs font-semibold">
                {riderLocation.longitude.toFixed(5)}
              </span>
            </div>
            {riderLocation.updatedAt && (
              <div className="flex justify-between items-center text-[#69736C] text-[11px] pt-1.5 border-t border-[#E5E9E4]">
                <span>Last Updated:</span>
                <span>{new Date(riderLocation.updatedAt).toLocaleTimeString()}</span>
              </div>
            )}
          </div>
        ) : (
          <div className="p-4 bg-white border border-[#E5E9E4] rounded-xl text-xs text-[#69736C] flex items-center gap-2.5">
            <AlertCircle className="h-4 w-4 text-[#69736C] shrink-0" />
            <span>
              {['delivered', 'cancelled'].includes(liveStatus)
                ? 'Delivery completed. Live location tracking closed.'
                : 'Location coordinates unavailable. Rider has not yet initiated GPS tracking.'}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
