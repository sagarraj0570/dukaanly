import { useOrders } from '@/hooks/useOrders'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ErrorState'
import { Package, ChevronRight } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useState } from 'react'

export const CustomerOrderHistory = () => {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  
  const { data, isLoading, isError, error, refetch } = useOrders(page, 10)

  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto space-y-4 animate-pulse">
        <div className="h-8 w-1/4 bg-gray-100 rounded mb-6" />
        <div className="h-32 bg-gray-100 rounded-lg" />
        <div className="h-32 bg-gray-100 rounded-lg" />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="max-w-4xl mx-auto">
        <ErrorState 
          title="Could not load orders"
          message={error?.message || "An error occurred"}
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  const orders = data?.items || []

  if (orders.length === 0) {
    return (
      <div className="max-w-4xl mx-auto text-center py-16 bg-white border rounded-lg shadow-sm">
        <Package className="mx-auto h-16 w-16 text-gray-300 mb-4" />
        <h2 className="text-2xl font-bold text-gray-900 mb-2">No Orders Yet</h2>
        <p className="text-gray-500 mb-8">You haven't placed any orders yet. Discover shops nearby!</p>
        <Button onClick={() => navigate('/customer')}>
          Browse Shops
        </Button>
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Order History</h1>
      
      <div className="space-y-4">
        {orders.map(order => (
          <div 
            key={order.id} 
            onClick={() => navigate(`/customer/orders/${order.id}`)}
            className="bg-white border rounded-lg p-5 shadow-sm hover:border-primary cursor-pointer transition-colors"
          >
            <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4 mb-4">
              <div>
                <p className="text-sm text-gray-500 mb-1">
                  Ordered on {new Date(order.created_at).toLocaleDateString()} at {new Date(order.created_at).toLocaleTimeString()}
                </p>
                <div className="flex items-center gap-2 text-sm font-medium">
                  Order #{order.id.split('-')[0]}
                  <span className={`px-2 py-0.5 rounded-full text-xs capitalize ${
                    ['delivered'].includes(order.status) ? 'bg-green-100 text-green-800' :
                    ['cancelled'].includes(order.status) ? 'bg-red-100 text-red-800' :
                    'bg-blue-100 text-blue-800'
                  }`}>
                    {order.status.replace(/_/g, ' ')}
                  </span>
                </div>
              </div>
              <div className="text-left sm:text-right">
                <p className="text-sm text-gray-500 mb-1">Total</p>
                <p className="font-bold text-gray-900">₹{Number(order.total_amount).toFixed(2)}</p>
              </div>
            </div>
            
            <div className="flex justify-between items-center border-t pt-4">
              <p className="text-sm text-gray-600 truncate max-w-[70%]">
                {order.items.map(item => `${item.quantity}x ${item.product_name}`).join(', ')}
              </p>
              <Button variant="ghost" size="sm" className="shrink-0 -mr-2">
                View Details <ChevronRight className="ml-1 h-4 w-4" />
              </Button>
            </div>
          </div>
        ))}
      </div>
      
      {/* Pagination controls if total pages > 1 */}
      {data && data.total > data.size && (
        <div className="flex justify-between items-center pt-4">
          <Button 
            variant="outline" 
            disabled={page === 1}
            onClick={() => setPage(p => Math.max(1, p - 1))}
          >
            Previous
          </Button>
          <span className="text-sm text-gray-500">
            Page {page} of {Math.ceil(data.total / data.size)}
          </span>
          <Button 
            variant="outline" 
            disabled={page >= Math.ceil(data.total / data.size)}
            onClick={() => setPage(p => p + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  )
}
