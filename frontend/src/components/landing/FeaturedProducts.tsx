import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/axios'
import { Link } from 'react-router-dom'
import { ArrowRight, Package, Loader2 } from 'lucide-react'
import { getProductImage } from '@/lib/commerceMedia'
import { formatCurrency, isTestEntity } from '@/lib/utils'
import { useState } from 'react'
import type { ProductListResponse, Product } from '@/hooks/useProducts'
import type { ShopListResponse } from '@/hooks/useShops'

export const FeaturedProducts = () => {
  const { data, isLoading, isError } = useQuery<Product[]>({
    queryKey: ['landing-featured-products'],
    queryFn: async () => {
      // 1. Discover verified partner shops dynamically
      const shopsRes = await api.get<ShopListResponse>('/shops', {
        params: { verified_only: true, size: 6, page: 1 },
      })
      const verifiedShops = (shopsRes.data?.items ?? []).filter(
        (s) => s.verification_status === 'verified' && s.is_orderable && !isTestEntity(s.name, s.description)
      )

      if (verifiedShops.length === 0) return []

      // 2. Fetch catalog products across verified shops
      const results = await Promise.allSettled(
        verifiedShops.slice(0, 3).map(async (shop) => {
          const { data } = await api.get<ProductListResponse>(
            `/shops/${shop.id}/products`,
            { params: { page: 1, size: 6, active_only: true } }
          )
          return data.items
        })
      )

      const allProducts: Product[] = []
      for (const result of results) {
        if (result.status === 'fulfilled') {
          allProducts.push(...result.value.filter((p) => !isTestEntity(p.name, p.description)))
        }
      }

      // Select diverse products across different categories
      const seen = new Set<string>()
      const diverse: Product[] = []
      for (const p of allProducts) {
        const cat = p.category || 'other'
        if (!seen.has(cat) && diverse.length < 8) {
          diverse.push(p)
          seen.add(cat)
        }
      }

      // Fill remaining spots if needed
      for (const p of allProducts) {
        if (diverse.length >= 8) break
        if (!diverse.some((d) => d.id === p.id)) diverse.push(p)
      }

      return diverse
    },
    staleTime: 5 * 60 * 1000,
  })

  const products = data ?? []

  if (isError || (!isLoading && products.length === 0)) return null

  return (
    <section className="py-24 px-6 lg:px-12 bg-bg">
      <div className="max-w-7xl mx-auto">
        {/* Section Header */}
        <div className="flex items-end justify-between mb-12">
          <div>
            <p className="text-sm font-semibold text-primary-700 tracking-wider uppercase mb-2">
              From Local Shelves
            </p>
            <h2 className="text-3xl lg:text-4xl font-bold text-text-primary tracking-tight">
              Featured Products
            </h2>
            <p className="mt-3 text-text-secondary text-lg max-w-xl">
              Real products, real prices — straight from your neighbourhood stores.
            </p>
          </div>
          <Link
            to="/login"
            className="hidden lg:inline-flex items-center gap-2 text-sm font-semibold text-primary-700 hover:text-primary-900 transition-colors group"
          >
            Explore full catalog
            <ArrowRight className="h-4 w-4 group-hover:translate-x-0.5 transition-transform" />
          </Link>
        </div>

        {/* Product Grid */}
        {isLoading ? (
          <div className="flex items-center justify-center h-64">
            <Loader2 className="h-8 w-8 text-primary-700 animate-spin" />
          </div>
        ) : (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-6">
            {products.map((product) => (
              <FeaturedProductCard key={product.id} product={product} />
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

interface ProductCardProps {
  product: Product
}

const FeaturedProductCard = ({ product }: ProductCardProps) => {
  const [imageError, setImageError] = useState(false)
  const resolvedImage = getProductImage(product.name, product.category, product.image_url)

  return (
    <Link
      to="/login"
      className="group flex flex-col bg-white border border-border rounded-2xl overflow-hidden hover:shadow-lg hover:border-primary-200/60 transition-all duration-300"
    >
      {/* Image */}
      <div className="relative h-44 w-full bg-bg flex items-center justify-center overflow-hidden">
        {!imageError ? (
          <img
            src={resolvedImage}
            alt={product.name}
            loading="lazy"
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
            onError={() => setImageError(true)}
          />
        ) : (
          <div className="flex flex-col items-center justify-center text-text-secondary/50 gap-1.5">
            <Package className="h-9 w-9 text-primary-700/40" aria-hidden="true" />
            <span className="text-[11px] font-medium">{product.category || 'Product'}</span>
          </div>
        )}

        {/* Category tag */}
        {product.category && (
          <span className="absolute top-3 left-3 rounded-md bg-white/90 backdrop-blur-sm px-2 py-0.5 text-[10px] font-semibold text-primary-700 border border-border">
            {product.category}
          </span>
        )}
      </div>

      {/* Content */}
      <div className="p-4 flex flex-col flex-1">
        <h3 className="font-semibold text-sm text-text-primary group-hover:text-primary-700 transition-colors line-clamp-2 leading-snug mb-2">
          {product.name}
        </h3>
        <div className="mt-auto">
          <span className="font-bold text-base text-text-primary">
            {formatCurrency(product.price)}
          </span>
        </div>
      </div>
    </Link>
  )
}
