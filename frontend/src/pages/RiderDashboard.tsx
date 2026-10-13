import { useRiderProfile, useCreateRiderProfile, useUpdateAvailability } from '@/hooks/useRiders'
import { useMyDeliveries } from '@/hooks/useDeliveries'
import { Button } from '@/components/ui/button'
import { Bike, Package, Clock, CheckCircle2, ChevronRight, Navigation, Power } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useState } from 'react'

export const RiderDashboard = () => {

  const { data: profile, isLoading: isLoadingProfile, isError: isErrorProfile } = useRiderProfile()
  const { mutate: createProfile, isPending: isCreating } = useCreateRiderProfile()
  const { mutate: updateAvailability, isPending: isUpdatingAvailability } = useUpdateAvailability()

  const { data: deliveries, isLoading: isLoadingDeliveries } = useMyDeliveries()
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // Profile creation fallback
  if (isErrorProfile && !profile) {
    return (
      <div className="max-w-md mx-auto text-center py-12 px-6 bg-white border border-border rounded-2xl shadow-soft">
        <div className="h-16 w-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-4 text-primary">
          <Bike className="h-8 w-8" />
        </div>
        <h2 className="text-xl font-bold text-foreground mb-2">Welcome to Dukaanly Rider</h2>
        <p className="text-sm text-muted-foreground mb-6 leading-relaxed">
          Set up your delivery partner profile to start receiving order delivery requests nearby.
        </p>

        {errorMsg && (
          <p role="alert" className="text-xs text-red-600 bg-red-50 p-2.5 rounded-lg border border-red-200 mb-4">
            {errorMsg}
          </p>
        )}

        <Button
          className="w-full h-11 font-semibold"
          onClick={() => {
            setErrorMsg(null)
            createProfile(undefined, {
              onError: (err: any) =>
                setErrorMsg(err.response?.data?.detail || 'Could not create profile'),
            })
          }}
          disabled={isCreating}
        >
          {isCreating ? 'Creating Profile...' : 'Set Up My Profile'}
        </Button>
      </div>
    )
  }

  if (isLoadingProfile || isLoadingDeliveries) {
    return (
      <div className="max-w-md mx-auto space-y-4 animate-pulse">
        <div className="h-28 bg-muted rounded-2xl" />
        <div className="h-44 bg-muted rounded-2xl" />
        <div className="h-44 bg-muted rounded-2xl" />
      </div>
    )
  }

  const handleToggleAvailability = () => {
    setErrorMsg(null)
    updateAvailability(!profile?.is_available, {
      onError: (err: any) =>
        setErrorMsg(err.response?.data?.detail || 'Could not update availability'),
    })
  }

  const activeDeliveries =
    deliveries?.filter((d) => ['assigned', 'picked_up', 'out_for_delivery'].includes(d.status)) || []
  const pastDeliveries =
    deliveries?.filter((d) => ['delivered', 'cancelled'].includes(d.status)) || []

  return (
    <div className="max-w-md mx-auto space-y-5 animate-fade-in">
      <h1 className="sr-only">Rider Dispatch Console</h1>

      {/* Availability / Duty Card */}
      <div
        id="rider-duty-card"
        className="bg-white border border-[#E5E9E4] rounded-2xl shadow-soft p-5 space-y-4"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className={`h-12 w-12 rounded-xl flex items-center justify-center transition-colors ${
                profile?.is_available
                  ? 'bg-[#EDF5EE] text-[#176B45] border border-[#A8D5B5]'
                  : 'bg-gray-100 text-[#69736C] border border-[#E5E9E4]'
              }`}
            >
              <Bike className="h-6 w-6" aria-hidden="true" />
            </div>
            <div>
              <p className="font-bold text-[#202923] text-sm">Duty Status</p>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span
                  className={`h-2 w-2 rounded-full ${
                    profile?.is_available ? 'bg-[#176B45] animate-pulse' : 'bg-gray-400'
                  }`}
                />
                <span className="text-xs font-semibold text-[#69736C]">
                  {profile?.is_available ? 'Available' : 'Offline'}
                </span>
              </div>
            </div>
          </div>

          <Button
            variant={profile?.is_available ? 'outline' : 'default'}
            size="sm"
            aria-pressed={profile?.is_available ?? false}
            onClick={handleToggleAvailability}
            disabled={isUpdatingAvailability}
            className={`font-semibold h-9 px-4 text-xs ${
              profile?.is_available
                ? 'border-[#E5E9E4] text-[#202923] hover:bg-gray-50'
                : 'bg-[#176B45] hover:bg-[#104B32] text-white'
            }`}
          >
            <Power className="h-3.5 w-3.5 mr-1.5" aria-hidden="true" />
            {profile?.is_available ? 'Go Offline' : 'Go Online'}
          </Button>
        </div>

        {errorMsg && (
          <p role="alert" className="text-xs text-red-600 bg-red-50 p-2.5 rounded-lg border border-red-200">
            {errorMsg}
          </p>
        )}
      </div>

      {/* Active Deliveries */}
      <div className="space-y-3">
        <div className="flex items-center justify-between px-1">
          <h2 className="text-sm font-bold text-[#202923] flex items-center gap-2">
            <Navigation className="h-4 w-4 text-[#176B45]" aria-hidden="true" />
            Active Deliveries ({activeDeliveries.length})
          </h2>
          {activeDeliveries.length > 0 && (
            <span className="text-xs text-[#176B45] font-semibold bg-[#EDF5EE] px-2 py-0.5 rounded-full border border-[#A8D5B5]/60">
              In Transit
            </span>
          )}
        </div>

        {activeDeliveries.length === 0 ? (
          <div className="bg-white border border-[#E5E9E4] rounded-2xl p-8 text-center shadow-soft">
            <Package className="h-10 w-10 text-[#69736C]/40 mx-auto mb-2.5" aria-hidden="true" />
            <p className="text-sm font-semibold text-[#202923]">No active deliveries</p>
            <p className="text-xs text-[#69736C] mt-1 max-w-xs mx-auto leading-relaxed">
              {!profile?.is_available
                ? 'Toggle your duty status online to start receiving order dispatches.'
                : 'Stay online. When a nearby customer places an order, it will appear here.'}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {activeDeliveries.map((delivery) => (
              <Link
                key={delivery.id}
                to={`/rider/deliveries/${delivery.id}`}
                className="block bg-white border border-[#E5E9E4] hover:border-[#176B45]/50 rounded-2xl p-4 shadow-soft transition-all space-y-3 group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45]"
              >
                <div className="flex justify-between items-center">
                  <span className="font-mono text-xs font-semibold text-[#69736C]">
                    #{delivery.id.split('-')[0].toUpperCase()}
                  </span>
                  <span className="badge-info capitalize">
                    {delivery.status.replace(/_/g, ' ')}
                  </span>
                </div>

                <div className="flex items-center justify-between text-xs text-[#69736C] pt-1 border-t border-[#E5E9E4]">
                  <div className="flex items-center gap-1.5">
                    <Clock className="h-3.5 w-3.5 text-[#176B45]" aria-hidden="true" />
                    <span>Assigned {new Date(delivery.assigned_at!).toLocaleTimeString()}</span>
                  </div>
                  <div className="flex items-center gap-1 text-[#176B45] font-semibold group-hover:translate-x-0.5 transition-transform">
                    View Details
                    <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Recent History */}
      <div id="rider-history" className="space-y-3 pt-2">
        <h2 className="text-sm font-bold text-[#202923] flex items-center gap-2 px-1">
          <CheckCircle2 className="h-4 w-4 text-[#176B45]" aria-hidden="true" />
          Recent History
        </h2>

        {pastDeliveries.length === 0 ? (
          <div className="bg-white border border-[#E5E9E4] rounded-2xl p-6 text-center shadow-soft text-xs text-[#69736C]">
            No completed deliveries yet.
          </div>
        ) : (
          <div className="bg-white border border-[#E5E9E4] rounded-2xl divide-y divide-[#E5E9E4] overflow-hidden shadow-soft">
            {pastDeliveries.slice(0, 5).map((delivery) => (
              <Link
                key={delivery.id}
                to={`/rider/deliveries/${delivery.id}`}
                className="p-3.5 flex justify-between items-center text-xs hover:bg-[#FAF9F6] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45]"
              >
                <div>
                  <span className="font-mono text-[#69736C]">
                    #{delivery.id.split('-')[0]}
                  </span>
                  <p className="text-[11px] text-[#69736C] mt-0.5">
                    {new Date(delivery.updated_at).toLocaleDateString('en-IN', {
                      day: 'numeric',
                      month: 'short',
                    })}
                  </p>
                </div>
                <span
                  className={
                    delivery.status === 'delivered' ? 'badge-success capitalize' : 'badge-error capitalize'
                  }
                >
                  {delivery.status.replace(/_/g, ' ')}
                </span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
