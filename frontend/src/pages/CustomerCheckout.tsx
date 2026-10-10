import { useCart } from '@/hooks/useCart'
import { useShop } from '@/hooks/useShops'
import { useCheckout } from '@/hooks/useOrders'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ErrorState'
import { formatCurrency } from '@/lib/utils'
import { ArrowLeft, ArrowRight, ShieldCheck, ShoppingBag } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useState, useRef, useEffect } from 'react'
import type { AxiosError } from 'axios'
export const CustomerCheckout = () => {
  const navigate = useNavigate()
  
  // Fetch cart
  const { data: cart, isLoading, isError, error, refetch } = useCart()
  
  // Optionally display shop name
  const { data: shop } = useShop(cart?.shop_id || '')
  
  // Checkout mutation
  const { mutate: checkout, isPending: isCheckingOut } = useCheckout()
  
  const [checkoutError, setCheckoutError] = useState<string | null>(null)
  
  // Persist idempotency key across the checkout page lifecycle to prevent duplicate orders during retries
  const idempotencyKey = useRef<string>('')
  useEffect(() => {
    if (!idempotencyKey.current) {
      idempotencyKey.current = crypto.randomUUID()
    }
  }, [])

  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto p-6 bg-white border rounded-lg shadow-sm animate-pulse space-y-6">
        <div className="h-8 bg-gray-100 rounded w-1/4 mb-4" />
        <div className="h-32 bg-gray-100 rounded mb-4" />
        <div className="h-12 bg-gray-100 rounded" />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="max-w-4xl mx-auto">
        <ErrorState 
          title="Could not load cart for checkout"
          message={error?.message || "Please try again later."}
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  if (!cart || cart.items.length === 0) {
    return (
      <div className="max-w-4xl mx-auto text-center py-16 bg-white border rounded-lg shadow-sm">
        <ShoppingBag className="mx-auto h-16 w-16 text-gray-300 mb-4" />
        <h2 className="text-2xl font-bold text-gray-900 mb-2">Cart is empty</h2>
        <p className="text-gray-500 mb-8">You cannot checkout an empty cart.</p>
        <Button onClick={() => navigate('/customer')}>Browse Shops</Button>
      </div>
    )
  }

  const handleCheckout = () => {
    setCheckoutError(null)
    
    checkout(
      { idempotency_key: idempotencyKey.current },
      {
        onSuccess: (order) => {
          // Navigate to payment page for the new order
          navigate(`/customer/payment/${order.id}`, { replace: true })
        },
        onError: (err: AxiosError<any>) => {
          setCheckoutError(err.response?.data?.detail || "Checkout failed. Please try again.")
        }
      }
    )
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <Button variant="ghost" onClick={() => navigate('/customer/cart')} className="-ml-4 text-gray-500">
        <ArrowLeft className="mr-2 h-4 w-4" /> Back to Cart
      </Button>
      
      <div className="bg-white border rounded-xl overflow-hidden shadow-sm flex flex-col lg:flex-row">
        
        {/* Review Section */}
        <div className="w-full lg:w-2/3 p-6 lg:p-8 border-b lg:border-b-0 lg:border-r">
          <h1 className="text-2xl font-bold text-gray-900 mb-6">Review your order</h1>
          
          <div className="mb-6">
            <span className="text-sm font-medium text-gray-500 uppercase tracking-wider">
              Ordering from
            </span>
            <p className="text-lg font-bold text-gray-900">{shop?.name || 'Loading shop...'}</p>
          </div>
          
          <div className="space-y-4 divide-y">
            {cart.items.map(item => (
              <div key={item.id} className="pt-4 flex justify-between gap-4">
                <div className="flex-1">
                  <h3 className="font-medium text-gray-900 line-clamp-1">{item.product_name}</h3>
                  <p className="text-sm text-gray-500">Qty: {item.quantity} × {formatCurrency(item.product_price)}</p>
                </div>
                <div className="font-semibold text-gray-900 whitespace-nowrap text-right">
                  {formatCurrency(item.item_total)}
                </div>
              </div>
            ))}
          </div>
        </div>
        
        {/* Summary Section */}
        <div className="w-full lg:w-1/3 p-6 lg:p-8 bg-gray-50 flex flex-col">
          <h2 className="text-xl font-bold text-gray-900 mb-6">Summary</h2>
          
          <div className="flex justify-between items-center mb-6 text-lg">
            <span className="font-medium text-gray-700">Order Total</span>
            <span className="font-extrabold text-2xl text-gray-900">{formatCurrency(cart.total_amount)}</span>
          </div>
          
          {checkoutError && (
            <div className="mb-6 p-4 bg-red-50 text-red-700 text-sm border border-red-200 rounded-md">
              <p className="font-semibold mb-1">Checkout Error</p>
              <p>{checkoutError}</p>
            </div>
          )}
          
          <div className="mt-auto pt-6 flex flex-col gap-4">
            <Button 
              size="lg" 
              className="w-full text-base h-12"
              onClick={handleCheckout}
              disabled={isCheckingOut}
            >
              {isCheckingOut ? 'Processing...' : 'Confirm Order'} 
              {!isCheckingOut && <ArrowRight className="ml-2 h-5 w-5" />}
            </Button>
            
            <div className="flex items-center justify-center text-sm text-gray-500 gap-2 mt-2">
              <ShieldCheck className="h-4 w-4" />
              <span>Secure Checkout</span>
            </div>
          </div>
        </div>
        
      </div>
    </div>
  )
}
