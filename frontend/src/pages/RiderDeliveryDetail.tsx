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
      (error) => {
        setLocationError(`Location error: ${error.message}`)
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 0
      }
    )

    return () => {
      navigator.geolocation.clearWatch(watchId)
    }
  }, [delivery?.status, updateLocation])

  const handleStatusTransition = (newStatus: DeliveryStatus) => {
    setActionError(null)
    updateStatus({ id: delivery!.id, status: newStatus }, {
      onError: (err: any) => setActionError(err.response?.data?.detail || "Could not update delivery status")
    })
  }

  if (isLoading) {
    return (
      <div className="max-w-3xl mx-auto p-6 space-y-6 animate-pulse">
        <div className="h-10 bg-gray-100 rounded w-1/4" />
        <div className="h-64 bg-gray-100 rounded-xl" />
      </div>
    )
  }

  if (isError || !delivery) {
    return (
      <div className="max-w-3xl mx-auto p-6">
        <ErrorState 
          title="Delivery not found"
          message={error?.message || "Could not retrieve delivery details"}
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <Button variant="ghost" onClick={() => navigate('/rider')} className="-ml-4 text-gray-500">
        <ArrowLeft className="mr-2 h-4 w-4" /> Back to Dashboard
      </Button>

      <div className="bg-white border rounded-xl shadow-sm overflow-hidden">
        <div className={`p-6 text-white ${
          ['delivered'].includes(delivery.status) ? 'bg-green-600' :
          ['cancelled'].includes(delivery.status) ? 'bg-red-600' :
          'bg-primary'
        }`}>
          <div className="flex justify-between items-start">
            <div>
              <h1 className="text-2xl font-bold mb-1 capitalize flex items-center gap-2">
                {delivery.status.replace(/_/g, ' ')}
                {delivery.status === 'out_for_delivery' && <Navigation className="h-5 w-5 animate-pulse" />}
              </h1>
              <p className="text-primary-foreground/80 font-mono text-sm">ID: {delivery.id}</p>
            </div>
          </div>
        </div>

        <div className="p-6 space-y-8">
          {actionError && (
            <div className="p-4 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm flex items-start gap-2">
              <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
              <p>{actionError}</p>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-4">
              <h2 className="text-lg font-bold text-gray-900 border-b pb-2">Destinations</h2>
              
              <div className="bg-gray-50 p-4 rounded-lg border">
                <div className="flex items-start gap-3">
                  <MapPin className="h-5 w-5 text-gray-400 mt-0.5" />
                  <div>
                    <p className="font-semibold text-gray-900">Customer Location</p>
                    {delivery.destination_latitude ? (
                      <p className="text-sm text-gray-500 font-mono mt-1">
                        {delivery.destination_latitude.toFixed(5)}, {delivery.destination_longitude?.toFixed(5)}
                      </p>
                    ) : (
                      <p className="text-sm text-red-500 mt-1">Coordinates missing</p>
                    )}
                  </div>
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <h2 className="text-lg font-bold text-gray-900 border-b pb-2">Tracking</h2>
              <div className="bg-gray-50 p-4 rounded-lg border">
                {isSharingLocation ? (
                  <div className="flex items-center gap-3 text-green-600">
                    <Navigation className="h-5 w-5 animate-pulse" />
                    <span className="font-medium text-sm">Live Location Sharing Active</span>
                  </div>
                ) : (
                  <div className="flex items-center gap-3 text-gray-500">
                    <MapPin className="h-5 w-5" />
                    <span className="text-sm">Location sharing inactive</span>
                  </div>
                )}
                {locationError && (
                  <p className="text-xs text-red-500 mt-2">{locationError}</p>
                )}
                <p className="text-xs text-gray-500 mt-2">
                  Location is shared securely with the customer and shop while you are out for delivery.
                </p>
              </div>
            </div>
          </div>

          <div className="border-t pt-6">
            <h2 className="text-lg font-bold text-gray-900 mb-4">Action Required</h2>
            
            <div className="flex flex-col gap-3">
              {delivery.status === 'assigned' && (
                <Button 
                  size="lg" 
                  onClick={() => handleStatusTransition('picked_up')}
                  disabled={isUpdatingStatus}
                >
                  <Package className="mr-2 h-5 w-5" /> Mark as Picked Up
                </Button>
              )}
              
              {delivery.status === 'picked_up' && (
                <Button 
                  size="lg" 
                  className="bg-orange-600 hover:bg-orange-700 text-white"
                  onClick={() => handleStatusTransition('out_for_delivery')}
                  disabled={isUpdatingStatus}
                >
                  <Navigation className="mr-2 h-5 w-5" /> Start Delivery
                </Button>
              )}
              
              {delivery.status === 'out_for_delivery' && (
                <Button 
                  size="lg" 
                  className="bg-green-600 hover:bg-green-700 text-white"
                  onClick={() => handleStatusTransition('delivered')}
                  disabled={isUpdatingStatus}
                >
                  <CheckCircle className="mr-2 h-5 w-5" /> Mark as Delivered
                </Button>
              )}
              
              {['pending', 'assigned', 'picked_up'].includes(delivery.status) && (
                <Button 
                  variant="outline" 
                  className="text-red-600 border-red-200 hover:bg-red-50"
                  onClick={() => handleStatusTransition('cancelled')}
                  disabled={isUpdatingStatus}
                >
                  Cancel Delivery
                </Button>
              )}

              {['delivered', 'cancelled'].includes(delivery.status) && (
                <p className="text-gray-500 text-center font-medium">
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
