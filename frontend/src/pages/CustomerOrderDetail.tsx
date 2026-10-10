import { useParams, useNavigate } from 'react-router-dom'
import { useOrder } from '@/hooks/useOrders'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ErrorState'
import { ArrowLeft, Package, AlertCircle } from 'lucide-react'

export const CustomerOrderDetail = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  
  const { data: order, isLoading, isError, error, refetch } = useOrder(id)

  if (isLoading) {
    return (
      <div className="max-w-3xl mx-auto p-6 space-y-6 animate-pulse">
        <div className="h-10 bg-gray-100 rounded w-1/4" />
        <div className="h-64 bg-gray-100 rounded-xl" />
      </div>
    )
  }

  if (isError || !order) {
    return (
      <div className="max-w-3xl mx-auto p-6">
        <ErrorState 
          title="Order not found"
          message={error?.message || "Could not retrieve order details"}
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <Button variant="ghost" onClick={() => navigate('/customer/orders')} className="-ml-4 text-gray-500">
        <ArrowLeft className="mr-2 h-4 w-4" /> Back to Orders
      </Button>

      <div className="bg-white border rounded-xl shadow-sm overflow-hidden">
        <div className="p-6 bg-gray-50 border-b">
          <div className="flex flex-col md:flex-row justify-between md:items-center gap-4">
            <div>
              <h1 className="text-xl font-bold text-gray-900 mb-1">
                Order #{order.id.split('-')[0]}
              </h1>
              <p className="text-sm text-gray-500">
                Placed on {new Date(order.created_at).toLocaleString()}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className={`px-3 py-1 rounded-full text-sm font-semibold capitalize ${
                ['delivered'].includes(order.status) ? 'bg-green-100 text-green-800' :
                ['cancelled'].includes(order.status) ? 'bg-red-100 text-red-800' :
                'bg-blue-100 text-blue-800'
              }`}>
                {order.status.replace(/_/g, ' ')}
              </span>
            </div>
          </div>
        </div>

        <div className="p-6 space-y-8">
          
          {/* Order Items */}
          <div className="space-y-4">
            <h2 className="text-lg font-bold text-gray-900 border-b pb-2">Items</h2>
            <div className="divide-y border rounded-lg">
              {order.items.map(item => (
                <div key={item.id} className="p-4 flex justify-between items-center bg-white">
                  <div>
                    <p className="font-semibold text-gray-900">{item.product_name}</p>
                    <p className="text-sm text-gray-500">Qty: {item.quantity} × ₹{Number(item.unit_price).toFixed(2)}</p>
                  </div>
                  <p className="font-medium text-gray-900">₹{Number(item.line_total).toFixed(2)}</p>
                </div>
              ))}
              <div className="p-4 bg-gray-50 flex justify-between items-center rounded-b-lg">
                <p className="font-bold text-gray-900">Total Amount</p>
                <p className="font-bold text-xl text-gray-900">₹{Number(order.total_amount).toFixed(2)}</p>
              </div>
            </div>
          </div>

          {/* Delivery Tracking Section */}
          <div className="space-y-4">
            <h2 className="text-lg font-bold text-gray-900 border-b pb-2">Delivery Tracking</h2>
            
            <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg text-amber-800 flex items-start gap-3">
              <AlertCircle className="h-5 w-5 mt-0.5 shrink-0" />
              <div>
                <p className="font-semibold mb-1">Tracking Unavailable</p>
                <p className="text-sm">
                  Live delivery tracking cannot be initialized because the backend API does not currently expose the <code>delivery_id</code> to the customer via the Order endpoints. This missing contract prevents fetching delivery status or subscribing to real-time location updates.
                </p>
              </div>
            </div>

            <div className="p-4 bg-gray-50 border rounded-lg flex items-center justify-center py-8">
              <div className="text-center text-gray-400">
                <Package className="h-10 w-10 mx-auto mb-2 opacity-50" />
                <p>Waiting for backend contract implementation...</p>
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  )
}
