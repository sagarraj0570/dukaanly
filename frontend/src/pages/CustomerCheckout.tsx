import { useCart } from '@/hooks/useCart'
import { useShop } from '@/hooks/useShops'
import { useCheckout } from '@/hooks/useOrders'
import { Button } from '@/components/ui/button'
import { BillCard } from '@/components/ui/BillCard'
import { ErrorState } from '@/components/ErrorState'
import { formatCurrency } from '@/lib/utils'
import {
  ArrowLeft,
  ArrowRight,
  ShieldCheck,
  ShoppingBag,
  Store,
  MapPin,
  Banknote,
  QrCode,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useState, useRef, useEffect } from 'react'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useLocationStore } from '@/store/useLocationStore'
import type { AxiosError } from 'axios'

export const CustomerCheckout = () => {
  useDocumentTitle('Checkout')
  const navigate = useNavigate()
  const { coords, addressLabel } = useLocationStore()

  const { data: cart, isLoading, isError, error, refetch } = useCart()
  const { data: shop } = useShop(cart?.shop_id || '')
  const { mutate: checkout, isPending: isCheckingOut } = useCheckout()

  const [deliveryNotes, setDeliveryNotes] = useState('')
  const [paymentMethod, setPaymentMethod] = useState<'upi' | 'cod'>('upi')
  const [checkoutError, setCheckoutError] = useState<string | null>(null)
  const [conflictItem, setConflictItem] = useState<string | null>(null)

  const idempotencyKey = useRef<string>('')
  useEffect(() => {
    if (!idempotencyKey.current) {
      idempotencyKey.current = crypto.randomUUID()
    }
  }, [])

  if (isLoading) {
    return (
      <div className="max-w-6xl mx-auto animate-pulse space-y-6">
        <div className="h-8 bg-sand rounded w-1/4" />
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          <div className="lg:col-span-7 h-80 bg-surface border border-border rounded-[14px]" />
          <div className="lg:col-span-5 h-72 bg-surface border border-border rounded-[14px]" />
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
      <div className="max-w-3xl mx-auto text-center py-16 bg-surface border border-border rounded-[14px] px-6">
        <div className="h-16 w-16 rounded-[12px] bg-sand flex items-center justify-center mx-auto mb-4 text-leaf">
          <ShoppingBag className="h-8 w-8" aria-hidden="true" />
        </div>
        <h1 className="font-display text-xl font-semibold text-ink mb-2">Cart is empty</h1>
        <p className="text-sm text-ink-soft mb-6">
          You cannot checkout an empty cart.
        </p>
        <Button
          onClick={() => navigate('/customer')}
          variant="default"
          className="rounded-[12px] px-6"
        >
          Browse Shops
        </Button>
      </div>
    )
  }

  const handleCheckout = () => {
    setCheckoutError(null)
    setConflictItem(null)
    checkout(
      {
        idempotency_key: idempotencyKey.current,
        destination_latitude: coords?.latitude,
        destination_longitude: coords?.longitude,
      },
      {
        onSuccess: (order) =>
          navigate(`/customer/payment/${order.id}`, { replace: true }),
        onError: (err: AxiosError<any>) => {
          if (err.response?.status === 409) {
            const detail = err.response.data?.detail
            const itemName = typeof detail === 'string' && detail.includes(':')
              ? detail.split(':')[1]?.trim()
              : detail || 'an item in your cart'
            setConflictItem(itemName)
            setCheckoutError(
              `Stock conflict: ${itemName} has insufficient inventory due to concurrent orders. Please adjust your cart quantity.`
            )
          } else {
            setCheckoutError(
              err.response?.data?.detail || 'Checkout could not be processed. Please try again.'
            )
          }
        },
      }
    )
  }

  const billRows = [
    ...cart.items.map((item) => ({
      label: item.product_name,
      value: formatCurrency(item.item_total),
      sub: `Qty ${item.quantity} × ${formatCurrency(item.product_price)}`,
    })),
    { label: 'Delivery fee', value: '₹0.00', sub: 'Hyperlocal express' },
    { label: 'Platform fee', value: '₹5.00' },
    { label: 'Taxes & local charges', value: '₹0.00', sub: 'Included in price' },
  ]

  const grandTotal = cart.total_amount + 5

  return (
    <div className="max-w-6xl mx-auto space-y-6 pb-24 lg:pb-12 animate-in fade-in-50 duration-200">
      <Button
        variant="ghost"
        onClick={() => navigate('/customer/cart')}
        className="gap-2 text-ink-soft hover:text-ink -ml-2"
      >
        <ArrowLeft className="h-4 w-4" /> Back to Cart
      </Button>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column: Order Steps (Address, Delivery Notes, Payment Method) */}
        <div className="lg:col-span-7 space-y-5">
          <div>
            <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink tracking-tight">
              Review your order
            </h1>
            <p className="text-xs sm:text-sm text-ink-soft mt-1">
              Review delivery destination, special notes, and select payment method.
            </p>
          </div>

          {/* Step 1: Delivery Address */}
          <section className="bg-surface border border-border rounded-[14px] p-5 space-y-3.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="h-6 w-6 rounded-full bg-sand text-ink text-xs font-bold flex items-center justify-center">
                  1
                </span>
                <h2 className="font-display text-base sm:text-lg font-semibold text-ink">
                  Delivery Destination
                </h2>
              </div>
              <span className="text-[11px] font-semibold text-leaf bg-sage-tint border border-leaf/20 px-2 py-0.5 rounded-[6px]">
                Express Delivery
              </span>
            </div>

            <div className="flex items-start gap-3 p-3.5 rounded-[12px] bg-sand/60 border border-border">
              <MapPin className="h-5 w-5 text-leaf mt-0.5 shrink-0" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="font-semibold text-sm text-ink truncate">
                  {addressLabel || 'Central Patna Area'}
                </p>
                <p className="text-xs text-ink-soft mt-0.5 leading-relaxed">
                  Doorstep delivery within partner merchant radius. A rider will be assigned upon merchant order acceptance.
                </p>
              </div>
            </div>

            {shop && (
              <div className="flex items-center gap-2 text-xs text-ink-soft pt-1">
                <Store className="h-3.5 w-3.5 text-leaf shrink-0" />
                <span>Dispatching from: </span>
                <strong className="text-ink font-semibold">{shop.name}</strong>
              </div>
            )}
          </section>

          {/* Step 2: Delivery Notes */}
          <section className="bg-surface border border-border rounded-[14px] p-5 space-y-3.5">
            <div className="flex items-center gap-2">
              <span className="h-6 w-6 rounded-full bg-sand text-ink text-xs font-bold flex items-center justify-center">
                2
              </span>
              <h2 className="font-display text-base sm:text-lg font-semibold text-ink">
                Delivery Instructions
              </h2>
            </div>

            <div className="space-y-1.5">
              <label htmlFor="delivery-notes" className="text-xs font-medium text-ink-soft block">
                Notes for delivery partner (optional)
              </label>
              <div className="relative">
                <textarea
                  id="delivery-notes"
                  value={deliveryNotes}
                  onChange={(e) => setDeliveryNotes(e.target.value)}
                  placeholder="e.g. Ring bell twice, leave with society guard, near landmark..."
                  rows={3}
                  className="w-full p-3 border border-border-strong rounded-[12px] text-sm bg-surface text-ink placeholder:text-ink-soft focus:outline-none focus:border-leaf focus:ring-2 focus:ring-leaf/30 transition-colors"
                />
              </div>
            </div>
          </section>

          {/* Step 3: Payment Method Radio Cards */}
          <section className="bg-surface border border-border rounded-[14px] p-5 space-y-3.5">
            <div className="flex items-center gap-2">
              <span className="h-6 w-6 rounded-full bg-sand text-ink text-xs font-bold flex items-center justify-center">
                3
              </span>
              <h2 className="font-display text-base sm:text-lg font-semibold text-ink">
                Payment Method
              </h2>
            </div>

            <div
              role="radiogroup"
              aria-label="Choose payment method"
              className="grid grid-cols-1 sm:grid-cols-2 gap-3"
            >
              {/* UPI Option */}
              <button
                type="button"
                role="radio"
                aria-checked={paymentMethod === 'upi'}
                onClick={() => setPaymentMethod('upi')}
                className={`flex items-start gap-3 p-4 rounded-[12px] border text-left transition-colors cursor-pointer ${
                  paymentMethod === 'upi'
                    ? 'bg-sage-tint border-leaf text-ink ring-1 ring-leaf'
                    : 'bg-surface hover:bg-sand border-border text-ink'
                }`}
              >
                <div className="h-9 w-9 rounded-[8px] bg-surface border border-border flex items-center justify-center shrink-0 text-leaf">
                  <QrCode className="h-5 w-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <p className="font-semibold text-sm text-ink">UPI Payment</p>
                    {paymentMethod === 'upi' && <CheckCircle2 className="h-4 w-4 text-leaf" />}
                  </div>
                  <p className="text-xs text-ink-soft mt-0.5 leading-snug">
                    Google Pay, PhonePe, Paytm, or BHIM QR code
                  </p>
                </div>
              </button>

              {/* Cash on Delivery Option */}
              <button
                type="button"
                role="radio"
                aria-checked={paymentMethod === 'cod'}
                onClick={() => setPaymentMethod('cod')}
                className={`flex items-start gap-3 p-4 rounded-[12px] border text-left transition-colors cursor-pointer ${
                  paymentMethod === 'cod'
                    ? 'bg-sage-tint border-leaf text-ink ring-1 ring-leaf'
                    : 'bg-surface hover:bg-sand border-border text-ink'
                }`}
              >
                <div className="h-9 w-9 rounded-[8px] bg-surface border border-border flex items-center justify-center shrink-0 text-leaf">
                  <Banknote className="h-5 w-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <p className="font-semibold text-sm text-ink">Cash on Delivery</p>
                    {paymentMethod === 'cod' && <CheckCircle2 className="h-4 w-4 text-leaf" />}
                  </div>
                  <p className="text-xs text-ink-soft mt-0.5 leading-snug">
                    Pay with cash or UPI directly to the delivery rider
                  </p>
                </div>
              </button>
            </div>
          </section>
        </div>

        {/* Right Column: Sticky BillCard Summary & Place Order Action */}
        <div className="lg:col-span-5 sticky top-20 self-start space-y-4">
          <BillCard
            title={shop?.name ? `${shop.name} Parchi` : 'Order Bill'}
            note="Verified Neighbourhood Merchant Invoice"
            rows={billRows}
            footer={{
              label: 'Total Payable',
              value: formatCurrency(grandTotal),
            }}
          />

          {/* Inline Error Notice including 409 stock-conflict */}
          {checkoutError && (
            <div
              role="alert"
              aria-live="assertive"
              className="p-4 bg-brick-tint border border-brick/30 text-brick-ink rounded-[12px] text-xs sm:text-sm space-y-1"
            >
              <div className="flex items-center gap-2 font-bold text-brick">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{conflictItem ? 'Inventory Concurrency Alert' : 'Order Notice'}</span>
              </div>
              <p className="leading-relaxed">{checkoutError}</p>
            </div>
          )}

          {/* Place Order Button (Full width at bottom of card) */}
          <Button
            size="lg"
            className="w-full h-12 rounded-[12px] font-semibold text-sm gap-2"
            onClick={handleCheckout}
            disabled={isCheckingOut}
            aria-busy={isCheckingOut}
          >
            {isCheckingOut ? 'Processing...' : 'Confirm Order'}
            {!isCheckingOut && <ArrowRight className="h-4 w-4" aria-hidden="true" />}
          </Button>

          <div className="flex items-center justify-center gap-1.5 text-xs text-ink-soft text-center">
            <ShieldCheck className="h-4 w-4 text-leaf shrink-0" />
            <span>Optimistic Concurrency Protection • Safe Hyperlocal Dispatch</span>
          </div>
        </div>
      </div>

      {/* Mobile Sticky Bottom Bar */}
      <div className="fixed bottom-0 inset-x-0 bg-surface border-t border-border p-3.5 flex items-center justify-between z-30 lg:hidden shadow-[0_-4px_16px_rgba(30,42,36,0.08)]">
        <div className="flex flex-col">
          <span className="text-xs text-ink-soft">
            Total Payable
          </span>
          <span className="num font-bold text-lg text-ink">
            {formatCurrency(grandTotal)}
          </span>
        </div>
        <Button
          onClick={handleCheckout}
          disabled={isCheckingOut}
          size="sm"
          className="h-10 px-5 font-semibold text-xs rounded-[10px]"
        >
          {isCheckingOut ? 'Processing order…' : 'Place Order'}
        </Button>
      </div>
    </div>
  )
}

export default CustomerCheckout
