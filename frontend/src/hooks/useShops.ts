import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/axios'

export interface Location {
  latitude: number
  longitude: number
}

export interface Shop {
  id: string
  owner_id: string
  name: string
  description: string | null
  address: string
  is_active: boolean
  location: Location
  created_at: string
  updated_at: string
}

export interface ShopListResponse {
  items: Shop[]
  total: number
  page: number
  size: number
}

export const fetchShops = async (page: number, size: number): Promise<ShopListResponse> => {
  const { data } = await api.get('/shops', {
    params: { page, size }
  })
  return data
}

export const fetchShopById = async (shopId: string): Promise<Shop> => {
  const { data } = await api.get(`/shops/${shopId}`)
  return data
}

export const useShops = (page: number = 1, size: number = 20) => {
  return useQuery({
    queryKey: ['shops', { page, size }],
    queryFn: () => fetchShops(page, size),
    staleTime: 5 * 60 * 1000, // 5 minutes
  })
}

export const useShop = (shopId: string) => {
  return useQuery({
    queryKey: ['shop', shopId],
    queryFn: () => fetchShopById(shopId),
    enabled: !!shopId,
    staleTime: 5 * 60 * 1000,
  })
}
