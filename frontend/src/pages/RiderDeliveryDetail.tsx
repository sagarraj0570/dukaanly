import { useParams, useNavigate } from 'react-router-dom'
import { useDelivery, useUpdateDeliveryStatus, type DeliveryStatus } from '@/hooks/useDeliveries'
import { useUpdateLocation } from '@/hooks/useRiders'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ErrorState'
import { ArrowLeft, MapPin, Package, CheckCircle, Navigation, AlertCircle } from 'lucide-react'
import { useState, useEffect } from 'react'

export const RiderDeliveryDetail = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const { data: delivery, isLoading, isError, error, refetch } = useDelivery(id)
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

    if (!navigator.geolocation) {
      return
    }

    const watchId = navigator.geolocation.watchPosition(
      (position) => {
        const { latitude, longitude } = position.coords
        updateLocation({ lat: latitude, lng: longitude })
      },
      (err) => {
        setLocationError(`Location error: ${err.message}`)
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 0,
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
        onError: (err: any) =>
          setActionError(err.response?.data?.detail || 'Could not update delivery status'),
      },
    )
  }

  if (isLoading) {
    return (
      <div className="max-w-md mx-auto space-y-4 animate-pulse">
        <div className="h-8 bg-muted rounded w-28" />
        <div className="h-64 bg-muted rounded-2xl" />
      </div>
    )
  }

  if (isError || !delivery) {
    return (
      <div className="max-w-md mx-auto space-y-4">
        <Button variant="ghost" onClick={() => navigate('/rider')} className="gap-2 text-muted-foreground -ml-2">
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

  const isDelivered = delivery.status === 'delivered'
  const isCancelled = delivery.status === 'cancelled'
  const stepOrder = ['assigned', 'picked_up', 'out_for_delivery', 'delivered']
  const currentStepIdx = stepOrder.indexOf(delivery.status)

  return (
    <div className="max-w-md mx-auto space-y-4 animate-fade-in">
      <Button
        variant="ghost"
        onClick={() => navigate('/rider')}
        className="gap-2 text-[#69736C] hover:text-[#202923] -ml-2"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Back to Dashboard
      </Button>

      <div className="bg-white border border-[#E5E9E4] rounded-2xl shadow-soft overflow-hidden">
        {/* Header Banner */}
        <div
          className={`p-5 text-white ${
            isDelivered
              ? 'bg-[#176B45]'
              : isCancelled
              ? 'bg-red-600'
              : 'bg-gradient-to-r from-[#176B45] to-[#104B32]'
          }`}
        >
          <div className="flex justify-between items-start">
            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-[#A8D5B5] block mb-1">
                Dispatch Status
              </span>
              <h1 className="text-xl font-bold mb-0.5 capitalize flex items-center gap-2">
                {delivery.status.replace(/_/g, ' ')}
                {delivery.status === 'out_for_delivery' && (
                  <Navigation className="h-4 w-4 animate-pulse" aria-hidden="true" />
                )}
              </h1>
              <p className="text-white/90 font-mono text-xs break-all">
                ID: {delivery.id}
              </p>
            </div>
          </div>

          {/* 3-Step Field Progress */}
          {!isCancelled && (
            <ol className="grid grid-cols-3 gap-2 mt-4 pt-4 border-t border-white/15 list-none p-0">
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
                        done ? 'bg-[#A8D5B5]' : 'bg-white/20'
                      }`}
                    />
                    <span
                      className={`text-[10px] font-semibold block ${
                        done ? 'text-white' : 'text-white/70'
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

        <div className="p-5 space-y-5">
          {actionError && (
            <div role="alert" className="p-3 bg-red-50 border border-red-200 text-red-700 rounded-xl text-xs flex items-start gap-2">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" aria-hidden="true" />
              <p>{actionError}</p>
            </div>
          )}

          {/* Destination Radar Card */}
          <div className="space-y-2">
            <h2 className="text-xs font-bold uppercase tracking-wider text-[#69736C]">
              Dropoff Destination
            </h2>
            <div className="bg-[#FAF9F6] p-4 rounded-xl border border-[#E5E9E4] flex items-center justify-between gap-3">
              <div className="flex items-start gap-3">
                <div className="h-9 w-9 rounded-xl bg-[#EDF5EE] border border-[#A8D5B5] flex items-center justify-center shrink-0">
                  <MapPin className="h-4 w-4 text-[#176B45]" aria-hidden="true" />
                </div>
                <div>
                  <p className="font-bold text-[#202923] text-xs">Customer Location</p>
                  {delivery.destination_latitude ? (
                    <p className="text-xs text-[#69736C] font-mono mt-0.5">
                      {delivery.destination_latitude.toFixed(5)}, {delivery.destination_longitude?.toFixed(5)}
                    </p>
                  ) : (
                    <p className="text-xs text-red-500 mt-0.5">Coordinates missing</p>
                  )}
                </div>
              </div>
              <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded bg-white border border-[#E5E9E4] text-[#176B45] shrink-0">
                PostGIS Pin
              </span>
            </div>
          </div>

          {/* Live GPS Telemetry */}
          <div className="space-y-2">
            <h2 className="text-xs font-bold uppercase tracking-wider text-[#69736C]">
              GPS Telemetry
            </h2>
            <div role="status" aria-live="polite" className="bg-[#FAF9F6] p-4 rounded-xl border border-[#E5E9E4]">
              {isSharingLocation ? (
                <div className="flex items-center gap-2 text-[#176B45]">
                  <Navigation className="h-4 w-4 animate-pulse" aria-hidden="true" />
                  <span className="font-bold text-xs">Live Location Sharing Active</span>
                </div>
              ) : (
                <div className="flex items-center gap-2 text-[#69736C]">
                  <MapPin className="h-4 w-4" aria-hidden="true" />
                  <span className="text-xs font-medium">Location sharing inactive</span>
                </div>
              )}
              {locationError && (
                <p role="alert" className="text-xs text-red-500 mt-1.5">{locationError}</p>
              )}
              <p className="text-[11px] text-[#69736C] mt-1.5 leading-relaxed">
                Location coordinates are broadcast via WebSocket to the customer while out for delivery.
              </p>
            </div>
          </div>

          {/* Tactile Action Controls */}
          <div className="border-t border-[#E5E9E4] pt-4">
            <h2 className="text-xs font-bold uppercase tracking-wider text-[#69736C] mb-3">
              Next Step
            </h2>

            <div className="flex flex-col gap-2.5">
              {delivery.status === 'assigned' && (
                <Button
                  size="lg"
                  className="w-full h-12 font-semibold gap-2 bg-[#176B45] hover:bg-[#104B32] text-white rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45]"
                  onClick={() => handleStatusTransition('picked_up')}
                  disabled={isUpdatingStatus}
                >
                  <Package className="h-4 w-4" aria-hidden="true" /> Mark as Picked Up
                </Button>
              )}

              {delivery.status === 'picked_up' && (
                <Button
                  size="lg"
                  className="w-full h-12 font-semibold bg-[#176B45] hover:bg-[#104B32] text-white gap-2 rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45]"
                  onClick={() => handleStatusTransition('out_for_delivery')}
                  disabled={isUpdatingStatus}
                >
                  <Navigation className="h-4 w-4" aria-hidden="true" /> Start Delivery
                </Button>
              )}

              {delivery.status === 'out_for_delivery' && (
                <Button
                  size="lg"
                  className="w-full h-12 font-semibold bg-[#176B45] hover:bg-[#104B32] text-white gap-2 rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45]"
                  onClick={() => handleStatusTransition('delivered')}
                  disabled={isUpdatingStatus}
                >
                  <CheckCircle className="h-4 w-4" aria-hidden="true" /> Mark as Delivered
                </Button>
              )}

              {['pending', 'assigned', 'picked_up'].includes(delivery.status) && (
                <Button
                  variant="outline"
                  className="w-full h-10 text-xs text-red-600 border-red-200 hover:bg-red-50 rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
                  onClick={() => handleStatusTransition('cancelled')}
                  disabled={isUpdatingStatus}
                >
                  Cancel Delivery
                </Button>
              )}

              {['delivered', 'cancelled'].includes(delivery.status) && (
                <p className="text-xs text-[#69736C] text-center py-2">
                  This delivery is complete.
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
