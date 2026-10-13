import { useState, useMemo, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useShops } from '@/hooks/useShops'
import { ShopCard } from '@/components/ShopCard'
import { ErrorState } from '@/components/ErrorState'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import {
  COMMERCE_CATEGORIES,
  HERO_GROCERY_IMAGE,
} from '@/lib/commerceMedia'
import {
  ChevronLeft,
  ChevronRight,
  Store,
  Search,
  Sparkles,
  ShoppingBasket,
  X,
} from 'lucide-react'

const ShopCardSkeleton = () => (
  <div className="bg-white border border-[#E5E9E4] rounded-2xl overflow-hidden animate-pulse">
    <div className="h-44 bg-[#EDF5EE]" />
    <div className="p-4 space-y-3">
      <div className="h-5 bg-[#EDF5EE] rounded w-2/3" />
      <div className="h-3.5 bg-[#EDF5EE] rounded w-full" />
      <div className="h-3.5 bg-[#EDF5EE] rounded w-4/5" />
      <div className="h-px bg-[#E5E9E4] mt-3" />
      <div className="h-3.5 bg-[#EDF5EE] rounded w-1/2" />
    </div>
  </div>
)

export const CustomerDashboard = () => {
  const [page, setPage] = useState(1)
  const size = 12
  const [searchParams, setSearchParams] = useSearchParams()
  const urlQuery = searchParams.get('q') || ''

  const [heroSearch, setHeroSearch] = useState(urlQuery)
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
  const [sortBy, setSortBy] = useState<'featured' | 'name' | 'open'>('featured')
  const [heroImgError, setHeroImgError] = useState(false)

  useEffect(() => {
    setHeroSearch(urlQuery)
  }, [urlQuery])

  const { data, isLoading, isError, error, refetch } = useShops(page, size)

  const handleHeroSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = heroSearch.trim()
    if (trimmed) {
      setSearchParams({ q: trimmed })
    } else {
      setSearchParams({})
    }
  }

  const clearFilters = () => {
    setHeroSearch('')
    setSelectedCategory(null)
    setSearchParams({})
  }

  const shops = data?.items || []

  const filteredShops = useMemo(() => {
    const query = urlQuery.trim().toLowerCase()
    const cat = selectedCategory?.toLowerCase()

    const list = shops.filter((shop) => {
      const hay = `${shop.name} ${shop.description || ''} ${shop.address}`.toLowerCase()
      const matchesQuery = !query || hay.includes(query)

      if (!cat) return matchesQuery

      // General / kirana stores carry all core neighbourhood categories; otherwise match text
      const isGeneralStore =
        hay.includes('kirana') ||
        hay.includes('general') ||
        hay.includes('grocery') ||
        hay.includes('mart') ||
        hay.includes('test')
      const matchesCat = isGeneralStore || hay.includes(cat.split(' ')[0])
      return matchesQuery && matchesCat
    })

    if (sortBy === 'name') {
      return [...list].sort((a, b) => a.name.localeCompare(b.name))
    }
    if (sortBy === 'open') {
      return [...list].sort((a, b) => Number(b.is_active) - Number(a.is_active))
    }
    return list
  }, [shops, urlQuery, selectedCategory, sortBy])

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

  return (
    <div className="space-y-8">
      {/* Two-Column Neighbourhood Hero */}
      <section className="hero-surface rounded-3xl border border-[#E5E9E4] overflow-hidden shadow-soft">
        <div className="grid grid-cols-1 lg:grid-cols-12 items-center gap-6 lg:gap-8 p-6 sm:p-8 lg:p-10">
          {/* Left Column: Editorial Headline + Working Search */}
          <div className="lg:col-span-7 space-y-4">
            <div className="inline-flex items-center gap-2 text-[11px] sm:text-xs font-bold uppercase tracking-widest text-[#176B45]">
              <span>Local Shops</span>
              <span className="text-[#A8D5B5]">•</span>
              <span>Fresh Products</span>
              <span className="text-[#A8D5B5]">•</span>
              <span>Fast Delivery</span>
            </div>

            <h1 className="text-3xl sm:text-4xl lg:text-[42px] font-bold text-[#202923] tracking-tight leading-[1.12]">
              Your neighbourhood
              <br />
              delivered to your door
            </h1>

            <p className="text-sm sm:text-base text-[#69736C] max-w-xl leading-relaxed">
              Discover local shops, fresh groceries, snacks, daily essentials and more — all from your neighbourhood.
            </p>

            {/* Hero Search Bar */}
            <form
              onSubmit={handleHeroSearchSubmit}
              className="pt-2 flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5 max-w-xl"
              role="search"
            >
              <div className="relative flex-1">
                <Search className="h-4.5 w-4.5 text-[#69736C] absolute left-4 top-1/2 -translate-y-1/2 pointer-events-none" aria-hidden="true" />
                <input
                  type="search"
                  value={heroSearch}
                  onChange={(e) => {
                    setHeroSearch(e.target.value)
                    if (e.target.value.trim()) {
                      setSearchParams({ q: e.target.value }, { replace: true })
                    } else {
                      setSearchParams({}, { replace: true })
                    }
                  }}
                  placeholder="Search for shops or products..."
                  aria-label="Search for shops or products"
                  className="w-full h-12 pl-11 pr-9 rounded-xl bg-white border border-[#E5E9E4] text-sm text-[#202923] placeholder:text-[#69736C] shadow-soft focus:border-[#176B45] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45] transition-colors"
                />
                {heroSearch && (
                  <button
                    type="button"
                    onClick={clearFilters}
                    aria-label="Clear search query"
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[#69736C] hover:text-[#202923] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45] rounded-full p-0.5"
                  >
                    <X className="h-4 w-4" aria-hidden="true" />
                  </button>
                )}
              </div>
              <Button
                type="submit"
                className="h-12 px-6 rounded-xl bg-[#176B45] hover:bg-[#104B32] text-white font-semibold text-sm shrink-0 shadow-sm"
              >
                Search
              </Button>
            </form>
          </div>

          {/* Right Column: Fresh Produce & Grocery Bag Showcase */}
          <div className="lg:col-span-5">
            <div className="relative rounded-2xl overflow-hidden border border-[#E5E9E4] bg-[#EDF5EE] aspect-[16/11] shadow-card">
              {!heroImgError ? (
                <img
                  src={HERO_GROCERY_IMAGE}
                  alt="Fresh neighbourhood groceries and produce"
                  onError={() => setHeroImgError(true)}
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className="w-full h-full flex flex-col items-center justify-center bg-gradient-to-br from-[#EDF5EE] to-[#A8D5B5]/50 p-6 text-center">
                  <ShoppingBasket className="h-14 w-14 text-[#176B45] mb-2" aria-hidden="true" />
                  <p className="font-bold text-base text-[#104B32]">Dukaanly Fresh</p>
                  <p className="text-xs text-[#104B32] font-medium">Local shops · Stronger communities</p>
                </div>
              )}

              <div className="absolute inset-0 bg-gradient-to-t from-black/45 via-transparent to-transparent pointer-events-none" />

              {/* Branded Neighbourhood Badge Overlay */}
              <div className="absolute bottom-3.5 left-3.5 right-3.5 sm:right-auto bg-white/95 backdrop-blur-sm border border-[#E5E9E4] rounded-xl px-4 py-2.5 shadow-card flex items-center gap-3">
                <div className="h-9 w-9 rounded-lg bg-[#176B45] flex items-center justify-center shrink-0">
                  <Store className="h-4.5 w-4.5 text-white" aria-hidden="true" />
                </div>
                <div>
                  <p className="text-xs font-bold text-[#202923] leading-tight">
                    Dukaanly Neighbourhood
                  </p>
                  <p className="text-[11px] text-[#69736C]">
                    Local shops. Stronger communities.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Category Shortcuts Strip */}
        <div className="border-t border-[#E5E9E4] bg-white/80 px-4 sm:px-8 lg:px-10 py-3 sm:py-4">
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 sm:gap-3">
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
                  className={`group flex flex-col items-center p-2.5 rounded-xl border text-center transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45] ${
                    isSelected
                      ? 'bg-[#EDF5EE] border-[#176B45] shadow-soft'
                      : 'bg-white border-[#E5E9E4] hover:border-[#A8D5B5] hover:bg-[#FAF9F6]'
                  }`}
                >
                  <div
                    className="h-12 w-12 sm:h-14 sm:w-14 rounded-xl overflow-hidden mb-2 border border-[#E5E9E4]/60 shrink-0"
                    style={{ backgroundColor: cat.bgTint }}
                  >
                    <img
                      src={cat.imageUrl}
                      alt={cat.label}
                      loading="lazy"
                      className="h-full w-full object-cover group-hover:scale-105 transition-transform duration-200"
                      onError={(e) => {
                        e.currentTarget.style.display = 'none'
                      }}
                    />
                  </div>
                  <span
                    className={`text-xs font-semibold line-clamp-1 ${
                      isSelected ? 'text-[#176B45]' : 'text-[#202923]'
                    }`}
                  >
                    {cat.shortLabel}
                  </span>
                </button>
              )
            })}
          </div>
        </div>
      </section>

      {/* Shops Discovery Section */}
      <section className="space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
          <div>
            <h2 className="text-xl sm:text-2xl font-bold text-[#202923]">
              Shops in your area
            </h2>
            {data && (
              <p className="text-sm text-[#69736C] mt-0.5">
                {hasActiveFilters
                  ? `Showing ${filteredShops.length} of ${data.total} ${
                      data.total === 1 ? 'shop' : 'shops'
                    }`
                  : `${data.total} ${data.total === 1 ? 'shop' : 'shops'} available`}
              </p>
            )}
          </div>

          <div className="flex items-center gap-2.5 flex-wrap">
            {hasActiveFilters && (
              <button
                type="button"
                onClick={clearFilters}
                aria-label={`Remove filter: ${selectedCategory || urlQuery}`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#EDF5EE] text-[#176B45] text-xs font-semibold border border-[#A8D5B5] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45]"
              >
                <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                <span>
                  {selectedCategory ? selectedCategory : `"${urlQuery}"`}
                </span>
                <X className="h-3.5 w-3.5 ml-0.5" aria-hidden="true" />
              </button>
            )}

            <div className="flex items-center gap-2 text-xs text-[#69736C]">
              <label htmlFor="shop-sort" className="font-medium">
                Sort by
              </label>
              <select
                id="shop-sort"
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as 'featured' | 'name' | 'open')}
                className="h-9 px-3 rounded-xl bg-white border border-[#E5E9E4] text-xs font-semibold text-[#202923] focus:border-[#176B45] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45] transition-colors"
              >
                <option value="featured">Featured</option>
                <option value="open">Open First</option>
                <option value="name">Name (A–Z)</option>
              </select>
            </div>
          </div>
        </div>

        {isLoading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <ShopCardSkeleton key={i} />
            ))}
          </div>
        ) : filteredShops.length === 0 ? (
          <EmptyState
            title={hasActiveFilters ? 'No matching shops found' : 'No shops found'}
            message={
              hasActiveFilters
                ? 'Try clearing your search or selecting a different category.'
                : 'There are currently no active shops available in the marketplace.'
            }
            icon={<Store className="h-7 w-7" />}
            action={
              hasActiveFilters ? (
                <Button variant="outline" onClick={clearFilters}>
                  Reset Filters
                </Button>
              ) : undefined
            }
          />
        ) : (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {filteredShops.map((shop) => (
                <ShopCard key={shop.id} shop={shop} />
              ))}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-8 pt-6 border-t border-[#E5E9E4]">
                <span className="text-sm text-[#69736C]">
                  Page {page} of {totalPages}
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
    </div>
  )
}
