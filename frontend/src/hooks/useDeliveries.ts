import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/axios'
import type { AxiosError } from 'axios'

export type DeliveryStatus = 'pending' | 'assigned' | 'picked_up' | 'out_for_delivery' | 'delivered' | 'cancelled'

export interface Delivery {
  id: string
  order_id: string
  rider_id: string | null
  status: DeliveryStatus
  destination_latitude: number | null
  destination_longitude: number | null
  assigned_at: string | null
  picked_up_at: string | null
  delivered_at: string | null
  created_at: string
  updated_at: string
}

export const fetchMyDeliveries = async (): Promise<Delivery[]> => {
  const { data } = await api.get('/riders/me/deliveries')
  return data
}

export const fetchDelivery = async (id: string): Promise<Delivery> => {
  const { data } = await api.get(`/deliveries/${id}`)
  return data
}

export const updateDeliveryStatus = async (id: string, status: DeliveryStatus): Promise<Delivery> => {
  const { data } = await api.patch(`/deliveries/${id}/status`, { status })
  return data
}

export const useMyDeliveries = () => {
  return useQuery({
    queryKey: ['my-deliveries'],
    queryFn: fetchMyDeliveries
  })
}

export const useDelivery = (id: string | undefined) => {
  return useQuery({
    queryKey: ['delivery', id],
    queryFn: () => fetchDelivery(id!),
    enabled: !!id
  })
}

export const useUpdateDeliveryStatus = () => {
  const queryClient = useQueryClient()
  return useMutation<Delivery, AxiosError, { id: string, status: DeliveryStatus }>({
    mutationFn: ({ id, status }) => updateDeliveryStatus(id, status),
    onSuccess: (data) => {
      queryClient.setQueryData(['delivery', data.id], data)
      queryClient.invalidateQueries({ queryKey: ['my-deliveries'] })
    }
  })
}
