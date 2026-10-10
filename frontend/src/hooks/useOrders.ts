import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/axios'
import type { AxiosError } from 'axios'

export interface OrderItem {
  id: string
  product_id: string | null
  product_name: string
  unit_price: number
  quantity: number
  line_total: number
}

export type OrderStatus = 'pending' | 'confirmed' | 'preparing' | 'ready_for_pickup' | 'out_for_delivery' | 'delivered' | 'cancelled'

export interface Order {
  id: string
  customer_id: string
  shop_id: string
  status: OrderStatus
  total_amount: number
  items: OrderItem[]
  created_at: string
  updated_at: string
}

export interface CheckoutPayload {
  idempotency_key: string
}

// Fetch single order
export const fetchOrder = async (orderId: string): Promise<Order> => {
  const { data } = await api.get(`/orders/${orderId}`)
  return data
}

// Checkout
export const checkout = async (payload: CheckoutPayload): Promise<Order> => {
  const { data } = await api.post('/orders/checkout', payload)
  return data
}

export const useOrder = (orderId: string | undefined) => {
  return useQuery({
    queryKey: ['order', orderId],
    queryFn: () => fetchOrder(orderId!),
    enabled: !!orderId,
    staleTime: 1000 * 60, // 1 minute
  })
}

export const useCheckout = () => {
  const queryClient = useQueryClient()
  return useMutation<Order, AxiosError, CheckoutPayload>({
    mutationFn: checkout,
    onSuccess: () => {
      // Upon successful checkout, the cart is cleared on the backend, 
      // so invalidate the cart to reflect that.
      queryClient.invalidateQueries({ queryKey: ['cart'] })
    }
  })
}
