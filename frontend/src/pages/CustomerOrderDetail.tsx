import { useParams, useNavigate } from 'react-router-dom'
import { useOrder, useCancelOrder } from '@/hooks/useOrders'
import { useShop } from '@/hooks/useShops'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ErrorState'
import { CustomerDeliveryTracker } from '@/components/CustomerDeliveryTracker'
import { BillCard } from '@/components/ui/BillCard'
import { StatusStamp, orderStatusTone } from '@/components/ui/StatusStamp'
import { formatCurrency } from '@/lib/utils'
import { ArrowLeft, Clock, Store } from 'lucide-react'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

const statusConfig: Record<string, { label: string }> = {
  delivered: { label: 'Delivered' },
  cancelled: { label: 'Cancelled' },
  pending: { label: 'Pending Payment' },
  confirmed: { label: 'Confirmed' },
  preparing: { label: 'Preparing' },
  ready_for_pickup: { label: 'Ready for Pickup' },
  out_for_delivery: { label: 'Out for Delivery' },
}

const getStatusConfig = (status: string) =>
  statusConfig[status] ?? {
    label: status.replace(/_/g, ' '),
  }

export const CustomerOrderDetail = () => {
  useDocumentTitle('Order Details & Tracking')
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const { data: order, isLoading, isError, error, refetch } = useOrder(id)
  const { data: shop } = useShop(order?.shop_id || '')
  const cancelOrderMutation = useCancelOrder()

  if (isLoading) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-8 space-y-6 animate-pulse">
        <div className="h-8 bg-sand rounded w-32" />
        <div className="h-28 bg-surface border border-border rounded-[14px]" />
        <div className="h-96 bg-surface border border-border rounded-[14px]" />
      </div>
    )
  }

  if (isError || !order) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-8">
        <ErrorState
          title="Order not found"
          message={error?.message || 'Could not retrieve order details'}
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  const { label } = getStatusConfig(order.status)

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
      <Button
        variant="ghost"
        onClick={() => navigate('/customer/orders')}
        className="gap-2 text-ink-soft hover:text-ink -ml-2 text-sm cursor-pointer"
      >
        <ArrowLeft className="h-4 w-4" /> Order History
      </Button>

      {/* Top row: Order Number, StatusStamp, Shop Name */}
      <div className="rounded-[14px] border border-border bg-surface p-5 sm:p-6 shadow-none">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="font-display text-2xl sm:text-3xl font-semibold tracking-tight text-ink">
                {`Order #${order.id.split('-')[0]}`}
              </h1>
              <StatusStamp tone={orderStatusTone(order.status)}>{label}</StatusStamp>
              {shop && (
                <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-ink-soft bg-sand px-3 py-1 rounded-full border border-border">
                  <Store className="h-3.5 w-3.5 text-ink-soft" />
                  {shop.name}
                </span>
              )}
            </div>
            <div className="flex items-center gap-1.5 mt-2 text-xs text-ink-soft">
              <Clock className="h-3.5 w-3.5" />
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

          <div className="flex flex-col sm:items-end justify-between gap-2">
            <div>
              <p className="text-xs text-ink-soft sm:text-right">Order Total</p>
              <p className="num text-xl sm:text-2xl font-bold text-ink sm:text-right">
                {formatCurrency(order.total_amount)}
              </p>
            </div>
            {['pending', 'confirmed', 'preparing'].includes(order.status) &&
              (!order.delivery || ['pending', 'assigned'].includes(order.delivery.status)) && (
                <Button
                  variant="outline"
                  size="sm"
                  className="text-xs text-brick-ink border-border hover:bg-brick-tint/20 h-8 rounded-xl font-medium mt-1 cursor-pointer"
                  onClick={async () => {
                    let reason: string | undefined
                    if (order.status !== 'pending') {
                      const input = window.prompt('Please provide a reason for cancelling this order:')
                      if (!input || !input.trim()) {
                        alert('A cancellation reason is required.')
                        return
                      }
                      reason = input.trim()
                    } else {
                      if (!window.confirm('Are you sure you want to cancel this order?')) {
                        return
                      }
                    }
                    try {
                      await cancelOrderMutation.mutateAsync({ orderId: order.id, reason })
                      await refetch()
                    } catch (err: any) {
                      alert(err.response?.data?.detail?.message || err.response?.data?.detail || 'Failed to cancel order')
                    }
                  }}
                  disabled={cancelOrderMutation.isPending}
                >
                  {cancelOrderMutation.isPending ? 'Cancelling...' : 'Cancel Order'}
                </Button>
              )}
          </div>
        </div>
      </div>

      {/* Main: Live Leaflet map beside ETA panel */}
      <CustomerDeliveryTracker
        delivery={order.delivery}
        orderStatus={order.status}
        onRefreshOrder={() => refetch()}
      />

      {/* Below it: Order Items as a BillCard */}
      <div className="max-w-2xl">
        <BillCard
          title="Order Items"
          note={`${order.items.length} ${order.items.length === 1 ? 'item' : 'items'} ${shop?.name ? `from ${shop.name}` : ''}`}
          rows={order.items.map((item) => ({
            label: item.product_name,
            value: formatCurrency(item.line_total),
            sub: `Qty ${item.quantity} × ${formatCurrency(item.unit_price)}`,
          }))}
          footer={{
            label: 'Total Amount',
            value: formatCurrency(order.total_amount),
          }}
        />
      </div>
    </div>
  )
}
