import { useOrders } from '@/hooks/useOrders'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ErrorState'
import { EmptyState } from '@/components/EmptyState'
import { getProductImage } from '@/lib/commerceMedia'
import { Package, ChevronRight, Clock } from 'lucide-react'
import { useNavigate, Link } from 'react-router-dom'
import { useState } from 'react'
import { formatCurrency } from '@/lib/utils'

const statusConfig: Record<string, { label: string; className: string }> = {
  delivered: { label: 'Delivered', className: 'badge-success' },
  cancelled: { label: 'Cancelled', className: 'badge-error' },
  pending: { label: 'Pending', className: 'badge-warning' },
  confirmed: { label: 'Confirmed', className: 'badge-info' },
  preparing: { label: 'Preparing', className: 'badge-info' },
  ready_for_pickup: { label: 'Ready for Pickup', className: 'badge-info' },
  processing: { label: 'Processing', className: 'badge-info' },
  out_for_delivery: { label: 'Out for Delivery', className: 'badge-info' },
}

const getStatusConfig = (status: string) =>
  statusConfig[status] ?? {
    label: status.replace(/_/g, ' '),
    className: 'badge-neutral',
  }

export const CustomerOrderHistory = () => {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)

  const { data, isLoading, isError, error, refetch } = useOrders(page, 10)

  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto space-y-4 animate-pulse">
        <div className="h-7 bg-[#EDF5EE] rounded w-36 mb-2" />
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-32 bg-white border border-[#E5E9E4] rounded-2xl" />
        ))}
      </div>
    )
  }

  if (isError) {
    return (
      <div className="max-w-4xl mx-auto">
        <ErrorState
          title="Could not load orders"
          message={error?.message || 'An error occurred'}
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  const orders = data?.items || []

  return (
    <div className="max-w-4xl mx-auto space-y-6 animate-fade-in">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="h-11 w-11 rounded-2xl bg-[#EDF5EE] border border-[#A8D5B5]/60 flex items-center justify-center">
            <Package className="h-5 w-5 text-[#176B45]" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-[#202923] leading-none">Order History</h1>
            {data && (
              <p className="text-xs sm:text-sm text-[#69736C] mt-1">
                {data.total} {data.total === 1 ? 'order' : 'orders'} placed
              </p>
            )}
          </div>
        </div>
      </div>

      {orders.length === 0 ? (
        <>
          <h2 className="sr-only">No Orders</h2>
          <EmptyState
            title="No Orders Yet"
            message="You haven't placed any orders yet. Discover shops nearby!"
            icon={<Package className="h-7 w-7" />}
            action={
              <Button
                onClick={() => navigate('/customer')}
                className="bg-[#176B45] hover:bg-[#104B32] text-white"
              >
                Browse Shops
              </Button>
            }
          />
        </>
      ) : (
        <>
          <div className="space-y-3.5">
            {orders.map((order) => {
              const { className } = getStatusConfig(order.status)
              return (
                <Link
                  key={order.id}
                  to={`/customer/orders/${order.id}`}
                  className="block bg-white border border-[#E5E9E4] rounded-2xl p-5 hover:border-[#176B45]/40 shadow-soft card-hover transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45]"
                >
                  <div className="flex items-start justify-between gap-3 mb-4">
                    <div>
                      <div className="flex items-center gap-2.5 flex-wrap">
                        <span className="font-bold text-[#202923] text-sm sm:text-base">
                          {`Order #${order.id.split('-')[0]}`}
                        </span>
                        <span className={`${className} capitalize`}>
                          {order.status.replace(/_/g, ' ')}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5 mt-1 text-xs text-[#69736C]">
                        <Clock className="h-3.5 w-3.5 text-[#176B45]" aria-hidden="true" />
                        {new Date(order.created_at).toLocaleDateString('en-IN', {
                          day: 'numeric',
                          month: 'short',
                          year: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="text-[11px] font-semibold uppercase tracking-wider text-[#69736C] mb-0.5">
                        Total
                      </p>
                      <p className="font-bold text-base sm:text-lg text-[#202923]">
                        {formatCurrency(order.total_amount)}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center justify-between border-t border-[#E5E9E4] pt-3.5 gap-4">
                    <div className="flex items-center gap-3 min-w-0">
                      {/* Item thumbnail stack */}
                      <div className="flex -space-x-2 shrink-0">
                        {order.items.slice(0, 3).map((item) => (
                          <div
                            key={item.id}
                            className="relative h-8 w-8 rounded-lg overflow-hidden bg-[#FAF9F6] border-2 border-white shadow-2xs flex items-center justify-center"
                          >
                            <Package className="h-4 w-4 text-[#176B45]/40" aria-hidden="true" />
                            <img
                              src={getProductImage(item.product_name)}
                              alt={item.product_name}
                              className="absolute inset-0 h-full w-full object-cover"
                              onError={(e) => {
                                e.currentTarget.style.display = 'none'
                              }}
                            />
                          </div>
                        ))}
                      </div>
                      <p className="text-xs text-[#69736C] line-clamp-1">
                        {order.items
                          .map((item) => `${item.quantity}× ${item.product_name}`)
                          .join(', ')}
                      </p>
                    </div>
                    <div className="flex items-center gap-1 text-xs font-bold text-[#176B45] shrink-0">
                      Track & Details <ChevronRight className="h-4 w-4" aria-hidden="true" />
                    </div>
                  </div>
                </Link>
              )
            })}
          </div>

          {/* Pagination */}
          {data && data.total > data.size && (
            <nav aria-label="Order pagination" className="flex justify-between items-center pt-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page === 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </Button>
              <span className="text-sm text-[#69736C]">
                Page {page} of {Math.ceil(data.total / data.size)}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= Math.ceil(data.total / data.size)}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </nav>
          )}
        </>
      )}
    </div>
  )
}
