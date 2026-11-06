import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  MapPin,
  Clock,
  Bike,
  Store,
  CheckCircle2,
  ArrowUpRight,
  Pill,
  Cake,
  Milk,
} from 'lucide-react'
import type { Shop } from '@/hooks/useShops'
import { getShopCoverImage } from '@/lib/commerceMedia'
import {
  useLocationStore,
  DELIVERY_LIMIT_METERS,
  DELIVERY_LIMIT_KM,
  haversineDistanceKm,
} from '@/store/useLocationStore'
import { StatusStamp } from '@/components/ui/StatusStamp'
import { cn } from 'cn'

interface ShopCardProps {
  shop: Shop
  wide?: boolean
  className?: string
}

const getCategoryFallback = (category?: string | null, name?: string) => {
  const text = `${category || ''} ${name || ''}`.toLowerCase()
  if (text.includes('pharmacy') || text.includes('chemist') || text.includes('med')) {
    return {
      bg: 'bg-sage-tint text-leaf',
      iconBg: 'bg-sand text-leaf',
      Icon: Pill,
      label: 'Pharmacy & Health',
    }
  }
  if (text.includes('bakery') || text.includes('cake') || text.includes('bread') || text.includes('confectionery')) {
    return {
      bg: 'bg-turmeric-tint text-ink',
      iconBg: 'bg-sand text-ink',
      Icon: Cake,
      label: 'Bakery & Confectionery',
    }
  }
  if (text.includes('dairy') || text.includes('milk')) {
    return {
      bg: 'bg-sand text-ink',
      iconBg: 'bg-surface text-ink',
      Icon: Milk,
      label: 'Dairy & Daily Essentials',
    }
  }
  return {
    bg: 'bg-sand text-leaf',
    iconBg: 'bg-sage-tint text-leaf',
    Icon: Store,
    label: 'Grocery & Supermarket',
  }
}

export const ShopCard = ({ shop, wide = false, className }: ShopCardProps) => {
  const [imgError, setImgError] = useState(false)
  const coverUrl = getShopCoverImage(shop.name, shop.description)
  const { coords } = useLocationStore()

  // Strip "(Verified Partner)" from displayed shop name
  const cleanShopName = shop.name.replace(/\s*\(\s*verified\s+partner\s*\)/i, '').trim()
  const isVerified =
    shop.verification_status === 'verified' ||
    shop.name.toLowerCase().includes('verified partner')

  // Compute immediate client Haversine distance from active store coordinates
  const clientDistanceMeters =
    coords &&
    shop.location &&
    typeof shop.location.latitude === 'number' &&
    typeof shop.location.longitude === 'number'
      ? Math.round(
          haversineDistanceKm(
            coords.latitude,
            coords.longitude,
            shop.location.latitude,
            shop.location.longitude
          ) * 1000
        )
      : null

  // Prefer authoritative PostGIS distance from API when available and fresh for active coordinates;
  // if user switches location, immediately use client distance to prevent stale cached data
  let distanceMeters: number | null = null
  if (
    typeof shop.distance_meters === 'number' &&
    (clientDistanceMeters === null || Math.abs(shop.distance_meters - clientDistanceMeters) < 250)
  ) {
    distanceMeters = shop.distance_meters
  } else {
    distanceMeters = clientDistanceMeters ?? shop.distance_meters ?? null
  }

  // Distance formatting
  let distanceText: string | null = null
  if (typeof distanceMeters === 'number') {
    if (distanceMeters < 100) {
      distanceText = '0.1 km'
    } else if (distanceMeters < 1000) {
      distanceText = `${Math.round(distanceMeters)} m`
    } else {
      distanceText = `${(distanceMeters / 1000).toFixed(1)} km`
    }
  }

  // Delivery eligibility: prefer active distance check, fallback to API boolean
  const maxRadius = shop.delivery_radius_meters ?? DELIVERY_LIMIT_METERS
  const isDeliveryEligible =
    distanceMeters !== null
      ? distanceMeters <= maxRadius
      : typeof shop.is_delivery_eligible === 'boolean'
      ? shop.is_delivery_eligible
      : true

  const fallback = getCategoryFallback((shop as any).category, shop.name)
  const FallbackIcon = fallback.Icon

  return (
    <Link
      to={`/customer/shops/${shop.id}`}
      className={cn(
        "group flex flex-col bg-surface border border-border rounded-[14px] overflow-hidden shadow-none card-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf focus-visible:ring-offset-2 focus-visible:ring-offset-paper transition-all",
        wide && "md:flex-row",
        className
      )}
    >
      {/* 16:9 Image on top (or half-width when wide) */}
      <div
        className={cn(
          "relative w-full aspect-video bg-sand overflow-hidden shrink-0",
          wide && "md:w-1/2 md:aspect-auto md:min-h-[220px]"
        )}
      >
        {!imgError && coverUrl ? (
          <img
            src={coverUrl}
            alt={`${cleanShopName} storefront`}
            loading="lazy"
            onError={() => setImgError(true)}
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
          />
        ) : (
          <div className={`h-full w-full flex flex-col items-center justify-center ${fallback.bg} p-4 text-center`}>
            <div className={`h-12 w-12 rounded-[12px] ${fallback.iconBg} flex items-center justify-center mb-2`}>
              <FallbackIcon className="h-6 w-6" aria-hidden="true" />
            </div>
            <span className="text-xs font-bold tracking-wide uppercase">
              {fallback.label}
            </span>
          </div>
        )}

        {/* Subtle scrim for contrast */}
        <div className="absolute inset-0 bg-black/20 pointer-events-none" />

        {/* Distance pill (top-left) */}
        {distanceText && (
          <div className="absolute top-3 left-3">
            <span className="inline-flex items-center gap-1 rounded-full bg-ink/80 px-2.5 py-1 text-xs font-semibold text-paper border border-border/20 num">
              <MapPin className="h-3 w-3 text-leaf" aria-hidden="true" />
              {distanceText}
            </span>
          </div>
        )}

        {/* Open or Closed StatusStamp (top-right) */}
        <div className="absolute top-3 right-3">
          <StatusStamp tone={shop.is_active ? 'success' : 'danger'}>
            {shop.is_active ? 'Open' : 'Closed'}
          </StatusStamp>
        </div>
      </div>

      {/* Shop Content */}
      <div className="p-4 sm:p-5 flex flex-col flex-1 justify-between">
        <div>
          {/* Name in display font + Verified badge */}
          <div className="flex items-start justify-between gap-2 mb-1.5">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="font-display font-semibold text-lg sm:text-xl text-ink group-hover:text-leaf transition-colors line-clamp-1">
                {cleanShopName}
              </h3>
              {isVerified && (
                <span className="inline-flex items-center gap-0.5 rounded-[8px] bg-sage-tint text-leaf border border-leaf/20 px-2 py-0.5 text-[11px] font-bold">
                  <CheckCircle2 className="h-3 w-3 shrink-0" aria-hidden="true" />
                  Verified
                </span>
              )}
            </div>
            <ArrowUpRight className="h-4 w-4 text-ink-soft group-hover:text-leaf shrink-0 mt-1 transition-colors" aria-hidden="true" />
          </div>

          {shop.description ? (
            <p className="text-xs text-ink-soft line-clamp-2 mb-3 leading-relaxed">
              {shop.description}
            </p>
          ) : (
            <p className="text-xs text-ink-soft line-clamp-2 mb-3 leading-relaxed">
              Local neighbourhood store offering daily essentials and groceries.
            </p>
          )}

          {/* Clear Eligibility Line: "Delivers to you" in leaf, or "Pickup only - 6.6 km, delivery limit 5 km" in ink-soft */}
          <div className="mb-3">
            {!shop.is_orderable || shop.verification_status === 'discovered' ? (
              <div className="flex items-center gap-1.5 text-xs text-ink-soft">
                <Store className="h-3.5 w-3.5 shrink-0 text-ink-soft" aria-hidden="true" />
                <span>In-store shopping only</span>
              </div>
            ) : isDeliveryEligible ? (
              <div className="flex items-center gap-1.5 text-xs font-semibold text-leaf">
                <Bike className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span>Delivers to you</span>
              </div>
            ) : (
              <div className="flex items-center gap-1.5 text-xs text-ink-soft">
                <Store className="h-3.5 w-3.5 shrink-0 text-ink-soft" aria-hidden="true" />
                <span>
                  Pickup only{distanceText ? ` - ${distanceText}` : ''}, delivery limit {DELIVERY_LIMIT_KM} km
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Footer: Address (truncate to 1 line) + Hours */}
        <div className="pt-3 border-t border-border flex items-center justify-between gap-2 text-xs text-ink-soft">
          <div className="flex items-center gap-1.5 min-w-0">
            <MapPin className="h-3.5 w-3.5 shrink-0 text-leaf" aria-hidden="true" />
            <span className="truncate">{shop.address}</span>
          </div>

          {shop.opening_hours && (
            <span className="inline-flex items-center gap-1 shrink-0 text-[11px] text-ink-soft whitespace-nowrap">
              <Clock className="h-3 w-3 shrink-0" aria-hidden="true" />
              <span>{shop.opening_hours}</span>
            </span>
          )}
        </div>
      </div>
    </Link>
  )
}
