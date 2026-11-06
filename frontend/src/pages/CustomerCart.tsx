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
import { BillCard } from '@/components/ui/BillCard'
import { formatCurrency } from '@/lib/utils'
import {
  getProductImage,
  getShopCoverImage,
  extractProductUnit,
} from '@/lib/commerceMedia'
import { ProductImage } from '@/components/ProductImage'
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
} from 'lucide-react'
import { useNavigate, Link } from 'react-router-dom'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useState } from 'react'

export const CustomerCart = () => {
  useDocumentTitle('Your Cart')
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
        <div className="h-8 bg-primary-50 rounded w-36" />
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-8 space-y-4">
            <div className="h-20 bg-surface border border-border rounded-2xl" />
            <div className="h-64 bg-surface border border-border rounded-2xl" />
          </div>
          <div className="lg:col-span-4 h-72 bg-surface border border-border rounded-2xl" />
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
          illustrationType="cart"
          icon={<ShoppingCart className="h-7 w-7" />}
          action={
            <Button
              onClick={() => navigate('/customer')}
              className="btn-primary gap-2 text-white rounded-xl px-6"
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
          className="h-9 w-9 rounded-xl border border-border bg-surface flex items-center justify-center text-text-primary hover:bg-primary-50 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <h1 className="text-2xl font-bold text-text-primary">Your Cart</h1>
      </div>

      {actionError && (
        <div className="p-4 bg-semantic-error/10 text-semantic-error border border-semantic-error/30 rounded-2xl text-sm">
          <p className="font-semibold mb-0.5">Action failed</p>
          <p>{actionError}</p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Shop Banner + Item Rows */}
        <div className="lg:col-span-8 space-y-4">
          <div className="bg-surface border border-border rounded-2xl overflow-hidden shadow-warm-xs">
            {/* Shop Identity Banner */}
            {shop && (
              <div className="px-5 py-4 bg-surface-alt border-b border-border flex items-center justify-between gap-4">
                <Link
                  to={`/customer/shops/${shop.id}`}
                  className="flex items-center gap-3.5 min-w-0 group"
                >
                  <div className="relative h-12 w-12 rounded-xl overflow-hidden bg-primary-50 border border-border shrink-0 flex items-center justify-center">
                    <Store className="h-5 w-5 text-primary-600/40" aria-hidden="true" />
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
                    <h2 className="font-bold text-sm sm:text-base text-text-primary group-hover:text-primary-700 transition-colors truncate">
                      {shop.name}
                    </h2>
                    <p className="text-xs text-text-secondary truncate mt-0.5">
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
            <div className="divide-y divide-border">
              {cart.items.map((item) => {
                const thumbUrl = getProductImage(item.product_name)
                const unitLabel = extractProductUnit(item.product_name)

                return (
                  <div
                    key={item.id}
                    className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:bg-surface-alt/50 transition-colors"
                  >
                    {/* Thumbnail + Product Info */}
                    <div className="flex items-center gap-3.5 flex-1 min-w-0">
                      <Link
                        to={`/customer/products/${item.product_id}`}
                        className="relative h-16 w-16 rounded-xl bg-surface-alt border border-border overflow-hidden shrink-0 flex items-center justify-center"
                      >
                        <ProductImage
                          src={thumbUrl}
                          alt={item.product_name}
                          className="w-full h-full"
                          imageClassName="object-cover"
                        />
                      </Link>

                      <div className="min-w-0 flex-1">
                        <Link
                          to={`/customer/products/${item.product_id}`}
                          className="font-semibold text-sm sm:text-base text-text-primary hover:text-primary-700 transition-colors line-clamp-1 block"
                        >
                          {item.product_name}
                        </Link>
                        {unitLabel && (
                          <p className="text-xs text-text-secondary mt-0.5">{unitLabel}</p>
                        )}
                        <p className="text-xs font-medium text-text-secondary mt-0.5">
                          {formatCurrency(item.product_price)}
                        </p>
                      </div>
                    </div>

                    {/* Quantity Stepper, Line Total & Remove */}
                    <div className="flex items-center justify-between sm:justify-end gap-4 sm:gap-5">
                      <div className="flex items-center border border-border rounded-xl h-9 bg-surface-alt overflow-hidden">
                        <button
                          type="button"
                          onClick={() =>
                            handleUpdateQuantity(item.id, item.quantity - 1)
                          }
                          disabled={item.quantity <= 1 || isUpdating || isRemoving}
                          className="w-8 h-full flex items-center justify-center text-text-primary hover:bg-primary-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                          aria-label={`Decrease quantity of ${item.product_name}`}
                        >
                          <Minus className="h-3.5 w-3.5" aria-hidden="true" />
                        </button>
                        <span className="w-9 text-center text-xs sm:text-sm font-bold text-text-primary border-x border-border h-full flex items-center justify-center bg-surface">
                          {item.quantity}
                        </span>
                        <button
                          type="button"
                          onClick={() =>
                            handleUpdateQuantity(item.id, item.quantity + 1)
                          }
                          disabled={isUpdating || isRemoving}
                          className="w-8 h-full flex items-center justify-center text-text-primary hover:bg-primary-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                          aria-label={`Increase quantity of ${item.product_name}`}
                        >
                          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                        </button>
                      </div>

                      <span className="font-bold text-sm sm:text-base text-text-primary min-w-[76px] text-right">
                        {formatCurrency(item.item_total)}
                      </span>

                      <button
                        type="button"
                        onClick={() => handleRemove(item.id)}
                        disabled={isRemoving || isUpdating}
                        className="p-2 text-text-muted hover:text-semantic-error hover:bg-semantic-error/10 rounded-lg transition-colors disabled:opacity-40"
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
            <div className="px-5 py-3.5 bg-surface-alt border-t border-border flex flex-wrap items-center justify-between gap-3">
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
                className="rounded-xl border-primary-200 text-primary-700 hover:bg-primary-50 font-semibold text-xs"
              >
                Continue Shopping
              </Button>

              {!confirmClear ? (
                <button
                  type="button"
                  onClick={() => setConfirmClear(true)}
                  disabled={isClearing}
                  className="text-xs font-semibold text-text-secondary hover:text-semantic-error transition-colors"
                >
                  Clear cart
                </button>
              ) : (
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-text-primary">
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
          <BillCard
            title="Aapka Cart"
            note={`${totalUnits} ${totalUnits === 1 ? 'item' : 'items'} in cart`}
            rows={[
              { label: 'Items Subtotal', value: formatCurrency(cart.total_amount) },
              { label: 'Delivery Fee', value: '₹0.00', sub: 'Hyperlocal express' },
              { label: 'Taxes & charges', value: '₹0.00', sub: 'Included in prices' },
            ]}
            footer={{
              label: 'Total Payable',
              value: formatCurrency(cart.total_amount),
            }}
          />

          <Button
            size="lg"
            className="w-full h-12 rounded-[12px] font-semibold text-sm gap-2"
            onClick={() => navigate('/customer/checkout')}
          >
            <span>Proceed to Checkout</span>
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Button>

          {/* Trust & Community Highlights */}
          <div className="bg-surface border border-border rounded-2xl p-5 shadow-warm-xs space-y-4">
            <div className="flex items-start gap-3">
              <div className="h-8 w-8 rounded-lg bg-primary-50 flex items-center justify-center shrink-0">
                <ShieldCheck className="h-4 w-4 text-primary-600" />
              </div>
              <div>
                <p className="text-xs font-bold text-text-primary">Secure Checkout</p>
                <p className="text-[11px] text-text-secondary">
                  Your order details and sandbox payment are protected
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <div className="h-8 w-8 rounded-lg bg-primary-50 flex items-center justify-center shrink-0">
                <Store className="h-4 w-4 text-primary-600" />
              </div>
              <div>
                <p className="text-xs font-bold text-text-primary">Local Shops</p>
                <p className="text-[11px] text-text-secondary">
                  Support neighbourhood businesses directly
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <div className="h-8 w-8 rounded-lg bg-primary-50 flex items-center justify-center shrink-0">
                <Truck className="h-4 w-4 text-primary-600" />
              </div>
              <div>
                <p className="text-xs font-bold text-text-primary">Fast Delivery</p>
                <p className="text-[11px] text-text-secondary">
                  Real-time order and rider tracking to your doorstep
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Mobile Sticky Bottom Bar for instant Proceed to Checkout (56px tall with safe-area padding) */}
      <div className="fixed bottom-0 inset-x-0 bg-surface/98 backdrop-blur-md border-t border-border px-4 py-3 pb-safe flex items-center justify-between z-40 lg:hidden shadow-[0_-4px_16px_rgba(30,42,36,0.1)] min-h-[56px]">
        <div className="flex flex-col">
          <span className="text-xs text-ink-soft">
            <span className="num font-semibold text-ink">{totalUnits}</span> {totalUnits === 1 ? 'item' : 'items'}
          </span>
          <span className="num font-bold text-base text-ink">
            {formatCurrency(cart.total_amount)}
          </span>
        </div>
        <Button
          size="sm"
          className="h-11 min-h-[44px] px-5 rounded-[12px] font-semibold text-xs gap-1.5 cursor-pointer"
          onClick={() => navigate('/customer/checkout')}
        >
          <span>Proceed to Checkout</span>
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
  )
}
