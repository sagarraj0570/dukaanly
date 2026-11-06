import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import {
  MapPin,
  Store,
  Phone,
  Globe,
  Clock,
  ExternalLink,
  Navigation,
  X,
  ShoppingBag,
  Sparkles,
  CheckCircle2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { NearbyStoreListing } from '@/hooks/useNearbyDiscovery'
import { getShopCoverImage } from '@/lib/commerceMedia'
import { resolveShopType } from '@/lib/shopTypeClassification'

interface DirectoryStoreModalProps {
  isOpen: boolean
  onClose: () => void
  store: NearbyStoreListing | null
}

export const DirectoryStoreModal = ({
  isOpen,
  onClose,
  store,
}: DirectoryStoreModalProps) => {
  const modalRef = useRef<HTMLDivElement>(null)

  // ESC key listener & focus trapping
  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    document.body.style.overflow = 'hidden'

    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.body.style.overflow = 'unset'
    }
  }, [isOpen, onClose])

  if (!isOpen || !store) return null

  const distanceFormatted =
    store.distance_meters < 1000
      ? `${Math.round(store.distance_meters)} m away`
      : `${(store.distance_meters / 1000).toFixed(1)} km away`

  const shopType = resolveShopType(store.name, store.category)
  const coverUrl = shopType.coverImageUrl || getShopCoverImage(store.name, store.category)

  const hasCoordinates =
    typeof store.latitude === 'number' &&
    typeof store.longitude === 'number' &&
    !isNaN(store.latitude) &&
    !isNaN(store.longitude) &&
    (store.latitude !== 0 || store.longitude !== 0)

  const queryTarget =
    store.name && store.address
      ? `${store.name}, ${store.address}`
      : store.name
      ? `${store.name}, Patna, Bihar`
      : hasCoordinates
      ? `${store.latitude},${store.longitude}`
      : 'Patna, Bihar'

  const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(
    queryTarget
  )}`

  const hasContactActions = Boolean(store.phone || store.website)

  const departments = shopType.departments

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="directory-store-modal-title"
      data-testid="directory-store-modal"
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-[rgba(30,42,36,0.45)] backdrop-blur-xs animate-in fade-in duration-200"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        ref={modalRef}
        className="relative w-full max-w-2xl max-h-[90dvh] sm:max-h-[92vh] overflow-hidden rounded-t-[20px] sm:rounded-[14px] bg-surface border-t sm:border border-border shadow-2xl flex flex-col overscroll-contain pb-safe sm:pb-0 animate-in zoom-in-95 duration-200"
      >
        {/* Cover Photo Banner */}
        <div className="relative h-44 sm:h-56 w-full bg-sand overflow-hidden shrink-0">
          <img
            src={coverUrl}
            alt={`${store.name} storefront`}
            className="w-full h-full object-cover"
          />
          <div className="absolute inset-0 bg-black/35" />

          {/* Close button */}
          <button
            type="button"
            onClick={onClose}
            aria-label="Close store details"
            className="absolute top-3 right-3 h-9 w-9 rounded-full bg-black/60 hover:bg-black/80 text-white flex items-center justify-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>

          {/* Header Badges */}
          <div className="absolute top-3 left-3 flex flex-wrap gap-2 items-center">
            <span className="inline-flex items-center gap-1 rounded-full bg-black/75 px-3 py-1 text-xs font-semibold text-white border border-white/20 shadow-none">
              <Store className="h-3.5 w-3.5 text-sage-tint" aria-hidden="true" />
              In-Store Neighbourhood Store
            </span>
            <span className="inline-flex items-center gap-1 rounded-full bg-leaf px-2.5 py-1 text-xs font-semibold text-leaf-ink border border-white/20 shadow-none">
              <MapPin className="h-3 w-3" aria-hidden="true" />
              {distanceFormatted}
            </span>
          </div>

          {/* Banner Title & Category (Bottom of Banner) */}
          <div className="absolute bottom-3 left-4 right-4 text-white">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span className="inline-flex items-center gap-1 text-[11px] font-bold tracking-wider bg-black/60 text-white px-2.5 py-0.5 rounded-full border border-white/25 shadow-none">
                <span className="select-none" aria-hidden="true">{shopType.icon}</span>
                <span>{shopType.badgeLabel}</span>
              </span>
              <span className="inline-flex items-center gap-1 text-[11px] font-medium text-leaf-ink bg-leaf px-2 py-0.5 rounded-full border border-white/20">
                <CheckCircle2 className="h-3 w-3" />
                Open for In-Store Shopping
              </span>
            </div>
            <h2
              id="directory-store-modal-title"
              className="text-xl sm:text-2xl font-bold tracking-tight text-white drop-shadow-sm line-clamp-1"
            >
              {store.name}
            </h2>
          </div>
        </div>

        {/* Scrollable Content Body */}
        <div className="overflow-y-auto p-4 sm:p-6 space-y-5 text-text-primary">
          {/* Quick Action Navigation Bar */}
          <div className={hasContactActions ? 'grid grid-cols-1 sm:grid-cols-2 gap-2.5' : 'flex flex-col gap-2.5'}>
            <a
              href={mapsUrl}
              target="_blank"
              rel="noopener noreferrer"
              data-testid="modal-open-in-maps-btn"
              className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-[12px] bg-leaf hover:bg-leaf-hover text-leaf-ink text-xs sm:text-sm font-semibold transition-colors shadow-none w-full"
            >
              <Navigation className="h-4 w-4" aria-hidden="true" />
              <span>Get Directions on Google Maps</span>
              <ExternalLink className="h-3.5 w-3.5 opacity-70" aria-hidden="true" />
            </a>

            {hasContactActions && (
              <div className="flex items-center gap-2">
                {store.phone ? (
                  <a
                    href={`tel:${store.phone}`}
                    className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-xl bg-surface hover:bg-primary-50 border border-border text-xs sm:text-sm font-semibold text-text-primary transition-colors"
                  >
                    <Phone className="h-4 w-4 text-primary-700" aria-hidden="true" />
                    <span>Call Store</span>
                  </a>
                ) : null}

                {store.website ? (
                  <a
                    href={store.website}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-xl bg-surface hover:bg-primary-50 border border-border text-xs sm:text-sm font-semibold text-text-primary transition-colors"
                  >
                    <Globe className="h-4 w-4 text-primary-700" aria-hidden="true" />
                    <span>Website</span>
                    <ExternalLink className="h-3 w-3 opacity-60" aria-hidden="true" />
                  </a>
                ) : null}
              </div>
            )}
          </div>

          {/* Location & Operating Details Card */}
          <div className="rounded-[12px] border border-border bg-surface-alt/70 p-4 space-y-3 text-xs sm:text-sm">
            <div className="flex items-start gap-2.5 text-text-secondary">
              <MapPin className="h-4 w-4 text-primary-700 shrink-0 mt-0.5" aria-hidden="true" />
              <div>
                <span className="font-semibold text-text-primary block mb-0.5">Verified Address</span>
                <p className="leading-relaxed">{store.address}</p>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2.5 border-t border-border/80">
              <div className="flex items-center gap-2 text-text-secondary">
                <Clock className="h-4 w-4 text-primary-700 shrink-0" aria-hidden="true" />
                <span>
                  <strong className="text-text-primary font-semibold">Hours: </strong>
                  {store.opening_hours || 'Mon–Sun: 9:00 AM – 9:30 PM'}
                </span>
              </div>
              {store.phone && (
                <div className="flex items-center gap-2 text-text-secondary">
                  <Phone className="h-4 w-4 text-primary-700 shrink-0" aria-hidden="true" />
                  <span>
                    <strong className="text-text-primary font-semibold">Contact: </strong>
                    {store.phone}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Department Guide & Items You Can Buy Here */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ShoppingBag className="h-4 w-4 text-primary-700" />
                <h3 className="font-bold text-sm sm:text-base text-text-primary">
                  In-Store Departments & Aisles
                </h3>
              </div>
              <span className="text-[11px] font-medium text-text-muted">
                Available In-Store
              </span>
            </div>
            <p className="text-xs text-text-secondary leading-relaxed">
              Explore what {store.name} offers during your in-person visit:
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {departments.map((dept, index) => (
                <div
                  key={index}
                  className="rounded-xl border border-border bg-surface p-3 space-y-2 shadow-none hover:border-border-strong transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-base select-none">{dept.icon}</span>
                    <h4 className="text-xs font-bold text-text-primary line-clamp-1">
                      {dept.title}
                    </h4>
                  </div>
                  <p className="text-[11px] text-text-secondary line-clamp-2 leading-relaxed">
                    {dept.description}
                  </p>
                  <div className="flex flex-wrap gap-1 pt-1">
                    {dept.popularItems.map((item, itemIdx) => (
                      <span
                        key={itemIdx}
                        className="inline-block text-[10px] font-medium text-text-secondary bg-surface-alt border border-border px-2 py-0.5 rounded-md"
                      >
                        {item}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Directory Notice & Merchant Claim Card */}
          <div className="rounded-[12px] border border-border bg-surface-alt p-4 space-y-3">
            <div className="flex items-start gap-3">
              <div className="h-8 w-8 rounded-xl bg-surface border border-border flex items-center justify-center shrink-0 text-text-secondary shadow-none">
                <Store className="h-4 w-4 text-primary-700" aria-hidden="true" />
              </div>
              <div className="space-y-1">
                <p className="font-bold text-xs sm:text-sm text-text-primary">
                  Neighbourhood In-Person Shopping
                </p>
                <p className="text-[11px] sm:text-xs text-text-secondary leading-relaxed">
                  {shopType.inStoreNotice} This business is listed from public verified records for neighbourhood discovery. Online ordering and doorstep delivery are currently unavailable for this store.
                </p>
              </div>
            </div>

            <div className="pt-2.5 border-t border-border flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs">
              <span className="text-text-secondary font-medium">
                Are you the store owner of {store.name}?
              </span>
              <div className="flex items-center gap-2">
                <Link
                  to={`/customer/shops/${encodeURIComponent(store.source_id)}`}
                  onClick={onClose}
                  className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-surface border border-border text-xs font-semibold text-text-primary hover:border-leaf transition-colors"
                >
                  <span>View Full Page</span>
                  <ExternalLink className="h-3 w-3 opacity-60" />
                </Link>
                <span className="inline-flex items-center gap-1 text-leaf font-semibold bg-surface border border-sage-tint px-3 py-1.5 rounded-lg shadow-none">
                  <Sparkles className="h-3 w-3" />
                  Claim Business
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="p-3.5 sm:p-4 border-t border-border bg-surface flex items-center justify-between text-xs text-text-muted shrink-0">
          <span>{store.attribution || 'Powered by Geoapify | © OpenStreetMap contributors'}</span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onClose}
            className="text-xs"
          >
            Close
          </Button>
        </div>
      </div>
    </div>
  )
}
