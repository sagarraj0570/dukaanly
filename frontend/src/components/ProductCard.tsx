import { Link } from 'react-router-dom'
import type { Product } from '@/hooks/useProducts'
import { useCart, useAddToCart, useUpdateCartItem, useRemoveCartItem } from '@/hooks/useCart'
import { formatCurrency } from '@/lib/utils'
import { getProductImage, extractProductUnit } from '@/lib/commerceMedia'
import { ProductImage } from '@/components/ProductImage'
import { Check, Plus, Minus } from 'lucide-react'
import { useState } from 'react'

interface ProductCardProps {
  product: Product
}

export const ProductCard = ({ product }: ProductCardProps) => {
  const [justAdded, setJustAdded] = useState(false)
  const [inlineError, setInlineError] = useState<string | null>(null)
  const { data: cart } = useCart()
  const { mutate: addToCart, isPending: isAdding } = useAddToCart()
  const { mutate: updateItem, isPending: isUpdating } = useUpdateCartItem()
  const { mutate: removeItem, isPending: isRemoving } = useRemoveCartItem()

  const cartItem = cart?.items?.find((item) => item.product_id === product.id)
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
    <div className="group flex flex-col bg-surface border border-border rounded-[14px] p-3 sm:p-4 shadow-none card-hover">
      {/* Clickable Image + Title Link */}
      <Link
        to={`/customer/products/${product.id}`}
        className="flex flex-col flex-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf focus-visible:ring-offset-2 focus-visible:ring-offset-paper rounded-[12px]"
      >
        {/* Product Image Container */}
        <div className="h-36 sm:h-40 w-full rounded-[12px] bg-sand border border-border/60 flex items-center justify-center relative overflow-hidden mb-3">
          <ProductImage
            src={product.thumb_url || resolvedImage}
            alt={product.name}
            category={product.category}
            className="w-full h-full"
            imageClassName={`transition-transform duration-300 group-hover:scale-105 ${
              !product.is_active ? 'opacity-40 grayscale' : ''
            }`}
          />

          {/* Category pill */}
          {product.category && (
            <span className="absolute top-2 left-2 max-w-[calc(100%-16px)] truncate rounded-[6px] bg-surface px-2 py-0.5 text-[10px] font-semibold text-leaf border border-border">
              {product.category}
            </span>
          )}

          {/* Out of stock label */}
          {!product.is_active && (
            <div className="absolute inset-0 bg-surface/75 flex items-center justify-center">
              <span className="px-2.5 py-1 text-xs font-semibold rounded-[8px] bg-brick-tint text-brick-ink border border-brick/30 uppercase tracking-[0.04em]">
                Out of stock
              </span>
            </div>
          )}
        </div>

        {/* Title & Unit */}
        <h3 className="font-semibold text-sm sm:text-[15px] text-ink group-hover:text-leaf transition-colors line-clamp-2 leading-snug">
          {product.name}
        </h3>

        <p className="text-xs text-ink-soft mt-0.5 mb-2 truncate">
          {unitLabel ? `(${unitLabel})` : product.category || 'Standard pack'}
        </p>

        {/* Price in tabular numerals */}
        <div className="mt-auto pt-1">
          <span className="num font-bold text-base sm:text-lg text-ink">
            {formatCurrency(product.price)}
          </span>
        </div>
      </Link>

      {inlineError && (
        <p role="alert" className="text-[11px] text-brick mt-1.5 line-clamp-2 leading-tight">
          {inlineError}
        </p>
      )}

      {/* Out of Stock, Quantity Stepper, or Add Button */}
      {!product.is_active ? (
        <span className="mt-3 w-full min-h-[36px] h-9 rounded-[10px] text-xs font-semibold inline-flex items-center justify-center bg-sand text-ink-soft border border-border cursor-not-allowed opacity-60">
          Out of stock
        </span>
      ) : cartItem ? (
        <div className="mt-3 flex items-center justify-between h-9 min-h-[36px] rounded-[10px] bg-sand border border-border px-1.5">
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault()
              e.stopPropagation()
              if (isUpdating || isRemoving) return
              if (cartItem.quantity <= 1) {
                removeItem(cartItem.id)
              } else {
                updateItem({ item_id: cartItem.id, quantity: cartItem.quantity - 1 })
              }
            }}
            disabled={isUpdating || isRemoving}
            aria-label={`Decrease quantity of ${product.name}`}
            className="h-7 w-7 rounded-[8px] bg-surface hover:bg-border/60 text-ink flex items-center justify-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf cursor-pointer"
          >
            <Minus className="h-3.5 w-3.5" />
          </button>
          <span className="num font-bold text-sm text-ink px-2 select-none">
            {cartItem.quantity}
          </span>
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault()
              e.stopPropagation()
              if (isUpdating || isRemoving) return
              updateItem({ item_id: cartItem.id, quantity: cartItem.quantity + 1 })
            }}
            disabled={isUpdating || isRemoving}
            aria-label={`Increase quantity of ${product.name}`}
            className="h-7 w-7 rounded-[8px] bg-surface hover:bg-border/60 text-ink flex items-center justify-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf cursor-pointer"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={handleQuickAdd}
          disabled={isAdding}
          aria-label={justAdded ? `Added ${product.name} to cart` : `Add ${product.name} to cart`}
          className={`mt-3 w-full min-h-[36px] h-9 rounded-[10px] text-xs sm:text-sm font-semibold inline-flex items-center justify-center gap-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf focus-visible:ring-offset-2 focus-visible:ring-offset-paper active:scale-[0.98] ${
            justAdded
              ? 'bg-sage-tint text-leaf border border-leaf/30'
              : 'bg-leaf hover:bg-leaf-hover text-leaf-ink border border-transparent'
          }`}
        >
          {isAdding ? (
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
      )}
    </div>
  )
}
