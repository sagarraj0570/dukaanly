import {
  useCart,
  useUpdateCartItem,
  useRemoveCartItem,
  useClearCart,
} from '@/hooks/useCart'
import { useShop } from '@/hooks/useShops'
import { ErrorState } from '@/components/ErrorState'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import { formatCurrency } from '@/lib/utils'
import {
  getProductImage,
  getShopCoverImage,
  extractProductUnit,
} from '@/lib/commerceMedia'
import {
  ShoppingCart,
  Trash2,
  Plus,
  Minus,
  ArrowLeft,
  ArrowRight,
  ShieldCheck,
  Store,
  Truck,
  Package,
} from 'lucide-react'
import { useNavigate, Link } from 'react-router-dom'
import { useState } from 'react'

export const CustomerCart = () => {
  const navigate = useNavigate()
  const { data: cart, isLoading, isError, error, refetch } = useCart()
  const { data: shop } = useShop(cart?.shop_id || '')
  const { mutate: updateQuantity, isPending: isUpdating } = useUpdateCartItem()
  const { mutate: removeItem, isPending: isRemoving } = useRemoveCartItem()
  const { mutate: clearCart, isPending: isClearing } = useClearCart()

  const [confirmClear, setConfirmClear] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  if (isLoading) {
    return (
      <div className="max-w-6xl mx-auto space-y-6 animate-pulse">
        <div className="h-8 bg-[#EDF5EE] rounded w-36" />
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-8 space-y-4">
            <div className="h-20 bg-white border border-[#E5E9E4] rounded-2xl" />
            <div className="h-64 bg-white border border-[#E5E9E4] rounded-2xl" />
          </div>
          <div className="lg:col-span-4 h-72 bg-white border border-[#E5E9E4] rounded-2xl" />
        </div>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="max-w-4xl mx-auto">
        <ErrorState
          title="Failed to load cart"
          message={error?.message || 'There was a problem loading your cart.'}
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  if (!cart || cart.items.length === 0) {
    return (
      <div className="max-w-3xl mx-auto py-6">
        <h1 className="sr-only">Your Cart</h1>
        <EmptyState
          title="Your cart is empty"
          message="Looks like you haven't added anything to your cart yet. Browse local neighbourhood shops to get started."
          icon={<ShoppingCart className="h-7 w-7" />}
          action={
            <Button
              onClick={() => navigate('/customer')}
              className="gap-2 bg-[#176B45] hover:bg-[#104B32] text-white rounded-xl px-6"
            >
              <Store className="h-4 w-4" />
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
    updateQuantity(
      { item_id: itemId, quantity: newQuantity },
      {
        onError: (err: any) =>
          setActionError(err.response?.data?.detail || err.message),
      }
    )
  }

  const handleRemove = (itemId: string) => {
    setActionError(null)
    removeItem(itemId, {
      onError: (err: any) =>
        setActionError(err.response?.data?.detail || err.message),
    })
  }

  const handleClearCart = () => {
    setActionError(null)
    clearCart(undefined, {
      onSuccess: () => setConfirmClear(false),
      onError: (err: any) =>
        setActionError(err.response?.data?.detail || err.message),
    })
  }

  const totalUnits = cart.items.reduce((sum, item) => sum + item.quantity, 0)

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header Row */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => navigate(-1)}
          aria-label="Go back"
          className="h-9 w-9 rounded-xl border border-[#E5E9E4] bg-white flex items-center justify-center text-[#202923] hover:bg-[#EDF5EE] transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <h1 className="text-2xl font-bold text-[#202923]">Your Cart</h1>
      </div>

      {actionError && (
        <div className="p-4 bg-red-50 text-red-700 border border-red-200 rounded-2xl text-sm">
          <p className="font-semibold mb-0.5">Action failed</p>
          <p>{actionError}</p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Shop Banner + Item Rows */}
        <div className="lg:col-span-8 space-y-4">
          <div className="bg-white border border-[#E5E9E4] rounded-2xl overflow-hidden shadow-soft">
            {/* Shop Identity Banner */}
            {shop && (
              <div className="px-5 py-4 bg-[#FAF9F6] border-b border-[#E5E9E4] flex items-center justify-between gap-4">
                <Link
                  to={`/customer/shops/${shop.id}`}
                  className="flex items-center gap-3.5 min-w-0 group"
                >
                  <div className="relative h-12 w-12 rounded-xl overflow-hidden bg-[#EDF5EE] border border-[#E5E9E4] shrink-0 flex items-center justify-center">
                    <Store className="h-5 w-5 text-[#176B45]/40" aria-hidden="true" />
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
                    <h2 className="font-bold text-sm sm:text-base text-[#202923] group-hover:text-[#176B45] transition-colors truncate">
                      {shop.name}
                    </h2>
                    <p className="text-xs text-[#69736C] truncate mt-0.5">
                      {shop.address}
                    </p>
                  </div>
                </Link>

                {shop.is_active ? (
                  <span className="badge-success shrink-0">Open</span>
                ) : (
                  <span className="badge-error shrink-0">Closed</span>
                )}
              </div>
            )}

            {/* Cart Item Rows */}
            <div className="divide-y divide-[#E5E9E4]">
              {cart.items.map((item) => {
                const thumbUrl = getProductImage(item.product_name)
                const unitLabel = extractProductUnit(item.product_name)

                return (
                  <div
                    key={item.id}
                    className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:bg-[#FAF9F6]/50 transition-colors"
                  >
                    {/* Thumbnail + Product Info */}
                    <div className="flex items-center gap-3.5 flex-1 min-w-0">
                      <Link
                        to={`/customer/products/${item.product_id}`}
                        className="relative h-16 w-16 rounded-xl bg-[#FAF9F6] border border-[#E5E9E4] overflow-hidden shrink-0 flex items-center justify-center"
                      >
                        <Package className="h-6 w-6 text-[#176B45]/40" aria-hidden="true" />
                        <img
                          src={thumbUrl}
                          alt={item.product_name}
                          className="absolute inset-0 h-full w-full object-cover"
                          onError={(e) => {
                            e.currentTarget.style.display = 'none'
                          }}
                        />
                      </Link>

                      <div className="min-w-0 flex-1">
                        <Link
                          to={`/customer/products/${item.product_id}`}
                          className="font-semibold text-sm sm:text-base text-[#202923] hover:text-[#176B45] transition-colors line-clamp-1 block"
                        >
                          {item.product_name}
                        </Link>
                        {unitLabel && (
                          <p className="text-xs text-[#69736C] mt-0.5">{unitLabel}</p>
                        )}
                        <p className="text-xs font-medium text-[#69736C] mt-0.5">
                          {formatCurrency(item.product_price)}
                        </p>
                      </div>
                    </div>

                    {/* Quantity Stepper, Line Total & Remove */}
                    <div className="flex items-center justify-between sm:justify-end gap-4 sm:gap-5">
                      <div className="flex items-center border border-[#E5E9E4] rounded-xl h-9 bg-[#FAF9F6] overflow-hidden">
                        <button
                          type="button"
                          onClick={() =>
                            handleUpdateQuantity(item.id, item.quantity - 1)
                          }
                          disabled={item.quantity <= 1 || isUpdating || isRemoving}
                          className="w-8 h-full flex items-center justify-center text-[#202923] hover:bg-[#EDF5EE] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                          aria-label={`Decrease quantity of ${item.product_name}`}
                        >
                          <Minus className="h-3.5 w-3.5" aria-hidden="true" />
                        </button>
                        <span className="w-9 text-center text-xs sm:text-sm font-bold text-[#202923] border-x border-[#E5E9E4] h-full flex items-center justify-center bg-white">
                          {item.quantity}
                        </span>
                        <button
                          type="button"
                          onClick={() =>
                            handleUpdateQuantity(item.id, item.quantity + 1)
                          }
                          disabled={isUpdating || isRemoving}
                          className="w-8 h-full flex items-center justify-center text-[#202923] hover:bg-[#EDF5EE] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                          aria-label={`Increase quantity of ${item.product_name}`}
                        >
                          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                        </button>
                      </div>

                      <span className="font-bold text-sm sm:text-base text-[#202923] min-w-[76px] text-right">
                        {formatCurrency(item.item_total)}
                      </span>

                      <button
                        type="button"
                        onClick={() => handleRemove(item.id)}
                        disabled={isRemoving || isUpdating}
                        className="p-2 text-[#69736C] hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-40"
                        aria-label={`Remove ${item.product_name} from cart`}
                      >
                        <Trash2 className="h-4 w-4" aria-hidden="true" />
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Bottom Actions Row */}
            <div className="px-5 py-3.5 bg-[#FAF9F6] border-t border-[#E5E9E4] flex flex-wrap items-center justify-between gap-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  navigate(
                    cart.shop_id
                      ? `/customer/shops/${cart.shop_id}`
                      : '/customer'
                  )
                }
                className="rounded-xl border-[#A8D5B5] text-[#176B45] hover:bg-[#EDF5EE] font-semibold text-xs"
              >
                Continue Shopping
              </Button>

              {!confirmClear ? (
                <button
                  type="button"
                  onClick={() => setConfirmClear(true)}
                  disabled={isClearing}
                  className="text-xs font-semibold text-[#69736C] hover:text-red-600 transition-colors"
                >
                  Clear cart
                </button>
              ) : (
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-[#202923]">
                    Remove all items?
                  </span>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={handleClearCart}
                    disabled={isClearing}
                    className="h-7 text-xs"
                  >
                    Yes, clear
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setConfirmClear(false)}
                    disabled={isClearing}
                    className="h-7 text-xs"
                  >
                    Cancel
                  </Button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right Column: Order Summary + Trust Highlights */}
        <div className="lg:col-span-4 space-y-4">
          <div className="bg-white border border-[#E5E9E4] rounded-2xl p-5 sm:p-6 shadow-soft space-y-4">
            <div>
              <h2 className="text-lg font-bold text-[#202923]">Order Summary</h2>
              <p className="text-xs text-[#69736C] mt-0.5">
                {totalUnits} {totalUnits === 1 ? 'item' : 'items'} in cart
              </p>
            </div>

            <div className="space-y-2.5 text-sm border-t border-[#E5E9E4] pt-4">
              <div className="flex justify-between items-center text-[#69736C]">
                <span>Subtotal</span>
                <span className="font-semibold text-[#202923]">
                  {formatCurrency(cart.total_amount)}
                </span>
              </div>
              <div className="flex justify-between items-center text-[#69736C]">
                <span>Delivery Fee</span>
                <span className="font-semibold text-[#176B45]">Free</span>
              </div>
            </div>

            <div className="border-t border-[#E5E9E4] pt-3.5 flex justify-between items-baseline">
              <span className="font-bold text-base text-[#202923]">Total</span>
              <span className="text-2xl font-bold text-[#202923]">
                {formatCurrency(cart.total_amount)}
              </span>
            </div>

            <Button
              size="lg"
              className="w-full h-12 rounded-xl bg-[#176B45] hover:bg-[#104B32] text-white text-sm sm:text-base font-semibold gap-2 shadow-sm"
              onClick={() => navigate('/customer/checkout')}
            >
              Proceed to Checkout <ArrowRight className="h-4.5 w-4.5" />
            </Button>
          </div>

          {/* Trust & Community Highlights */}
          <div className="bg-white border border-[#E5E9E4] rounded-2xl p-5 shadow-soft space-y-4">
            <div className="flex items-start gap-3">
              <div className="h-8 w-8 rounded-lg bg-[#EDF5EE] flex items-center justify-center shrink-0">
                <ShieldCheck className="h-4 w-4 text-[#176B45]" />
              </div>
              <div>
                <p className="text-xs font-bold text-[#202923]">Secure Checkout</p>
                <p className="text-[11px] text-[#69736C]">
                  Your order details and sandbox payment are protected
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <div className="h-8 w-8 rounded-lg bg-[#EDF5EE] flex items-center justify-center shrink-0">
                <Store className="h-4 w-4 text-[#176B45]" />
              </div>
              <div>
                <p className="text-xs font-bold text-[#202923]">Local Shops</p>
                <p className="text-[11px] text-[#69736C]">
                  Support neighbourhood businesses directly
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <div className="h-8 w-8 rounded-lg bg-[#EDF5EE] flex items-center justify-center shrink-0">
                <Truck className="h-4 w-4 text-[#176B45]" />
              </div>
              <div>
                <p className="text-xs font-bold text-[#202923]">Fast Delivery</p>
                <p className="text-[11px] text-[#69736C]">
                  Real-time order and rider tracking to your doorstep
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
