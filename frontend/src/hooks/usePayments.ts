import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/axios'
import type { AxiosError } from 'axios'

export interface PaymentInitiationResponse {
  payment_id: string
  order_id: string
  provider: string
  provider_order_id: string
  amount: number
  currency: string
  key_id: string | null
}

export interface PaymentVerificationRequest {
  razorpay_order_id: string
  razorpay_payment_id: string
  razorpay_signature: string
}

export interface Payment {
  id: string
  order_id: string
  provider: string
  provider_payment_id: string | null
  amount: number
  currency: string
  status: 'created' | 'pending' | 'captured' | 'failed' | 'refunded'
  created_at: string
  paid_at: string | null
}

export const initiatePayment = async (orderId: string): Promise<PaymentInitiationResponse> => {
  const { data } = await api.post(`/orders/${orderId}/payment`)
  return data
}

export const verifyPayment = async (payload: PaymentVerificationRequest): Promise<Payment> => {
  const { data } = await api.post(`/payments/verify`, payload)
  return data
}

export const useInitiatePayment = () => {
  return useMutation<PaymentInitiationResponse, AxiosError, string>({
    mutationFn: initiatePayment
  })
}

export const useVerifyPayment = () => {
  const queryClient = useQueryClient()
  return useMutation<Payment, AxiosError, PaymentVerificationRequest>({
    mutationFn: verifyPayment,
    onSuccess: (data) => {
      // Refresh the order to reflect updated status
      queryClient.invalidateQueries({ queryKey: ['order', data.order_id] })
    }
  })
}
