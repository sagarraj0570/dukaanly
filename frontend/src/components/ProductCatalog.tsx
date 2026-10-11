import { useState, useMemo } from 'react'
import { useShopProducts } from '@/hooks/useProducts'
import { ProductCard } from './ProductCard'
import { ErrorState } from './ErrorState'
import { EmptyState } from './EmptyState'
import { Button } from './ui/button'
import { ChevronLeft, ChevronRight, PackageSearch } from 'lucide-react'

interface ProductCatalogProps {
  shopId: string
}

export const ProductCatalog = ({ shopId }: ProductCatalogProps) => {
  const [page, setPage] = useState(1)
  const size = 12

  // We are not using category filter params unless we explicitly want a specific category.
  // We'll fetch active_only=true by default from our hook logic.
  const { data, isLoading, isError, error, refetch } = useShopProducts(shopId, page, size)

  const items = data?.items
  // Group products by category on the current page for organization, if there are any.
  const productsByCategory = useMemo(() => {
    if (!items) return {}
    
    const groups: Record<string, typeof items> = {}
    items.forEach(product => {
      const cat = product.category || 'Uncategorized'
      if (!groups[cat]) groups[cat] = []
      groups[cat].push(product)
    })
    
    // Sort keys so Uncategorized is at the bottom
    return Object.keys(groups).sort((a, b) => {
      if (a === 'Uncategorized') return 1
      if (b === 'Uncategorized') return -1
      return a.localeCompare(b)
    }).reduce((acc, key) => {
      acc[key] = groups[key]
      return acc
    }, {} as Record<string, typeof items>)
  }, [items])

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-64 rounded-lg bg-gray-100 animate-pulse border" />
          ))}
        </div>
      </div>
    )
  }

  if (isError) {
    return (
      <ErrorState 
        title="Failed to load products"
        message={error?.message || "Could not retrieve the catalog for this shop."}
        onRetry={() => refetch()}
      />
    )
  }

  const products = data?.items || []
  const totalPages = data ? Math.ceil(data.total / data.size) : 0

  if (products.length === 0 && page === 1) {
    return (
      <EmptyState 
        title="No products available"
        message="This shop hasn't added any active products yet."
        icon={<PackageSearch className="h-8 w-8" />}
      />
    )
  }

  return (
    <div className="space-y-10">
      {Object.entries(productsByCategory).map(([category, catProducts]) => (
        <section key={category}>
          <h3 className="text-xl font-bold text-gray-900 mb-4 pb-2 border-b">
            {category}
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {catProducts.map(product => (
              <ProductCard key={product.id} product={product} />
            ))}
          </div>
        </section>
      ))}

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between border-t pt-4 mt-6">
          <span className="text-sm text-gray-500">
            Page {page} of {totalPages}
          </span>
          <div className="flex items-center gap-2">
            <Button 
              variant="outline" 
              size="sm"
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
            >
              <ChevronLeft className="h-4 w-4 mr-1" /> Previous
            </Button>
            <Button 
              variant="outline" 
              size="sm"
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
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
