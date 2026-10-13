import { useParams, useNavigate, Link } from 'react-router-dom'
import { useShop } from '@/hooks/useShops'
import { ErrorState } from '@/components/ErrorState'
import { ProductCatalog } from '@/components/ProductCatalog'
import { Button } from '@/components/ui/button'
import { MapPin, ArrowLeft, CheckCircle2, XCircle, Store, ChevronRight } from 'lucide-react'
import { getShopCoverImage } from '@/lib/commerceMedia'
import { useState } from 'react'

export const ShopDetail = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [coverError, setCoverError] = useState(false)

  const { data: shop, isLoading, isError, error, refetch } = useShop(id || '')

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-5 bg-[#EDF5EE] rounded w-48" />
        <div className="h-64 bg-white border border-[#E5E9E4] rounded-3xl overflow-hidden p-6 space-y-4">
          <div className="h-36 bg-[#EDF5EE] rounded-2xl" />
          <div className="h-7 bg-[#EDF5EE] rounded w-1/3" />
          <div className="h-4 bg-[#EDF5EE] rounded w-1/2" />
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-8">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-64 bg-white border border-[#E5E9E4] rounded-2xl" />
          ))}
        </div>
      </div>
    )
  }

  if (isError || !shop) {
    return (
      <div className="space-y-4">
        <Button
          variant="ghost"
          onClick={() => navigate('/customer')}
          className="gap-2 text-[#69736C] hover:text-[#202923] -ml-2"
        >
          <ArrowLeft className="h-4 w-4" /> Back to Shops
        </Button>
        <ErrorState
          title="Shop not found"
          message={error?.message || 'The shop you are looking for does not exist or is currently unavailable.'}
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  const coverUrl = getShopCoverImage(shop.name, shop.description)

  return (
    <div className="space-y-6">
      {/* Breadcrumb row */}
      <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-xs text-[#69736C]">
        <Link to="/customer" className="hover:text-[#176B45] font-medium transition-colors focus-visible:outline-none focus-visible:underline">
          Shops
        </Link>
        <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="text-[#202923] font-semibold truncate max-w-xs" aria-current="page">Store Catalog</span>
      </nav>

      {/* Storefront Hero Showcase */}
      <div className="bg-white border border-[#E5E9E4] rounded-3xl overflow-hidden shadow-soft">
        {/* Storefront Wide Banner */}
        <div className="relative h-48 sm:h-64 w-full bg-[#EDF5EE] overflow-hidden">
          {!coverError ? (
            <img
              src={coverUrl}
              alt={`${shop.name} storefront`}
              onError={() => setCoverError(true)}
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="w-full h-full bg-gradient-to-r from-[#176B45] to-[#104B32] flex items-center justify-center text-white">
              <Store className="h-16 w-16 opacity-40" aria-hidden="true" />
            </div>
          )}

          <div className="absolute inset-0 bg-gradient-to-t from-black/55 via-black/15 to-transparent pointer-events-none" />

          {/* Operating status pill */}
          <div className="absolute top-4 right-4">
            {shop.is_active ? (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-white/95 backdrop-blur-sm px-3 py-1.5 text-xs font-bold text-[#176B45] shadow-sm border border-[#A8D5B5]">
                <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                Accepting Orders
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-white/95 backdrop-blur-sm px-3 py-1.5 text-xs font-bold text-red-700 shadow-sm border border-red-200">
                <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
                Closed
              </span>
            )}
          </div>
        </div>

        {/* Identity & Address Details */}
        <div className="p-6 sm:p-8">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <span className="inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider text-[#176B45] bg-[#EDF5EE] px-2.5 py-0.5 rounded-full">
                  <Store className="h-3 w-3" aria-hidden="true" />
                  Local Store
                </span>
              </div>
              <h1 className="text-2xl sm:text-3xl font-bold text-[#202923] tracking-tight">
                {shop.name}
              </h1>
              {shop.description && (
                <p className="text-sm text-[#69736C] mt-2 max-w-2xl leading-relaxed">
                  {shop.description}
                </p>
              )}
            </div>
          </div>

          <div className="flex items-start sm:items-center gap-2 text-xs sm:text-sm text-[#69736C] mt-4 pt-4 border-t border-[#E5E9E4] min-w-0">
            <MapPin className="h-4 w-4 shrink-0 text-[#176B45] mt-0.5 sm:mt-0" aria-hidden="true" />
            <span className="break-words line-clamp-2">{shop.address}</span>
          </div>
        </div>
      </div>

      {/* Product Catalog Section */}
      <section aria-label="Product catalog" className="space-y-4 pt-2">
        <ProductCatalog shopId={shop.id} />
      </section>
    </div>
  )
}
