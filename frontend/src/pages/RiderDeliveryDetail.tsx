import { useParams, useNavigate } from 'react-router-dom'
import {
  useDelivery,
  useUpdateDeliveryStatus,
  useDeliveryRoute,
  useDeliveryEta,
  type DeliveryStatus,
} from '@/hooks/useDeliveries'
import { useUpdateLocation } from '@/hooks/useRiders'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ErrorState'
import {
  ArrowLeft,
  MapPin,
  Package,
  CheckCircle,
  Navigation,
  AlertCircle,
  Clock,
} from 'lucide-react'
import { useState, useEffect } from 'react'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { DeliveryRouteMap } from '@/components/DeliveryRouteMap'

const formatArrivalWindow = (earliest: string | null, latest: string | null, remainingSeconds: number): string => {
  if (earliest && latest) {
    const earliestMin = Math.max(1, Math.round((new Date(earliest).getTime() - Date.now()) / 60000))
    const latestMin = Math.max(earliestMin + 2, Math.round((new Date(latest).getTime() - Date.now()) / 60000))
    return `${earliestMin}–${latestMin} min`
  }
  if (remainingSeconds > 0) {
    return `~${Math.max(1, Math.round(remainingSeconds / 60))} min`
  }
  return 'Arriving shortly'
}

export const RiderDeliveryDetail = () => {
  useDocumentTitle('Delivery Dispatch')
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const { data: delivery, isLoading, isError, error, refetch } = useDelivery(id)

  const isCancelled = delivery?.status === 'cancelled'
  const isDelivered = delivery?.status === 'delivered'
  const isTerminal = isCancelled || isDelivered

  const {
    data: route,
    isLoading: isRouteLoading,
    isError: isRouteError,
    error: routeError,
    refetch: refetchRoute,
  } = useDeliveryRoute(id, !!id && !isTerminal)
  const { data: etaData, refetch: refetchEta } = useDeliveryEta(id, !!id && !isTerminal)
  const { mutate: updateStatus, isPending: isUpdatingStatus } = useUpdateDeliveryStatus()
  const { mutate: updateLocation } = useUpdateLocation()

  const [actionError, setActionError] = useState<string | null>(null)
  const [locationError, setLocationError] = useState<string | null>(null)
  const isSharingLocation = delivery?.status === 'out_for_delivery' && !locationError

  // Auto-start location tracking if out for delivery
  useEffect(() => {
    if (delivery?.status !== 'out_for_delivery') {
      return
    }

    if (typeof window !== 'undefined' && window.isSecureContext === false) {
      setLocationError('Location tracking requires an HTTPS connection. Please access Dukaanly over HTTPS.')
      return
    }

    if (!navigator.geolocation) {
      setLocationError('Geolocation is not supported by your browser.')
      return
    }

    let lastSent = 0
    let lastLat = 0
    let lastLng = 0

    const watchId = navigator.geolocation.watchPosition(
      (position) => {
        const { latitude, longitude } = position.coords
        const now = Date.now()
        const distMoved =
          lastLat !== 0 && lastLng !== 0
            ? Math.hypot((latitude - lastLat) * 111000, (longitude - lastLng) * 111000)
            : 999
        if (now - lastSent >= 3000 || distMoved >= 10) {
          lastSent = now
          lastLat = latitude
          lastLng = longitude
          setLocationError(null)
          updateLocation({ lat: latitude, lng: longitude })
        }
      },
      (err) => {
        let msg = `Location error: ${err.message}`
        if (err.code === err.PERMISSION_DENIED) {
          msg =
            typeof window !== 'undefined' && window.isSecureContext === false
              ? 'Location tracking requires an HTTPS connection. Please access Dukaanly over HTTPS.'
              : 'Location permission was denied. Please allow location access in your mobile browser settings.'
        } else if (err.code === err.POSITION_UNAVAILABLE) {
          msg = 'GPS signal is currently unavailable. Retrying...'
        } else if (err.code === err.TIMEOUT) {
          msg = 'GPS request timed out. Retrying...'
        }
        setLocationError(msg)
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 5000,
      },
    )

    return () => {
      navigator.geolocation.clearWatch(watchId)
    }
  }, [delivery?.status, updateLocation])

  const handleStatusTransition = (newStatus: DeliveryStatus) => {
    setActionError(null)
    updateStatus(
      { id: delivery!.id, status: newStatus },
      {
        onSuccess: () => {
          refetchEta()
          refetchRoute()
        },
        onError: (err: any) =>
          setActionError(err.response?.data?.detail || 'Could not update delivery status'),
      },
    )
  }

  if (isLoading) {
    return (
      <div className="max-w-md mx-auto px-4 py-6 space-y-4 animate-pulse">
        <div className="h-8 bg-sand rounded w-28" />
        <div className="h-64 bg-surface border border-border rounded-[14px]" />
      </div>
    )
  }

  if (isError || !delivery) {
    return (
      <div className="max-w-md mx-auto px-4 py-6 space-y-4">
        <Button variant="ghost" onClick={() => navigate('/rider')} className="gap-2 text-ink-soft -ml-2">
          <ArrowLeft className="h-4 w-4" /> Back to Dashboard
        </Button>
        <ErrorState
          title="Delivery not found"
          message={error?.message || 'Could not retrieve delivery details'}
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  const stepOrder = ['assigned', 'picked_up', 'out_for_delivery', 'delivered']
  const currentStepIdx = stepOrder.indexOf(delivery.status)

  return (
    <div className="max-w-md mx-auto px-4 py-6 sm:py-8 space-y-4">
      <Button
        variant="ghost"
        onClick={() => navigate('/rider')}
        className="gap-2 text-ink-soft hover:text-ink -ml-2 cursor-pointer"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Back to Dashboard
      </Button>

      <div className="rounded-[14px] border border-border bg-surface shadow-none overflow-hidden space-y-5">
        {/* Header Banner */}
        <div className="p-5 border-b border-border bg-sand">
          <div className="flex justify-between items-start">
            <div>
              <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-soft block mb-1">
                Dispatch Status
              </span>
              <div className="flex items-center gap-2 mb-1">
                <h1 className="font-display text-xl font-semibold text-ink lowercase flex items-center gap-2">
                  {delivery.status.replace(/_/g, ' ')}
                  {delivery.status === 'out_for_delivery' && (
                    <Navigation className="h-4 w-4 text-leaf animate-pulse" aria-hidden="true" />
                  )}
                </h1>
              </div>
              <p className="text-ink-soft font-mono text-xs break-all">
                ID: {delivery.id}
              </p>
            </div>
          </div>

          {/* 3-Step Field Progress */}
          {!isCancelled && (
            <ol className="grid grid-cols-3 gap-2 mt-4 pt-3 border-t border-border list-none p-0">
              {[
                { label: '1. Pickup', idx: 1 },
                { label: '2. En Route', idx: 2 },
                { label: '3. Handover', idx: 3 },
              ].map((step) => {
                const done = currentStepIdx >= step.idx
                const isCurrent = currentStepIdx === step.idx
                return (
                  <li key={step.label} aria-current={isCurrent ? 'step' : undefined} className="space-y-1">
                    <div
                      className={`h-1.5 rounded-full ${
                        done ? 'bg-leaf' : 'bg-border'
                      }`}
                    />
                    <span
                      className={`text-[10px] font-semibold block ${
                        done || isCurrent ? 'text-ink' : 'text-ink-soft'
                      }`}
                    >
                      {step.label}
                    </span>
                  </li>
                )
              })}
            </ol>
          )}
        </div>

        <div className="p-5 space-y-5 pt-0">
          {actionError && (
            <div role="alert" className="p-3 bg-brick-tint/40 border border-brick-ink/30 text-brick-ink rounded-xl text-xs flex items-start gap-2">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" aria-hidden="true" />
              <p>{actionError}</p>
            </div>
          )}

          {/* Smart Delivery ETA Dispatch Timing */}
          {etaData && !['delivered', 'cancelled'].includes(delivery.status) && (
            <div className="bg-sand border border-border rounded-xl p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-ink-soft">
                  <Clock className="h-4 w-4" />
                  <span>Dropoff Target Window</span>
                </div>
                <span className="font-display text-sm font-semibold text-ink bg-surface border border-border px-2.5 py-0.5 rounded-full num">
                  {formatArrivalWindow(
                    etaData.eta.earliest_at,
                    etaData.eta.latest_at,
                    etaData.eta.remaining_seconds
                  )}
                </span>
              </div>

              {etaData.delay_explanation && (
                <div className="bg-turmeric-tint/40 border border-turmeric-ink/20 text-turmeric-ink rounded-xl p-2.5 text-xs flex items-start gap-2">
                  <AlertCircle className="h-3.5 w-3.5 text-turmeric-ink shrink-0 mt-0.5" />
                  <p>{etaData.delay_explanation}</p>
                </div>
              )}

              <div className="grid grid-cols-2 gap-2 text-xs">
                {etaData.breakdown.preparation_remaining_seconds > 0 && (
                  <div className="bg-surface p-2.5 rounded-xl border border-border">
                    <span className="text-[11px] text-ink-soft block">Shop Prep</span>
                    <span className="num font-semibold text-ink">
                      ~{Math.ceil(etaData.breakdown.preparation_remaining_seconds / 60)} min left
                    </span>
                  </div>
                )}
                <div className="bg-surface p-2.5 rounded-xl border border-border">
                  <span className="text-[11px] text-ink-soft block">
                    {delivery.status === 'assigned' ? 'Travel to Shop' : 'Road Driving Time'}
                  </span>
                  <span className="num font-semibold text-ink">
                    ~
                    {Math.ceil(
                      (delivery.status === 'assigned'
                        ? etaData.breakdown.pickup_travel_remaining_seconds
                        : etaData.breakdown.dropoff_travel_seconds) / 60
                    )}{' '}
                    min
                  </span>
                </div>
                {delivery.status === 'assigned' && etaData.breakdown.dropoff_travel_seconds > 0 && (
                  <div className="bg-surface p-2.5 rounded-xl border border-border">
                    <span className="text-[11px] text-ink-soft block">Shop to Customer</span>
                    <span className="num font-semibold text-ink">
                      ~{Math.ceil(etaData.breakdown.dropoff_travel_seconds / 60)} min
                    </span>
                  </div>
                )}
                <div className="bg-surface p-2.5 rounded-xl border border-border">
                  <span className="text-[11px] text-ink-soft block">Routing Source</span>
                  <span className="font-semibold text-ink">
                    {etaData.eta.source === 'osrm' ? 'OSRM Live Road' : 'Traffic Fallback'}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Interactive OSRM Route Navigation Map */}
          <DeliveryRouteMap
            route={route}
            fallbackCustomerLocation={
              delivery.destination_latitude && delivery.destination_longitude
                ? {
                    latitude: delivery.destination_latitude,
                    longitude: delivery.destination_longitude,
                    name: 'Customer Location',
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

          {/* Destination Radar Card */}
          <div className="space-y-2">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-soft">
              Dropoff Destination
            </h2>
            <div className="bg-sand p-3.5 rounded-xl border border-border flex items-center justify-between gap-3">
              <div className="flex items-start gap-3">
                <div className="h-9 w-9 rounded-xl bg-surface border border-border flex items-center justify-center shrink-0 text-ink-soft">
                  <MapPin className="h-4 w-4" aria-hidden="true" />
                </div>
                <div>
                  <p className="font-semibold text-ink text-xs">Customer Location</p>
                  {delivery.destination_latitude ? (
                    <p className="text-xs text-ink-soft font-mono mt-0.5 num">
                      {delivery.destination_latitude.toFixed(5)}, {delivery.destination_longitude?.toFixed(5)}
                    </p>
                  ) : (
                    <p className="text-xs text-brick-ink mt-0.5">Coordinates missing</p>
                  )}
                </div>
              </div>
              <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-1 rounded bg-surface border border-border text-ink-soft shrink-0">
                PostGIS Pin
              </span>
            </div>
          </div>

          {/* Live GPS Telemetry */}
          <div className="space-y-2">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-soft">
              GPS Telemetry
            </h2>
            <div role="status" aria-live="polite" className="bg-sand p-3.5 rounded-xl border border-border">
              {isSharingLocation ? (
                <div className="flex items-center gap-2 text-leaf">
                  <Navigation className="h-4 w-4 animate-pulse" aria-hidden="true" />
                  <span className="font-semibold text-xs">Live Location Sharing Active</span>
                </div>
              ) : (
                <div className="flex items-center gap-2 text-ink-soft">
                  <MapPin className="h-4 w-4" aria-hidden="true" />
                  <span className="text-xs font-medium">Location sharing inactive</span>
                </div>
              )}
              {locationError && (
                <p role="alert" className="text-xs text-brick-ink mt-1.5">{locationError}</p>
              )}
              <p className="text-[11px] text-ink-soft mt-1.5 leading-relaxed">
                Location coordinates are broadcast via WebSocket to the customer while out for delivery.
              </p>
            </div>
          </div>

          {/* Tactile Action Controls */}
          <div className="border-t border-border pt-4">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-soft mb-3">
              Next Step
            </h2>

            <div className="flex flex-col gap-2.5">
              {delivery.status === 'assigned' && (
                <Button
                  size="lg"
                  className="w-full min-h-[48px] font-semibold gap-2 bg-leaf hover:bg-leaf/90 text-white rounded-xl cursor-pointer"
                  onClick={() => handleStatusTransition('picked_up')}
                  disabled={isUpdatingStatus}
                >
                  <Package className="h-4 w-4" aria-hidden="true" /> Mark as Picked Up
                </Button>
              )}

              {delivery.status === 'picked_up' && (
                <Button
                  size="lg"
                  className="w-full min-h-[48px] font-semibold bg-leaf hover:bg-leaf/90 text-white gap-2 rounded-xl cursor-pointer"
                  onClick={() => handleStatusTransition('out_for_delivery')}
                  disabled={isUpdatingStatus}
                >
                  <Navigation className="h-4 w-4" aria-hidden="true" /> Start Delivery
                </Button>
              )}

              {delivery.status === 'out_for_delivery' && (
                <Button
                  size="lg"
                  className="w-full min-h-[48px] font-semibold bg-leaf hover:bg-leaf/90 text-white gap-2 rounded-xl cursor-pointer"
                  onClick={() => handleStatusTransition('delivered')}
                  disabled={isUpdatingStatus}
                >
                  <CheckCircle className="h-4 w-4" aria-hidden="true" /> Mark as Delivered
                </Button>
              )}

              {['pending', 'assigned', 'picked_up'].includes(delivery.status) && (
                <Button
                  variant="outline"
                  className="w-full min-h-[44px] text-xs text-brick-ink border-border hover:bg-brick-tint/20 rounded-xl cursor-pointer"
                  onClick={() => handleStatusTransition('cancelled')}
                  disabled={isUpdatingStatus}
                >
                  Cancel Delivery
                </Button>
              )}

              {['delivered', 'cancelled'].includes(delivery.status) && (
                <p className="text-xs text-ink-soft text-center py-2">
                  {delivery.status === 'cancelled' ? 'This delivery was cancelled.' : 'This delivery is complete.'}
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
