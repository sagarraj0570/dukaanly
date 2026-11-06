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
      queryClient.invalidateQueries({ queryKey: ['delivery-route', data.id] })
    }
  })
}

export interface RouteLeg {
  from_name: string
  to_name: string
  from_latitude: number
  from_longitude: number
  to_latitude: number
  to_longitude: number
  distance_meters: number
  duration_seconds: number
  duration_minutes: number
  geometry: [number, number][]
  is_fallback: boolean
  cached: boolean
}

export interface DeliveryRouteLocation {
  latitude: number
  longitude: number
  name: string
}

export interface DeliveryRoute {
  delivery_id: string
  status: DeliveryStatus
  rider_location: DeliveryRouteLocation | null
  shop_location: DeliveryRouteLocation
  customer_location: DeliveryRouteLocation
  legs: RouteLeg[]
  total_distance_meters: number
  total_duration_seconds: number
  total_duration_minutes: number
  combined_geometry: [number, number][]
  active_leg_index: number
  is_fallback: boolean
  cached: boolean
  attribution: string
}

export const fetchDeliveryRoute = async (deliveryId: string): Promise<DeliveryRoute> => {
  const { data } = await api.get(`/deliveries/${deliveryId}/route`)
  return data
}

export const useDeliveryRoute = (deliveryId: string | undefined, enabled: boolean = true) => {
  return useQuery({
    queryKey: ['delivery-route', deliveryId],
    queryFn: () => fetchDeliveryRoute(deliveryId!),
    enabled: !!deliveryId && enabled,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status && ['assigned', 'picked_up', 'out_for_delivery'].includes(status)) {
        return 15000 // Poll route every 15s during active delivery
      }
      return false
    },
  })
}

export interface DeliveryEtaDetail {
  earliest_at: string | null
  latest_at: string | null
  remaining_seconds: number
  source: 'osrm' | 'fallback_estimate' | 'unavailable' | string
  is_estimated: boolean
  calculated_at: string | null
}

export interface DeliveryEtaBreakdown {
  preparation_remaining_seconds: number
  assignment_wait_seconds: number
  pickup_travel_remaining_seconds: number
  pickup_buffer_seconds: number
  dropoff_travel_seconds: number
  handoff_buffer_seconds: number
}

export interface DeliveryEtaResponse {
  delivery_id: string
  status: DeliveryStatus
  eta: DeliveryEtaDetail
  breakdown: DeliveryEtaBreakdown
  update_reason: string | null
  delay_explanation: string | null
}

export interface DeliveryPreparationUpdate {
  estimated_minutes: number
  started_at?: string | null
  delay_reason?: string | null
}

export const fetchDeliveryEta = async (deliveryId: string): Promise<DeliveryEtaResponse> => {
  const { data } = await api.get(`/deliveries/${deliveryId}/eta`)
  return data
}

export const updateDeliveryPreparation = async (
  deliveryId: string,
  prep: DeliveryPreparationUpdate
): Promise<DeliveryEtaResponse> => {
  const { data } = await api.patch(`/deliveries/${deliveryId}/preparation`, prep)
  return data
}

export const useDeliveryEta = (deliveryId: string | undefined, enabled: boolean = true) => {
  return useQuery({
    queryKey: ['delivery-eta', deliveryId],
    queryFn: () => fetchDeliveryEta(deliveryId!),
    enabled: !!deliveryId && enabled,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status && ['pending', 'assigned', 'picked_up', 'out_for_delivery'].includes(status)) {
        return 15000 // Poll ETA every 15s during active delivery
      }
      return false
    },
  })
}

export const useUpdateDeliveryPreparation = () => {
  const queryClient = useQueryClient()
  return useMutation<DeliveryEtaResponse, AxiosError, { deliveryId: string; prep: DeliveryPreparationUpdate }>({
    mutationFn: ({ deliveryId, prep }) => updateDeliveryPreparation(deliveryId, prep),
    onSuccess: (data) => {
      queryClient.setQueryData(['delivery-eta', data.delivery_id], data)
      queryClient.invalidateQueries({ queryKey: ['delivery', data.delivery_id] })
    },
  })
}

