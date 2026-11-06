import React, { useState } from 'react'
import { ShoppingBag, Check } from 'lucide-react'
import { AUTH_PREVIEW_PRODUCTS, type PreviewProduct } from '@/constants/authPreviewProducts'

interface ProductStackCardProps {
  className?: string
  style?: React.CSSProperties
}

export const ProductStackCard: React.FC<ProductStackCardProps> = ({
  className = '',
  style,
}) => {
  const [imageErrors, setImageErrors] = useState<Record<string, boolean>>({})

  const handleImageError = (id: string) => {
    setImageErrors(prev => ({ ...prev, [id]: true }))
  }

  const totalPrice = AUTH_PREVIEW_PRODUCTS.reduce((sum, item) => sum + item.price, 0)

  return (
    <div
      style={style}
      className={`relative select-none bg-white/20 backdrop-blur-md border border-white/30 rounded-2xl p-3.5 shadow-[0_12px_28px_rgba(15,61,46,0.22)] text-white ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between pb-2 mb-2 border-b border-white/15">
        <div className="flex items-center gap-1.5">
          <div className="h-5 w-5 rounded-md bg-white/20 flex items-center justify-center text-accent-200">
            <ShoppingBag className="h-3 w-3" />
          </div>
          <span className="text-xs font-bold text-white tracking-tight">
            Popular in Your Area
          </span>
        </div>
        <span className="text-[11px] font-semibold text-accent-200 bg-white/15 px-2 py-0.5 rounded-md">
          3 items • ₹{totalPrice}
        </span>
      </div>

      {/* Product List Rows */}
      <div className="space-y-2">
        {AUTH_PREVIEW_PRODUCTS.map((prod: PreviewProduct) => {
          const hasError = imageErrors[prod.id]
          return (
            <div
              key={prod.id}
              className="flex items-center justify-between gap-2.5 bg-black/10 hover:bg-black/15 transition-colors p-1.5 rounded-xl border border-white/10"
            >
              {/* Product Thumbnail */}
              <div className="h-9 w-9 rounded-lg overflow-hidden bg-white/20 shrink-0 flex items-center justify-center">
                {!hasError ? (
                  <img
                    src={prod.imageUrl}
                    alt={prod.name}
                    className="h-full w-full object-cover"
                    loading="lazy"
                    onError={() => handleImageError(prod.id)}
                  />
                ) : (
                  <span className="text-[10px] font-bold text-white/80">
                    {prod.name.charAt(0)}
                  </span>
                )}
              </div>

              {/* Product Name & Weight */}
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-white truncate leading-snug">
                  {prod.name}
                </p>
                <p className="text-[10px] text-white/70 truncate">
                  {prod.weight} • {prod.shopName}
                </p>
              </div>

              {/* Price & Status */}
              <div className="text-right shrink-0">
                <p className="text-xs font-extrabold text-white">₹{prod.price}</p>
                <span className="inline-flex items-center gap-0.5 text-[9px] text-emerald-300 font-medium">
                  <Check className="h-2.5 w-2.5" /> in stock
                </span>
              </div>
            </div>
          )
        })}
      </div>

      {/* Footer Trust Note */}
      <div className="flex items-center justify-between mt-2.5 pt-2 border-t border-white/15 text-[10px] text-white/80 font-medium">
        <span>Verified MRP • No Surge Pricing</span>
        <span className="text-[9px] bg-emerald-950/40 text-emerald-200 px-1.5 py-0.5 rounded font-mono font-medium">
          Instant kirana billing
        </span>
      </div>
    </div>
  )
}

export default ProductStackCard
