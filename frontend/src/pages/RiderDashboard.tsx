import { useRiderProfile, useCreateRiderProfile, useUpdateAvailability } from '@/hooks/useRiders'
import { useMyDeliveries } from '@/hooks/useDeliveries'
import { Button } from '@/components/ui/button'
import { User, MapPin, Package, Clock, CheckCircle } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useState } from 'react'

export const RiderDashboard = () => {
  const navigate = useNavigate()
  
  const { data: profile, isLoading: isLoadingProfile, isError: isErrorProfile } = useRiderProfile()
  const { mutate: createProfile, isPending: isCreating } = useCreateRiderProfile()
  const { mutate: updateAvailability, isPending: isUpdatingAvailability } = useUpdateAvailability()
  
  const { data: deliveries, isLoading: isLoadingDeliveries } = useMyDeliveries()
  
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // Profile creation fallback
  if (isErrorProfile && !profile) {
    return (
      <div className="max-w-2xl mx-auto text-center py-16 bg-white border rounded-lg shadow-sm">
        <User className="mx-auto h-16 w-16 text-gray-300 mb-4" />
        <h2 className="text-2xl font-bold text-gray-900 mb-2">Welcome to Dukaanly Rider</h2>
        <p className="text-gray-500 mb-8">You need to setup your rider profile before you can start receiving deliveries.</p>
        
        {errorMsg && <p className="text-red-500 mb-4">{errorMsg}</p>}
        
        <Button 
          onClick={() => {
            setErrorMsg(null)
            createProfile(undefined, {
              onError: (err: any) => setErrorMsg(err.response?.data?.detail || "Could not create profile")
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
      <div className="max-w-4xl mx-auto space-y-6 animate-pulse">
        <div className="h-24 bg-gray-100 rounded-lg" />
        <div className="h-64 bg-gray-100 rounded-lg" />
      </div>
    )
  }

  const handleToggleAvailability = () => {
    setErrorMsg(null)
    updateAvailability(!profile?.is_available, {
      onError: (err: any) => setErrorMsg(err.response?.data?.detail || "Could not update availability")
    })
  }

  const activeDeliveries = deliveries?.filter(d => ['assigned', 'picked_up', 'out_for_delivery'].includes(d.status)) || []
  const pastDeliveries = deliveries?.filter(d => ['delivered', 'cancelled'].includes(d.status)) || []

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      
      {/* Profile & Availability Card */}
      <div className="bg-white border rounded-xl shadow-sm p-6 flex flex-col md:flex-row justify-between items-center gap-4">
        <div className="flex items-center gap-4">
          <div className="h-16 w-16 bg-primary/10 rounded-full flex items-center justify-center text-primary">
            <User className="h-8 w-8" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900">Rider Dashboard</h1>
            <p className="text-sm text-gray-500">Manage your availability and deliveries</p>
          </div>
        </div>
        
        <div className="flex flex-col items-center md:items-end gap-2">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-500">Status:</span>
            <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${profile?.is_available ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'}`}>
              {profile?.is_available ? 'Available' : 'Offline'}
            </span>
          </div>
          <Button 
            variant={profile?.is_available ? "outline" : "default"} 
            onClick={handleToggleAvailability}
            disabled={isUpdatingAvailability}
          >
            {profile?.is_available ? 'Go Offline' : 'Go Online'}
          </Button>
          {errorMsg && <p className="text-xs text-red-500 max-w-xs text-right">{errorMsg}</p>}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        
        {/* Active Deliveries */}
        <div className="space-y-4">
          <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
            <MapPin className="h-5 w-5 text-primary" /> Active Deliveries ({activeDeliveries.length})
          </h2>
          
          {activeDeliveries.length === 0 ? (
            <div className="bg-white border rounded-xl p-8 text-center shadow-sm">
              <Package className="h-10 w-10 text-gray-300 mx-auto mb-3" />
              <p className="text-gray-500">No active deliveries right now.</p>
              {!profile?.is_available && <p className="text-xs text-gray-400 mt-2">Go online to receive assignments.</p>}
            </div>
          ) : (
            <div className="space-y-4">
              {activeDeliveries.map(delivery => (
                <div key={delivery.id} className="bg-white border rounded-xl p-5 shadow-sm hover:border-primary transition-colors cursor-pointer" onClick={() => navigate(`/rider/deliveries/${delivery.id}`)}>
                  <div className="flex justify-between items-start mb-3">
                    <span className="text-xs font-mono text-gray-500">{delivery.id.split('-')[0]}</span>
                    <span className="inline-flex items-center rounded-full bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700 capitalize border border-blue-200">
                      {delivery.status.replace(/_/g, ' ')}
                    </span>
                  </div>
                  <div className="mb-4">
                    <p className="text-sm text-gray-600 mb-1">Assigned At</p>
                    <p className="font-medium text-gray-900">{new Date(delivery.assigned_at!).toLocaleTimeString()}</p>
                  </div>
                  <Button variant="secondary" className="w-full text-sm h-9">
                    View Delivery Details
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Past Deliveries */}
        <div className="space-y-4">
          <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
            <CheckCircle className="h-5 w-5 text-green-500" /> Recent History
          </h2>
          
          {pastDeliveries.length === 0 ? (
            <div className="bg-white border rounded-xl p-8 text-center shadow-sm">
              <Clock className="h-10 w-10 text-gray-300 mx-auto mb-3" />
              <p className="text-gray-500">No completed deliveries yet.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {pastDeliveries.slice(0, 5).map(delivery => (
                <div key={delivery.id} className="bg-white border rounded-lg p-4 shadow-sm text-sm">
                  <div className="flex justify-between items-center mb-1">
                    <span className="font-mono text-gray-500 text-xs">{delivery.id.split('-')[0]}</span>
                    <span className={`capitalize font-semibold ${delivery.status === 'delivered' ? 'text-green-600' : 'text-red-600'}`}>
                      {delivery.status}
                    </span>
                  </div>
                  <p className="text-gray-500 text-xs">{new Date(delivery.updated_at).toLocaleString()}</p>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>
    </div>
  )
}
