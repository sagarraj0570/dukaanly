import { useParams, useNavigate } from 'react-router-dom'
import { useOrder } from '@/hooks/useOrders'
import { useShop } from '@/hooks/useShops'
import { ErrorState } from '@/components/ErrorState'
import { Button } from '@/components/ui/button'
import { formatCurrency } from '@/lib/utils'
import { CheckCircle, Clock, Store, XCircle } from 'lucide-react'

export const CustomerOrderConfirmation = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  
  const { data: order, isLoading, isError, error, refetch } = useOrder(id)
  const { data: shop } = useShop(order?.shop_id || '')

  if (isLoading) {
    return (
      <div className="max-w-2xl mx-auto p-8 bg-white border rounded-xl shadow-sm text-center animate-pulse space-y-6">
        <div className="h-16 w-16 bg-gray-100 rounded-full mx-auto mb-4" />
        <div className="h-8 bg-gray-100 rounded w-1/2 mx-auto" />
        <div className="h-4 bg-gray-100 rounded w-3/4 mx-auto" />
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

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="bg-white border rounded-xl shadow-sm overflow-hidden">
        
        {/* Header Status */}
        <div className={`p-8 text-center border-b ${
          isConfirmed ? 'bg-green-50 border-green-100' :
          isCancelled ? 'bg-red-50 border-red-100' :
          'bg-yellow-50 border-yellow-100'
        }`}>
          {isConfirmed ? (
            <CheckCircle className="h-16 w-16 text-green-500 mx-auto mb-4" />
          ) : isCancelled ? (
            <XCircle className="h-16 w-16 text-red-500 mx-auto mb-4" />
          ) : (
            <Clock className="h-16 w-16 text-yellow-500 mx-auto mb-4" />
          )}
          
          <h1 className={`text-2xl font-bold mb-2 ${
            isConfirmed ? 'text-green-900' :
            isCancelled ? 'text-red-900' :
            'text-yellow-900'
          }`}>
            {isConfirmed ? 'Order Confirmed!' :
             isCancelled ? 'Order Cancelled' :
             'Payment Pending'}
          </h1>
          
          <p className={`text-sm ${
            isConfirmed ? 'text-green-700' :
            isCancelled ? 'text-red-700' :
            'text-yellow-700'
          }`}>
            {isConfirmed ? 'Your payment was successful and the shop has received your order.' :
             isCancelled ? 'This order was cancelled and will not be fulfilled.' :
             'We are waiting for payment confirmation.'}
          </p>
        </div>
        
        {/* Order Details */}
        <div className="p-6 lg:p-8 space-y-8">
          
          <div className="flex flex-col md:flex-row justify-between gap-6 pb-6 border-b">
            <div>
              <p className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-1">Order Reference</p>
              <p className="font-mono text-sm font-semibold text-gray-900">{order.id}</p>
            </div>
            <div>
              <p className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-1">Date</p>
              <p className="text-sm font-semibold text-gray-900">{new Date(order.created_at).toLocaleString()}</p>
            </div>
            <div>
              <p className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-1">Current Status</p>
              <span className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-semibold text-gray-800 capitalize border">
                {order.status.replace(/_/g, ' ')}
              </span>
            </div>
          </div>
          
          <div>
            <div className="flex items-center gap-2 mb-4">
              <Store className="h-5 w-5 text-gray-400" />
              <h2 className="text-lg font-bold text-gray-900">{shop?.name || 'Loading shop...'}</h2>
            </div>
            
            <div className="space-y-3 bg-gray-50 p-4 rounded-lg border">
              {order.items.map(item => (
                <div key={item.id} className="flex justify-between gap-4">
                  <div className="flex-1">
                    <p className="font-medium text-gray-900 line-clamp-1">{item.product_name}</p>
                    <p className="text-sm text-gray-500">Qty: {item.quantity} × {formatCurrency(item.unit_price)}</p>
                  </div>
                  <div className="font-semibold text-gray-900">
                    {formatCurrency(item.line_total)}
                  </div>
                </div>
              ))}
            </div>
          </div>
          
          <div className="flex justify-between items-center pt-6 border-t">
            <span className="font-bold text-gray-900 text-lg">Total Paid</span>
            <span className="font-extrabold text-2xl text-gray-900">{formatCurrency(order.total_amount)}</span>
          </div>
          
        </div>
      </div>
      
      <div className="flex flex-col sm:flex-row justify-center gap-4">
        {isPending && (
          <Button onClick={() => navigate(`/customer/payment/${order.id}`)} className="w-full sm:w-auto">
            Retry Payment
          </Button>
        )}
        <Button variant="outline" onClick={() => navigate('/customer')} className="w-full sm:w-auto">
          Continue Shopping
        </Button>
      </div>
    </div>
  )
}
