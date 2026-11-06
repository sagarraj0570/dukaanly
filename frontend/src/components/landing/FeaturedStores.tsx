import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/axios'
import { Link } from 'react-router-dom'
import { Store, MapPin, ArrowRight, Loader2, CheckCircle2 } from 'lucide-react'
import { useState } from 'react'
import { getShopCoverImage } from '@/lib/commerceMedia'
import type { ShopListResponse } from '@/hooks/useShops'

export const FeaturedStores = () => {
  const { data, isLoading, isError } = useQuery<ShopListResponse>({
    queryKey: ['landing-featured-shops'],
    queryFn: async () => {
      const { data } = await api.get('/shops', {
        params: { verified_only: true, size: 6, page: 1 },
      })
      return data
    },
    staleTime: 5 * 60 * 1000,
  })

  // Security & integrity safeguard: Ensure ONLY verified, orderable partner stores are presented
  const shops = (data?.items ?? []).filter(
    (shop) => shop.verification_status === 'verified' && shop.is_orderable
  ).slice(0, 3)

  if (isError || (!isLoading && shops.length === 0)) return null

  return (
    <section className="py-24 px-6 lg:px-12 bg-white">
      <div className="max-w-7xl mx-auto">
        {/* Section Header */}
        <div className="flex items-end justify-between mb-12">
          <div>
            <p className="text-sm font-semibold text-primary-700 tracking-wider uppercase mb-2">
              Verified Partners
            </p>
            <h2 className="text-3xl lg:text-4xl font-bold text-text-primary tracking-tight">
              Featured Stores
            </h2>
            <p className="mt-3 text-text-secondary text-lg max-w-xl">
              Verified local shops ready to serve your neighbourhood with real inventory and honest pricing.
            </p>
          </div>
          <Link
            to="/login"
            className="hidden lg:inline-flex items-center gap-2 text-sm font-semibold text-primary-700 hover:text-primary-900 transition-colors group"
          >
            Browse all stores
            <ArrowRight className="h-4 w-4 group-hover:translate-x-0.5 transition-transform" />
          </Link>
        </div>

        {/* Store Grid */}
        {isLoading ? (
          <div className="flex items-center justify-center h-64">
            <Loader2 className="h-8 w-8 text-primary-700 animate-spin" />
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            {shops.map((shop) => (
              <FeaturedStoreCard key={shop.id} shop={shop} />
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

interface StoreCardProps {
  shop: {
    id: string
    name: string
    description: string | null
    address: string
    is_active: boolean
    is_orderable?: boolean
    verification_status?: string
  }
}

const FeaturedStoreCard = ({ shop }: StoreCardProps) => {
  const [imgError, setImgError] = useState(false)
  const coverUrl = getShopCoverImage(shop.name, shop.description)

  return (
    <Link
      to="/login"
      className="group flex flex-col bg-bg border border-border rounded-3xl overflow-hidden hover:shadow-xl hover:border-primary-200 transition-all duration-300"
    >
      {/* Store Image */}
      <div className="relative h-52 w-full bg-gradient-to-br from-primary-50 to-primary-100/50 overflow-hidden">
        {!imgError ? (
          <img
            src={coverUrl}
            alt={`${shop.name} storefront`}
            loading="lazy"
            onError={() => setImgError(true)}
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
          />
        ) : (
          <div className="h-full w-full flex flex-col items-center justify-center text-primary-700 p-4 text-center">
            <div className="h-16 w-16 rounded-2xl bg-white/80 flex items-center justify-center shadow-sm mb-3 group-hover:scale-110 transition-transform duration-300">
              <Store className="h-8 w-8 text-primary-700" aria-hidden="true" />
            </div>
            <span className="text-xs font-semibold tracking-wider uppercase text-primary-900">
              Neighbourhood Store
            </span>
          </div>
        )}

        {/* Status */}
        <div className="absolute top-4 right-4">
          {shop.is_active ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white/95 backdrop-blur-sm px-3 py-1 text-xs font-semibold text-primary-700 shadow-sm border border-primary-200/60">
              <span className="h-1.5 w-1.5 rounded-full bg-primary-700" />
              Open Now
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white/95 backdrop-blur-sm px-3 py-1 text-xs font-semibold text-text-secondary shadow-sm">
              Closed
            </span>
          )}
        </div>

        {/* Partner badge - only for verified orderable shops */}
        {shop.verification_status === 'verified' && shop.is_orderable && (
          <div className="absolute bottom-4 left-4">
            <span className="inline-flex items-center gap-1 rounded-full bg-primary-700 text-white px-3 py-1 text-xs font-semibold shadow-md">
              <CheckCircle2 className="h-3 w-3 shrink-0" aria-hidden="true" /> Verified Partner
            </span>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-6 flex flex-col flex-1">
        <h3 className="font-bold text-lg text-text-primary group-hover:text-primary-700 transition-colors mb-2">
          {shop.name}
        </h3>

        <p className="text-sm text-text-secondary line-clamp-2 mb-4 leading-relaxed flex-1">
          {shop.description || 'Your trusted local store offering fresh products, daily essentials, and quality service.'}
        </p>

        <div className="flex items-center gap-1.5 text-xs text-text-secondary pt-4 border-t border-border">
          <MapPin className="h-3.5 w-3.5 shrink-0 text-primary-700" aria-hidden="true" />
          <span className="line-clamp-1">{shop.address}</span>
        </div>
      </div>
    </Link>
  )
}
