import { useCart } from '@/hooks/useCart'
import { useShop } from '@/hooks/useShops'
import { useCheckout } from '@/hooks/useOrders'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ErrorState'
import { formatCurrency } from '@/lib/utils'
import { getProductImage, getShopCoverImage } from '@/lib/commerceMedia'
import {
  ArrowLeft,
  ArrowRight,
  ShieldCheck,
  ShoppingBag,
  Store,
  MapPin,
  CreditCard,
  Package,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useState, useRef, useEffect } from 'react'
import type { AxiosError } from 'axios'

export const CustomerCheckout = () => {
  const navigate = useNavigate()

  const { data: cart, isLoading, isError, error, refetch } = useCart()
  const { data: shop } = useShop(cart?.shop_id || '')
  const { mutate: checkout, isPending: isCheckingOut } = useCheckout()

  const [checkoutError, setCheckoutError] = useState<string | null>(null)

  const idempotencyKey = useRef<string>('')
  useEffect(() => {
    if (!idempotencyKey.current) {
      idempotencyKey.current = crypto.randomUUID()
    }
  }, [])

  if (isLoading) {
    return (
      <div className="max-w-5xl mx-auto animate-pulse space-y-6">
        <div className="h-8 bg-[#EDF5EE] rounded w-1/4" />
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-8 h-72 bg-white border border-[#E5E9E4] rounded-2xl" />
          <div className="lg:col-span-4 h-64 bg-white border border-[#E5E9E4] rounded-2xl" />
        </div>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="max-w-4xl mx-auto">
        <ErrorState
          title="Could not load cart"
          message={error?.message || 'Please try again.'}
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  if (!cart || cart.items.length === 0) {
    return (
      <div className="max-w-3xl mx-auto text-center py-16 bg-white border border-[#E5E9E4] rounded-3xl shadow-soft px-6">
        <div className="h-16 w-16 rounded-2xl bg-[#EDF5EE] flex items-center justify-center mx-auto mb-4 text-[#176B45]">
          <ShoppingBag className="h-8 w-8" aria-hidden="true" />
        </div>
        <h1 className="text-xl font-bold text-[#202923] mb-2">Cart is empty</h1>
        <p className="text-sm text-[#69736C] mb-6">
          You cannot checkout an empty cart.
        </p>
        <Button
          onClick={() => navigate('/customer')}
          className="bg-[#176B45] hover:bg-[#104B32] text-white rounded-xl px-6"
        >
          Browse Shops
        </Button>
      </div>
    )
  }

  const handleCheckout = () => {
    setCheckoutError(null)
    checkout(
      { idempotency_key: idempotencyKey.current },
      {
        onSuccess: (order) =>
          navigate(`/customer/payment/${order.id}`, { replace: true }),
        onError: (err: AxiosError<any>) => {
          setCheckoutError(
            err.response?.data?.detail || 'Checkout failed. Please try again.'
          )
        },
      }
    )
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <Button
        variant="ghost"
        onClick={() => navigate('/customer/cart')}
        className="gap-2 text-[#69736C] hover:text-[#202923] -ml-2"
      >
        <ArrowLeft className="h-4 w-4" /> Back to Cart
      </Button>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Order Review & Fulfillment */}
        <div className="lg:col-span-8 space-y-4">
          <div className="bg-white border border-[#E5E9E4] rounded-2xl overflow-hidden shadow-soft">
            <div className="px-4 sm:px-6 py-4 sm:py-5 border-b border-[#E5E9E4] bg-[#FAF9F6] flex items-center justify-between gap-4">
              <div>
                <h1 className="text-xl font-bold text-[#202923]">
                  Review your order
                </h1>
                {shop && (
                  <div className="flex min-w-0 items-center gap-2 mt-1 text-xs sm:text-sm text-[#69736C]">
                    <Store className="h-3.5 w-3.5 text-[#176B45]" aria-hidden="true" />
                    <span className="shrink-0">Ordering from</span>
                    <span className="truncate font-semibold text-[#202923]">
                      {shop.name}
                    </span>
                  </div>
                )}
              </div>

              {shop && (
                <div className="relative h-11 w-11 rounded-xl overflow-hidden border border-[#E5E9E4] bg-[#EDF5EE] shrink-0 hidden sm:flex items-center justify-center">
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
              )}
            </div>

            {shop?.address && (
              <div className="px-4 sm:px-6 py-3 bg-white border-b border-[#E5E9E4] flex min-w-0 items-center gap-2 text-xs text-[#69736C]">
                <MapPin className="h-3.5 w-3.5 text-[#176B45] shrink-0" aria-hidden="true" />
                <span className="truncate">Store location: {shop.address}</span>
              </div>
            )}

            <div className="divide-y divide-[#E5E9E4]">
              {cart.items.map((item) => (
                <div
                  key={item.id}
                  className="px-4 sm:px-6 py-3.5 sm:py-4 flex items-center justify-between gap-4"
                >
                  <div className="flex items-center gap-3.5 flex-1 min-w-0">
                    <div className="relative h-12 w-12 rounded-xl overflow-hidden bg-[#FAF9F6] border border-[#E5E9E4] shrink-0 flex items-center justify-center">
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
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold text-sm sm:text-base text-[#202923] line-clamp-1">
                        {item.product_name}
                      </p>
                      <p className="text-xs text-[#69736C] mt-0.5">
                        Qty {item.quantity} × {formatCurrency(item.product_price)}
                      </p>
                    </div>
                  </div>
                  <span className="font-bold text-sm sm:text-base text-[#202923] shrink-0">
                    {formatCurrency(item.item_total)}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Payment Method Info Banner */}
          <div className="bg-white border border-[#E5E9E4] rounded-2xl p-5 shadow-soft flex items-start gap-3.5">
            <div className="h-10 w-10 rounded-xl bg-[#EDF5EE] flex items-center justify-center shrink-0 text-[#176B45]">
              <CreditCard className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-[#202923]">
                Sandbox Payment Gateway
              </h2>
              <p className="text-xs text-[#69736C] mt-0.5 leading-relaxed">
                After confirming your order, you will be directed to the simulated payment step where you can test payment capture or failure.
              </p>
            </div>
          </div>
        </div>

        {/* Right Column: Summary & Confirm CTA */}
        <div className="lg:col-span-4 bg-white border border-[#E5E9E4] rounded-2xl overflow-hidden shadow-soft">
          <div className="px-5 py-4 border-b border-[#E5E9E4] bg-[#FAF9F6]">
            <h2 className="font-bold text-base text-[#202923]">Order Summary</h2>
          </div>
          <div className="p-5 space-y-4">
            <div className="space-y-2.5 text-sm">
              <div className="flex justify-between items-center text-[#69736C]">
                <span>Subtotal</span>
                <span className="font-semibold text-[#202923]">
                  {formatCurrency(cart.total_amount)}
                </span>
              </div>
              <div className="flex justify-between items-center text-[#69736C]">
                <span>Delivery</span>
                <span className="font-semibold text-[#176B45]">Free</span>
              </div>
            </div>

            <div className="border-t border-[#E5E9E4] pt-3.5 flex justify-between items-baseline">
              <span className="font-bold text-[#202923]">Total</span>
              <span className="text-2xl font-bold text-[#202923]">
                {formatCurrency(cart.total_amount)}
              </span>
            </div>

            {checkoutError && (
              <div role="alert" aria-live="assertive" className="p-3 bg-red-50 text-red-700 text-xs sm:text-sm border border-red-200 rounded-xl">
                <p className="font-semibold mb-0.5">Checkout Error</p>
                <p>{checkoutError}</p>
              </div>
            )}

            <Button
              size="lg"
              className="w-full h-12 rounded-xl bg-[#176B45] hover:bg-[#104B32] text-white font-semibold gap-2 shadow-sm"
              onClick={handleCheckout}
              disabled={isCheckingOut}
              aria-busy={isCheckingOut}
            >
              {isCheckingOut ? 'Processing...' : 'Confirm Order'}
              {!isCheckingOut && <ArrowRight className="h-4 w-4" aria-hidden="true" />}
            </Button>

            <div className="flex items-center justify-center gap-1.5 text-xs text-[#69736C]">
              <ShieldCheck className="h-3.5 w-3.5 text-[#176B45]" />
              <span>Secure Checkout · Sandbox Mode</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
