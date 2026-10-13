import { useParams, useNavigate } from 'react-router-dom'
import { useOrder } from '@/hooks/useOrders'
import { useShop } from '@/hooks/useShops'
import { ErrorState } from '@/components/ErrorState'
import { Button } from '@/components/ui/button'
import { getProductImage, getShopCoverImage } from '@/lib/commerceMedia'
import { formatCurrency } from '@/lib/utils'
import { CheckCircle, Clock, Store, XCircle, ArrowRight, Package } from 'lucide-react'

export const CustomerOrderConfirmation = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const { data: order, isLoading, isError, error, refetch } = useOrder(id)
  const { data: shop } = useShop(order?.shop_id || '')

  if (isLoading) {
    return (
      <div className="max-w-2xl mx-auto animate-pulse space-y-6">
        <div className="h-48 bg-[#EDF5EE] rounded-2xl" />
        <div className="h-32 bg-white border border-[#E5E9E4] rounded-2xl" />
        <div className="h-24 bg-white border border-[#E5E9E4] rounded-2xl" />
      </div>
    )
  }

  if (isError || !order) {
    return (
      <div className="max-w-2xl mx-auto">
        <ErrorState
          title="Order not found"
          message={error?.message || "We couldn't retrieve this order's confirmation."}
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  const isConfirmed = order.status !== 'pending' && order.status !== 'cancelled'
  const isPending = order.status === 'pending'
  const isCancelled = order.status === 'cancelled'

  const headerConfig = isConfirmed
    ? {
        bg: 'bg-[#EDF5EE]',
        border: 'border-[#A8D5B5]',
        icon: <CheckCircle className="h-14 w-14 text-[#176B45]" />,
        title: 'Order Confirmed!',
        subtitle: 'Your payment was successful and the shop has received your order.',
        textColor: 'text-[#104B32]',
      }
    : isCancelled
    ? {
        bg: 'bg-red-50',
        border: 'border-red-100',
        icon: <XCircle className="h-14 w-14 text-red-500" />,
        title: 'Order Cancelled',
        subtitle: 'This order was cancelled and will not be fulfilled.',
        textColor: 'text-red-800',
      }
    : {
        bg: 'bg-amber-50',
        border: 'border-amber-200',
        icon: <Clock className="h-14 w-14 text-amber-500" />,
        title: 'Payment Pending',
        subtitle: 'We are waiting for payment confirmation.',
        textColor: 'text-amber-800',
      }

  return (
    <div className="max-w-2xl mx-auto space-y-5 animate-fade-in">
      {/* Status header card */}
      <div className={`rounded-2xl border ${headerConfig.border} ${headerConfig.bg} p-8 text-center shadow-xs`}>
        <div className="flex justify-center mb-4">{headerConfig.icon}</div>
        <h1 className={`text-2xl font-bold mb-2 ${headerConfig.textColor}`}>{headerConfig.title}</h1>
        <p className={`text-sm ${headerConfig.textColor} font-medium`}>{headerConfig.subtitle}</p>
      </div>

      {/* Order details card */}
      <div className="bg-white border border-[#E5E9E4] rounded-2xl overflow-hidden shadow-soft">
        {/* Meta */}
        <div className="px-4 sm:px-6 py-4 border-b border-[#E5E9E4] bg-[#FAF9F6] grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4 text-sm">
          <div>
            <p className="text-xs font-semibold text-[#69736C] uppercase tracking-wider mb-0.5">Reference</p>
            <p className="font-mono font-semibold text-[#202923] text-xs">{order.id.split('-')[0].toUpperCase()}</p>
          </div>
          <div>
            <p className="text-xs font-semibold text-[#69736C] uppercase tracking-wider mb-0.5">Date</p>
            <p className="font-semibold text-[#202923] text-xs">
              {new Date(order.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
            </p>
          </div>
          <div>
            <p className="text-xs font-semibold text-[#69736C] uppercase tracking-wider mb-0.5">Status</p>
            <span className="inline-flex items-center rounded-full bg-white border border-[#E5E9E4] px-2.5 py-0.5 text-[11px] font-semibold text-[#202923] capitalize">
              {order.status.replace(/_/g, ' ')}
            </span>
          </div>
        </div>

        {/* Shop + items */}
        <div className="p-4 sm:p-6 space-y-4">
          {shop && (
            <div className="flex items-center gap-3 mb-2">
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
              <div className="flex min-w-0 items-center gap-1.5">
                <Store className="h-3.5 w-3.5 text-[#176B45]" aria-hidden="true" />
                <h2 className="truncate font-bold text-[#202923]">{shop.name}</h2>
              </div>
            </div>
          )}

          <div className="bg-white rounded-xl border border-[#E5E9E4] divide-y divide-[#E5E9E4] overflow-hidden">
            {order.items.map((item) => (
              <div key={item.id} className="flex justify-between items-center px-4 py-3.5 gap-4">
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <div className="relative h-10 w-10 rounded-lg overflow-hidden bg-[#FAF9F6] border border-[#E5E9E4] shrink-0 flex items-center justify-center">
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
                    <p className="font-semibold text-sm text-[#202923] line-clamp-1">{item.product_name}</p>
                    <p className="text-xs text-[#69736C]">Qty {item.quantity} × {formatCurrency(item.unit_price)}</p>
                  </div>
                </div>
                <span className="font-bold text-sm text-[#202923] shrink-0">{formatCurrency(item.line_total)}</span>
              </div>
            ))}
            <div className="flex justify-between items-center px-4 py-3.5 bg-[#FAF9F6]">
              <p className="font-bold text-[#202923]">Total Paid</p>
              <p className="font-bold text-lg text-[#202923]">{formatCurrency(order.total_amount)}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex flex-col sm:flex-row gap-3">
        {isPending && (
          <Button
            onClick={() => navigate(`/customer/payment/${order.id}`)}
            className="sm:flex-1 gap-2 bg-[#176B45] hover:bg-[#104B32] text-white"
          >
            Retry Payment <ArrowRight className="h-4 w-4" />
          </Button>
        )}
        {isConfirmed && (
          <Button
            onClick={() => navigate(`/customer/orders/${order.id}`)}
            className="sm:flex-1 gap-2 bg-[#176B45] hover:bg-[#104B32] text-white"
          >
            Track Order
          </Button>
        )}
        <Button
          variant="outline"
          onClick={() => navigate('/customer')}
          className="sm:flex-1 border-[#E5E9E4] text-[#202923]"
        >
          Continue Shopping
        </Button>
      </div>
    </div>
  )
}
