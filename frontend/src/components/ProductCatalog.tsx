import { useState, useMemo } from 'react'
import { useShopProducts } from '@/hooks/useProducts'
import { ProductCard } from './ProductCard'
import { ErrorState } from './ErrorState'
import { EmptyState } from './EmptyState'
import { Button } from './ui/button'
import { ChevronLeft, ChevronRight, PackageSearch, Search, X } from 'lucide-react'

interface ProductCatalogProps {
  shopId: string
}

export const ProductCatalog = ({ shopId }: ProductCatalogProps) => {
  const [page, setPage] = useState(1)
  const size = 20
  const [selectedCat, setSelectedCat] = useState<string>('All')
  const [searchQuery, setSearchQuery] = useState('')
  const [sortBy, setSortBy] = useState<'featured' | 'price-asc' | 'price-desc' | 'name'>('featured')

  const { data, isLoading, isError, error, refetch } = useShopProducts(shopId, page, size)

  const items = data?.items || []

  // Extract unique categories from items
  const availableCategories = useMemo(() => {
    const set = new Set<string>()
    items.forEach((p) => {
      if (p.category) set.add(p.category)
    })
    return ['All', ...Array.from(set)]
  }, [items])

  // Filter & sort
  const displayedProducts = useMemo(() => {
    let result = items

    if (selectedCat !== 'All') {
      result = result.filter((p) => p.category === selectedCat)
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim()
      result = result.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          (p.category && p.category.toLowerCase().includes(q)) ||
          (p.description && p.description.toLowerCase().includes(q))
      )
    }

    if (sortBy === 'price-asc') {
      return [...result].sort((a, b) => Number(a.price) - Number(b.price))
    }
    if (sortBy === 'price-desc') {
      return [...result].sort((a, b) => Number(b.price) - Number(a.price))
    }
    if (sortBy === 'name') {
      return [...result].sort((a, b) => a.name.localeCompare(b.name))
    }

    return result
  }, [items, selectedCat, searchQuery, sortBy])

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 sm:gap-5">
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={i}
              className="h-72 rounded-2xl bg-white border border-[#E5E9E4] p-4 animate-pulse space-y-3"
            >
              <div className="h-36 bg-[#EDF5EE] rounded-xl" />
              <div className="h-4 bg-[#EDF5EE] rounded w-3/4" />
              <div className="h-3 bg-[#EDF5EE] rounded w-1/3" />
              <div className="h-8 bg-[#EDF5EE] rounded-full mt-4" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (isError) {
    return (
      <ErrorState
        title="Failed to load products"
        message={error?.message || 'Could not retrieve the catalog for this shop.'}
        onRetry={() => refetch()}
      />
    )
  }

  const totalPages = data ? Math.ceil(data.total / data.size) : 0

  if (items.length === 0 && page === 1) {
    return (
      <EmptyState
        title="No products available"
        message="This shop hasn't added any active products yet."
        icon={<PackageSearch className="h-8 w-8" />}
      />
    )
  }

  return (
    <div className="space-y-6">
      {/* Category Tabs */}
      <div role="tablist" aria-label="Product categories" className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none border-b border-[#E5E9E4]">
        {availableCategories.map((cat) => {
          const isActive = selectedCat === cat
          return (
            <button
              key={cat}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => setSelectedCat(cat)}
              className={`px-4 py-2.5 text-xs sm:text-sm font-semibold border-b-2 transition-colors whitespace-nowrap -mb-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45] rounded-t-lg ${
                isActive
                  ? 'border-[#176B45] text-[#176B45]'
                  : 'border-transparent text-[#69736C] hover:text-[#202923]'
              }`}
            >
              {cat === 'All' ? 'All Products' : cat}
            </button>
          )
        })}
      </div>

      {/* In-Shop Search & Sort Controls */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="h-4 w-4 text-[#69736C] absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" aria-hidden="true" />
          <input
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search products in this shop..."
            aria-label="Search products in this shop"
            className="w-full h-10 pl-10 pr-8 rounded-full bg-white border border-[#E5E9E4] text-xs sm:text-sm text-[#202923] placeholder:text-[#69736C] focus:border-[#176B45] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45] transition-colors"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              aria-label="Clear search"
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[#69736C] hover:text-[#202923] p-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45] rounded-full"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          )}
        </div>

        <div className="flex items-center gap-2 text-xs text-[#69736C] self-end sm:self-auto">
          <label htmlFor="product-sort" className="font-medium whitespace-nowrap">
            Sort by
          </label>
          <select
            id="product-sort"
            value={sortBy}
            onChange={(e) =>
              setSortBy(
                e.target.value as 'featured' | 'price-asc' | 'price-desc' | 'name'
              )
            }
            className="h-9 px-3 rounded-xl bg-white border border-[#E5E9E4] text-xs font-semibold text-[#202923] focus:border-[#176B45] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45] transition-colors"
          >
            <option value="featured">Popular</option>
            <option value="price-asc">Price: Low to High</option>
            <option value="price-desc">Price: High to Low</option>
            <option value="name">Name (A–Z)</option>
          </select>
        </div>
      </div>

      {/* Screen reader live announcement */}
      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {displayedProducts.length} {displayedProducts.length === 1 ? 'product' : 'products'} available
      </div>

      {/* Product Grid */}
      {displayedProducts.length === 0 ? (
        <EmptyState
          title="No matching products"
          message="No products match your search or filter in this shop."
          icon={<PackageSearch className="h-8 w-8" />}
          action={
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setSelectedCat('All')
                setSearchQuery('')
              }}
            >
              Reset Filters
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 sm:gap-5">
          {displayedProducts.map((product) => (
            <ProductCard key={product.id} product={product} />
          ))}
        </div>
      )}

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between border-t border-[#E5E9E4] pt-4 mt-6">
          <span className="text-xs sm:text-sm text-[#69736C]">
            Page {page} of {totalPages}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
            >
              <ChevronLeft className="h-4 w-4 mr-1" /> Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
            >
              Next <ChevronRight className="h-4 w-4 ml-1" />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
