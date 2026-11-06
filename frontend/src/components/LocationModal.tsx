import { useEffect, useRef, useState, useMemo } from 'react'
import {
  MapPin,
  Navigation,
  Check,
  X,
  AlertCircle,
  Loader2,
  ChevronDown,
  ChevronUp,
  Search,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useLocationStore } from '@/store/useLocationStore'
import {
  searchPatnaPlaces,
  type PatnaPlace,
} from '@/constants/patnaPlaces'

interface LocationModalProps {
  isOpen: boolean
  onClose: () => void
}

export const LocationModal = ({ isOpen, onClose }: LocationModalProps) => {
  const modalRef = useRef<HTMLDivElement>(null)
  const searchInputRef = useRef<HTMLInputElement>(null)

  const {
    coords,
    addressLabel,
    radiusMeters,
    deliveryOnly,
    isGps,
    isLocating,
    locationError,
    setLocation,
    setRadius,
    setDeliveryOnly,
    requestGpsLocation,
    clearError,
  } = useLocationStore()

  // Search by place query
  const [searchQuery, setSearchQuery] = useState('')

  // Advanced manual coordinates entry state
  const [showAdvancedCoords, setShowAdvancedCoords] = useState(false)
  const [manualLat, setManualLat] = useState('')
  const [manualLon, setManualLon] = useState('')
  const [manualError, setManualError] = useState<string | null>(null)

  // Filter places based on search input
  const filteredPlaces = useMemo(() => {
    return searchPatnaPlaces(searchQuery)
  }, [searchQuery])

  // Handle ESC key and focus trapping
  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    modalRef.current?.focus()

    return () => {
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen, onClose])

  if (!isOpen) return null

  const handleGpsClick = async () => {
    const success = await requestGpsLocation()
    if (success) {
      onClose()
    }
  }

  const handleSelectPlace = (place: PatnaPlace) => {
    setLocation(place.coords, place.name, false)
  }

  const handleManualSet = () => {
    setManualError(null)
    const lat = parseFloat(manualLat)
    const lon = parseFloat(manualLon)

    if (manualLat.trim() === '' || manualLon.trim() === '') {
      setManualError('Both latitude and longitude are required.')
      return
    }
    if (isNaN(lat) || lat < -90 || lat > 90) {
      setManualError('Latitude must be a number between -90 and 90.')
      return
    }
    if (isNaN(lon) || lon < -180 || lon > 180) {
      setManualError('Longitude must be a number between -180 and 180.')
      return
    }

    setLocation({ latitude: lat, longitude: lon }, 'Custom Location', false)
    setShowAdvancedCoords(false)
  }

  const radiusKm = Math.round(radiusMeters / 1000)

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="location-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[rgba(30,42,36,0.45)] animate-in fade-in duration-200"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        ref={modalRef}
        tabIndex={-1}
        className="w-full max-w-lg bg-surface rounded-[14px] shadow-[0_8px_24px_rgba(30,42,36,0.12)] border border-border overflow-hidden focus:outline-none animate-in zoom-in-95 duration-200 flex flex-col max-h-[90vh]"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4.5 border-b border-border bg-surface-alt shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="h-9 w-9 rounded-xl bg-primary-50 border border-primary-200 flex items-center justify-center text-primary-700">
              <MapPin className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <h2 id="location-modal-title" className="font-bold text-base text-text-primary">
                Set Delivery Location
              </h2>
              <p className="text-xs text-text-secondary">
                Search your place or neighbourhood in Patna
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close location settings"
            className="h-8 w-8 rounded-full flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-black/5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        {/* Active Location Banner */}
        <div className="px-6 py-3.5 bg-primary-50/70 border-b border-primary-200/50 flex items-center justify-between gap-3 shrink-0">
          {coords ? (
            <>
              <div className="flex items-center gap-2 min-w-0">
                <div className="h-2 w-2 rounded-full bg-primary-600 shrink-0 animate-pulse" />
                <div className="min-w-0">
                  <span className="text-[11px] font-semibold text-primary-700 uppercase tracking-wider block">
                    Active Location {isGps ? '(GPS Verified)' : ''}
                  </span>
                  <span className="text-xs sm:text-sm font-bold text-text-primary truncate block">
                    {addressLabel}
                  </span>
                </div>
              </div>
              <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-surface border border-primary-200 text-primary-700 shrink-0 shadow-2xs">
                Within {radiusKm} km
              </span>
            </>
          ) : (
            <div className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4 text-text-muted shrink-0" aria-hidden="true" />
              <span className="text-xs text-text-secondary italic">
                No location set — search below or use GPS
              </span>
            </div>
          )}
        </div>

        {/* Error notification if geolocation failed */}
        {locationError && (
          <div className="mx-6 mt-4 p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-800 flex items-start gap-2.5 shrink-0">
            <AlertCircle className="h-4 w-4 text-red-600 shrink-0 mt-0.5" aria-hidden="true" />
            <div className="flex-1">
              <p className="font-semibold">Location Access</p>
              <p>{locationError}</p>
            </div>
            <button
              type="button"
              onClick={clearError}
              aria-label="Dismiss error"
              className="text-red-600 hover:text-red-900"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        )}

        {/* Modal Body */}
        <div className="p-6 space-y-5 overflow-y-auto flex-1">
          {/* Place Search - Primary Interface */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <label
                htmlFor="place-search-input"
                className="text-xs font-semibold uppercase tracking-wider text-text-secondary block"
              >
                Search by Place or Neighbourhood
              </label>
              <span className="text-[11px] font-medium text-text-muted">
                {filteredPlaces.length} {filteredPlaces.length === 1 ? 'place' : 'places'} found
              </span>
            </div>

            {/* Search Input Bar */}
            <div className="relative">
              <Search
                className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted pointer-events-none"
                aria-hidden="true"
              />
              <input
                id="place-search-input"
                ref={searchInputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search area (e.g. Boring Road, Kankarbagh, Danapur, AIIMS)..."
                aria-label="Search by place or neighbourhood"
                className="w-full h-11 pl-10 pr-9 rounded-[12px] bg-surface-alt border border-border text-xs sm:text-sm text-text-primary placeholder:text-text-muted focus:border-leaf focus:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-leaf transition-all shadow-none"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery('')}
                  aria-label="Clear place search"
                  className="absolute right-3 top-1/2 -translate-y-1/2 h-5 w-5 rounded-full flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-black/5 transition-colors"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>

            {/* Places Result List */}
            <div className="space-y-2 max-h-56 overflow-y-auto pr-1 rounded-[12px] border border-border bg-surface-alt/40 p-2">
              {filteredPlaces.length > 0 ? (
                filteredPlaces.map((place) => {
                  const isSelected =
                    !isGps &&
                    coords?.latitude === place.coords.latitude &&
                    coords?.longitude === place.coords.longitude

                  return (
                    <button
                      key={place.id}
                      type="button"
                      onClick={() => handleSelectPlace(place)}
                      aria-pressed={isSelected}
                      className={`w-full flex items-start justify-between p-3 rounded-xl border text-left transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf ${
                        isSelected
                          ? 'bg-primary-50 border-leaf text-primary-900 shadow-none ring-1 ring-leaf'
                          : 'bg-surface border-border hover:bg-surface-alt hover:border-border-strong text-text-primary'
                      }`}
                    >
                      <div className="min-w-0 pr-3">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-bold text-xs sm:text-sm">
                            {place.name}
                          </span>
                          <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-surface-alt border border-border text-text-secondary shrink-0">
                            {place.area}
                          </span>
                        </div>
                        <p className="text-[11px] text-text-secondary mt-1 line-clamp-1">
                          {place.description}
                        </p>
                      </div>

                      {isSelected ? (
                        <div className="h-5 w-5 rounded-full bg-primary-700 text-white flex items-center justify-center shrink-0 mt-0.5 shadow-2xs">
                          <Check className="h-3 w-3" aria-hidden="true" />
                        </div>
                      ) : (
                        <span className="text-[11px] font-semibold text-primary-600 hover:text-primary-700 shrink-0 self-center">
                          Select
                        </span>
                      )}
                    </button>
                  )
                })
              ) : (
                <div className="p-6 text-center space-y-2">
                  <MapPin className="mx-auto h-6 w-6 text-text-muted" />
                  <p className="text-xs font-semibold text-text-primary">
                    No neighbourhood found for "{searchQuery}"
                  </p>
                  <p className="text-[11px] text-text-secondary max-w-xs mx-auto">
                    Try searching for common areas like Boring Road, Kankarbagh, Bailey Road, or Danapur.
                  </p>
                  <button
                    type="button"
                    onClick={() => setSearchQuery('')}
                    className="text-xs font-bold text-primary-700 hover:underline pt-1"
                  >
                    Clear search &amp; view all places
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* GPS Quick Action */}
          <div className="p-3 rounded-[12px] bg-surface-alt border border-border flex items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <div className="h-8 w-8 rounded-xl bg-primary-100 text-primary-700 flex items-center justify-center shrink-0">
                <Navigation className="h-4 w-4" />
              </div>
              <div>
                <span className="text-xs font-bold text-text-primary block">
                  Use Device Location
                </span>
                <span className="text-[11px] text-text-secondary">
                  Detect via device sensor
                </span>
              </div>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleGpsClick}
              disabled={isLocating}
              className="text-xs font-semibold border-primary-300 text-primary-700 hover:bg-primary-50 shrink-0"
            >
              {isLocating ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
                  <span>Detecting...</span>
                </>
              ) : (
                <>
                  <Navigation className="h-3.5 w-3.5 mr-1.5" />
                  <span>Use GPS</span>
                </>
              )}
            </Button>
          </div>

          {/* Discovery Radius Options */}
          <div className="pt-2 border-t border-border">
            <div className="flex items-center justify-between mb-2.5">
              <div>
                <label className="text-xs font-semibold uppercase tracking-wider text-text-secondary block">
                  Search Radius
                </label>
                <p className="text-[10px] text-text-muted mt-0.5">
                  Search radius finds shops near you. Delivery eligibility (5 km) is checked separately at checkout.
                </p>
              </div>
              <span className="text-xs font-semibold text-primary-700 shrink-0 ml-2">
                {radiusKm} km radius
              </span>
            </div>

            <div className="grid grid-cols-3 gap-2">
              {[
                { meters: 3000, label: '3 km', desc: 'Strict Nearby' },
                { meters: 5000, label: '5 km', desc: 'Default Limit' },
                { meters: 10000, label: '10 km', desc: 'Expanded' },
              ].map((opt) => {
                const isActive = radiusMeters === opt.meters
                return (
                  <button
                    key={opt.meters}
                    type="button"
                    onClick={() => setRadius(opt.meters)}
                    aria-pressed={isActive}
                    className={`p-2.5 rounded-xl border text-center transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf ${
                      isActive
                        ? 'bg-leaf text-leaf-ink border-leaf shadow-none'
                        : 'bg-surface-alt border-border text-text-primary hover:bg-surface hover:border-border-strong'
                    }`}
                  >
                    <div className="font-bold text-sm">{opt.label}</div>
                    <div
                      className={`text-[10px] mt-0.5 ${
                        isActive ? 'text-white/80' : 'text-text-secondary'
                      }`}
                    >
                      {opt.desc}
                    </div>
                  </button>
                )
              })}
            </div>
          </div>

          {/* Delivery Eligibility Toggle */}
          <div className="p-3.5 rounded-[12px] bg-surface-alt border border-border flex items-center justify-between gap-3">
            <div>
              <div className="text-xs font-bold text-text-primary">
                Delivery-Eligible Only
              </div>
              <div className="text-[11px] text-text-secondary mt-0.5">
                Hide pickup-only shops exceeding the 5 km delivery boundary
              </div>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={deliveryOnly}
              aria-label="Delivery eligible only switch"
              onClick={() => setDeliveryOnly(!deliveryOnly)}
              className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf ${
                deliveryOnly ? 'bg-leaf' : 'bg-border'
              }`}
            >
              <span
                className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-surface shadow-none ring-0 transition duration-200 ease-in-out ${
                  deliveryOnly ? 'translate-x-5' : 'translate-x-0'
                }`}
              />
            </button>
          </div>

          {/* Advanced: Exact Coordinates (Optional Collapsible for QA/Devs) */}
          <div className="border border-border/80 rounded-[12px] overflow-hidden">
            <button
              type="button"
              onClick={() => setShowAdvancedCoords((v) => !v)}
              aria-expanded={showAdvancedCoords}
              className="w-full flex items-center justify-between px-4 py-2.5 bg-surface-alt/60 text-left hover:bg-surface-alt transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
            >
              <span className="text-[11px] font-medium text-text-muted">
                Need custom coordinates? Enter Lat / Lon (Advanced)
              </span>
              {showAdvancedCoords ? (
                <ChevronUp className="h-3.5 w-3.5 text-text-muted" aria-hidden="true" />
              ) : (
                <ChevronDown className="h-3.5 w-3.5 text-text-muted" aria-hidden="true" />
              )}
            </button>

            {showAdvancedCoords && (
              <div className="px-4 pb-4 pt-3 space-y-3 border-t border-border">
                <p className="text-[10px] text-text-muted">
                  Optional: Enter exact decimal degrees for custom testing locations.
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label htmlFor="manual-lat" className="text-[11px] font-semibold text-text-secondary block mb-1">
                      Latitude
                    </label>
                    <input
                      id="manual-lat"
                      type="number"
                      step="any"
                      value={manualLat}
                      onChange={(e) => setManualLat(e.target.value)}
                      placeholder="e.g. 25.6144"
                      className="w-full h-9 px-3 rounded-xl bg-surface border border-border text-xs text-text-primary placeholder:text-text-muted focus:border-primary-600 focus:outline-none transition-colors"
                    />
                  </div>
                  <div>
                    <label htmlFor="manual-lon" className="text-[11px] font-semibold text-text-secondary block mb-1">
                      Longitude
                    </label>
                    <input
                      id="manual-lon"
                      type="number"
                      step="any"
                      value={manualLon}
                      onChange={(e) => setManualLon(e.target.value)}
                      placeholder="e.g. 85.1158"
                      className="w-full h-9 px-3 rounded-xl bg-surface border border-border text-xs text-text-primary placeholder:text-text-muted focus:border-primary-600 focus:outline-none transition-colors"
                    />
                  </div>
                </div>
                {manualError && (
                  <p role="alert" className="text-[11px] text-red-600 font-medium">
                    {manualError}
                  </p>
                )}
                <Button
                  type="button"
                  onClick={handleManualSet}
                  className="w-full h-8 rounded-xl btn-primary text-white text-xs font-semibold"
                >
                  Set Custom Coordinates
                </Button>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 border-t border-border bg-surface-alt flex justify-end shrink-0">
          <Button
            type="button"
            onClick={onClose}
            className="btn-primary h-10 px-6 rounded-[12px] text-leaf-ink font-semibold shadow-none"
          >
            Apply &amp; Discover Shops
          </Button>
        </div>
      </div>
    </div>
  )
}
