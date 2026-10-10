import { useState } from 'react'
import { useShops } from '@/hooks/useShops'
import { ShopCard } from '@/components/ShopCard'
import { ErrorState } from '@/components/ErrorState'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import { ChevronLeft, ChevronRight, Store } from 'lucide-react'

export const CustomerDashboard = () => {
  const [page, setPage] = useState(1)
  const size = 12

  const { data, isLoading, isError, error, refetch } = useShops(page, size)

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Shops in your area</h1>
          <p className="text-gray-500">Discover local businesses near you.</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-48 rounded-lg bg-gray-100 animate-pulse border" />
          ))}
        </div>
      </div>
    )
  }

  if (isError) {
    return (
      <ErrorState 
        title="Failed to load shops"
        message={error?.message || "Please check your connection and try again."}
        onRetry={() => refetch()}
      />
    )
  }

  const shops = data?.items || []
  const totalPages = data ? Math.ceil(data.total / data.size) : 0

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Shops in your area</h1>
          <p className="text-gray-500">Discover local businesses near you.</p>
        </div>
        
        {/* Placeholder for future Search / Filtering */}
        {/* Note: The backend API (GET /api/v1/shops) currently does not support search or category filters. 
            Once supported, the search input and category filters will be plugged in here. */}
        <div className="text-sm text-gray-400 italic">
          Search and filtering deferred to future backend milestone.
        </div>
      </div>

      {shops.length === 0 ? (
        <EmptyState 
          title="No shops found"
          message="There are currently no active shops available in the marketplace."
          icon={<Store className="h-8 w-8" />}
        />
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
            {shops.map((shop) => (
              <ShopCard key={shop.id} shop={shop} />
            ))}
          </div>

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
        </>
      )}
    </div>
  )
}
