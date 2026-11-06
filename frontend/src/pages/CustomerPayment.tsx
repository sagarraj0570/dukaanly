import { useParams, useNavigate } from 'react-router-dom'
import { useOrder, useOrderReservation } from '@/hooks/useOrders'
import { useInitiatePayment, useVerifyPayment } from '@/hooks/usePayments'
import { useSynchronizedCountdown } from '@/hooks/useSynchronizedCountdown'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ErrorState'
import { formatCurrency } from '@/lib/utils'
import { CreditCard, CheckCircle, Zap, XCircle, Lock, Clock, AlertTriangle, ArrowLeft, RefreshCw } from 'lucide-react'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useState, useEffect, useMemo } from 'react'

export const CustomerPayment = () => {
  useDocumentTitle('Payment Simulation')
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const { data: order, isLoading: isLoadingOrder, isError: isErrorOrder, refetch: refetchOrder } = useOrder(id)
  const { data: reservation, refetch: refetchReservation } = useOrderReservation(id, !!id)
  const { mutate: initiatePayment, isPending: isInitiating } = useInitiatePayment()
  const { mutate: verifyPayment, isPending: isVerifying } = useVerifyPayment()

  const [initiationError, setInitiationError] = useState<string | null>(null)
  const [verificationError, setVerificationError] = useState<string | null>(null)
  const [providerDetails, setProviderDetails] = useState<any>(null)

  // 1. Authoritative Backend Stock Release Check
  // Invariant: The frontend countdown must NEVER unilaterally declare that stock is released.
  // ONLY the backend (via OrderStatus.cancelled or ReservationStatus.expired/released) determines stock release.
  const isStockReleasedAuthoritatively = useMemo(() => {
    if (order?.status === 'cancelled') return true
    if (reservation?.status === 'expired' || reservation?.status === 'released') return true
    return false
  }, [order, reservation])

  // 2. High-precision, drift-free synchronized countdown hook
  // Anchors server duration to the monotonic performance.now() clock rather than user's system clock (Date.now()).
  const { secondsRemaining, formattedTime, isTimerElapsed, isExpiringSoon } = useSynchronizedCountdown({
    serverSecondsRemaining: reservation?.seconds_remaining,
    serverTime: reservation?.server_time,
    isAuthoritativeExpired: isStockReleasedAuthoritatively,
    onLocalTimerElapsed: () => {
      // Countdown reached 0 locally: immediate query to backend to check authoritative status
      refetchOrder()
      refetchReservation()
    },
  })

  useEffect(() => {
    if (order && order.status === 'pending' && !isStockReleasedAuthoritatively && !providerDetails && !isInitiating && !initiationError) {
      initiatePayment(order.id, {
        onSuccess: (data) => setProviderDetails(data),
        onError: (err: any) => setInitiationError(err.response?.data?.detail || 'Failed to initiate payment'),
      })
    }
  }, [order, isStockReleasedAuthoritatively, providerDetails, isInitiating, initiationError, initiatePayment])

  const handleInitiatePayment = () => {
    setInitiationError(null)
    initiatePayment(order!.id, {
      onSuccess: (data) => setProviderDetails(data),
      onError: (err: any) => setInitiationError(err.response?.data?.detail || 'Failed to initiate payment'),
    })
  }

  const simulatePayment = (success: boolean) => {
    setVerificationError(null)
    if (!providerDetails || isStockReleasedAuthoritatively) return

    const paymentId = success && providerDetails.mock_payment_id
      ? providerDetails.mock_payment_id
      : `pay_mock_${crypto.randomUUID().slice(0, 10)}`

    const signature = success && providerDetails.mock_signature
      ? providerDetails.mock_signature
      : '0000000000000000000000000000000000000000000000000000000000000000'

    const payload = {
      razorpay_order_id: providerDetails.provider_order_id,
      razorpay_payment_id: paymentId,
      razorpay_signature: signature,
    }

    verifyPayment(payload, {
      onSuccess: () => navigate(`/customer/orders/${order!.id}/confirmation`, { replace: true }),
      onError: (err: any) => {
        setVerificationError(err.response?.data?.detail || 'Payment verification failed')
        refetchOrder()
        refetchReservation()
      },
    })
  }

  if (isLoadingOrder) {
    return (
      <div className="max-w-md mx-auto animate-pulse">
        <div className="h-80 bg-muted rounded-2xl" />
      </div>
    )
  }

  if (isErrorOrder || !order) {
    return (
      <div className="max-w-md mx-auto">
        <ErrorState title="Could not load order" message="We couldn't retrieve the details for this order." onRetry={() => refetchOrder()} />
      </div>
    )
  }

  if (order.status !== 'pending' && !isStockReleasedAuthoritatively) {
    return (
      <div className="max-w-md mx-auto">
        <div className="bg-white border border-border rounded-2xl p-8 text-center shadow-soft">
          <CheckCircle className="h-14 w-14 text-green-500 mx-auto mb-4" />
          <h1 className="text-xl font-bold text-foreground mb-2">Order no longer pending</h1>
          <p className="text-muted-foreground mb-6">
            Status: <span className="font-semibold text-foreground capitalize">{order.status.replace(/_/g, ' ')}</span>
          </p>
          <Button onClick={() => navigate(`/customer/orders/${order.id}/confirmation`)}>
            View Order Status
          </Button>
        </div>
      </div>
    )
  }

  const busy = isInitiating || isVerifying

  return (
    <div className="max-w-md mx-auto animate-fade-in space-y-4">
      {/* 1. Authoritative Active Reservation Banner */}
      {!isStockReleasedAuthoritatively && !isTimerElapsed && secondsRemaining !== null && (
        <div className={`p-4 rounded-2xl border flex items-center justify-between transition-colors ${
          isExpiringSoon
            ? 'bg-amber-50 border-amber-300 text-amber-900'
            : 'bg-emerald-50 border-emerald-200 text-emerald-900'
        }`}>
          <div className="flex items-center gap-2.5">
            <Clock className={`h-5 w-5 ${isExpiringSoon ? 'text-amber-600 animate-pulse' : 'text-emerald-600'}`} />
            <div>
              <p className="text-xs font-bold uppercase tracking-wider">Inventory Reserved</p>
              <p className="text-xs text-text-secondary">Complete payment to confirm order</p>
            </div>
          </div>
          <div className="text-right">
            <span className="font-mono text-lg font-extrabold tracking-tight">
              {formattedTime}
            </span>
          </div>
        </div>
      )}

      {/* 2. Local Timer Window Elapsed Notice (Awaiting Authoritative Backend Confirmation) */}
      {!isStockReleasedAuthoritatively && isTimerElapsed && (
        <div className="p-4 rounded-2xl border bg-amber-50 border-amber-300 text-amber-900 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <RefreshCw className="h-5 w-5 text-amber-600 animate-spin" />
            <div>
              <p className="text-xs font-bold uppercase tracking-wider">Verifying Reservation Status</p>
              <p className="text-xs text-amber-700">Reservation window reached 00:00. Syncing with server...</p>
            </div>
          </div>
          <div className="text-right">
            <span className="font-mono text-lg font-extrabold tracking-tight text-amber-800">00:00</span>
          </div>
        </div>
      )}

      {/* 3. Authoritative Stock Released Notice (Confirmed by Backend) */}
      {isStockReleasedAuthoritatively && (
        <div className="p-5 rounded-2xl bg-red-50 border border-red-200 text-center space-y-3">
          <div className="h-12 w-12 rounded-xl bg-red-100 flex items-center justify-center mx-auto text-red-600">
            <AlertTriangle className="h-6 w-6" />
          </div>
          <div>
            <h2 className="text-base font-bold text-red-900">Reservation Expired</h2>
            <p className="text-xs text-red-700 mt-1 leading-relaxed">
              Your temporary stock reservation window has expired and items have been safely restored to inventory by the server.
            </p>
          </div>
          <Button
            className="w-full btn-primary text-white font-semibold rounded-xl gap-2 mt-2"
            onClick={() => navigate('/customer/cart')}
          >
            <ArrowLeft className="h-4 w-4" />
            Return to Cart & Re-order
          </Button>
        </div>
      )}

      {/* Main Payment Card */}
      <div className={`bg-surface border border-border rounded-2xl overflow-hidden shadow-soft ${isStockReleasedAuthoritatively ? 'opacity-60 pointer-events-none' : ''}`}>
        {/* Header */}
        <div className="bg-gradient-to-r from-primary-700 to-primary-900 p-6 text-white text-center">
          <div className="h-14 w-14 rounded-2xl bg-white/15 border border-white/20 flex items-center justify-center mx-auto mb-3">
            <CreditCard className="h-7 w-7 text-white" aria-hidden="true" />
          </div>
          <h1 className="text-xl font-bold text-white mb-0.5">Complete Payment</h1>
          <p className="text-white/90 text-xs font-mono">
            Order {order.id.split('-')[0].toUpperCase()}
          </p>
        </div>

        <div className="p-6 space-y-5">
          {/* Amount */}
          <div className="bg-primary-50 border border-primary-200/80 rounded-xl p-5 text-center">
            <p className="text-xs font-semibold text-primary-900 uppercase tracking-wider mb-1.5">
              Amount Due
            </p>
            <p className="text-3xl sm:text-4xl font-bold text-text-primary tracking-tight">{formatCurrency(order.total_amount)}</p>
          </div>

          {/* Errors */}
          {initiationError && (
            <div role="alert" aria-live="assertive" className="p-3 bg-red-50 border border-red-100 rounded-xl text-sm text-semantic-error text-center">
              <p className="font-medium mb-1">Failed to initialize payment</p>
              <p className="mb-3">{initiationError}</p>
              <Button variant="outline" size="sm" onClick={handleInitiatePayment} disabled={isInitiating}>
                Retry
              </Button>
            </div>
          )}

          {verificationError && (
            <div role="alert" aria-live="assertive" className="p-3 bg-red-50 border border-red-100 rounded-xl text-sm text-semantic-error text-center">
              <p className="font-medium mb-1">Verification Failed</p>
              <p className="text-xs mt-0.5 mb-2">{verificationError}</p>
              {!isStockReleasedAuthoritatively && (
                <p className="text-[11px] text-red-600 font-medium">You can re-attempt payment before your reservation timer expires.</p>
              )}
            </div>
          )}

          {/* Sandbox controls */}
          {!initiationError && !isStockReleasedAuthoritatively && (
            <div className="space-y-3">
              <div className="bg-accent-100/70 border border-accent-200 rounded-xl p-3 text-center">
                <p className="text-xs font-semibold text-accent-700">Sandbox Simulation Environment</p>
                <p className="text-[11px] text-accent-600 mt-0.5">Choose an outcome to simulate payment</p>
              </div>

              <Button
                size="lg"
                className="w-full h-12 btn-primary gap-2 font-semibold rounded-xl"
                onClick={() => simulatePayment(true)}
                disabled={busy || !providerDetails || isStockReleasedAuthoritatively}
              >
                {busy ? 'Processing...' : (
                  <>
                    <Zap className="h-4 w-4" />
                    Simulate Success
                  </>
                )}
              </Button>

              <Button
                size="lg"
                variant="outline"
                className="w-full h-12 text-semantic-error border-red-200 hover:bg-red-50 gap-2 rounded-xl"
                onClick={() => simulatePayment(false)}
                disabled={busy || !providerDetails || isStockReleasedAuthoritatively}
              >
                <XCircle className="h-4 w-4" />
                Simulate Failure
              </Button>
            </div>
          )}

          <div className="flex items-center justify-center gap-1.5 text-xs text-text-secondary pt-1">
            <Lock className="h-3 w-3" />
            Payments are simulated for demo purposes
          </div>
        </div>
      </div>
    </div>
  )
}
