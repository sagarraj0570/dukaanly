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

export type OrderStatus = 'pending' | 'confirmed' | 'preparing' | 'ready_for_delivery' | 'ready_for_pickup' | 'out_for_delivery' | 'delivered' | 'cancelled'

export type DeliveryStatus = 'pending' | 'assigned' | 'picked_up' | 'out_for_delivery' | 'delivered' | 'cancelled'

export interface OrderDeliverySummary {
  id: string
  status: DeliveryStatus
  rider_id: string | null
  assigned_at: string | null
  picked_up_at: string | null
  delivered_at: string | null
}

export interface Order {
  id: string
  customer_id: string
  shop_id: string
  status: OrderStatus
  total_amount: number
  items: OrderItem[]
  created_at: string
  updated_at: string
  delivery?: OrderDeliverySummary | null
  reservation_expires_at?: string | null
  reservation_status?: string | null
}

export interface ReservationItem {
  product_id: string
  quantity: number
  status: string
  reservation_reference: string
}

export interface OrderReservation {
  order_id: string
  status: 'active' | 'consumed' | 'released' | 'expired' | 'none'
  expires_at: string | null
  seconds_remaining: number
  server_time?: string
  is_expired: boolean
  items: ReservationItem[]
}

export const fetchOrderReservation = async (orderId: string): Promise<OrderReservation> => {
  const { data } = await api.get(`/orders/${orderId}/reservation`)
  return data
}

export const useOrderReservation = (orderId: string | undefined, enabled: boolean = true) => {
  return useQuery({
    queryKey: ['order-reservation', orderId],
    queryFn: () => fetchOrderReservation(orderId!),
    enabled: !!orderId && enabled,
    refetchInterval: (query) => {
      const data = query.state.data
      if (data && data.status === 'active' && !data.is_expired) {
        return 5000
      }
      return false
    },
  })
}

export interface CheckoutPayload {
  idempotency_key: string
  destination_latitude?: number | null
  destination_longitude?: number | null
}

export interface OrderListResponse {
  items: Order[]
  total: number
  page: number
  size: number
}

// Fetch multiple orders
export const fetchOrders = async (page: number = 1, size: number = 20): Promise<OrderListResponse> => {
  const { data } = await api.get('/orders', { params: { page, size } })
  return data
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

export const useOrders = (page: number = 1, size: number = 20) => {
  return useQuery({
    queryKey: ['orders', page, size],
    queryFn: () => fetchOrders(page, size),
  })
}

export interface CancelOrderPayload {
  orderId: string
  reason?: string
}

export const cancelOrder = async ({ orderId, reason }: CancelOrderPayload): Promise<Order> => {
  const { data } = await api.post(`/orders/${orderId}/cancel`, { reason })
  return data
}

export const useCancelOrder = () => {
  const queryClient = useQueryClient()
  return useMutation<Order, AxiosError, CancelOrderPayload>({
    mutationFn: cancelOrder,
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['order', variables.orderId] })
      queryClient.invalidateQueries({ queryKey: ['orders'] })
    }
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
