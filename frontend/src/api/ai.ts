import { api } from '@/api/axios'

export interface CatalogProductItem {
  product_id: string
  product_name: string
  product_description?: string | null
  category?: string | null
  price: number
  stock: number
  image_url?: string | null
  shop_id: string
  shop_name: string
  shop_address: string
  distance_meters: number
  is_delivery_eligible: boolean
}

export interface ProposedCartItem {
  product_id: string
  product_name: string
  quantity: number
  unit_price: number
  item_total: number
  available_stock: number
  image_url?: string | null
}

export interface ProposedCart {
  shop_id: string
  shop_name: string
  shop_address: string
  distance_meters: number
  items: ProposedCartItem[]
  total_amount: number
  is_delivery_eligible: boolean
  has_different_shop_in_current_cart: boolean
  warning_message?: string | null
}

export interface ShoppingAssistantResponse {
  assistant_message: string
  clarifying_question?: string | null
  matched_products: CatalogProductItem[]
  proposed_cart?: ProposedCart | null
  search_query_used?: string | null
  provider: string
  model: string
  latency_ms: number
}

export interface ShoppingChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export interface ShoppingAssistantPayload {
  message: string
  latitude: number
  longitude: number
  shop_id?: string | null
  history?: ShoppingChatMessage[]
}

export interface AiStatusResponse {
  enabled: boolean
  provider: string
  model: string
  features: {
    shopping_assistant: boolean
    catalog_search: boolean
    order_support: boolean
  }
  circuit_breaker_open: boolean
  details: string
}

export const getAiStatus = async (): Promise<AiStatusResponse> => {
  const { data } = await api.get('/ai/status')
  return data
}

export const sendShoppingAssistantChat = async (
  payload: ShoppingAssistantPayload
): Promise<ShoppingAssistantResponse> => {
  const { data } = await api.post('/ai/assistant/chat', payload)
  return data
}
