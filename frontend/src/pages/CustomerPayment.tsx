import { useParams, useNavigate } from 'react-router-dom'
import { useOrder } from '@/hooks/useOrders'
import { useInitiatePayment, useVerifyPayment } from '@/hooks/usePayments'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ErrorState'
import { formatCurrency } from '@/lib/utils'
import { CreditCard, CheckCircle, Zap, XCircle, Lock } from 'lucide-react'
import { useState, useEffect } from 'react'

export const CustomerPayment = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const { data: order, isLoading: isLoadingOrder, isError: isErrorOrder, refetch: refetchOrder } = useOrder(id)
  const { mutate: initiatePayment, isPending: isInitiating } = useInitiatePayment()
  const { mutate: verifyPayment, isPending: isVerifying } = useVerifyPayment()

  const [initiationError, setInitiationError] = useState<string | null>(null)
  const [verificationError, setVerificationError] = useState<string | null>(null)
  const [providerDetails, setProviderDetails] = useState<any>(null)

  useEffect(() => {
    if (order && order.status === 'pending' && !providerDetails && !isInitiating && !initiationError) {
      initiatePayment(order.id, {
        onSuccess: (data) => setProviderDetails(data),
        onError: (err: any) => setInitiationError(err.response?.data?.detail || 'Failed to initiate payment'),
      })
    }
  }, [order, providerDetails, isInitiating, initiationError, initiatePayment])

  const handleInitiatePayment = () => {
    setInitiationError(null)
    initiatePayment(order!.id, {
      onSuccess: (data) => setProviderDetails(data),
      onError: (err: any) => setInitiationError(err.response?.data?.detail || 'Failed to initiate payment'),
    })
  }

  const simulatePayment = (success: boolean) => {
    setVerificationError(null)
    if (!providerDetails) return
    const payload = {
      razorpay_order_id: providerDetails.provider_order_id,
      razorpay_payment_id: `pay_mock_${crypto.randomUUID().slice(0, 10)}`,
      razorpay_signature: success ? 'mock_signature_valid' : 'mock_signature_invalid',
    }
    verifyPayment(payload, {
      onSuccess: () => navigate(`/customer/orders/${order!.id}/confirmation`, { replace: true }),
      onError: (err: any) => {
        setVerificationError(err.response?.data?.detail || 'Payment verification failed')
        refetchOrder()
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

  if (order.status !== 'pending') {
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
    <div className="max-w-md mx-auto animate-fade-in">
      <div className="bg-white border border-[#E5E9E4] rounded-2xl overflow-hidden shadow-soft">
        {/* Header */}
        <div className="bg-gradient-to-r from-[#176B45] to-[#104B32] p-6 text-white text-center">
          <div className="h-14 w-14 rounded-2xl bg-white/15 border border-white/20 flex items-center justify-center mx-auto mb-3">
            <CreditCard className="h-7 w-7 text-white" aria-hidden="true" />
          </div>
          <h1 className="text-xl font-bold mb-0.5">Complete Payment</h1>
          <p className="text-white/90 text-xs font-mono">
            Order {order.id.split('-')[0].toUpperCase()}
          </p>
        </div>

        <div className="p-6 space-y-5">
          {/* Amount */}
          <div className="bg-[#EDF5EE] border border-[#A8D5B5]/60 rounded-xl p-5 text-center">
            <p className="text-xs font-semibold text-[#104B32] uppercase tracking-wider mb-1.5">
              Amount Due
            </p>
            <p className="text-3xl sm:text-4xl font-bold text-[#202923] tracking-tight">{formatCurrency(order.total_amount)}</p>
          </div>

          {/* Errors */}
          {initiationError && (
            <div role="alert" aria-live="assertive" className="p-3 bg-red-50 border border-red-100 rounded-xl text-sm text-red-700 text-center">
              <p className="font-medium mb-1">Failed to initialize payment</p>
              <p className="mb-3">{initiationError}</p>
              <Button variant="outline" size="sm" onClick={handleInitiatePayment} disabled={isInitiating}>
                Retry
              </Button>
            </div>
          )}

          {verificationError && (
            <div role="alert" aria-live="assertive" className="p-3 bg-red-50 border border-red-100 rounded-xl text-sm text-red-700 text-center">
              <p className="font-medium mb-1">Verification Failed</p>
              <p>{verificationError}</p>
            </div>
          )}

          {/* Sandbox controls */}
          {!initiationError && (
            <div className="space-y-3">
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-center">
                <p className="text-xs font-semibold text-amber-800">Sandbox Simulation Environment</p>
                <p className="text-[11px] text-amber-700 mt-0.5">Choose an outcome to simulate payment</p>
              </div>

              <Button
                size="lg"
                className="w-full h-12 bg-[#176B45] hover:bg-[#104B32] text-white gap-2 font-semibold rounded-xl"
                onClick={() => simulatePayment(true)}
                disabled={busy || !providerDetails}
              >
                {busy ? 'Processing…' : (
                  <>
                    <Zap className="h-4 w-4" />
                    Simulate Success
                  </>
                )}
              </Button>

              <Button
                size="lg"
                variant="outline"
                className="w-full h-12 text-red-600 border-red-200 hover:bg-red-50 gap-2 rounded-xl"
                onClick={() => simulatePayment(false)}
                disabled={busy || !providerDetails}
              >
                <XCircle className="h-4 w-4" />
                Simulate Failure
              </Button>
            </div>
          )}

          <div className="flex items-center justify-center gap-1.5 text-xs text-[#69736C] pt-1">
            <Lock className="h-3 w-3" />
            Payments are simulated for demo purposes
          </div>
        </div>
      </div>
    </div>
  )
}
