import { useParams, useNavigate } from 'react-router-dom'
import { useOrder } from '@/hooks/useOrders'
import { useInitiatePayment, useVerifyPayment } from '@/hooks/usePayments'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ErrorState'
import { formatCurrency } from '@/lib/utils'
import { CreditCard, CheckCircle } from 'lucide-react'
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
    // Only initiate payment if the order is successfully fetched and in pending state
    if (order && order.status === 'pending' && !providerDetails && !isInitiating && !initiationError) {
      setInitiationError(null)
      initiatePayment(order.id, {
        onSuccess: (data) => {
          setProviderDetails(data)
        },
        onError: (err: any) => {
          setInitiationError(err.response?.data?.detail || "Failed to initiate payment")
        }
      })
    }
  }, [order, providerDetails, isInitiating, initiationError, initiatePayment])

  const handleInitiatePayment = () => {
    setInitiationError(null)
    initiatePayment(order!.id, {
      onSuccess: (data) => {
        setProviderDetails(data)
      },
      onError: (err: any) => {
        setInitiationError(err.response?.data?.detail || "Failed to initiate payment")
      }
    })
  }
  
  const simulateProviderSuccess = () => {
    setVerificationError(null)
    if (!providerDetails) return
    
    // As per Razorpay mock provider constraints:
    const mockVerificationPayload = {
      razorpay_order_id: providerDetails.provider_order_id,
      razorpay_payment_id: `pay_mock_${crypto.randomUUID().slice(0, 10)}`,
      razorpay_signature: "mock_signature_valid" // Required for mock success
    }
    
    verifyPayment(mockVerificationPayload, {
      onSuccess: () => {
        navigate(`/customer/orders/${order!.id}/confirmation`, { replace: true })
      },
      onError: (err: any) => {
        setVerificationError(err.response?.data?.detail || "Payment verification failed")
        refetchOrder()
      }
    })
  }

  const simulateProviderFailure = () => {
    setVerificationError(null)
    if (!providerDetails) return
    
    const mockVerificationPayload = {
      razorpay_order_id: providerDetails.provider_order_id,
      razorpay_payment_id: `pay_mock_${crypto.randomUUID().slice(0, 10)}`,
      razorpay_signature: "mock_signature_invalid" // Induces mock failure
    }
    
    verifyPayment(mockVerificationPayload, {
      onSuccess: () => {
        navigate(`/customer/orders/${order!.id}/confirmation`, { replace: true })
      },
      onError: (err: any) => {
        setVerificationError(err.response?.data?.detail || "Payment verification failed")
        refetchOrder()
      }
    })
  }

  if (isLoadingOrder) {
    return (
      <div className="max-w-md mx-auto p-8 bg-white border rounded-xl shadow-sm text-center animate-pulse">
        <div className="h-12 w-12 bg-gray-100 rounded-full mx-auto mb-4" />
        <div className="h-6 bg-gray-100 rounded w-1/2 mx-auto mb-2" />
        <div className="h-4 bg-gray-100 rounded w-3/4 mx-auto" />
      </div>
    )
  }

  if (isErrorOrder || !order) {
    return (
      <div className="max-w-2xl mx-auto">
        <ErrorState 
          title="Could not load order"
          message="We couldn't retrieve the details for this order."
          onRetry={() => refetchOrder()}
        />
      </div>
    )
  }

  if (order.status !== 'pending') {
    return (
      <div className="max-w-md mx-auto p-8 bg-white border rounded-xl shadow-sm text-center">
        <CheckCircle className="h-16 w-16 text-green-500 mx-auto mb-4" />
        <h2 className="text-2xl font-bold text-gray-900 mb-2">Order no longer pending</h2>
        <p className="text-gray-500 mb-6">This order is in status: <span className="font-semibold">{order.status}</span>.</p>
        <Button onClick={() => navigate(`/customer/orders/${order.id}/confirmation`)}>View Order Status</Button>
      </div>
    )
  }

  return (
    <div className="max-w-md mx-auto space-y-6">
      <div className="bg-white border rounded-xl overflow-hidden shadow-sm p-6 lg:p-8">
        <div className="text-center mb-8">
          <CreditCard className="h-12 w-12 text-primary mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Complete Payment</h1>
          <p className="text-gray-500">
            Order Reference: <span className="font-mono text-xs">{order.id}</span>
          </p>
        </div>
        
        <div className="bg-gray-50 rounded-lg p-6 mb-8 text-center border">
          <div className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-2">Amount to pay</div>
          <div className="text-4xl font-extrabold text-gray-900">{formatCurrency(order.total_amount)}</div>
        </div>

        {initiationError && (
          <div className="mb-6 p-4 bg-red-50 text-red-700 text-sm border border-red-200 rounded-md text-center">
            <p className="font-semibold mb-1">Failed to initialize payment</p>
            <p className="mb-3">{initiationError}</p>
            <Button variant="outline" size="sm" onClick={handleInitiatePayment} disabled={isInitiating}>
              Retry Initialization
            </Button>
          </div>
        )}

        {verificationError && (
          <div className="mb-6 p-4 bg-red-50 text-red-700 text-sm border border-red-200 rounded-md text-center">
            <p className="font-semibold mb-1">Payment Verification Failed</p>
            <p>{verificationError}</p>
          </div>
        )}

        {!initiationError && (
          <div className="space-y-4">
            <Button 
              size="lg" 
              className="w-full text-base h-12 bg-green-600 hover:bg-green-700 text-white"
              onClick={simulateProviderSuccess}
              disabled={isInitiating || isVerifying || !providerDetails}
            >
              {isInitiating || isVerifying ? 'Processing...' : 'Simulate Success'}
            </Button>
            
            <Button 
              size="lg"
              variant="outline"
              className="w-full text-base h-12 text-red-600 border-red-200 hover:bg-red-50 hover:text-red-700"
              onClick={simulateProviderFailure}
              disabled={isInitiating || isVerifying || !providerDetails}
            >
              Simulate Failure
            </Button>
            
            <div className="text-center text-xs text-gray-400 mt-4">
              (Sandbox Simulation Environment)
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
