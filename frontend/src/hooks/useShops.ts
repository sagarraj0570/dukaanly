import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/axios'

export interface Location {
  latitude: number
  longitude: number
}

export interface Shop {
  id: string
  owner_id?: string | null
  name: string
  description: string | null
  address: string
  phone?: string | null
  opening_hours?: string | null
  is_active: boolean
  is_orderable?: boolean
  verification_status?: 'discovered' | 'claimed' | 'verified'
  source?: string | null
  source_id?: string | null
  source_attribution?: string | null
  location: Location
  created_at: string
  updated_at: string
  distance_meters?: number | null
  is_delivery_eligible?: boolean | null
  delivery_radius_meters?: number
}

export interface ShopListResponse {
  items: Shop[]
  total: number
  page: number
  size: number
  user_latitude?: number | null
  user_longitude?: number | null
  radius_meters?: number | null
}

export interface DeliveryEligibilityResponse {
  shop_id: string
  shop_name: string
  customer_location: Location
  distance_meters: number
  is_delivery_eligible: boolean
  delivery_radius_meters: number
  message: string
}

export interface FetchShopsParams {
  page?: number
  size?: number
  latitude?: number | null
  longitude?: number | null
  radius_meters?: number
  delivery_only?: boolean
  verified_only?: boolean
}

export const fetchShops = async (
  pageOrParams: number | FetchShopsParams = 1,
  defaultSize: number = 20
): Promise<ShopListResponse> => {
  const params: FetchShopsParams =
    typeof pageOrParams === 'number'
      ? { page: pageOrParams, size: defaultSize }
      : { page: 1, size: defaultSize, ...pageOrParams }

  const queryParams: Record<string, any> = {
    page: params.page ?? 1,
    size: params.size ?? 20,
  }

  if (params.latitude !== undefined && params.latitude !== null) {
    queryParams.latitude = params.latitude
  }
  if (params.longitude !== undefined && params.longitude !== null) {
    queryParams.longitude = params.longitude
  }
  if (params.radius_meters !== undefined && params.radius_meters !== null) {
    queryParams.radius_meters = params.radius_meters
  }
  if (params.delivery_only !== undefined && params.delivery_only !== null) {
    queryParams.delivery_only = params.delivery_only
  }
  if (params.verified_only !== undefined && params.verified_only !== null) {
    queryParams.verified_only = params.verified_only
  }

  const { data } = await api.get('/shops', { params: queryParams })
  return data
}

export const fetchShopById = async (shopId: string): Promise<Shop> => {
  const { data } = await api.get(`/shops/${shopId}`)
  return data
}

export const fetchShopDeliveryEligibility = async (
  shopId: string,
  latitude: number,
  longitude: number
): Promise<DeliveryEligibilityResponse> => {
  const { data } = await api.get(`/shops/${shopId}/delivery-eligibility`, {
    params: { latitude, longitude },
  })
  return data
}

export const useShops = (
  pageOrParams: number | FetchShopsParams = 1,
  size: number = 20
) => {
  const params: FetchShopsParams =
    typeof pageOrParams === 'number'
      ? { page: pageOrParams, size }
      : { page: 1, size: 20, ...pageOrParams }

  const {
    page = 1,
    size: pageSize = 20,
    latitude,
    longitude,
    radius_meters,
    delivery_only,
  } = params

  return useQuery({
    queryKey: [
      'shops',
      { page, size: pageSize, latitude, longitude, radius_meters, delivery_only },
    ],
    queryFn: () => fetchShops(params),
    staleTime: 2 * 60 * 1000,
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

export const useShopDeliveryEligibility = (
  shopId: string,
  latitude?: number | null,
  longitude?: number | null
) => {
  const hasCoords =
    typeof latitude === 'number' &&
    typeof longitude === 'number' &&
    !isNaN(latitude) &&
    !isNaN(longitude)

  return useQuery({
    queryKey: ['shop-delivery-eligibility', shopId, latitude, longitude],
    queryFn: () =>
      fetchShopDeliveryEligibility(shopId, latitude as number, longitude as number),
    enabled: !!shopId && hasCoords,
    staleTime: 5 * 60 * 1000,
  })
}
