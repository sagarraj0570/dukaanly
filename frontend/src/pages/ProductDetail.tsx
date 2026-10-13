import { useParams, useNavigate, Link } from 'react-router-dom'
import { useProduct } from '@/hooks/useProducts'
import { useShop } from '@/hooks/useShops'
import { useAddToCart } from '@/hooks/useCart'
import { ErrorState } from '@/components/ErrorState'
import { Button } from '@/components/ui/button'
import { formatCurrency } from '@/lib/utils'
import { getProductImage, extractProductUnit } from '@/lib/commerceMedia'
import {
  ArrowLeft,
  Package,
  Store,
  ShoppingCart,
  Check,
  Tag,
  Plus,
  Minus,
  ShieldCheck,
} from 'lucide-react'
import { useState } from 'react'
import type { AxiosError } from 'axios'

export const ProductDetail = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [imageError, setImageError] = useState(false)
  const [quantity, setQuantity] = useState(1)
  const [addError, setAddError] = useState<string | null>(null)
  const [added, setAdded] = useState(false)

  const { data: product, isLoading, isError, error, refetch } = useProduct(id || '')
  const { data: shop } = useShop(product?.shop_id || '')
  const { mutate: addToCart, isPending: isAdding } = useAddToCart()

  const handleAddToCart = () => {
    setAddError(null)
    setAdded(false)
    if (!product) return

    addToCart(
      { product_id: product.id, quantity },
      {
        onSuccess: () => {
          setAdded(true)
          setTimeout(() => setAdded(false), 3000)
        },
        onError: (err: AxiosError<any>) => {
          setAddError(err.response?.data?.detail || err.message)
        },
      }
    )
  }

  if (isLoading) {
    return (
      <div className="max-w-5xl mx-auto animate-pulse space-y-6">
        <div className="h-8 bg-[#EDF5EE] rounded w-32" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 bg-white border border-[#E5E9E4] rounded-3xl p-6 sm:p-8">
          <div className="h-80 bg-[#EDF5EE] rounded-2xl" />
          <div className="space-y-4 pt-2">
            <div className="h-5 bg-[#EDF5EE] rounded w-1/4" />
            <div className="h-8 bg-[#EDF5EE] rounded w-3/4" />
            <div className="h-8 bg-[#EDF5EE] rounded w-1/3" />
            <div className="h-4 bg-[#EDF5EE] rounded w-full" />
            <div className="h-12 bg-[#EDF5EE] rounded-xl mt-8" />
          </div>
        </div>
      </div>
    )
  }

  if (isError || !product) {
    return (
      <div className="max-w-5xl mx-auto space-y-4">
        <Button
          variant="ghost"
          onClick={() => navigate(-1)}
          className="gap-2 text-[#69736C] -ml-2"
        >
          <ArrowLeft className="h-4 w-4" /> Go Back
        </Button>
        <ErrorState
          title="Product not found"
          message={
            error?.message ||
            'The product you are looking for does not exist or is currently unavailable.'
          }
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  const resolvedImage = getProductImage(product.name, product.category, product.image_url)
  const unitLabel = extractProductUnit(product.name)

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Back navigation */}
      <Button
        variant="ghost"
        onClick={() => navigate(`/customer/shops/${product.shop_id}`)}
        className="gap-2 text-[#69736C] hover:text-[#202923] -ml-2"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to {shop?.name || 'Shop'}
      </Button>

      <div className="bg-white border border-[#E5E9E4] rounded-3xl overflow-hidden shadow-soft">
        <div className="grid grid-cols-1 md:grid-cols-12">
          {/* Product Image Showcase */}
          <div className="md:col-span-6 p-6 sm:p-8 bg-[#FAF9F6] border-b md:border-b-0 md:border-r border-[#E5E9E4] flex items-center justify-center">
            <div className="relative w-full max-w-[380px] aspect-square rounded-2xl overflow-hidden bg-white border border-[#E5E9E4] flex items-center justify-center shadow-soft mx-auto">
              {!imageError ? (
                <img
                  src={resolvedImage}
                  alt={product.name}
                  className="w-full h-full object-cover"
                  onError={() => setImageError(true)}
                />
              ) : (
                <div className="flex flex-col items-center justify-center text-[#69736C]/50 gap-3">
                  <Package className="h-16 w-16 text-[#176B45]/40" aria-hidden="true" />
                  <span className="text-xs font-semibold uppercase tracking-wider">
                    Product Image
                  </span>
                </div>
              )}

              {!product.is_active && (
                <div className="absolute inset-0 bg-white/75 backdrop-blur-[2px] flex items-center justify-center">
                  <span className="badge-error text-sm px-4 py-1.5 shadow-sm">
                    Currently Unavailable
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Product Details & Controls */}
          <div className="md:col-span-6 p-6 sm:p-8 flex flex-col">
            <div className="flex items-center justify-between gap-2 mb-3">
              {product.category ? (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-[#EDF5EE] px-3 py-1 text-xs font-bold text-[#176B45] uppercase tracking-wider">
                  <Tag className="h-3 w-3" aria-hidden="true" />
                  {product.category}
                </span>
              ) : (
                <span />
              )}
              {product.is_active ? (
                <span className="badge-success">Available</span>
              ) : (
                <span className="badge-error">Unavailable</span>
              )}
            </div>

            <h1 className="text-2xl sm:text-3xl font-bold text-[#202923] leading-tight">
              {product.name}
            </h1>

            {unitLabel && (
              <p className="text-sm font-medium text-[#69736C] mt-1">
                Pack size: {unitLabel}
              </p>
            )}

            <div className="mt-4 mb-5 flex items-baseline gap-2">
              <span className="text-3xl font-bold text-[#176B45]">
                {formatCurrency(product.price)}
              </span>
              <span className="text-xs text-[#69736C]">Inclusive of all taxes</span>
            </div>

            {product.description && (
              <p className="text-sm sm:text-base text-[#69736C] leading-relaxed mb-6">
                {product.description}
              </p>
            )}

            {/* Sold by Shop Card */}
            <Link
              to={`/customer/shops/${product.shop_id}`}
              className="flex items-center justify-between gap-3 p-3.5 rounded-2xl bg-[#FAF9F6] border border-[#E5E9E4] hover:border-[#A8D5B5] transition-colors mb-6 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45] focus-visible:ring-offset-2"
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className="h-9 w-9 rounded-xl bg-[#EDF5EE] flex items-center justify-center shrink-0">
                  <Store className="h-4.5 w-4.5 text-[#176B45]" aria-hidden="true" />
                </div>
                <div className="min-w-0">
                  <p className="text-xs text-[#69736C]">Sold by local shop</p>
                  <p className="text-sm font-bold text-[#202923] truncate">
                    {shop?.name || 'Local Partner Store'}
                  </p>
                </div>
              </div>
              <span className="text-xs font-semibold text-[#176B45] shrink-0">
                View Store →
              </span>
            </Link>

            {/* Quantity & Add to Cart */}
            <div className="mt-auto space-y-3 pt-2 border-t border-[#E5E9E4]">
              {addError && (
                <div role="alert" aria-live="assertive" className="p-3.5 bg-red-50 text-red-700 text-xs sm:text-sm border border-red-200 rounded-xl">
                  <p className="font-semibold mb-0.5">Could not add to cart</p>
                  <p>{addError}</p>
                  {addError.toLowerCase().includes('one shop') && (
                    <Link
                      to="/customer/cart"
                      className="underline font-semibold text-red-700 mt-1.5 inline-block"
                    >
                      View current cart →
                    </Link>
                  )}
                </div>
              )}

              <div className="flex items-center gap-3 pt-2">
                {/* Quantity Stepper */}
                <div
                  role="group"
                  aria-label="Quantity selector"
                  className="flex items-center border border-[#E5E9E4] rounded-xl h-12 bg-[#FAF9F6] overflow-hidden shrink-0"
                >
                  <button
                    type="button"
                    onClick={() => setQuantity((q) => Math.max(1, q - 1))}
                    disabled={quantity <= 1 || !product.is_active}
                    aria-label="Decrease quantity"
                    className="w-10 h-full flex items-center justify-center text-[#202923] hover:bg-[#EDF5EE] disabled:opacity-40 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45]"
                  >
                    <Minus className="h-4 w-4" aria-hidden="true" />
                  </button>
                  <span role="status" aria-live="polite" className="w-10 text-center text-sm font-bold text-[#202923]">
                    {quantity}
                  </span>
                  <button
                    type="button"
                    onClick={() => setQuantity((q) => q + 1)}
                    disabled={!product.is_active}
                    aria-label="Increase quantity"
                    className="w-10 h-full flex items-center justify-center text-[#202923] hover:bg-[#EDF5EE] disabled:opacity-40 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45]"
                  >
                    <Plus className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>

                {/* Primary Add to Cart CTA */}
                <Button
                  size="lg"
                  className="flex-1 h-12 rounded-xl bg-[#176B45] hover:bg-[#104B32] text-white text-sm sm:text-base font-semibold gap-2 shadow-sm px-3 sm:px-6"
                  disabled={!product.is_active || isAdding || added}
                  onClick={handleAddToCart}
                >
                  {isAdding ? (
                    'Adding…'
                  ) : added ? (
                    <>
                      <Check className="h-5 w-5" aria-hidden="true" /> Added to Cart
                    </>
                  ) : (
                    <>
                      <ShoppingCart className="h-5 w-5" aria-hidden="true" /> Add to Cart
                    </>
                  )}
                </Button>
              </div>

              <div className="flex items-center gap-1.5 text-xs text-[#69736C] pt-1">
                <ShieldCheck className="h-3.5 w-3.5 text-[#176B45]" />
                <span>Availability is confirmed when you add this item to your cart</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
