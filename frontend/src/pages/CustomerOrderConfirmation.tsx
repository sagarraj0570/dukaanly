import { lazy, Suspense } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useOrder } from '@/hooks/useOrders'
import { useShop } from '@/hooks/useShops'
import { ErrorState } from '@/components/ErrorState'
import { Button } from '@/components/ui/button'
import { getProductImage, getShopCoverImage } from '@/lib/commerceMedia'
import { ProductImage } from '@/components/ProductImage'
import { formatCurrency } from '@/lib/utils'
import { CheckCircle, Clock, Store, XCircle, ArrowRight } from 'lucide-react'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

// Lazy-load 3D Order Success Scene
const OrderSuccessScene = lazy(() => import('@/components/three/OrderSuccessScene'))

export const CustomerOrderConfirmation = () => {
  useDocumentTitle('Order Confirmation')
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const { data: order, isLoading, isError, error, refetch } = useOrder(id)
  const { data: shop } = useShop(order?.shop_id || '')

  if (isLoading) {
    return (
      <div className="max-w-2xl mx-auto animate-pulse space-y-6">
        <div className="h-48 bg-primary-50 rounded-2xl" />
        <div className="h-32 bg-surface border border-border rounded-2xl" />
        <div className="h-24 bg-surface border border-border rounded-2xl" />
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
        bg: 'bg-primary-50',
        border: 'border-primary-200',
        icon: <CheckCircle className="h-14 w-14 text-primary-700" />,
        title: 'Order Confirmed!',
        subtitle: 'Your payment was successful and the shop has received your order.',
        textColor: 'text-primary-900',
      }
    : isCancelled
    ? {
        bg: 'bg-red-50',
        border: 'border-red-100',
        icon: <XCircle className="h-14 w-14 text-semantic-error" />,
        title: 'Order Cancelled',
        subtitle: 'This order was cancelled and will not be fulfilled.',
        textColor: 'text-semantic-error',
      }
    : {
        bg: 'bg-accent-100/70',
        border: 'border-accent-200',
        icon: <Clock className="h-14 w-14 text-accent-600" />,
        title: 'Payment Pending',
        subtitle: 'We are waiting for payment confirmation.',
        textColor: 'text-accent-700',
      }

  return (
    <div className="max-w-2xl mx-auto space-y-5 animate-fade-in">
      {/* Status header card */}
      <div className={`rounded-2xl border ${headerConfig.border} ${headerConfig.bg} p-8 text-center shadow-xs`}>
        {isConfirmed ? (
          <div className="mb-4 flex justify-center min-h-[128px]">
            <Suspense fallback={headerConfig.icon}>
              <OrderSuccessScene className="h-32 w-32 mx-auto" />
            </Suspense>
          </div>
        ) : (
          <div className="flex justify-center mb-4">{headerConfig.icon}</div>
        )}
        <h1 className={`text-2xl font-bold mb-2 ${headerConfig.textColor}`}>{headerConfig.title}</h1>
        <p className={`text-sm ${headerConfig.textColor} font-medium`}>{headerConfig.subtitle}</p>
      </div>

      {/* Order details card */}
      <div className="bg-surface border border-border rounded-2xl overflow-hidden shadow-soft">
        {/* Meta */}
        <div className="px-4 sm:px-6 py-4 border-b border-border bg-surface-alt grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4 text-sm">
          <div>
            <p className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-0.5">Reference</p>
            <p className="font-mono font-semibold text-text-primary text-xs">{order.id.split('-')[0].toUpperCase()}</p>
          </div>
          <div>
            <p className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-0.5">Date</p>
            <p className="font-semibold text-text-primary text-xs">
              {new Date(order.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
            </p>
          </div>
          <div>
            <p className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-0.5">Status</p>
            <span className="inline-flex items-center rounded-full bg-surface border border-border px-2.5 py-0.5 text-[11px] font-semibold text-text-primary capitalize">
              {order.status.replace(/_/g, ' ')}
            </span>
          </div>
        </div>

        {/* Shop + items */}
        <div className="p-4 sm:p-6 space-y-4">
          {shop && (
            <div className="flex items-center gap-3 mb-2">
              <div className="relative h-9 w-9 rounded-xl overflow-hidden bg-primary-50 border border-border shrink-0 flex items-center justify-center">
                <Store className="h-4 w-4 text-primary-500/40" aria-hidden="true" />
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
                <Store className="h-3.5 w-3.5 text-primary-700" aria-hidden="true" />
                <h2 className="truncate font-bold text-text-primary">{shop.name}</h2>
              </div>
            </div>
          )}

          <div className="bg-surface rounded-xl border border-border divide-y divide-border overflow-hidden">
            {order.items.map((item) => (
              <div key={item.id} className="flex justify-between items-center px-4 py-3.5 gap-4">
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <div className="relative h-10 w-10 rounded-lg overflow-hidden bg-surface-alt border border-border shrink-0 flex items-center justify-center">
                    <ProductImage
                      src={getProductImage(item.product_name)}
                      alt={item.product_name}
                      className="w-full h-full"
                      imageClassName="object-cover"
                    />
                  </div>
                  <div className="min-w-0">
                    <p className="font-semibold text-sm text-text-primary line-clamp-1">{item.product_name}</p>
                    <p className="text-xs text-text-secondary">Qty {item.quantity} × {formatCurrency(item.unit_price)}</p>
                  </div>
                </div>
                <span className="font-bold text-sm text-text-primary shrink-0">{formatCurrency(item.line_total)}</span>
              </div>
            ))}
            <div className="flex justify-between items-center px-4 py-3.5 bg-surface-alt">
              <p className="font-bold text-text-primary">Total Paid</p>
              <p className="font-bold text-lg text-text-primary">{formatCurrency(order.total_amount)}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex flex-col sm:flex-row gap-3">
        {isPending && (
          <Button
            onClick={() => navigate(`/customer/payment/${order.id}`)}
            className="sm:flex-1 gap-2 btn-primary"
          >
            Retry Payment <ArrowRight className="h-4 w-4" />
          </Button>
        )}
        {isConfirmed && (
          <Button
            onClick={() => navigate(`/customer/orders/${order.id}`)}
            className="sm:flex-1 gap-2 btn-primary"
          >
            Track Order
          </Button>
        )}
        <Button
          variant="outline"
          onClick={() => navigate('/customer')}
          className="sm:flex-1 border-border text-text-primary hover:bg-surface-alt"
        >
          Continue Shopping
        </Button>
      </div>
    </div>
  )
}
