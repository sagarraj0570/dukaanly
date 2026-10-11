import { useState, useEffect } from 'react'
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
  RotateCw 
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
  onRefreshOrder
}: CustomerDeliveryTrackerProps) => {
  const token = useAuthStore((state) => state.token)
  
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'reconnecting' | 'disconnected'>('disconnected')
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

          if (wasReconnecting && onRefreshOrder) {
            onRefreshOrder()
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
              if (payload.data.rider_location && typeof payload.data.rider_location.latitude === 'number') {
                setRiderLocation({
                  latitude: payload.data.rider_location.latitude,
                  longitude: payload.data.rider_location.longitude,
                  updatedAt: payload.data.rider_location.updated_at || new Date().toISOString()
                })
              }
            } else if (payload.event === 'delivery.location_updated' && payload.data) {
              if (typeof payload.data.latitude === 'number' && typeof payload.data.longitude === 'number') {
                setRiderLocation({
                  latitude: payload.data.latitude,
                  longitude: payload.data.longitude,
                  updatedAt: payload.timestamp || new Date().toISOString()
                })
              }
            } else if (payload.event === 'delivery.status_changed' && payload.data) {
              if (payload.data.status) {
                setWsDeliveryStatus(payload.data.status)
                onRefreshOrder?.()
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
  }, [delivery?.id, delivery?.status, token, onRefreshOrder])

  // 15-minute freshness check matching backend settings
  const isStale = (updatedAt: string | null): boolean => {
    if (!updatedAt) return true
    const ageMs = currentTime - new Date(updatedAt).getTime()
    return ageMs > 15 * 60 * 1000
  }

  // State: No delivery assigned yet
  if (!delivery) {
    return (
      <div className="bg-white border rounded-xl p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between border-b pb-3">
          <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
            <Truck className="h-5 w-5 text-primary" /> Delivery Tracking
          </h2>
          <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-gray-100 text-gray-700">
            Unassigned
          </span>
        </div>

        <div className="p-6 bg-blue-50 border border-blue-200 rounded-lg flex items-start gap-3">
          <Clock className="h-5 w-5 text-blue-600 mt-0.5 shrink-0" />
          <div>
            <h3 className="font-semibold text-blue-900 mb-1">Waiting for Delivery Assignment</h3>
            <p className="text-sm text-blue-800">
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
    { key: 'delivered', label: 'Delivered', time: delivery.delivered_at }
  ]

  const stageOrder = ['pending', 'assigned', 'picked_up', 'out_for_delivery', 'delivered']
  const currentIndex = stageOrder.indexOf(liveStatus)

  return (
    <div className="bg-white border rounded-xl p-6 shadow-sm space-y-6">
      
      {/* Header & Connection Indicator */}
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-3 border-b pb-4">
        <div>
          <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
            <Truck className="h-5 w-5 text-primary" /> Live Delivery Tracking
          </h2>
          <p className="text-xs text-gray-500 font-mono mt-0.5">
            Delivery ID: {delivery.id}
          </p>
        </div>

        {/* Live Status & Connection Pill */}
        <div className="flex items-center gap-3">
          {connectionStatus === 'connected' && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-green-50 text-green-700 border border-green-200">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </span>
              Live Connected
            </span>
          )}

          {connectionStatus === 'reconnecting' && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200">
              <RotateCw className="h-3 w-3 animate-spin text-amber-600" />
              Reconnecting...
            </span>
          )}

          {connectionStatus === 'connecting' && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200">
              <Wifi className="h-3 w-3 animate-pulse text-blue-600" />
              Connecting...
            </span>
          )}

          {connectionStatus === 'disconnected' && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-600 border border-gray-200">
              <WifiOff className="h-3 w-3 text-gray-400" />
              {['delivered', 'cancelled'].includes(liveStatus) ? 'Completed' : 'Offline'}
            </span>
          )}

          <span className={`px-2.5 py-1 rounded-full text-xs font-semibold capitalize ${
            liveStatus === 'delivered' ? 'bg-green-100 text-green-800' :
            liveStatus === 'cancelled' ? 'bg-red-100 text-red-800' :
            liveStatus === 'out_for_delivery' ? 'bg-orange-100 text-orange-800' :
            'bg-blue-100 text-blue-800'
          }`}>
            {liveStatus.replace(/_/g, ' ')}
          </span>
        </div>
      </div>

      {/* Progress Timeline */}
      <div className="py-2">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {stages.map((stage, idx) => {
            const isCompleted = currentIndex > idx + 1 || liveStatus === 'delivered'
            const isCurrent = stageOrder[currentIndex] === stage.key && liveStatus !== 'delivered'
            
            return (
              <div 
                key={stage.key}
                className={`p-3 rounded-lg border text-center transition-all ${
                  isCompleted 
                    ? 'bg-green-50 border-green-200 text-green-900' 
                    : isCurrent 
                    ? 'bg-blue-50 border-blue-300 text-blue-900 shadow-sm ring-1 ring-blue-300' 
                    : 'bg-gray-50 border-gray-200 text-gray-500'
                }`}
              >
                <div className="flex justify-center mb-1.5">
                  {isCompleted ? (
                    <CheckCircle2 className="h-5 w-5 text-green-600" />
                  ) : isCurrent ? (
                    <Truck className="h-5 w-5 text-blue-600 animate-pulse" />
                  ) : (
                    <Clock className="h-5 w-5 text-gray-400" />
                  )}
                </div>
                <p className="font-semibold text-xs">{stage.label}</p>
                {stage.time && (
                  <p className="text-[10px] text-gray-500 mt-0.5">
                    {new Date(stage.time).toLocaleTimeString()}
                  </p>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Rider Location Tracking Display */}
      <div className="bg-gray-50 border rounded-lg p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-gray-900 flex items-center gap-2">
            <MapPin className="h-4 w-4 text-primary" /> Rider Coordinates & Signal
          </h3>
          {riderLocation && (
            <span className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
              isStale(riderLocation.updatedAt)
                ? 'bg-amber-100 text-amber-800'
                : 'bg-green-100 text-green-800'
            }`}>
              {isStale(riderLocation.updatedAt) ? 'Last Known (Stale)' : 'Active Signal'}
            </span>
          )}
        </div>

        {riderLocation ? (
          <div className="bg-white p-3 rounded border text-sm space-y-1.5">
            <div className="flex justify-between items-center text-gray-700">
              <span className="text-xs text-gray-500">Latitude:</span>
              <span className="font-mono text-xs font-semibold">{riderLocation.latitude.toFixed(5)}</span>
            </div>
            <div className="flex justify-between items-center text-gray-700">
              <span className="text-xs text-gray-500">Longitude:</span>
              <span className="font-mono text-xs font-semibold">{riderLocation.longitude.toFixed(5)}</span>
            </div>
            {riderLocation.updatedAt && (
              <div className="flex justify-between items-center text-gray-500 text-[11px] pt-1 border-t">
                <span>Timestamp:</span>
                <span>{new Date(riderLocation.updatedAt).toLocaleTimeString()}</span>
              </div>
            )}
          </div>
        ) : (
          <div className="p-3 bg-white border rounded text-xs text-gray-500 flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-gray-400 shrink-0" />
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
