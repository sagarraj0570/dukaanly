import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/axios'
import type { AxiosError } from 'axios'

export interface CartItem {
  id: string
  product_id: string
  quantity: number
  product_name: string
  product_price: number
  item_total: number
}

export interface Cart {
  id: string
  customer_id: string
  shop_id: string | null
  items: CartItem[]
  total_amount: number
}

// Fetch Cart
export const fetchCart = async (): Promise<Cart> => {
  const { data } = await api.get('/cart')
  return data
}

// Add Item
export interface AddItemPayload {
  product_id: string
  quantity: number
}
export const addItemToCart = async (payload: AddItemPayload): Promise<Cart> => {
  const { data } = await api.post('/cart/items', payload)
  return data
}

// Update Item
export interface UpdateItemPayload {
  item_id: string
  quantity: number
}
export const updateCartItem = async (payload: UpdateItemPayload): Promise<Cart> => {
  const { data } = await api.patch(`/cart/items/${payload.item_id}`, { quantity: payload.quantity })
  return data
}

// Remove Item
export const removeCartItem = async (itemId: string): Promise<Cart> => {
  const { data } = await api.delete(`/cart/items/${itemId}`)
  return data
}

// Clear Cart
export const clearCart = async (): Promise<Cart> => {
  const { data } = await api.delete('/cart')
  return data
}

// Hooks
export const useCart = () => {
  return useQuery({
    queryKey: ['cart'],
    queryFn: fetchCart,
    staleTime: 1000 * 60 * 5, // 5 minutes
  })
}

export const useAddToCart = () => {
  const queryClient = useQueryClient()
  return useMutation<Cart, AxiosError, AddItemPayload>({
    mutationFn: addItemToCart,
    onSuccess: (data) => {
      queryClient.setQueryData(['cart'], data)
    },
  })
}

export const useUpdateCartItem = () => {
  const queryClient = useQueryClient()
  return useMutation<Cart, AxiosError, UpdateItemPayload>({
    mutationFn: updateCartItem,
    onSuccess: (data) => {
      queryClient.setQueryData(['cart'], data)
    },
  })
}

export const useRemoveCartItem = () => {
  const queryClient = useQueryClient()
  return useMutation<Cart, AxiosError, string>({
    mutationFn: removeCartItem,
    onSuccess: (data) => {
      queryClient.setQueryData(['cart'], data)
    },
  })
}

export const useClearCart = () => {
  const queryClient = useQueryClient()
  return useMutation<Cart, AxiosError, void>({
    mutationFn: clearCart,
    onSuccess: (data) => {
      queryClient.setQueryData(['cart'], data)
    },
  })
}
