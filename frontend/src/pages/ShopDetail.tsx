import { useParams, useNavigate } from 'react-router-dom'
import { useShop } from '@/hooks/useShops'
import { ErrorState } from '@/components/ErrorState'
import { ProductCatalog } from '@/components/ProductCatalog'
import { Button } from '@/components/ui/button'
import { MapPin, ArrowLeft, Clock, Store } from 'lucide-react'

export const ShopDetail = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  
  const { data: shop, isLoading, isError, error, refetch } = useShop(id || '')

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-48 bg-gray-100 rounded-lg" />
        <div className="space-y-4">
          <div className="h-8 bg-gray-100 rounded w-1/3" />
          <div className="h-4 bg-gray-100 rounded w-1/2" />
          <div className="h-4 bg-gray-100 rounded w-1/4" />
        </div>
      </div>
    )
  }

  if (isError || !shop) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate('/customer')} className="mb-4">
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to Shops
        </Button>
        <ErrorState 
          title="Shop not found"
          message={error?.message || "The shop you are looking for does not exist or is currently unavailable."}
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Back Navigation */}
      <div>
        <Button variant="ghost" onClick={() => navigate('/customer')} className="-ml-4 text-gray-500 hover:text-gray-900">
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to Shops
        </Button>
      </div>

      {/* Shop Header Area */}
      <div className="bg-white border rounded-xl overflow-hidden shadow-sm">
        <div className="h-48 bg-gray-100 flex items-center justify-center">
          <Store className="h-16 w-16 text-gray-300" />
        </div>
        <div className="p-6 sm:p-8">
          <div className="flex flex-col sm:flex-row justify-between items-start gap-4 mb-4">
            <div>
              <h1 className="text-3xl font-bold text-gray-900 mb-2">{shop.name}</h1>
              {shop.description && (
                <p className="text-gray-600 max-w-2xl">{shop.description}</p>
              )}
            </div>
            
            <div className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium border ${
              shop.is_active 
                ? 'bg-green-50 text-green-700 border-green-200' 
                : 'bg-red-50 text-red-700 border-red-200'
            }`}>
              <Clock className="h-4 w-4 mr-1.5" />
              {shop.is_active ? 'Accepting Orders' : 'Currently Closed'}
            </div>
          </div>

          <div className="flex items-start gap-2 text-gray-500 mt-6 pt-6 border-t">
            <MapPin className="h-5 w-5 shrink-0 text-gray-400 mt-0.5" />
            <span>{shop.address}</span>
          </div>
        </div>
      </div>

      {/* Catalog Area */}
      <div className="space-y-4">
        <h2 className="text-2xl font-bold text-gray-900 mb-6">Products</h2>
        <ProductCatalog shopId={shop.id} />
      </div>
    </div>
  )
}
