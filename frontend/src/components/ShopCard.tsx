import { Link } from 'react-router-dom'
import { MapPin, Store, ArrowUpRight } from 'lucide-react'
import type { Shop } from '@/hooks/useShops'
import { getShopCoverImage } from '@/lib/commerceMedia'
import { useState } from 'react'

interface ShopCardProps {
  shop: Shop
}

export const ShopCard = ({ shop }: ShopCardProps) => {
  const [imgError, setImgError] = useState(false)
  const coverUrl = getShopCoverImage(shop.name, shop.description)

  return (
    <Link
      to={`/customer/shops/${shop.id}`}
      className="group flex flex-col bg-white border border-[#E5E9E4] rounded-2xl overflow-hidden shadow-soft card-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45] focus-visible:ring-offset-2"
    >
      {/* Storefront Photography */}
      <div className="relative h-44 w-full bg-[#EDF5EE] overflow-hidden">
        {!imgError ? (
          <img
            src={coverUrl}
            alt={`${shop.name} storefront`}
            loading="lazy"
            onError={() => setImgError(true)}
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
          />
        ) : (
          <div className="h-full w-full flex flex-col items-center justify-center bg-gradient-to-br from-[#EDF5EE] to-[#A8D5B5]/40 text-[#176B45] p-4 text-center">
            <div className="h-12 w-12 rounded-2xl bg-white/80 flex items-center justify-center shadow-sm mb-2">
              <Store className="h-6 w-6 text-[#176B45]" aria-hidden="true" />
            </div>
            <span className="text-xs font-semibold tracking-wide uppercase text-[#104B32]">
              Neighbourhood Store
            </span>
          </div>
        )}

        {/* Subtle gradient scrim for legibility */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/35 via-transparent to-black/10 pointer-events-none" />

        {/* Operating status pill */}
        <div className="absolute top-3 right-3">
          {shop.is_active ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white/95 backdrop-blur-sm px-2.5 py-1 text-xs font-semibold text-[#176B45] shadow-sm border border-[#A8D5B5]/60">
              <span className="h-1.5 w-1.5 rounded-full bg-[#176B45]" />
              Open
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white/95 backdrop-blur-sm px-2.5 py-1 text-xs font-semibold text-red-700 shadow-sm border border-red-200">
              Closed
            </span>
          )}
        </div>
      </div>

      {/* Shop Content */}
      <div className="p-4 flex flex-col flex-1">
        <div className="flex items-start justify-between gap-2 mb-1.5">
          <h3 className="font-bold text-base text-[#202923] group-hover:text-[#176B45] transition-colors line-clamp-1">
            {shop.name}
          </h3>
          <ArrowUpRight className="h-4 w-4 text-[#69736C] group-hover:text-[#176B45] shrink-0 mt-0.5 transition-colors" aria-hidden="true" />
        </div>

        {shop.description ? (
          <p className="text-xs sm:text-sm text-[#69736C] line-clamp-2 mb-3.5 leading-relaxed">
            {shop.description}
          </p>
        ) : (
          <p className="text-xs sm:text-sm text-[#69736C] line-clamp-2 mb-3.5 leading-relaxed">
            Local neighbourhood store offering daily essentials and groceries.
          </p>
        )}

        <div className="mt-auto pt-3 border-t border-[#E5E9E4] flex items-center gap-1.5 text-xs text-[#69736C]">
          <MapPin className="h-3.5 w-3.5 shrink-0 text-[#176B45]" aria-hidden="true" />
          <span className="line-clamp-1">{shop.address}</span>
        </div>
      </div>
    </Link>
  )
}
