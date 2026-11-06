import { useParams, useNavigate, Link } from 'react-router-dom'
import { useShop, useShopDeliveryEligibility } from '@/hooks/useShops'
import { useCart } from '@/hooks/useCart'
import { useLocationStore } from '@/store/useLocationStore'
import { ErrorState } from '@/components/ErrorState'
import { ProductCatalog } from '@/components/ProductCatalog'
import { Button } from '@/components/ui/button'
import { StatusStamp } from '@/components/ui/StatusStamp'
import { BillCard } from '@/components/ui/BillCard'
import {
  MapPin,
  ArrowLeft,
  Store,
  ChevronRight,
  Truck,
  PackageSearch,
  Phone,
  Clock,
  Navigation,
  ExternalLink,
  ShoppingBag,
} from 'lucide-react'
import { getShopCoverImage } from '@/lib/commerceMedia'
import { resolveShopType } from '@/lib/shopTypeClassification'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { formatCurrency } from '@/lib/utils'
import { useState } from 'react'

export const ShopDetail = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [coverError, setCoverError] = useState(false)
  const { coords, addressLabel } = useLocationStore()

  const { data: shop, isLoading, isError, error, refetch } = useShop(id || '')
  const { data: eligibility } = useShopDeliveryEligibility(id || '', coords?.latitude, coords?.longitude)
  const { data: cart } = useCart()

  useDocumentTitle(shop?.name ? `${shop.name}` : 'Store Catalog')

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse max-w-6xl mx-auto">
        <div className="h-5 bg-sand rounded w-48" />
        <div className="h-56 bg-surface border border-border rounded-[14px] p-6 space-y-4">
          <div className="h-28 bg-sand rounded-[12px]" />
          <div className="h-7 bg-sand rounded w-1/3" />
          <div className="h-4 bg-sand rounded w-1/2" />
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-8">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-64 bg-surface border border-border rounded-[14px]" />
          ))}
        </div>
      </div>
    )
  }

  if (isError || !shop) {
    return (
      <div className="space-y-4 max-w-6xl mx-auto">
        <Button
          variant="ghost"
          onClick={() => navigate('/customer')}
          className="gap-2 text-ink-soft hover:text-ink -ml-2"
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

  const shopType = resolveShopType(shop.name, shop.description)
  const coverUrl = shopType.coverImageUrl || getShopCoverImage(shop.name, shop.description)
  const isDiscoveredDirectory = !shop.is_orderable || shop.verification_status === 'discovered'

  const cartItemCount = cart?.items ? cart.items.reduce((s, i) => s + i.quantity, 0) : 0
  const cartRows = cart?.items?.map((item) => ({
    label: item.product_name,
    value: formatCurrency(item.item_total),
    sub: `${item.quantity} x ${formatCurrency(item.product_price)}`,
  })) || []

  return (
    <div className="space-y-6 max-w-6xl mx-auto pb-24 lg:pb-16 animate-in fade-in-50 duration-200">
      {/* Breadcrumb row */}
      <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-xs text-ink-soft">
        <Link to="/customer" className="hover:text-leaf font-medium transition-colors focus-visible:outline-none focus-visible:underline">
          Shops
        </Link>
        <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="text-ink font-semibold truncate max-w-xs" aria-current="page">Store Catalog</span>
      </nav>

      {/* Storefront Hero Showcase */}
      <div className="bg-surface border border-border rounded-[14px] overflow-hidden shadow-none">
        {/* Storefront Banner */}
        <div className="relative h-44 sm:h-56 w-full bg-sand overflow-hidden">
          {!coverError ? (
            <img
              src={coverUrl}
              alt={`${shop.name} storefront`}
              onError={() => setCoverError(true)}
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="w-full h-full bg-sand flex items-center justify-center text-ink-soft">
              <Store className="h-16 w-16 opacity-30" aria-hidden="true" />
            </div>
          )}

          <div className="absolute inset-0 bg-black/25 pointer-events-none" />

          {/* Open / Closed StatusStamp (top-right) */}
          <div className="absolute top-4 right-4">
            {isDiscoveredDirectory ? (
              <StatusStamp tone="neutral">
                Directory Listing
              </StatusStamp>
            ) : (
              <StatusStamp tone={shop.is_active ? 'success' : 'danger'}>
                {shop.is_active ? 'Open' : 'Closed'}
              </StatusStamp>
            )}
          </div>
        </div>

        {/* Identity & Address Details */}
        <div className="p-5 sm:p-7">
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-2 flex-wrap">
                <span className="inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider text-leaf bg-sage-tint border border-leaf/20 px-2.5 py-0.5 rounded-[8px]">
                  <Store className="h-3 w-3" aria-hidden="true" />
                  {isDiscoveredDirectory ? 'Directory Listing' : 'Verified Partner'}
                </span>
                <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-ink bg-sand border border-border px-2.5 py-0.5 rounded-[8px]">
                  <span className="select-none" aria-hidden="true">{shopType.icon}</span>
                  <span>{shopType.badgeLabel}</span>
                </span>
                {shop.opening_hours && (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-ink-soft bg-surface border border-border px-2.5 py-0.5 rounded-[8px]">
                    <Clock className="h-3 w-3 text-leaf" aria-hidden="true" />
                    <span>{shop.opening_hours}</span>
                  </span>
                )}
              </div>

              <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink tracking-tight">
                {shop.name}
              </h1>
              {shop.description && (
                <p className="text-xs sm:text-sm text-ink-soft mt-1.5 max-w-2xl leading-relaxed">
                  {shop.description}
                </p>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-4 text-xs sm:text-sm text-ink-soft mt-4 pt-4 border-t border-border">
            <div className="flex items-start sm:items-center gap-2 min-w-0">
              <MapPin className="h-4 w-4 shrink-0 text-leaf mt-0.5 sm:mt-0" aria-hidden="true" />
              <span className="break-words line-clamp-2">{shop.address}</span>
            </div>
            {shop.phone && (
              <div className="flex items-center gap-1.5 font-medium text-ink bg-sand border border-border px-3 py-1 rounded-[8px]">
                <Phone className="h-3.5 w-3.5 text-leaf" aria-hidden="true" />
                <span>{shop.phone}</span>
              </div>
            )}
          </div>

          {/* Directory Notice or Real-time Delivery Eligibility Banner */}
          {isDiscoveredDirectory ? (
            <div className="mt-4 p-4 rounded-[12px] border border-border bg-sand/60 text-ink space-y-3">
              <div className="flex items-start gap-3">
                <div className="h-9 w-9 rounded-[10px] bg-surface border border-border flex items-center justify-center shrink-0 text-ink-soft">
                  <Store className="h-5 w-5" aria-hidden="true" />
                </div>
                <div className="space-y-1">
                  <p className="font-bold text-sm text-ink">
                    Neighbourhood Directory Listing (In-Store Only)
                  </p>
                  <p className="text-xs text-ink-soft leading-relaxed">
                    This business is listed from public records for neighbourhood discovery. Online ordering and doorstep delivery are currently unavailable for this store.
                  </p>
                  {shop.source_attribution && (
                    <p className="text-[11px] text-ink-soft">
                      Source: {shop.source_attribution}
                    </p>
                  )}
                </div>
              </div>
              <div className="pt-3 border-t border-border flex flex-wrap items-center justify-between gap-2 text-xs">
                <span className="text-ink-soft font-medium">Are you the store owner?</span>
                <span className="text-leaf font-semibold bg-surface border border-sage-tint px-3 py-1 rounded-[8px]">
                  Claim this business
                </span>
              </div>
            </div>
          ) : eligibility ? (
            <div
              className={`mt-4 p-3.5 rounded-[12px] border flex items-center justify-between gap-3 text-xs sm:text-sm ${
                eligibility.is_delivery_eligible
                  ? 'bg-sage-tint border-leaf/30 text-leaf'
                  : 'bg-turmeric-tint border-turmeric/30 text-turmeric-ink'
              }`}
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="h-8 w-8 rounded-[8px] bg-surface border border-current/20 flex items-center justify-center shrink-0">
                  <Truck className="h-4 w-4" aria-hidden="true" />
                </div>
                <div>
                  <p className="font-bold text-xs sm:text-sm">
                    {eligibility.is_delivery_eligible
                      ? `Delivers to ${addressLabel || 'your location'}`
                      : 'Store Pickup Only'}
                  </p>
                  <p className="text-[11px] sm:text-xs opacity-90">
                    {eligibility.message}
                  </p>
                </div>
              </div>
              <span className="shrink-0 text-xs font-semibold px-2.5 py-1 rounded-full bg-surface border border-current/20 num">
                {eligibility.distance_meters < 1000
                  ? `${Math.round(eligibility.distance_meters)} m away`
                  : `${(eligibility.distance_meters / 1000).toFixed(1)} km away`}
              </span>
            </div>
          ) : null}
        </div>
      </div>

      {/* Main Content: Product Catalog Grid + Desktop BillCard Sidebar */}
      {isDiscoveredDirectory ? (
        <section aria-label="Store Information" className="space-y-6 pt-2">
          {/* In-Store Welcome & Directions Card */}
          <div className="bg-surface border border-border rounded-[14px] p-6 space-y-4 shadow-none">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-start gap-4">
                <div className="h-12 w-12 rounded-[12px] bg-sand text-leaf flex items-center justify-center shrink-0">
                  <PackageSearch className="h-6 w-6" aria-hidden="true" />
                </div>
                <div>
                  <h2 className="font-display text-xl font-semibold text-ink">In-Store Shopping Only</h2>
                  <p className="text-xs sm:text-sm text-ink-soft mt-1 max-w-xl leading-relaxed">
                    {shop.name} is a verified neighbourhood store. Visit the store directly at the address above to shop in person.
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2.5 flex-wrap">
                <a
                  href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(
                    `${shop.name}, ${shop.address}`
                  )}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-[12px] bg-leaf hover:bg-leaf-hover text-leaf-ink text-xs sm:text-sm font-semibold transition-colors"
                >
                  <Navigation className="h-4 w-4" aria-hidden="true" />
                  <span>Get Directions</span>
                  <ExternalLink className="h-3 w-3 opacity-70" aria-hidden="true" />
                </a>

                {shop.phone && (
                  <a
                    href={`tel:${shop.phone}`}
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-[12px] bg-sand hover:bg-surface border border-border text-xs sm:text-sm font-semibold text-ink transition-colors"
                  >
                    <Phone className="h-3.5 w-3.5 text-leaf" />
                    <span>Call Store</span>
                  </a>
                )}
              </div>
            </div>
          </div>

          {/* Department Guide */}
          <div className="bg-surface border border-border rounded-[14px] p-6 space-y-4 shadow-none">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ShoppingBag className="h-5 w-5 text-leaf" />
                <h3 className="font-display text-base sm:text-lg font-semibold text-ink">
                  In-Store Departments & Aisles
                </h3>
              </div>
              <span className="text-xs font-semibold text-leaf bg-sage-tint border border-leaf/20 px-2.5 py-1 rounded-[8px]">
                Available In-Person
              </span>
            </div>
            <p className="text-xs sm:text-sm text-ink-soft leading-relaxed">
              Explore what {shop.name} typically stocks for your in-person visit:
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 pt-2">
              {shopType.departments.map((dept, i) => (
                <div
                  key={i}
                  className="rounded-[12px] border border-border bg-sand/40 p-4 space-y-2 hover:border-border-strong transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-lg select-none">{dept.icon}</span>
                    <h4 className="text-xs sm:text-sm font-bold text-ink">
                      {dept.title}
                    </h4>
                  </div>
                  <p className="text-xs text-ink-soft line-clamp-2 leading-relaxed">
                    {dept.description}
                  </p>
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {dept.popularItems.map((item, idx) => (
                      <span
                        key={idx}
                        className="inline-block text-[11px] font-medium text-ink-soft bg-surface border border-border px-2 py-0.5 rounded-[6px]"
                      >
                        {item}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      ) : (
        <div className="flex flex-col lg:flex-row gap-8 items-start">
          {/* Main Product Catalog */}
          <div className="flex-1 w-full min-w-0">
            <ProductCatalog shopId={shop.id} />
          </div>

          {/* Desktop Right Sidebar: Live Cart as a BillCard */}
          <aside className="hidden lg:block w-80 shrink-0 sticky top-20 self-start space-y-3">
            <BillCard
              title="Aapka Order"
              note={cartItemCount > 0 ? `${cartItemCount} items from this shop` : 'Your bill is empty'}
              rows={
                cartRows.length > 0
                  ? cartRows
                  : [{ label: 'Items in cart', value: '0' }, { label: 'Estimated delivery', value: '₹0.00' }]
              }
              footer={{
                label: 'Total',
                value: formatCurrency(cart?.total_amount || 0),
              }}
            />
            {cartItemCount > 0 && (
              <Button
                onClick={() => navigate('/customer/checkout')}
                variant="default"
                className="w-full h-11 font-semibold rounded-[12px]"
              >
                Proceed to Checkout ({cartItemCount} items)
              </Button>
            )}
          </aside>

          {/* Mobile Sticky Bottom Bar: View cart · N items · ₹total */}
          {cartItemCount > 0 && (
            <div className="fixed bottom-0 inset-x-0 bg-surface border-t border-border p-3.5 flex items-center justify-between z-30 lg:hidden shadow-[0_-4px_16px_rgba(30,42,36,0.08)]">
              <div className="flex flex-col">
                <span className="text-xs text-ink-soft">
                  <span className="num font-semibold text-ink">{cartItemCount}</span> {cartItemCount === 1 ? 'item' : 'items'} in cart
                </span>
                <span className="num font-bold text-base text-ink">
                  {formatCurrency(cart?.total_amount || 0)}
                </span>
              </div>
              <Button
                onClick={() => navigate('/customer/checkout')}
                variant="default"
                size="sm"
                className="h-10 px-4 font-semibold text-xs rounded-[10px]"
              >
                View cart · <span className="num">{cartItemCount}</span> items · <span className="num">{formatCurrency(cart?.total_amount || 0)}</span>
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default ShopDetail
