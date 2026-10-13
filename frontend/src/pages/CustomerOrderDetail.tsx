import { useParams, useNavigate } from 'react-router-dom'
import { useOrder } from '@/hooks/useOrders'
import { useShop } from '@/hooks/useShops'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ErrorState'
import { CustomerDeliveryTracker } from '@/components/CustomerDeliveryTracker'
import { getProductImage, getShopCoverImage } from '@/lib/commerceMedia'
import { formatCurrency } from '@/lib/utils'
import { ArrowLeft, Package, Clock, Store } from 'lucide-react'

const statusConfig: Record<string, { label: string; className: string }> = {
  delivered: { label: 'Delivered', className: 'badge-success' },
  cancelled: { label: 'Cancelled', className: 'badge-error' },
  pending: { label: 'Pending Payment', className: 'badge-warning' },
  confirmed: { label: 'Confirmed', className: 'badge-info' },
  preparing: { label: 'Preparing', className: 'badge-info' },
  ready_for_pickup: { label: 'Ready for Pickup', className: 'badge-info' },
  out_for_delivery: { label: 'Out for Delivery', className: 'badge-info' },
}

const getStatusConfig = (status: string) =>
  statusConfig[status] ?? {
    label: status.replace(/_/g, ' '),
    className: 'badge-neutral',
  }

export const CustomerOrderDetail = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const { data: order, isLoading, isError, error, refetch } = useOrder(id)
  const { data: shop } = useShop(order?.shop_id || '')

  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto space-y-4 animate-pulse">
        <div className="h-8 bg-[#EDF5EE] rounded w-32" />
        <div className="h-24 bg-white border border-[#E5E9E4] rounded-2xl" />
        <div className="h-64 bg-white border border-[#E5E9E4] rounded-2xl" />
      </div>
    )
  }

  if (isError || !order) {
    return (
      <div className="max-w-4xl mx-auto">
        <ErrorState
          title="Order not found"
          message={error?.message || 'Could not retrieve order details'}
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  const { label, className } = getStatusConfig(order.status)

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <Button
        variant="ghost"
        onClick={() => navigate('/customer/orders')}
        className="gap-2 text-[#69736C] hover:text-[#202923] -ml-2"
      >
        <ArrowLeft className="h-4 w-4" /> Order History
      </Button>

      {/* Order Header Card */}
      <div className="bg-white border border-[#E5E9E4] rounded-2xl overflow-hidden shadow-soft">
        <div className="px-6 py-5 bg-[#FAF9F6] border-b border-[#E5E9E4] flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-xl font-bold text-[#202923]">
                {`Order #${order.id.split('-')[0]}`}
              </h1>
              <span className={className}>{label}</span>
            </div>
            <div className="flex items-center gap-1.5 mt-1 text-xs text-[#69736C]">
              <Clock className="h-3.5 w-3.5 text-[#176B45]" />
              <span>
                Placed{' '}
                {new Date(order.created_at).toLocaleString('en-IN', {
                  day: 'numeric',
                  month: 'short',
                  year: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </span>
            </div>
          </div>

          <div className="text-left sm:text-right">
            <p className="text-xs text-[#69736C] mb-0.5">Order Total</p>
            <p className="text-xl font-bold text-[#202923]">
              {formatCurrency(order.total_amount)}
            </p>
          </div>
        </div>

        {/* Shop Banner if available */}
        {shop && (
          <div className="px-6 py-3.5 border-b border-[#E5E9E4] flex items-center gap-3">
            <div className="relative h-9 w-9 rounded-xl overflow-hidden bg-[#EDF5EE] border border-[#E5E9E4] shrink-0 flex items-center justify-center">
              <Store className="h-4 w-4 text-[#176B45]/40" aria-hidden="true" />
              <img
                src={getShopCoverImage(shop.name, shop.description)}
                alt={shop.name}
                className="absolute inset-0 h-full w-full object-cover"
                onError={(e) => {
                  e.currentTarget.style.display = 'none'
                }}
              />
            </div>
            <div className="min-w-0">
              <p className="text-xs text-[#69736C]">Merchant</p>
              <p className="text-sm font-bold text-[#202923] truncate">{shop.name}</p>
            </div>
          </div>
        )}

        {/* Order Items with Thumbnails */}
        <div className="p-4 sm:p-6 space-y-4">
          <div className="flex items-center gap-2">
            <Package className="h-4.5 w-4.5 text-[#176B45]" aria-hidden="true" />
            <h2 className="text-base font-bold text-[#202923]">Order Items</h2>
          </div>

          <div className="border border-[#E5E9E4] rounded-2xl divide-y divide-[#E5E9E4] overflow-hidden">
            {order.items.map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between px-4 py-3.5 gap-4 bg-white"
              >
                <div className="flex items-center gap-3.5 min-w-0">
                  <div className="relative h-12 w-12 rounded-xl overflow-hidden bg-[#FAF9F6] border border-[#E5E9E4] shrink-0 flex items-center justify-center">
                    <Package className="h-5 w-5 text-[#176B45]/40" aria-hidden="true" />
                    <img
                      src={getProductImage(item.product_name)}
                      alt={item.product_name}
                      className="absolute inset-0 h-full w-full object-cover"
                      onError={(e) => {
                        e.currentTarget.style.display = 'none'
                      }}
                    />
                  </div>
                  <div className="min-w-0">
                    <p className="font-semibold text-sm text-[#202923] truncate">
                      {item.product_name}
                    </p>
                    <p className="text-xs text-[#69736C] mt-0.5">
                      Qty {item.quantity} × {formatCurrency(item.unit_price)}
                    </p>
                  </div>
                </div>
                <p className="font-bold text-sm text-[#202923] shrink-0">
                  {formatCurrency(item.line_total)}
                </p>
              </div>
            ))}

            <div className="px-4 py-3.5 bg-[#FAF9F6] flex justify-between items-center">
              <div className="flex items-center gap-1.5">
                <Store className="h-3.5 w-3.5 text-[#176B45]" />
                <span className="text-xs font-semibold text-[#69736C]">
                  Total Amount
                </span>
              </div>
              <p className="font-bold text-base text-[#202923]">
                {formatCurrency(order.total_amount)}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Live Delivery Tracking Timeline & Coordinates */}
      <CustomerDeliveryTracker
        delivery={order.delivery}
        orderStatus={order.status}
        onRefreshOrder={() => refetch()}
      />
    </div>
  )
}
