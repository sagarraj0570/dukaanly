import { Link } from 'react-router-dom'
import type { Product } from '@/hooks/useProducts'
import { useAddToCart } from '@/hooks/useCart'
import { formatCurrency } from '@/lib/utils'
import { getProductImage, extractProductUnit } from '@/lib/commerceMedia'
import { Package, Check, Plus } from 'lucide-react'
import { useState } from 'react'

interface ProductCardProps {
  product: Product
}

export const ProductCard = ({ product }: ProductCardProps) => {
  const [imageError, setImageError] = useState(false)
  const [justAdded, setJustAdded] = useState(false)
  const [inlineError, setInlineError] = useState<string | null>(null)
  const { mutate: addToCart, isPending: isAdding } = useAddToCart()

  const resolvedImage = getProductImage(product.name, product.category, product.image_url)
  const unitLabel = extractProductUnit(product.name)

  const handleQuickAdd = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (!product.is_active || isAdding) return

    setInlineError(null)
    addToCart(
      { product_id: product.id, quantity: 1 },
      {
        onSuccess: () => {
          setJustAdded(true)
          setTimeout(() => setJustAdded(false), 1800)
        },
        onError: (err: any) => {
          setInlineError(err.response?.data?.detail || 'Cannot add item')
          setTimeout(() => setInlineError(null), 3500)
        },
      }
    )
  }

  return (
    <div className="group flex flex-col bg-white border border-[#E5E9E4] rounded-2xl p-3 sm:p-4 shadow-soft card-hover">
      {/* Clickable Image + Title Link */}
      <Link
        to={`/customer/products/${product.id}`}
        className="flex flex-col flex-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45] focus-visible:ring-offset-2 rounded-xl"
      >
        {/* Product Image Container */}
        <div className="h-36 sm:h-40 w-full rounded-xl bg-[#FAF9F6] border border-[#E5E9E4]/60 flex items-center justify-center relative overflow-hidden mb-3">
          {!imageError ? (
            <img
              src={resolvedImage}
              alt={product.name}
              loading="lazy"
              className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
              onError={() => setImageError(true)}
            />
          ) : (
            <div className="flex flex-col items-center justify-center text-[#69736C]/50 gap-1.5">
              <Package className="h-9 w-9 text-[#176B45]/40" aria-hidden="true" />
              <span className="text-[11px] font-medium">{product.category || 'Product'}</span>
            </div>
          )}

          {/* Category pill */}
          {product.category && (
            <span className="absolute top-2 left-2 max-w-[calc(100%-16px)] truncate rounded-md bg-white/90 backdrop-blur-sm px-2 py-0.5 text-[10px] font-semibold text-[#176B45] border border-[#E5E9E4]">
              {product.category}
            </span>
          )}

          {/* Unavailable overlay */}
          {!product.is_active && (
            <div className="absolute inset-0 bg-white/75 backdrop-blur-[1px] flex items-center justify-center">
              <span className="badge-error text-xs shadow-sm">Unavailable</span>
            </div>
          )}
        </div>

        {/* Title & Unit */}
        <h3 className="font-semibold text-sm sm:text-[15px] text-[#202923] group-hover:text-[#176B45] transition-colors line-clamp-2 leading-snug">
          {product.name}
        </h3>

        <p className="text-xs text-[#69736C] mt-0.5 mb-2 truncate">
          {unitLabel ? `(${unitLabel})` : product.category || 'Standard pack'}
        </p>

        {/* Price */}
        <div className="mt-auto pt-1">
          <span className="font-bold text-base sm:text-lg text-[#202923]">
            {formatCurrency(product.price)}
          </span>
        </div>
      </Link>

      {inlineError && (
        <p role="alert" className="text-[11px] text-red-600 mt-1.5 line-clamp-2 leading-tight">
          {inlineError}
        </p>
      )}

      {/* Prominent Add Button */}
      <button
        type="button"
        onClick={handleQuickAdd}
        disabled={!product.is_active || isAdding}
        aria-label={
          justAdded
            ? `Added ${product.name} to cart`
            : !product.is_active
            ? `${product.name} is unavailable`
            : `Add ${product.name} to cart`
        }
        className={`mt-3 w-full h-9 rounded-full text-xs sm:text-sm font-semibold inline-flex items-center justify-center gap-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45] ${
          !product.is_active
            ? 'bg-gray-100 text-[#69736C] cursor-not-allowed'
            : justAdded
            ? 'bg-[#EDF5EE] text-[#176B45] border border-[#A8D5B5]'
            : 'bg-[#176B45] hover:bg-[#104B32] text-white shadow-sm'
        }`}
      >
        {!product.is_active ? (
          'Unavailable'
        ) : isAdding ? (
          'Adding...'
        ) : justAdded ? (
          <>
            <Check className="h-3.5 w-3.5" aria-hidden="true" /> Added
          </>
        ) : (
          <>
            <Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add
          </>
        )}
      </button>
    </div>
  )
}
