import { useState, useMemo, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useShops } from '@/hooks/useShops'
import { useNearbyDiscovery } from '@/hooks/useNearbyDiscovery'
import { ShopCard } from '@/components/ShopCard'
import {
  NearbyDiscoverySection,
  isNonNeighbourhoodStore,
} from '@/components/NearbyDiscoverySection'
import { LocationModal } from '@/components/LocationModal'
import { ErrorState } from '@/components/ErrorState'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { COMMERCE_CATEGORIES } from '@/lib/commerceMedia'
import {
  ChevronLeft,
  ChevronRight,
  Store,
  Sparkles,
  X,
  ShoppingBag,
  MapPin,
  Zap,
  Compass,
} from 'lucide-react'
import {
  useLocationStore,
  isInPatnaBoundingBox,
  DELIVERY_LIMIT_METERS,
  haversineDistanceKm,
} from '@/store/useLocationStore'

const ShopCardSkeleton = () => (
  <div className="bg-surface border border-border rounded-[14px] overflow-hidden animate-pulse flex flex-col">
    <div className="bg-sand aspect-video w-full" />
    <div className="p-4 sm:p-5 space-y-3 flex-1 flex flex-col justify-between">
      <div className="space-y-2">
        <div className="h-5 bg-sand rounded w-2/3" />
        <div className="h-3.5 bg-sand rounded w-full" />
        <div className="h-3.5 bg-sand rounded w-4/5" />
      </div>
      <div className="pt-3 border-t border-border flex justify-between">
        <div className="h-3.5 bg-sand rounded w-1/3" />
        <div className="h-3.5 bg-sand rounded w-1/4" />
      </div>
    </div>
  </div>
)

export const CustomerDashboard = () => {
  useDocumentTitle('Local Stores')
  const [page, setPage] = useState(1)
  const size = 12
  const [searchParams, setSearchParams] = useSearchParams()
  const urlQuery = searchParams.get('q') || ''

  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'all' | 'online' | 'directory'>('all')
  const [sortBy, setSortBy] = useState<'closest' | 'featured' | 'name' | 'open'>('closest')
  const [isLocationModalOpen, setIsLocationModalOpen] = useState(false)
  const [isPatnaBannerDismissed, setIsPatnaBannerDismissed] = useState(false)

  const openLocationModal = () => setIsLocationModalOpen(true)
  const closeLocationModal = () => setIsLocationModalOpen(false)

  const {
    coords,
    radiusMeters,
    deliveryOnly,
    isGpsDenied,
    setRadius,
    toggleDeliveryOnly,
    setDemoPatnaLocation,
  } = useLocationStore()

  useEffect(() => {
    if (!coords) {
      setDemoPatnaLocation()
    }
  }, [coords, setDemoPatnaLocation])

  // Registered Dukaanly Partner Shops (orderable, verified inventory)
  const { data, isLoading, isError, error, refetch } = useShops({
    page,
    size,
    latitude: coords?.latitude,
    longitude: coords?.longitude,
    radius_meters: radiusMeters,
    delivery_only: deliveryOnly,
    verified_only: true,
  })

  // Real-world nearby physical stores discovered via Geoapify
  const discoveryCategory = selectedCategory
    ? selectedCategory.toLowerCase().split(' ')[0]
    : undefined

  const {
    data: discoveryData,
    isLoading: isDiscoveryLoading,
    isError: isDiscoveryError,
    error: discoveryError,
    refetch: refetchDiscovery,
    isFetching: isDiscoveryFetching,
  } = useNearbyDiscovery({
    lat: coords?.latitude,
    lon: coords?.longitude,
    radius: radiusMeters,
    category: discoveryCategory,
    limit: 15,
  })

  const rawDiscoveryItems = useMemo(
    () => discoveryData?.items || [],
    [discoveryData?.items]
  )

  // Filter out non-neighbourhood places so counts agree
  const filteredDiscoveryItems = useMemo(() => {
    return rawDiscoveryItems.filter(
      (item) => !isNonNeighbourhoodStore(item.name, item.category)
    )
  }, [rawDiscoveryItems])

  const discoveryCount = filteredDiscoveryItems.length

  const clearFilters = () => {
    setSelectedCategory(null)
    setSearchParams({})
  }

  const shops = data?.items || []

  // Check shop delivery eligibility based on active location and shared limit constant
  const isShopEligibleForDelivery = (shop: (typeof shops)[0]): boolean => {
    let dMeters: number | null = null
    if (
      coords &&
      shop.location &&
      typeof shop.location.latitude === 'number' &&
      typeof shop.location.longitude === 'number'
    ) {
      dMeters = Math.round(
        haversineDistanceKm(
          coords.latitude,
          coords.longitude,
          shop.location.latitude,
          shop.location.longitude
        ) * 1000
      )
    } else if (typeof shop.distance_meters === 'number') {
      dMeters = shop.distance_meters
    }
    const maxR = shop.delivery_radius_meters ?? DELIVERY_LIMIT_METERS
    return dMeters !== null ? dMeters <= maxR : (shop.is_delivery_eligible ?? true)
  }

  const filteredShops = useMemo(() => {
    const query = urlQuery.trim().toLowerCase()
    const cat = selectedCategory?.toLowerCase()

    const list = shops.filter((shop) => {
      const hay = `${shop.name} ${shop.description || ''} ${shop.address}`.toLowerCase()
      const matchesQuery = !query || hay.includes(query)
      if (!matchesQuery) return false

      if (cat) {
        const isGeneralStore =
          hay.includes('kirana') ||
          hay.includes('general') ||
          hay.includes('grocery') ||
          hay.includes('mart')
        const matchesCat = isGeneralStore || hay.includes(cat.split(' ')[0])
        if (!matchesCat) return false
      }

      if (deliveryOnly && !isShopEligibleForDelivery(shop)) {
        return false
      }

      return true
    })

    if (sortBy === 'closest') {
      return [...list].sort((a, b) => {
        const getDist = (s: typeof a) => {
          if (coords && s.location) {
            return haversineDistanceKm(
              coords.latitude,
              coords.longitude,
              s.location.latitude,
              s.location.longitude
            )
          }
          return s.distance_meters ?? 999999
        }
        return getDist(a) - getDist(b)
      })
    }
    if (sortBy === 'name') {
      return [...list].sort((a, b) => a.name.localeCompare(b.name))
    }
    if (sortBy === 'open') {
      return [...list].sort((a, b) => Number(b.is_active) - Number(a.is_active))
    }
    return list
  }, [shops, urlQuery, selectedCategory, sortBy, deliveryOnly, coords])

  // Count how many partner shops deliver to the active location
  const deliveringShopsCount = useMemo(() => {
    return filteredShops.filter((s) => isShopEligibleForDelivery(s)).length
  }, [filteredShops, coords])

  if (isError) {
    return (
      <ErrorState
        title="Failed to load shops"
        message={error?.message || 'Please check your connection and try again.'}
        onRetry={() => refetch()}
      />
    )
  }

  const totalPages = data ? Math.ceil(data.total / data.size) : 0
  const hasActiveFilters = Boolean(urlQuery.trim() || selectedCategory)

  // Service area check
  const isOutsidePatna = coords ? !isInPatnaBoundingBox(coords) : false
  const showPatnaNotice = !isPatnaBannerDismissed && (isOutsidePatna || isGpsDenied)

  return (
    <div className="space-y-8 max-w-6xl mx-auto animate-in fade-in-50 duration-200">
      
      {/* 1. Dismissible Patna Demo Location Banner (shown when GPS is denied or outside Patna) */}
      {showPatnaNotice && (
        <div
          role="region"
          aria-label="Patna Service Area Banner"
          className="rounded-[14px] border border-turmeric/40 bg-turmeric-tint/60 p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs sm:text-sm text-ink"
        >
          <div className="flex items-center gap-2.5">
            <div className="h-8 w-8 rounded-[8px] bg-sand flex items-center justify-center shrink-0 text-leaf">
              <MapPin className="h-4 w-4" aria-hidden="true" />
            </div>
            <div>
              <p className="font-bold text-ink">
                Dukaanly serves Patna. Explore with a Patna demo location
              </p>
              <p className="text-ink-soft text-xs">
                Switch to central Boring Road to explore orderable partner stores, live inventory, and express delivery.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Button
              type="button"
              size="sm"
              onClick={() => {
                setDemoPatnaLocation()
                setIsPatnaBannerDismissed(true)
              }}
              className="text-xs font-semibold px-3 py-1.5 h-8 bg-leaf text-white hover:bg-leaf/90"
            >
              Explore Boring Road, Patna (demo)
            </Button>
            <button
              type="button"
              onClick={() => setIsPatnaBannerDismissed(true)}
              className="text-ink-soft hover:text-ink p-1 rounded-full shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf cursor-pointer"
              aria-label="Dismiss banner"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* 2. Hero Section: Directly on Paper Background with Hairline Divider Below */}
      <section className="space-y-4 pt-1">
        <div>
          <h1 className="font-display text-2xl sm:text-3xl lg:text-[34px] font-semibold text-ink tracking-tight">
            Aapke mohalle ki dukaanein
          </h1>
          <p className="text-xs sm:text-sm text-ink-soft mt-1 max-w-2xl leading-relaxed">
            Patna ke vishwasniya mohalla kirana, dairy aur medical stores se seedhe aapke ghar tak.
          </p>
        </div>

        {/* Category Row: a single horizontally scrollable row with snap, equal-width tiles */}
        <div className="pt-2">
          <div className="flex overflow-x-auto gap-3 pb-2 scrollbar-none snap-x snap-mandatory">
            {COMMERCE_CATEGORIES.map((cat) => {
              const isSelected = selectedCategory === cat.id
              return (
                <button
                  key={cat.id}
                  type="button"
                  aria-pressed={isSelected}
                  onClick={() =>
                    setSelectedCategory((prev) => (prev === cat.id ? null : cat.id))
                  }
                  className={`group snap-start shrink-0 flex-1 min-w-[80px] sm:min-w-[96px] flex flex-col items-center p-2 rounded-[12px] border text-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf cursor-pointer ${
                    isSelected
                      ? 'bg-sage-tint border-leaf text-leaf'
                      : 'bg-surface border-border hover:bg-sand text-ink'
                  }`}
                >
                  {/* Photo: 56px rounded-12px with sand overlay and saturate(0.85) */}
                  <div className="relative h-14 w-14 rounded-[12px] overflow-hidden mb-2 border border-border/60 shrink-0 bg-sand">
                    <img
                      src={cat.imageUrl}
                      alt={cat.label}
                      loading="lazy"
                      className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-105 filter saturate-[0.85]"
                      onError={(e) => {
                        e.currentTarget.style.display = 'none'
                      }}
                    />
                    <div className="absolute inset-0 bg-sand/20 mix-blend-multiply pointer-events-none" />
                  </div>
                  {/* Label under it: 2 lines allowed, no truncation */}
                  <span className="text-xs font-semibold leading-tight text-center line-clamp-2 min-h-[32px] flex items-center justify-center text-ink">
                    {cat.label}
                  </span>
                </button>
              )
            })}
          </div>
        </div>

        {/* Hairline divider below hero */}
        <div className="border-b border-border pt-2" />
      </section>

      {/* 3. Filter & Tab Switcher */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
        <div className="inline-flex p-1 rounded-[12px] bg-sand border border-border self-start flex-wrap gap-1">
          <button
            type="button"
            data-testid="tab-all-stores"
            onClick={() => setActiveTab('all')}
            className={`px-3.5 py-1.5 rounded-[8px] text-xs sm:text-sm font-semibold transition-colors inline-flex items-center gap-1.5 cursor-pointer ${
              activeTab === 'all'
                ? 'bg-leaf text-white'
                : 'text-ink-soft hover:text-ink'
            }`}
          >
            <Store className="h-4 w-4" aria-hidden="true" />
            <span>All Stores ({filteredShops.length + discoveryCount})</span>
          </button>
          <button
            type="button"
            data-testid="tab-order-online"
            onClick={() => setActiveTab('online')}
            className={`px-3.5 py-1.5 rounded-[8px] text-xs sm:text-sm font-semibold transition-colors inline-flex items-center gap-1.5 cursor-pointer ${
              activeTab === 'online'
                ? 'bg-leaf text-white'
                : 'text-ink-soft hover:text-ink'
            }`}
          >
            <Zap className="h-4 w-4" aria-hidden="true" />
            <span>Order Online ({filteredShops.length})</span>
          </button>
          <button
            type="button"
            data-testid="tab-in-store"
            onClick={() => setActiveTab('directory')}
            className={`px-3.5 py-1.5 rounded-[8px] text-xs sm:text-sm font-semibold transition-colors inline-flex items-center gap-1.5 cursor-pointer ${
              activeTab === 'directory'
                ? 'bg-leaf text-white'
                : 'text-ink-soft hover:text-ink'
            }`}
          >
            <Compass className="h-4 w-4" aria-hidden="true" />
            <span>In-Store Places ({discoveryCount})</span>
          </button>
        </div>

        {/* Consistent Summary Counts */}
        <div className="text-xs text-ink-soft flex items-center gap-1.5 flex-wrap">
          <span className="num font-semibold text-ink">{filteredShops.length}</span>
          <span>online partner stores</span>
          <span>•</span>
          <span className="num font-semibold text-ink">{discoveryCount}</span>
          <span>in-store places</span>
        </div>
      </div>

      {/* 4. Partner Shops Near You */}
      {(activeTab === 'all' || activeTab === 'online') && (
        <section className="space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
            <div>
              {/* Computed Eyebrow: Never claim delivery when every card says Pickup only */}
              <div className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider mb-1">
                <ShoppingBag className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                {deliveringShopsCount > 0 ? (
                  <span className="text-leaf">
                    {deliveringShopsCount} {deliveringShopsCount === 1 ? 'shop delivers' : 'shops deliver'} to you
                  </span>
                ) : (
                  <span className="text-ink-soft">
                    These shops are outside the delivery area. Pickup available.
                  </span>
                )}
              </div>

              <h2 className="font-display text-xl sm:text-2xl font-semibold text-ink">
                Partner shops near you
              </h2>
              {data && (
                <p className="text-xs sm:text-sm text-ink-soft mt-0.5">
                  {hasActiveFilters
                    ? `Showing ${filteredShops.length} of ${data.total} verified partner stores`
                    : `${filteredShops.length} verified partner stores found within ${Math.round(radiusMeters / 1000)} km`}
                </p>
              )}
            </div>

            <div className="flex items-center gap-2.5 flex-wrap">
              {/* Radius Selector Pills */}
              <div className="flex items-center gap-1 p-1 rounded-[10px] bg-sand border border-border">
                {[
                  { m: 3000, label: '3 km' },
                  { m: 5000, label: '5 km' },
                  { m: 10000, label: '10 km' },
                ].map((chip) => (
                  <button
                    key={chip.m}
                    type="button"
                    onClick={() => setRadius(chip.m)}
                    aria-pressed={radiusMeters === chip.m}
                    aria-label={`Search radius ${chip.label}`}
                    className={`px-2.5 py-1 rounded-[6px] text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf cursor-pointer ${
                      radiusMeters === chip.m
                        ? 'bg-leaf text-white'
                        : 'text-ink-soft hover:text-ink hover:bg-surface'
                    }`}
                  >
                    {chip.label}
                  </button>
                ))}
              </div>

              {/* Delivery-Only Toggle: Proper checkbox/switch labeled "Delivering to me only" */}
              <label className="inline-flex items-center gap-2 h-9 px-3 rounded-[10px] bg-surface border border-border text-xs font-semibold text-ink cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={deliveryOnly}
                  onChange={toggleDeliveryOnly}
                  className="h-4 w-4 rounded border-border text-leaf focus:ring-leaf accent-[var(--leaf)] cursor-pointer"
                />
                <span>Delivering to me only</span>
              </label>

              {hasActiveFilters && (
                <button
                  type="button"
                  onClick={clearFilters}
                  aria-label={`Remove filter: ${selectedCategory || urlQuery}`}
                  className="inline-flex items-center gap-1.5 h-9 px-3 rounded-[10px] bg-sage-tint text-leaf text-xs font-semibold border border-leaf/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf cursor-pointer"
                >
                  <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>
                    {selectedCategory ? selectedCategory : `"${urlQuery}"`}
                  </span>
                  <X className="h-3.5 w-3.5 ml-0.5" aria-hidden="true" />
                </button>
              )}

              <div className="flex items-center gap-2 text-xs text-ink-soft">
                <label htmlFor="shop-sort" className="font-medium">
                  Sort by
                </label>
                <select
                  id="shop-sort"
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as 'closest' | 'featured' | 'name' | 'open')}
                  className="h-9 px-3 rounded-[10px] bg-surface border border-border text-xs font-semibold text-ink focus:border-leaf focus:outline-none focus-visible:ring-2 focus-visible:ring-leaf"
                >
                  <option value="closest">Closest First</option>
                  <option value="featured">Featured</option>
                  <option value="open">Open First</option>
                  <option value="name">Name (A–Z)</option>
                </select>
              </div>
            </div>
          </div>

          {isLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              <ShopCardSkeleton />
              <ShopCardSkeleton />
              <ShopCardSkeleton />
            </div>
          ) : filteredShops.length === 0 ? (
            <div className="space-y-4">
              <EmptyState
                title={hasActiveFilters ? 'No matching partner shops found' : 'No partner shops found in radius'}
                message={
                  hasActiveFilters
                    ? 'Try clearing your search or selecting a different category.'
                    : deliveryOnly
                    ? `No delivery-eligible partner shops found within ${Math.round(radiusMeters / 1000)} km. Try turning off the delivery filter or expanding your radius.`
                    : 'There are currently no active partner shops in this radius. You can still discover physical stores below.'
                }
                illustrationType={hasActiveFilters ? 'search' : 'store'}
                icon={<Store className="h-7 w-7 text-leaf" />}
                action={
                  hasActiveFilters ? (
                    <Button variant="outline" onClick={clearFilters}>
                      Reset Filters
                    </Button>
                  ) : radiusMeters < 10000 ? (
                    <Button
                      type="button"
                      onClick={() => {
                        setRadius(10000)
                        if (deliveryOnly) toggleDeliveryOnly()
                      }}
                      variant="default"
                    >
                      Expand Search to 10 km
                    </Button>
                  ) : undefined
                }
              />
            </div>
          ) : (
            <>
              {/* Partner Shops Grid:
                  1 shop = 1 wide horizontal card;
                  2 shops = 2 equal cards;
                  3+ shops = responsive grid of equal cards (minmax 300px, 1fr) */}
              <div
                className={
                  filteredShops.length === 1
                    ? "grid grid-cols-1"
                    : filteredShops.length === 2
                    ? "grid grid-cols-1 md:grid-cols-2 gap-6"
                    : "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
                }
              >
                {filteredShops.map((shop) => (
                  <ShopCard
                    key={shop.id}
                    shop={shop}
                    wide={filteredShops.length === 1}
                  />
                ))}
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between mt-8 pt-6 border-t border-border">
                  <span className="text-sm text-ink-soft">
                    Page <span className="num font-semibold text-ink">{page}</span> of <span className="num font-semibold text-ink">{totalPages}</span>
                  </span>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      disabled={page === 1}
                      className="gap-1"
                    >
                      <ChevronLeft className="h-4 w-4" /> Previous
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                      disabled={page >= totalPages}
                      className="gap-1"
                    >
                      Next <ChevronRight className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </section>
      )}

      {/* 5. Directory Section: Collapsed to 6 compact rows by default, attribution kept */}
      {(activeTab === 'all' || activeTab === 'directory') && (
        <NearbyDiscoverySection
          selectedCategory={selectedCategory}
          previewLimit={activeTab === 'all' ? 6 : undefined}
          onViewAll={() => setActiveTab('directory')}
          items={filteredDiscoveryItems}
          isLoading={isDiscoveryLoading}
          isError={isDiscoveryError}
          error={discoveryError}
          refetch={refetchDiscovery}
          isFetching={isDiscoveryFetching}
          onOpenLocationModal={openLocationModal}
        />
      )}

      <LocationModal
        isOpen={isLocationModalOpen}
        onClose={closeLocationModal}
      />
    </div>
  )
}
export default CustomerDashboard
