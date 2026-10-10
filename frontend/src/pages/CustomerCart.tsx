import { useCart, useUpdateCartItem, useRemoveCartItem, useClearCart } from '@/hooks/useCart'
import { ErrorState } from '@/components/ErrorState'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import { formatCurrency } from '@/lib/utils'
import { ShoppingCart, Trash2, Plus, Minus, ArrowRight } from 'lucide-react'
import { useNavigate, Link } from 'react-router-dom'
import { useState } from 'react'

export const CustomerCart = () => {
  const navigate = useNavigate()
  const { data: cart, isLoading, isError, error, refetch } = useCart()
  const { mutate: updateQuantity, isPending: isUpdating } = useUpdateCartItem()
  const { mutate: removeItem, isPending: isRemoving } = useRemoveCartItem()
  const { mutate: clearCart, isPending: isClearing } = useClearCart()
  
  const [confirmClear, setConfirmClear] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse max-w-4xl mx-auto">
        <div className="h-8 bg-gray-100 rounded w-1/4 mb-6" />
        <div className="space-y-4">
          {[1, 2].map(i => (
            <div key={i} className="h-24 bg-gray-100 rounded-lg" />
          ))}
        </div>
        <div className="h-32 bg-gray-100 rounded-lg mt-8" />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="max-w-4xl mx-auto">
        <ErrorState 
          title="Failed to load cart"
          message={error?.message || "There was a problem loading your cart."}
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  if (!cart || cart.items.length === 0) {
    return (
      <div className="max-w-4xl mx-auto">
        <EmptyState 
          title="Your cart is empty"
          message="Looks like you haven't added anything to your cart yet."
          icon={<ShoppingCart className="h-10 w-10" />}
          action={
            <Button onClick={() => navigate('/customer')} className="mt-4">
              Browse Shops
            </Button>
          }
        />
      </div>
    )
  }

  const handleUpdateQuantity = (itemId: string, newQuantity: number) => {
    setActionError(null)
    if (newQuantity < 1) return
    updateQuantity({ item_id: itemId, quantity: newQuantity }, {
      onError: (err: any) => setActionError(err.response?.data?.detail || err.message)
    })
  }

  const handleRemove = (itemId: string) => {
    setActionError(null)
    removeItem(itemId, {
      onError: (err: any) => setActionError(err.response?.data?.detail || err.message)
    })
  }

  const handleClearCart = () => {
    setActionError(null)
    clearCart(undefined, {
      onSuccess: () => setConfirmClear(false),
      onError: (err: any) => setActionError(err.response?.data?.detail || err.message)
    })
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <h1 className="text-2xl font-bold text-gray-900">Your Cart</h1>
      
      {actionError && (
        <div className="p-4 bg-red-50 text-red-700 border border-red-200 rounded-md">
          <p className="font-semibold mb-1">Action failed</p>
          <p className="text-sm">{actionError}</p>
        </div>
      )}

      <div className="bg-white border rounded-lg shadow-sm overflow-hidden">
        <div className="divide-y">
          {cart.items.map((item) => (
            <div key={item.id} className="p-4 sm:p-6 flex flex-col sm:flex-row sm:items-center gap-4">
              <div className="flex-1">
                <Link to={`/customer/products/${item.product_id}`} className="font-bold text-gray-900 hover:text-primary transition-colors text-lg">
                  {item.product_name}
                </Link>
                <div className="text-gray-500 mt-1">{formatCurrency(item.product_price)} each</div>
              </div>
              
              <div className="flex items-center justify-between sm:justify-end gap-6 w-full sm:w-auto mt-2 sm:mt-0">
                {/* Quantity Controls */}
                <div className="flex items-center border rounded-md h-10 w-32">
                  <button 
                    onClick={() => handleUpdateQuantity(item.id, item.quantity - 1)}
                    disabled={item.quantity <= 1 || isUpdating || isRemoving}
                    className="flex-1 flex items-center justify-center text-gray-500 hover:text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:hover:bg-transparent h-full transition-colors"
                    aria-label="Decrease quantity"
                  >
                    <Minus className="h-4 w-4" />
                  </button>
                  <div className="flex-1 flex items-center justify-center font-medium border-x h-full">
                    {item.quantity}
                  </div>
                  <button 
                    onClick={() => handleUpdateQuantity(item.id, item.quantity + 1)}
                    disabled={isUpdating || isRemoving}
                    className="flex-1 flex items-center justify-center text-gray-500 hover:text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:hover:bg-transparent h-full transition-colors"
                    aria-label="Increase quantity"
                  >
                    <Plus className="h-4 w-4" />
                  </button>
                </div>

                <div className="font-bold text-lg min-w-[100px] text-right">
                  {formatCurrency(item.item_total)}
                </div>

                <button 
                  onClick={() => handleRemove(item.id)}
                  disabled={isRemoving || isUpdating}
                  className="text-red-500 hover:text-red-700 p-2 rounded-md hover:bg-red-50 disabled:opacity-50 transition-colors"
                  aria-label="Remove item"
                >
                  <Trash2 className="h-5 w-5" />
                </button>
              </div>
            </div>
          ))}
        </div>
        
        <div className="bg-gray-50 p-6 border-t flex flex-col sm:flex-row justify-between items-center gap-4">
          <div className="flex items-center gap-4 w-full sm:w-auto">
            {!confirmClear ? (
              <Button 
                variant="outline" 
                className="text-red-600 border-red-200 hover:bg-red-50 hover:text-red-700 w-full sm:w-auto"
                onClick={() => setConfirmClear(true)}
                disabled={isClearing}
              >
                Clear Cart
              </Button>
            ) : (
              <div className="flex items-center gap-2 w-full sm:w-auto">
                <span className="text-sm font-medium text-gray-700">Are you sure?</span>
                <Button 
                  variant="destructive" 
                  size="sm"
                  onClick={handleClearCart}
                  disabled={isClearing}
                >
                  Yes, Clear
                </Button>
                <Button 
                  variant="ghost" 
                  size="sm"
                  onClick={() => setConfirmClear(false)}
                  disabled={isClearing}
                >
                  Cancel
                </Button>
              </div>
            )}
          </div>
          
          <div className="flex items-center justify-between sm:justify-end gap-6 w-full sm:w-auto">
            <div className="text-gray-500 font-medium">Subtotal</div>
            <div className="text-2xl font-extrabold text-gray-900">
              {formatCurrency(cart.total_amount)}
            </div>
          </div>
        </div>
      </div>
      
      <div className="flex justify-end">
        {/* Checkout placeholder */}
        <Button size="lg" className="w-full sm:w-auto" disabled>
          Proceed to Checkout <ArrowRight className="ml-2 h-5 w-5" />
        </Button>
      </div>
      
      <div className="text-center text-sm text-gray-500">
        Checkout functionality is pending Sub-task 18.
      </div>
    </div>
  )
}
