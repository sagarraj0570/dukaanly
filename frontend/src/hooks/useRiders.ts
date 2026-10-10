import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/axios'
import type { AxiosError } from 'axios'

export interface RiderProfile {
  id: string
  user_id: string
  is_available: boolean
  latitude: number | null
  longitude: number | null
  location_updated_at: string | null
  created_at: string
  updated_at: string
}

export const fetchRiderProfile = async (): Promise<RiderProfile> => {
  const { data } = await api.get('/riders/me')
  return data
}

export const createRiderProfile = async (): Promise<RiderProfile> => {
  const { data } = await api.post('/riders/profile')
  return data
}

export const updateRiderAvailability = async (is_available: boolean): Promise<RiderProfile> => {
  const { data } = await api.patch('/riders/me/availability', { is_available })
  return data
}

export const updateRiderLocation = async (lat: number, lng: number): Promise<RiderProfile> => {
  const { data } = await api.patch('/riders/me/location', { latitude: lat, longitude: lng })
  return data
}

export const useRiderProfile = () => {
  return useQuery({
    queryKey: ['rider-profile'],
    queryFn: fetchRiderProfile,
    retry: false
  })
}

export const useCreateRiderProfile = () => {
  const queryClient = useQueryClient()
  return useMutation<RiderProfile, AxiosError>({
    mutationFn: createRiderProfile,
    onSuccess: (data) => {
      queryClient.setQueryData(['rider-profile'], data)
    }
  })
}

export const useUpdateAvailability = () => {
  const queryClient = useQueryClient()
  return useMutation<RiderProfile, AxiosError, boolean>({
    mutationFn: updateRiderAvailability,
    onSuccess: (data) => {
      queryClient.setQueryData(['rider-profile'], data)
    }
  })
}

export const useUpdateLocation = () => {
  const queryClient = useQueryClient()
  return useMutation<RiderProfile, AxiosError, { lat: number, lng: number }>({
    mutationFn: ({ lat, lng }) => updateRiderLocation(lat, lng),
    onSuccess: (data) => {
      queryClient.setQueryData(['rider-profile'], data)
    }
  })
}
