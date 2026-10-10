import { Link } from 'react-router-dom'
import type { Product } from '@/hooks/useProducts'
import { formatCurrency } from '@/lib/utils'
import { Package } from 'lucide-react'
import { useState } from 'react'

interface ProductCardProps {
  product: Product
}

export const ProductCard = ({ product }: ProductCardProps) => {
  const [imageError, setImageError] = useState(false)

  return (
    <Link 
      to={`/customer/products/${product.id}`}
      className="group flex flex-col bg-white border rounded-lg overflow-hidden hover:shadow-md transition-shadow focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
    >
      <div className="h-40 bg-gray-100 flex items-center justify-center border-b overflow-hidden relative">
        {product.image_url && !imageError ? (
          <img 
            src={product.image_url} 
            alt={product.name} 
            className="w-full h-full object-cover transition-transform group-hover:scale-105"
            onError={() => setImageError(true)}
          />
        ) : (
          <div className="flex flex-col items-center justify-center text-gray-400">
            <Package className="h-8 w-8 mb-1 opacity-50" />
            <span className="text-xs font-medium uppercase tracking-wider opacity-70">No Image</span>
          </div>
        )}
        
        {!product.is_active && (
          <div className="absolute top-2 right-2">
            <span className="inline-flex items-center rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800 shadow-sm border border-red-200">
              Unavailable
            </span>
          </div>
        )}
      </div>
      
      <div className="p-4 flex flex-col flex-1">
        {product.category && (
          <span className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">
            {product.category}
          </span>
        )}
        
        <h3 className="font-bold text-gray-900 group-hover:text-primary transition-colors line-clamp-1 mb-1">
          {product.name}
        </h3>
        
        {product.description && (
          <p className="text-sm text-gray-500 line-clamp-2 mb-3 flex-1">
            {product.description}
          </p>
        )}
        
        <div className="mt-auto pt-2">
          <span className="font-bold text-lg text-gray-900">
            {formatCurrency(product.price)}
          </span>
        </div>
      </div>
    </Link>
  )
}
