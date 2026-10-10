import { Link } from 'react-router-dom'
import { MapPin } from 'lucide-react'
import type { Shop } from '@/hooks/useShops'

interface ShopCardProps {
  shop: Shop
}

export const ShopCard = ({ shop }: ShopCardProps) => {
  return (
    <Link 
      to={`/customer/shops/${shop.id}`}
      className="group flex flex-col bg-white border rounded-lg overflow-hidden hover:shadow-md transition-shadow focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
    >
      <div className="h-32 bg-gray-100 flex items-center justify-center border-b">
        {/* Placeholder for shop image if backend adds it later */}
        <span className="text-gray-400 text-sm font-medium">No Image</span>
      </div>
      <div className="p-4 flex flex-col flex-1">
        <div className="flex justify-between items-start mb-2">
          <h3 className="font-bold text-lg text-gray-900 group-hover:text-primary transition-colors line-clamp-1">
            {shop.name}
          </h3>
          {!shop.is_active && (
            <span className="inline-flex items-center rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800">
              Closed
            </span>
          )}
        </div>
        
        {shop.description && (
          <p className="text-sm text-gray-500 line-clamp-2 mb-3 flex-1">
            {shop.description}
          </p>
        )}
        
        <div className="flex items-start gap-1.5 text-xs text-gray-500 mt-auto pt-2 border-t">
          <MapPin className="h-4 w-4 shrink-0 text-gray-400" />
          <span className="line-clamp-1">{shop.address}</span>
        </div>
      </div>
    </Link>
  )
}
