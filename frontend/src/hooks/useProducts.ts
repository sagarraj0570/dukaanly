import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/axios'

export interface Product {
  id: string
  shop_id: string
  name: string
  description: string | null
  category: string | null
  price: number // It comes as string/number from backend, typically string for decimals
  image_url: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface ProductListResponse {
  items: Product[]
  total: number
  page: number
  size: number
}

export const fetchShopProducts = async (
  shopId: string,
  page: number,
  size: number,
  category?: string | null,
  active_only: boolean = true
): Promise<ProductListResponse> => {
  const { data } = await api.get(`/shops/${shopId}/products`, {
    params: { page, size, category: category || undefined, active_only }
  })
  return data
}

export const fetchProductById = async (productId: string): Promise<Product> => {
  const { data } = await api.get(`/products/${productId}`)
  return data
}

export const useShopProducts = (
  shopId: string,
  page: number = 1,
  size: number = 20,
  category?: string | null
) => {
  return useQuery({
    queryKey: ['shops', shopId, 'products', { page, size, category }],
    queryFn: () => fetchShopProducts(shopId, page, size, category),
    enabled: !!shopId,
    staleTime: 5 * 60 * 1000,
  })
}

export const useProduct = (productId: string) => {
  return useQuery({
    queryKey: ['product', productId],
    queryFn: () => fetchProductById(productId),
    enabled: !!productId,
    staleTime: 5 * 60 * 1000,
  })
}
