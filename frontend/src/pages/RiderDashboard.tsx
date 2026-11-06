import { useRiderProfile, useCreateRiderProfile, useUpdateAvailability } from '@/hooks/useRiders'
import { useMyDeliveries } from '@/hooks/useDeliveries'
import { Button } from '@/components/ui/button'
import { StatusStamp, orderStatusTone } from '@/components/ui/StatusStamp'
import { Bike, Clock, CheckCircle2, ChevronRight, Navigation } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useState } from 'react'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

export const RiderDashboard = () => {
  useDocumentTitle('Field Dispatch Console')

  const { data: profile, isLoading: isLoadingProfile, isError: isErrorProfile } = useRiderProfile()
  const { mutate: createProfile, isPending: isCreating } = useCreateRiderProfile()
  const { mutate: updateAvailability, isPending: isUpdatingAvailability } = useUpdateAvailability()

  const { data: deliveries, isLoading: isLoadingDeliveries } = useMyDeliveries()
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // Profile creation fallback
  if (isErrorProfile && !profile) {
    return (
      <div className="max-w-md mx-auto text-center py-10 px-6 bg-surface border border-border rounded-[14px] shadow-none">
        <div className="h-16 w-16 rounded-2xl bg-sand flex items-center justify-center mx-auto mb-4 text-ink">
          <Bike className="h-8 w-8" />
        </div>
        <h2 className="font-display text-xl font-semibold text-ink mb-2">Welcome to Dukaanly Rider</h2>
        <p className="text-sm text-ink-soft mb-6 leading-relaxed">
          Set up your delivery partner profile to start receiving order delivery requests nearby.
        </p>

        {errorMsg && (
          <p role="alert" className="text-xs text-brick-ink bg-brick-tint/40 p-2.5 rounded-xl border border-brick-ink/30 mb-4">
            {errorMsg}
          </p>
        )}

        <Button
          className="w-full min-h-[44px] font-semibold bg-leaf hover:bg-leaf/90 text-white rounded-xl"
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
      <div className="max-w-md mx-auto px-4 py-6 space-y-4 animate-pulse">
        <div className="h-28 bg-sand rounded-[14px]" />
        <div className="h-44 bg-surface border border-border rounded-[14px]" />
        <div className="h-44 bg-surface border border-border rounded-[14px]" />
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
    <div className="max-w-2xl mx-auto px-4 py-6 sm:py-8 space-y-5">
      <h1 className="sr-only">Rider Dispatch Console</h1>

      {/* Large On Duty / Off Duty Switch Card at the top */}
      <div
        id="rider-duty-card"
        className="rounded-[14px] border border-border bg-surface p-5 space-y-4 shadow-none"
      >
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div
              className={`h-12 w-12 rounded-xl flex items-center justify-center transition-colors border ${
                profile?.is_available
                  ? 'bg-sage-tint text-leaf border-leaf/30'
                  : 'bg-sand text-ink-soft border-border'
              }`}
            >
              <Bike className="h-6 w-6" aria-hidden="true" />
            </div>
            <div>
              <p className="font-semibold text-ink text-sm">Duty Status</p>
              <div className="flex items-center gap-2 mt-0.5">
                <span
                  className={`h-2.5 w-2.5 rounded-full ${
                    profile?.is_available ? 'bg-leaf' : 'bg-ink-soft'
                  }`}
                  aria-hidden="true"
                />
                <span className="text-xs font-semibold text-ink">
                  {profile?.is_available ? 'On duty' : 'Off duty'}
                </span>
                <span className="text-[11px] text-ink-soft">
                  {profile?.is_available ? 'Available' : 'Offline'}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2.5 shrink-0">
            <span className="text-sm font-semibold text-ink select-none hidden sm:inline">
              {profile?.is_available ? 'On duty' : 'Off duty'}
            </span>
            <button
              type="button"
              role="switch"
              aria-checked={profile?.is_available ?? false}
              aria-label={profile?.is_available ? 'Go Offline' : 'Go Online'}
              onClick={handleToggleAvailability}
              disabled={isUpdatingAvailability}
              className={`relative inline-flex h-7 w-12 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf focus-visible:ring-offset-2 ${
                profile?.is_available ? 'bg-leaf' : 'bg-border-strong'
              } ${isUpdatingAvailability ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <span className="sr-only">
                {profile?.is_available ? 'Go Offline' : 'Go Online'}
              </span>
              <span
                aria-hidden="true"
                className={`pointer-events-none inline-block h-6 w-6 transform rounded-full bg-surface shadow-xs ring-0 transition duration-200 ease-in-out ${
                  profile?.is_available ? 'translate-x-5' : 'translate-x-0'
                }`}
              />
            </button>
          </div>
        </div>

        {errorMsg && (
          <p role="alert" className="text-xs text-brick-ink bg-brick-tint/40 p-2.5 rounded-xl border border-brick-ink/30">
            {errorMsg}
          </p>
        )}
      </div>

      {/* Active Deliveries List */}
      <div className="space-y-3">
        <div className="flex items-center justify-between px-1">
          <h2 className="text-sm font-semibold text-ink flex items-center gap-2">
            <Navigation className="h-4 w-4 text-leaf" aria-hidden="true" />
            Active Deliveries ({activeDeliveries.length})
          </h2>
          {activeDeliveries.length > 0 && (
            <span className="text-xs text-leaf font-semibold bg-sage-tint px-2.5 py-0.5 rounded-full border border-leaf/30">
              In Transit
            </span>
          )}
        </div>

        {activeDeliveries.length === 0 ? (
          <div className="rounded-[14px] border border-border bg-surface p-6 text-center shadow-none space-y-2">
            <div className="h-12 w-12 rounded-full bg-sand flex items-center justify-center mx-auto text-ink-soft mb-1">
              <Bike className="h-6 w-6" />
            </div>
            {profile?.is_available ? (
              <>
                <p className="font-display font-semibold text-base text-ink">
                  Abhi koi order nahi. Aap on duty hain.
                </p>
                <p className="text-xs text-ink-soft max-w-xs mx-auto leading-relaxed">
                  Jaise hi aapke ilaqe mein koi naya order aayega, yahan dikhega.
                </p>
              </>
            ) : (
              <>
                <p className="font-display font-semibold text-base text-ink">
                  Aap abhi offline hain
                </p>
                <p className="text-xs text-ink-soft max-w-xs mx-auto leading-relaxed">
                  Delivery orders receive karne ke liye upar wale switch se online ho jayein.
                </p>
              </>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            {activeDeliveries.map((delivery) => {
              const currentStepLabel =
                delivery.status === 'assigned'
                  ? 'Step 1: Head to shop for pickup'
                  : delivery.status === 'picked_up'
                  ? 'Step 2: Collect parcel and start ride'
                  : 'Step 3: Delivering to customer'

              const nextActionText =
                delivery.status === 'assigned'
                  ? 'Pickup Order at Shop'
                  : delivery.status === 'picked_up'
                  ? 'Start Ride to Customer'
                  : 'Open Delivery & Complete Handover'

              return (
                <div
                  key={delivery.id}
                  className="rounded-[14px] border border-border bg-surface p-4 shadow-none space-y-3.5"
                >
                  <div className="flex justify-between items-center">
                    <span className="font-mono text-xs font-semibold text-ink-soft">
                      #{delivery.id.split('-')[0].toUpperCase()}
                    </span>
                    <StatusStamp tone={orderStatusTone(delivery.status)}>
                      {delivery.status}
                    </StatusStamp>
                  </div>

                  <div className="p-3 bg-sand rounded-xl border border-border space-y-1">
                    <p className="text-xs font-semibold text-ink">{currentStepLabel}</p>
                    {delivery.assigned_at && (
                      <div className="flex items-center gap-1.5 text-[11px] text-ink-soft">
                        <Clock className="h-3 w-3" />
                        <span>Assigned {new Date(delivery.assigned_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                      </div>
                    )}
                  </div>

                  {/* Next Action as Full-Width Button */}
                  <Link
                    to={`/rider/deliveries/${delivery.id}`}
                    className="w-full min-h-[44px] flex items-center justify-center gap-2 bg-leaf hover:bg-leaf/90 text-white rounded-xl text-sm font-semibold transition"
                  >
                    <span>{nextActionText}</span>
                    <ChevronRight className="h-4 w-4" />
                  </Link>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Recent History */}
      <div id="rider-history" className="space-y-3 pt-2">
        <h2 className="text-sm font-semibold text-ink flex items-center gap-2 px-1">
          <CheckCircle2 className="h-4 w-4 text-leaf" aria-hidden="true" />
          Recent History
        </h2>

        {pastDeliveries.length === 0 ? (
          <div className="rounded-[14px] border border-border bg-surface p-5 text-center shadow-none text-xs text-ink-soft">
            No completed deliveries yet.
          </div>
        ) : (
          <div className="rounded-[14px] border border-border bg-surface divide-y divide-border overflow-hidden shadow-none">
            {pastDeliveries.slice(0, 5).map((delivery) => (
              <Link
                key={delivery.id}
                to={`/rider/deliveries/${delivery.id}`}
                className="p-3.5 flex justify-between items-center text-xs hover:bg-sand/40 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <span className="text-xs text-ink-soft font-medium">
                    {new Date(delivery.updated_at).toLocaleDateString('en-IN', {
                      day: 'numeric',
                      month: 'short',
                    })}
                  </span>
                  <span className="text-xs font-semibold text-ink font-sans">
                    {delivery.id.split('-')[0].toUpperCase()}
                  </span>
                </div>
                <StatusStamp tone={orderStatusTone(delivery.status)}>
                  {delivery.status}
                </StatusStamp>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
