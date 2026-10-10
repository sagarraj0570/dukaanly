import { useParams, useNavigate } from 'react-router-dom'
import { useProduct } from '@/hooks/useProducts'
import { useShop } from '@/hooks/useShops'
import { ErrorState } from '@/components/ErrorState'
import { Button } from '@/components/ui/button'
import { formatCurrency } from '@/lib/utils'
import { ArrowLeft, Package, Store } from 'lucide-react'
import { useState } from 'react'

export const ProductDetail = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [imageError, setImageError] = useState(false)
  
  const { data: product, isLoading, isError, error, refetch } = useProduct(id || '')
  
  // We optionally fetch the shop to display shop navigation gracefully
  const { data: shop } = useShop(product?.shop_id || '')

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse max-w-4xl mx-auto">
        <div className="h-8 bg-gray-100 rounded w-1/4 mb-8" />
        <div className="flex flex-col md:flex-row gap-8">
          <div className="w-full md:w-1/2 h-80 bg-gray-100 rounded-lg" />
          <div className="w-full md:w-1/2 space-y-4">
            <div className="h-8 bg-gray-100 rounded w-3/4" />
            <div className="h-6 bg-gray-100 rounded w-1/4" />
            <div className="h-4 bg-gray-100 rounded w-full" />
            <div className="h-4 bg-gray-100 rounded w-full" />
          </div>
        </div>
      </div>
    )
  }

  if (isError || !product) {
    return (
      <div className="space-y-4 max-w-4xl mx-auto">
        <Button variant="ghost" onClick={() => navigate(-1)} className="mb-4">
          <ArrowLeft className="mr-2 h-4 w-4" /> Go Back
        </Button>
        <ErrorState 
          title="Product not found"
          message={error?.message || "The product you are looking for does not exist or is currently unavailable."}
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <Button 
        variant="ghost" 
        onClick={() => navigate(`/customer/shops/${product.shop_id}`)} 
        className="-ml-4 text-gray-500 hover:text-gray-900"
      >
        <ArrowLeft className="mr-2 h-4 w-4" /> Back to {shop?.name || 'Shop'}
      </Button>

      <div className="bg-white border rounded-xl overflow-hidden shadow-sm flex flex-col md:flex-row">
        {/* Image Section */}
        <div className="w-full md:w-1/2 bg-gray-100 flex items-center justify-center min-h-[300px] md:min-h-[400px] relative border-b md:border-b-0 md:border-r">
          {product.image_url && !imageError ? (
            <img 
              src={product.image_url} 
              alt={product.name} 
              className="w-full h-full object-cover"
              onError={() => setImageError(true)}
            />
          ) : (
            <div className="flex flex-col items-center justify-center text-gray-400">
              <Package className="h-16 w-16 mb-2 opacity-50" />
              <span className="text-sm font-medium uppercase tracking-wider opacity-70">No Image Available</span>
            </div>
          )}
        </div>

        {/* Details Section */}
        <div className="w-full md:w-1/2 p-6 md:p-8 flex flex-col">
          <div className="mb-6">
            <div className="flex items-start justify-between gap-4 mb-2">
              {product.category && (
                <span className="text-sm font-medium text-gray-500 uppercase tracking-wider">
                  {product.category}
                </span>
              )}
              {!product.is_active && (
                <span className="inline-flex items-center rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-semibold text-red-800 border border-red-200">
                  Currently Unavailable
                </span>
              )}
            </div>
            
            <h1 className="text-3xl font-bold text-gray-900 mb-4">{product.name}</h1>
            
            <div className="text-3xl font-extrabold text-gray-900 mb-6">
              {formatCurrency(product.price)}
            </div>
            
            {product.description && (
              <div className="prose prose-sm text-gray-600 mb-8">
                <p>{product.description}</p>
              </div>
            )}
          </div>
          
          <div className="mt-auto pt-6 border-t border-gray-100 flex items-center gap-3">
            <Store className="h-5 w-5 text-gray-400" />
            <span className="text-sm text-gray-500 font-medium">
              Sold by: <span className="text-gray-900">{shop?.name || 'Loading shop...'}</span>
            </span>
          </div>
          
          <div className="mt-6 p-4 border rounded-lg bg-gray-50 text-center">
            <p className="text-sm text-gray-500 font-medium">Add to Cart functionality is pending Sub-task 17C.</p>
          </div>
        </div>
      </div>
    </div>
  )
}
