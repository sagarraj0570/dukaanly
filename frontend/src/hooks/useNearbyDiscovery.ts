import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/axios'

export interface NearbyStoreListing {
  source: string
  source_id: string
  name: string
  category: string
  address: string
  latitude: number
  longitude: number
  distance_meters: number
  phone?: string | null
  website?: string | null
  opening_hours?: string | null
  is_directory_listing: boolean
  is_dukaanly_merchant: boolean
  is_orderable: boolean
  is_delivery_eligible: boolean
  attribution: string
}

export interface NearbyDiscoveryResponse {
  items: NearbyStoreListing[]
  total: number
  latitude: number
  longitude: number
  radius_meters: number
  category?: string | null
  cached: boolean
  attribution: string
}

export interface FetchNearbyStoresParams {
  lat?: number | null
  lon?: number | null
  radius?: number
  category?: string | null
  limit?: number
}

export const fetchNearbyStores = async (
  params: FetchNearbyStoresParams
): Promise<NearbyDiscoveryResponse> => {
  const queryParams: Record<string, string | number> = {
    lat: params.lat!,
    lon: params.lon!,
  }

  if (params.radius) {
    queryParams.radius = params.radius
  }
  if (params.category) {
    queryParams.category = params.category
  }
  if (params.limit) {
    queryParams.limit = params.limit
  }

  const response = await api.get<NearbyDiscoveryResponse>('/discovery/nearby', {
    params: queryParams,
  })
  return response.data
}

export const useNearbyDiscovery = (
  params: FetchNearbyStoresParams,
  options?: { retry?: boolean | number }
) => {
  const isEnabled =
    typeof params.lat === 'number' &&
    typeof params.lon === 'number' &&
    !isNaN(params.lat) &&
    !isNaN(params.lon)

  return useQuery({
    queryKey: [
      'discovery',
      'nearby',
      {
        lat: params.lat,
        lon: params.lon,
        radius: params.radius ?? 3000,
        category: params.category || 'all',
        limit: params.limit ?? 20,
      },
    ],
    queryFn: () => fetchNearbyStores(params),
    enabled: isEnabled,
    staleTime: 5 * 60 * 1000, // 5 minutes matching backend Redis/memory cache
    gcTime: 10 * 60 * 1000,
    retry: options?.retry ?? false,
  })
}
