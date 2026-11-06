import React, { useState } from 'react'
import {
  Package,
  ShoppingBag,
  Milk,
  Cookie,
  Coffee,
  Sparkles,
  Home,
  Croissant,
  Pill,
} from 'lucide-react'

export interface ProductImageProps extends Omit<React.ImgHTMLAttributes<HTMLImageElement>, 'src'> {
  src?: string | null
  alt: string
  category?: string | null
  className?: string
  imageClassName?: string
  fallbackClassName?: string
  showCategoryIcon?: boolean
}

/**
 * Returns a category-specific Lucide icon for fallback illustration.
 */
function getCategoryFallbackIcon(category?: string | null) {
  const cat = (category || '').toLowerCase()

  if (cat.includes('grocer') || cat.includes('staple') || cat.includes('spice')) {
    return ShoppingBag
  }
  if (cat.includes('dairy') || cat.includes('milk')) {
    return Milk
  }
  if (cat.includes('snack') || cat.includes('biscuit') || cat.includes('cookie')) {
    return Cookie
  }
  if (cat.includes('beverage') || cat.includes('drink') || cat.includes('tea') || cat.includes('coffee')) {
    return Coffee
  }
  if (cat.includes('personal') || cat.includes('beauty') || cat.includes('care')) {
    return Sparkles
  }
  if (cat.includes('household') || cat.includes('cleaning') || cat.includes('home')) {
    return Home
  }
  if (cat.includes('bakery') || cat.includes('bread') || cat.includes('cake') || cat.includes('pastry')) {
    return Croissant
  }
  if (cat.includes('med') || cat.includes('pharma') || cat.includes('health')) {
    return Pill
  }

  return Package
}

export const ProductImage: React.FC<ProductImageProps> = ({
  src,
  alt,
  category,
  className = '',
  imageClassName = '',
  fallbackClassName = '',
  showCategoryIcon = true,
  loading = 'lazy',
  decoding = 'async',
  ...rest
}) => {
  const [hasError, setHasError] = useState(false)
  const [isLoading, setIsLoading] = useState(Boolean(src && src.trim().length > 0))

  const FallbackIcon = getCategoryFallbackIcon(category)

  // Empty or invalid src triggers fallback directly
  const hasValidSource = Boolean(src && src.trim().length > 0 && !hasError)

  return (
    <div
      className={`relative overflow-hidden flex items-center justify-center bg-[#FBF8F1] dark:bg-surface-alt ${className}`}
      data-testid="product-image-container"
    >
      {/* Loading Skeleton Shimmer */}
      {isLoading && hasValidSource && (
        <div
          className="absolute inset-0 bg-sand animate-pulse"
          aria-hidden="true"
          data-testid="product-image-skeleton"
        />
      )}

      {hasValidSource ? (
        <img
          src={src!}
          alt={alt}
          loading={loading}
          decoding={decoding}
          onLoad={() => setIsLoading(false)}
          onError={() => {
            setIsLoading(false)
            setHasError(true)
          }}
          className={`w-full h-full object-contain transition-opacity duration-300 ${
            isLoading ? 'opacity-0' : 'opacity-100'
          } ${imageClassName}`}
          {...rest}
        />
      ) : (
        <div
          className={`flex flex-col items-center justify-center text-text-muted/70 gap-1.5 p-3 text-center ${fallbackClassName}`}
          data-testid="product-image-fallback"
        >
          {showCategoryIcon && (
            <FallbackIcon
              className="h-9 w-9 text-primary-600/60 dark:text-primary-400/60"
              aria-hidden="true"
              data-testid="category-fallback-icon"
            />
          )}
          <span className="text-[11px] font-medium tracking-tight text-text-muted/80 max-w-[120px] truncate">
            {category || 'Product'}
          </span>
        </div>
      )}
    </div>
  )
}

export default ProductImage
