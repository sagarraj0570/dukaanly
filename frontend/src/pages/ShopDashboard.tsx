import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/store/useAuthStore'
import { api } from '@/api/axios'
import type { Shop } from '@/hooks/useShops'
import type { Product } from '@/hooks/useProducts'
import type { Order, OrderStatus } from '@/hooks/useOrders'
import { useUpdateDeliveryPreparation } from '@/hooks/useDeliveries'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ErrorState'
import { EmptyState } from '@/components/EmptyState'
import { StatusStamp, orderStatusTone } from '@/components/ui/StatusStamp'
import { formatCurrency } from '@/lib/utils'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { ProductImage } from '@/components/ProductImage'
import {
  getProductImage,
  getShopCoverImage,
  extractProductUnit,
} from '@/lib/commerceMedia'
import {
  Store,
  Package,
  ClipboardList,
  Settings,
  Plus,
  Clock,
  MapPin,
  TrendingUp,
  Boxes,
  RefreshCw,
  X,
  Check,
  Truck,
  Eye,
  EyeOff,
  Upload,
  RotateCcw,
  Minus,
  Pencil,
} from 'lucide-react'

export const ShopDashboard = () => {
  useDocumentTitle('Merchant Operations')
  const { user } = useAuthStore()
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<'orders' | 'products' | 'settings'>('orders')
  const [orderFilter, setOrderFilter] = useState<'new' | 'preparing' | 'ready' | 'completed' | 'all'>('new')

  // Modals
  const [isAddProductOpen, setIsAddProductOpen] = useState(false)
  const [newProductName, setNewProductName] = useState('')
  const [newProductCategory, setNewProductCategory] = useState('Groceries')
  const [newProductPrice, setNewProductPrice] = useState('')
  const [newProductDesc, setNewProductDesc] = useState('')
  const [newProductStock, setNewProductStock] = useState('')
  const [productError, setProductError] = useState<string | null>(null)

  // Delivery Preparation adjustment modal
  const [prepModalDeliveryId, setPrepModalDeliveryId] = useState<string | null>(null)
  const [prepMinutes, setPrepMinutes] = useState(10)
  const [prepDelayReason, setPrepDelayReason] = useState('')
  const updatePrepMutation = useUpdateDeliveryPreparation()

  const modalContainerRef = useRef<HTMLDivElement>(null)
  const initialInputRef = useRef<HTMLInputElement>(null)
  const triggerButtonRef = useRef<HTMLElement | null>(null)

  const openAddProductModal = () => {
    triggerButtonRef.current = document.activeElement as HTMLElement
    setIsAddProductOpen(true)
  }

  const closeAddProductModal = () => {
    setIsAddProductOpen(false)
    triggerButtonRef.current?.focus()
  }

  useEffect(() => {
    if (!isAddProductOpen) return

    const timer = setTimeout(() => {
      initialInputRef.current?.focus()
    }, 50)

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        closeAddProductModal()
      } else if (e.key === 'Tab' && modalContainerRef.current) {
        const focusables = modalContainerRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        )
        if (focusables.length === 0) return
        const first = focusables[0]
        const last = focusables[focusables.length - 1]

        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      clearTimeout(timer)
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [isAddProductOpen])

  // Edit stock inline with optimistic locking
  const [editingStockId, setEditingStockId] = useState<string | null>(null)
  const [editingStockValue, setEditingStockValue] = useState<string>('')
  const [stockVersion, setStockVersion] = useState<number | null>(null)
  const [stockLoading, setStockLoading] = useState(false)
  const [stockFeedback, setStockFeedback] = useState<string | null>(null)

  // 1. Fetch user's shop
  const {
    data: shop,
    isLoading: isShopLoading,
    isError: isShopError,
    error: shopError,
    refetch: refetchShop,
  } = useQuery<Shop | null>({
    queryKey: ['my-shop', user?.id],
    queryFn: async () => {
      try {
        const res = await api.get('/shops/me')
        return res.data
      } catch (err: any) {
        if (err.response?.status === 404) {
          return null
        }
        let page = 1
        while (page <= 10) {
          const res = await api.get('/shops', { params: { page, size: 100, active_only: false } })
          const items: Shop[] = res.data.items || []
          const found = items.find((s) => s.owner_id === user?.id)
          if (found) return found
          if (items.length < 100 || (res.data.total && page * 100 >= res.data.total)) break
          page++
        }
        return null
      }
    },
    enabled: !!user?.id,
  })

  // 2. Fetch shop orders
  const {
    data: ordersData,
    isLoading: isOrdersLoading,
    refetch: refetchOrders,
  } = useQuery<{ items: Order[]; total: number }>({
    queryKey: ['shop-orders', shop?.id],
    queryFn: async () => {
      const res = await api.get(`/shops/${shop!.id}/orders`, { params: { size: 50 } })
      return res.data
    },
    enabled: !!shop?.id,
    refetchInterval: 15000,
  })

  // 3. Fetch shop products
  const {
    data: productsData,
    isLoading: isProductsLoading,
  } = useQuery<{ items: Product[]; total: number }>({
    queryKey: ['shop-products', shop?.id],
    queryFn: async () => {
      const res = await api.get(`/shops/${shop!.id}/products`, {
        params: { size: 100 },
      })
      return res.data
    },
    enabled: !!shop?.id,
  })

  // 4. Mutations
  const toggleShopActive = useMutation({
    mutationFn: async (isActive: boolean) => {
      const res = await api.patch(`/shops/${shop!.id}`, { is_active: isActive })
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-shop'] })
    },
  })

  const updateOrderStatus = useMutation({
    mutationFn: async ({ orderId, status, reason }: { orderId: string; status: OrderStatus; reason?: string }) => {
      const res = await api.patch(`/shops/${shop!.id}/orders/${orderId}/status`, { status, reason })
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['shop-orders', shop?.id] })
    },
  })

  const uploadImageMutation = useMutation({
    mutationFn: async ({ productId, file }: { productId: string; file: File }) => {
      const formData = new FormData()
      formData.append('file', file)
      const res = await api.post(`/shops/${shop!.id}/products/${productId}/image`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['shop-products', shop?.id] })
    },
    onError: (err: any) => {
      alert(err.response?.data?.detail || 'Failed to upload product image')
    },
  })

  const deleteImageMutation = useMutation({
    mutationFn: async (productId: string) => {
      const res = await api.delete(`/shops/${shop!.id}/products/${productId}/image`)
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['shop-products', shop?.id] })
    },
    onError: (err: any) => {
      alert(err.response?.data?.detail || 'Failed to revert to master image')
    },
  })

  const createProductMutation = useMutation({
    mutationFn: async (payload: {
      name: string
      category: string
      price: number
      description: string
      stock: number
    }) => {
      const res = await api.post(`/shops/${shop!.id}/products`, {
        name: payload.name,
        category: payload.category,
        price: payload.price,
        description: payload.description,
        is_active: true,
      })
      const product = res.data

      if (product.id) {
        try {
          const invRes = await api.get(`/products/${product.id}/inventory`)
          const currentVersion = invRes.data.version
          await api.patch(`/products/${product.id}/inventory`, {
            stock: payload.stock,
            expected_version: currentVersion,
          })
        } catch {
          // Handled safely
        }
      }
      return product
    },
    onSuccess: () => {
      setIsAddProductOpen(false)
      setNewProductName('')
      setNewProductPrice('')
      setNewProductDesc('')
      setProductError(null)
      queryClient.invalidateQueries({ queryKey: ['shop-products', shop?.id] })
    },
    onError: (err: any) => {
      setProductError(err.response?.data?.detail || 'Failed to create product.')
    },
  })

  const handleStartEditStock = async (productId: string) => {
    setEditingStockId(productId)
    setStockLoading(true)
    setStockFeedback(null)
    try {
      const res = await api.get(`/products/${productId}/inventory`)
      setEditingStockValue(String(res.data.stock))
      setStockVersion(res.data.version)
    } catch {
      setEditingStockValue('')
      setStockVersion(null)
      setStockFeedback('Unable to load current inventory.')
    } finally {
      setStockLoading(false)
    }
  }

  const handleSaveStock = async (productId: string) => {
    const val = parseInt(editingStockValue, 10)
    if (isNaN(val) || val < 0 || stockVersion === null) return
    setStockLoading(true)
    setStockFeedback(null)
    try {
      await api.patch(`/products/${productId}/inventory`, {
        stock: val,
        expected_version: stockVersion,
      })
      setEditingStockId(null)
      queryClient.invalidateQueries({ queryKey: ['shop-products', shop?.id] })
    } catch (err: any) {
      setStockFeedback(err.response?.data?.detail || 'Conflict: stock updated by another user')
    } finally {
      setStockLoading(false)
    }
  }

  const toggleProductActive = useMutation({
    mutationFn: async ({ productId, isActive }: { productId: string; isActive: boolean }) => {
      const res = await api.patch(`/products/${productId}`, { is_active: isActive })
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['shop-products', shop?.id] })
    },
  })

  if (isShopLoading) {
    return (
      <div className="space-y-6 animate-pulse max-w-6xl mx-auto px-4 py-8">
        <div className="h-32 bg-sand rounded-[14px]" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="h-20 bg-surface border border-border rounded-[14px]" />
          <div className="h-20 bg-surface border border-border rounded-[14px]" />
          <div className="h-20 bg-surface border border-border rounded-[14px]" />
        </div>
        <div className="h-80 bg-surface border border-border rounded-[14px]" />
      </div>
    )
  }

  if (isShopError) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <ErrorState
          title="Could not load shop"
          message={shopError?.message || 'Failed to load your shop profile.'}
          onRetry={() => refetchShop()}
        />
      </div>
    )
  }

  if (!shop) {
    return (
      <div className="max-w-2xl mx-auto py-12 px-4">
        <EmptyState
          title="No Shop Registered"
          message="You are registered as a Shop Owner, but no shop profile is linked to your account yet."
          illustrationType="store"
          icon={<Store className="h-10 w-10 text-ink-soft" />}
        />
      </div>
    )
  }

  const orders = ordersData?.items || []
  const products = productsData?.items || []

  const activeOrdersCount = orders.filter((o) =>
    ['confirmed', 'preparing', 'ready_for_pickup'].includes(o.status)
  ).length

  const filteredOrders = orders.filter((o) => {
    if (orderFilter === 'new') {
      return o.status === 'confirmed' || o.status === 'pending'
    }
    if (orderFilter === 'preparing') {
      return o.status === 'preparing'
    }
    if (orderFilter === 'ready') {
      return o.status === 'ready_for_pickup' || o.status === 'out_for_delivery'
    }
    if (orderFilter === 'completed') {
      return o.status === 'delivered' || o.status === 'cancelled'
    }
    return true
  })

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 sm:py-8 space-y-6">
      {/* Top Header: Shop name & Large Open/Closed switch */}
      <div className="rounded-[14px] border border-border bg-surface p-5 sm:p-6 shadow-none">
        <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
          <div className="flex items-start sm:items-center gap-4 min-w-0">
            <div className="h-16 w-16 sm:h-18 sm:w-18 rounded-[12px] overflow-hidden bg-sand border border-border shrink-0 flex items-center justify-center">
              <img
                src={getShopCoverImage(shop.name, shop.description)}
                alt={shop.name}
                className="h-full w-full object-cover"
                onError={(e) => {
                  e.currentTarget.style.display = 'none'
                }}
              />
            </div>

            <div className="min-w-0">
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <StatusStamp tone={shop.is_active ? 'success' : 'danger'}>
                  {shop.is_active ? 'Open for orders' : 'Store closed'}
                </StatusStamp>
              </div>

              <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink tracking-tight truncate">
                {shop.name}
              </h1>
              <div className="flex items-center gap-1.5 text-xs text-ink-soft mt-1 truncate">
                <MapPin className="h-3.5 w-3.5 text-ink-soft shrink-0" />
                <span className="truncate">{shop.address}</span>
              </div>
            </div>
          </div>

          {/* Large Open/Closed Switch with visible label */}
          <div className="flex items-center gap-3 shrink-0">
            <span className="text-sm font-semibold text-ink select-none">
              {shop.is_active ? 'Open for orders' : 'Closed'}
            </span>
            <button
              type="button"
              role="switch"
              aria-checked={shop.is_active}
              aria-label="Toggle store open status"
              onClick={() => toggleShopActive.mutate(!shop.is_active)}
              disabled={toggleShopActive.isPending}
              className={`relative inline-flex h-7 w-12 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf focus-visible:ring-offset-2 ${
                shop.is_active ? 'bg-leaf' : 'bg-border-strong'
              } ${toggleShopActive.isPending ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <span
                aria-hidden="true"
                className={`pointer-events-none inline-block h-6 w-6 transform rounded-full bg-surface shadow-xs ring-0 transition duration-200 ease-in-out ${
                  shop.is_active ? 'translate-x-5' : 'translate-x-0'
                }`}
              />
            </button>
          </div>
        </div>

        {/* 3 Plain Stat Cells separated by hairline dividers on surface background */}
        <div className="grid grid-cols-3 divide-x divide-border bg-surface rounded-xl border border-border mt-5">
          <div className="p-3.5 sm:p-4 text-center">
            <div className="flex items-center justify-center gap-1 text-[10px] uppercase tracking-wider font-semibold text-ink-soft mb-1">
              <Boxes className="h-3.5 w-3.5" />
              Products
            </div>
            <p className="num font-display text-xl sm:text-2xl font-semibold text-ink">{products.length}</p>
          </div>
          <div className="p-3.5 sm:p-4 text-center">
            <div className="flex items-center justify-center gap-1 text-[10px] uppercase tracking-wider font-semibold text-ink-soft mb-1">
              <TrendingUp className="h-3.5 w-3.5" />
              Active Orders
            </div>
            <p className="num font-display text-xl sm:text-2xl font-semibold text-leaf">{activeOrdersCount}</p>
          </div>
          <div className="p-3.5 sm:p-4 text-center">
            <div className="flex items-center justify-center gap-1 text-[10px] uppercase tracking-wider font-semibold text-ink-soft mb-1">
              <Clock className="h-3.5 w-3.5" />
              Total Orders
            </div>
            <p className="num font-display text-xl sm:text-2xl font-semibold text-ink">{orders.length}</p>
          </div>
        </div>
      </div>

      {/* Primary Navigation Tabs */}
      <div className="flex flex-col gap-2 border-b border-border sm:flex-row sm:items-center sm:justify-between">
        <div
          role="tablist"
          aria-label="Shop management views"
          className="flex items-center gap-2 overflow-x-auto overflow-y-hidden whitespace-nowrap scrollbar-none -mx-1 px-1"
        >
          <button
            type="button"
            role="tab"
            id="tab-orders"
            aria-selected={activeTab === 'orders'}
            aria-controls="panel-orders"
            onClick={() => setActiveTab('orders')}
            className={`flex shrink-0 items-center gap-2 px-3 sm:px-4 py-3 text-xs sm:text-sm font-semibold border-b-2 transition-colors -mb-px cursor-pointer ${
              activeTab === 'orders'
                ? 'border-leaf text-ink font-semibold'
                : 'border-transparent text-ink-soft hover:text-ink font-medium'
            }`}
          >
            <ClipboardList className="h-4 w-4" aria-hidden="true" />
            Incoming Orders
            {activeOrdersCount > 0 && (
              <span className="h-5 min-w-[20px] px-1.5 rounded-full bg-sage-tint text-leaf border border-leaf/30 text-[11px] flex items-center justify-center font-bold num">
                {activeOrdersCount}
              </span>
            )}
          </button>
          <button
            type="button"
            role="tab"
            id="tab-products"
            aria-selected={activeTab === 'products'}
            aria-controls="panel-products"
            onClick={() => setActiveTab('products')}
            className={`flex shrink-0 items-center gap-2 px-3 sm:px-4 py-3 text-xs sm:text-sm font-semibold border-b-2 transition-colors -mb-px cursor-pointer ${
              activeTab === 'products'
                ? 'border-leaf text-ink font-semibold'
                : 'border-transparent text-ink-soft hover:text-ink font-medium'
            }`}
          >
            <Package className="h-4 w-4" aria-hidden="true" />
            Catalog & Inventory ({products.length})
          </button>
          <button
            type="button"
            role="tab"
            id="tab-settings"
            aria-selected={activeTab === 'settings'}
            aria-controls="panel-settings"
            onClick={() => setActiveTab('settings')}
            className={`flex shrink-0 items-center gap-2 px-3 sm:px-4 py-3 text-xs sm:text-sm font-semibold border-b-2 transition-colors -mb-px cursor-pointer ${
              activeTab === 'settings'
                ? 'border-leaf text-ink font-semibold'
                : 'border-transparent text-ink-soft hover:text-ink font-medium'
            }`}
          >
            <Settings className="h-4 w-4" aria-hidden="true" />
            Shop Information
          </button>
        </div>

        <div className="pb-2 self-end sm:self-auto">
          {activeTab === 'orders' && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetchOrders()}
              className="gap-1.5 text-xs rounded-xl border-border bg-surface text-ink hover:bg-sand min-h-[36px]"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </Button>
          )}
          {activeTab === 'products' && (
            <Button
              size="sm"
              onClick={openAddProductModal}
              className="gap-1.5 text-xs font-semibold bg-leaf hover:bg-leaf/90 text-white rounded-xl min-h-[36px]"
            >
              <Plus className="h-3.5 w-3.5" />
              Add Product
            </Button>
          )}
        </div>
      </div>

      {/* TAB 1: ORDERS */}
      {activeTab === 'orders' && (
        <div id="panel-orders" role="tabpanel" aria-labelledby="tab-orders" className="space-y-4">
          <h2 className="sr-only">Incoming Orders Management</h2>

          {/* Underline Order Stage Filter Tabs with count badges */}
          <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none border-b border-border">
            {[
              {
                id: 'new',
                label: 'New',
                count: orders.filter((o) => o.status === 'confirmed' || o.status === 'pending').length,
              },
              {
                id: 'preparing',
                label: 'Preparing',
                count: orders.filter((o) => o.status === 'preparing').length,
              },
              {
                id: 'ready',
                label: 'Ready',
                count: orders.filter((o) => o.status === 'ready_for_pickup' || o.status === 'out_for_delivery').length,
              },
              {
                id: 'completed',
                label: 'Done',
                count: orders.filter((o) => o.status === 'delivered' || o.status === 'cancelled').length,
              },
              {
                id: 'all',
                label: 'All',
                count: orders.length,
              },
            ].map((filter) => (
              <button
                key={filter.id}
                type="button"
                onClick={() => setOrderFilter(filter.id as any)}
                className={`flex items-center gap-1.5 px-3 py-2 text-xs font-semibold border-b-2 transition-colors whitespace-nowrap cursor-pointer -mb-px ${
                  orderFilter === filter.id
                    ? 'border-leaf text-ink font-bold'
                    : 'border-transparent text-ink-soft hover:text-ink'
                }`}
              >
                <span>{filter.label}</span>
                <span
                  className={`px-1.5 py-0.2 rounded-full text-[10px] font-semibold num ${
                    orderFilter === filter.id
                      ? 'bg-sage-tint text-leaf'
                      : 'bg-sand text-ink-soft'
                  }`}
                >
                  {filter.count}
                </span>
              </button>
            ))}
          </div>

          {isOrdersLoading ? (
            <div className="space-y-3 animate-pulse">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-32 bg-surface border border-border rounded-[14px]" />
              ))}
            </div>
          ) : filteredOrders.length === 0 ? (
            <div className="rounded-[14px] border border-dashed border-border bg-surface p-10 text-center space-y-2">
              <div className="h-12 w-12 rounded-full bg-sand flex items-center justify-center mx-auto text-ink-soft mb-2">
                <ClipboardList className="h-6 w-6" aria-hidden="true" />
              </div>
              <p className="font-display font-semibold text-base text-ink">
                Abhi koi naya order nahi
              </p>
              <p className="text-xs text-ink-soft max-w-sm mx-auto leading-relaxed">
                Naye orders aane par yahan dikhenge aur aap unhe accept ya prepare kar sakte hain.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {filteredOrders.map((order) => (
                <div
                  key={order.id}
                  className="rounded-[14px] border border-border bg-surface p-4 sm:p-5 shadow-none space-y-4"
                >
                  {/* Order Top Bar: Order number, StatusStamp, Time, Total */}
                  <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-2 border-b border-border pb-3.5">
                    <div className="flex items-center gap-3 flex-wrap">
                      <span className="font-mono text-xs font-bold text-ink-soft">
                        #{order.id.split('-')[0].toUpperCase()}
                      </span>
                      <StatusStamp tone={orderStatusTone(order.status)}>
                        {order.status.replace(/_/g, ' ')}
                      </StatusStamp>
                      <span className="text-xs text-ink-soft">
                        {new Date(order.created_at).toLocaleTimeString('en-IN', {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </span>
                    </div>

                    <div className="sm:text-right font-bold text-base text-ink num">
                      {formatCurrency(order.total_amount)}
                    </div>
                  </div>

                  {/* Order Items with 48px Thumbnails */}
                  <div className="space-y-2">
                    {order.items.map((item) => (
                      <div
                        key={item.id}
                        className="flex items-center justify-between text-xs sm:text-sm text-ink gap-3"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="h-10 w-10 rounded-lg overflow-hidden bg-sand border border-border shrink-0">
                            <ProductImage
                              src={getProductImage(item.product_name)}
                              alt={item.product_name}
                              className="w-full h-full"
                              imageClassName="object-cover"
                            />
                          </div>
                          <span className="truncate">
                            <span className="num font-semibold">{item.quantity}×</span> {item.product_name}
                          </span>
                        </div>
                        <span className="num text-ink-soft font-semibold shrink-0">
                          {formatCurrency(item.line_total)}
                        </span>
                      </div>
                    ))}
                  </div>

                  {/* Rider Status and Large Primary Action Buttons */}
                  <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 pt-3 border-t border-border">
                    <div className="flex items-center gap-1.5 text-xs text-ink-soft">
                      <Truck className="h-3.5 w-3.5 text-ink-soft" />
                      <span>
                        {order.delivery
                          ? `Rider: ${order.delivery.status.replace(/_/g, ' ')}`
                          : 'Rider unassigned'}
                      </span>
                    </div>

                    {/* Full-width 48px primary action buttons on mobile, inline on tablet/desktop */}
                    <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 pt-1">
                      {order.status === 'pending' && (
                        <>
                          <Button
                            size="lg"
                            className="min-h-[48px] h-12 px-5 rounded-xl bg-leaf hover:bg-leaf/90 text-white text-sm font-semibold w-full sm:w-auto cursor-pointer"
                            onClick={() =>
                              updateOrderStatus.mutate({
                                orderId: order.id,
                                status: 'confirmed',
                              })
                            }
                            disabled={updateOrderStatus.isPending}
                          >
                            Accept Order
                          </Button>
                          <Button
                            variant="outline"
                            size="lg"
                            className="min-h-[48px] h-12 px-4 rounded-xl text-sm text-brick-ink border-border hover:bg-brick-tint/20 font-semibold w-full sm:w-auto cursor-pointer"
                            onClick={() => {
                              const reason = window.prompt('Reason for rejecting this order:')
                              if (!reason || !reason.trim()) return
                              api.post(`/shops/${shop!.id}/orders/${order.id}/reject`, { reason: reason.trim() })
                                .then(() => queryClient.invalidateQueries({ queryKey: ['shop-orders', shop?.id] }))
                                .catch((err) => alert(err.response?.data?.detail?.message || err.response?.data?.detail || 'Rejection failed'))
                            }}
                            disabled={updateOrderStatus.isPending}
                          >
                            Reject
                          </Button>
                        </>
                      )}

                      {order.status === 'confirmed' && (
                        <Button
                          size="lg"
                          className="min-h-[48px] h-12 px-6 rounded-xl bg-leaf hover:bg-leaf/90 text-white text-sm font-semibold w-full sm:w-auto cursor-pointer"
                          onClick={() =>
                            updateOrderStatus.mutate({
                              orderId: order.id,
                              status: 'preparing',
                            })
                          }
                          disabled={updateOrderStatus.isPending}
                        >
                          Start Preparing
                        </Button>
                      )}

                      {order.status === 'preparing' && (
                        <>
                          {order.delivery?.id && (
                            <Button
                              variant="outline"
                              size="lg"
                              className="min-h-[48px] h-12 px-4 rounded-xl border-border bg-surface text-ink hover:bg-sand text-xs font-semibold gap-1.5 w-full sm:w-auto cursor-pointer"
                              onClick={() => {
                                setPrepModalDeliveryId(order.delivery!.id)
                                setPrepMinutes(10)
                                setPrepDelayReason('')
                              }}
                            >
                              <Clock className="h-3.5 w-3.5 text-ink-soft" />
                              Adjust Prep Time
                            </Button>
                          )}
                          <Button
                            size="lg"
                            className="min-h-[48px] h-12 px-6 rounded-xl bg-leaf hover:bg-leaf/90 text-white text-sm font-semibold w-full sm:w-auto cursor-pointer"
                            onClick={() =>
                              updateOrderStatus.mutate({
                                orderId: order.id,
                                status: 'ready_for_pickup',
                              })
                            }
                            disabled={updateOrderStatus.isPending}
                          >
                            Mark Ready
                          </Button>
                        </>
                      )}

                      {['confirmed', 'preparing'].includes(order.status) && (
                        <Button
                          variant="ghost"
                          size="lg"
                          className="min-h-[44px] px-3 rounded-xl text-xs text-brick-ink hover:bg-brick-tint/20 cursor-pointer"
                          onClick={() =>
                            updateOrderStatus.mutate({
                              orderId: order.id,
                              status: 'cancelled',
                              reason: window.prompt('Reason for cancellation:') || 'Cancelled by merchant',
                            })
                          }
                          disabled={updateOrderStatus.isPending}
                        >
                          Cancel
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 2: PRODUCTS & INVENTORY */}
      {activeTab === 'products' && (
        <div id="panel-products" role="tabpanel" aria-labelledby="tab-products" className="space-y-4">
          <h2 className="sr-only">Catalog & Inventory Management</h2>

          {isProductsLoading ? (
            <div className="space-y-3 animate-pulse">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-20 bg-surface border border-border rounded-[14px]" />
              ))}
            </div>
          ) : products.length === 0 ? (
            <EmptyState
              title="No products yet"
              message="Add products to your shop catalog so customers can order."
              icon={<Package className="h-8 w-8 text-ink-soft" />}
              action={
                <Button
                  size="sm"
                  onClick={openAddProductModal}
                  className="bg-leaf hover:bg-leaf/90 text-white rounded-xl min-h-[44px] px-5"
                >
                  <Plus className="h-4 w-4 mr-1.5" />
                  Add First Product
                </Button>
              }
            />
          ) : (
            <div className="space-y-4">
              {/* Desktop Table View (hidden on mobile) */}
              <div className="hidden md:block rounded-[14px] border border-border bg-surface overflow-hidden shadow-none">
                <table className="w-full text-left text-sm">
                  <thead className="bg-sand border-b border-border text-xs text-ink-soft uppercase tracking-wider">
                    <tr>
                      <th className="px-5 py-3 font-semibold">Product</th>
                      <th className="px-4 py-3 font-semibold">Category</th>
                      <th className="px-4 py-3 font-semibold">Price</th>
                      <th className="px-4 py-3 font-semibold">Status</th>
                      <th className="px-5 py-3 font-semibold text-right">Inventory Stock</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {products.map((product) => {
                      const thumbUrl = getProductImage(product.name, product.category, product.image_url)
                      const unitLabel = extractProductUnit(product.name)

                      return (
                        <tr key={product.id} className="hover:bg-sand/40 transition-colors">
                          {/* Product Thumbnail (48px) + Name */}
                          <td className="px-5 py-3.5">
                            <div className="flex items-center gap-3 min-w-0">
                              <div className="relative group/thumb h-12 w-12 rounded-xl overflow-hidden bg-sand border border-border shrink-0 flex items-center justify-center">
                                <ProductImage
                                  src={product.thumb_url || thumbUrl}
                                  alt={product.name}
                                  category={product.category}
                                  className="w-full h-full"
                                />
                                <label
                                  className="absolute inset-0 bg-ink/70 text-white opacity-0 group-hover/thumb:opacity-100 flex flex-col items-center justify-center cursor-pointer transition-opacity text-[9px] font-semibold"
                                  title="Upload custom image"
                                >
                                  <Upload className="h-3.5 w-3.5 mb-0.5" />
                                  <span>Upload</span>
                                  <input
                                    type="file"
                                    accept="image/jpeg,image/png,image/webp"
                                    className="hidden"
                                    onChange={(e) => {
                                      const f = e.target.files?.[0]
                                      if (f) uploadImageMutation.mutate({ productId: product.id, file: f })
                                    }}
                                  />
                                </label>
                              </div>

                              <div className="min-w-0">
                                <div className="flex items-center gap-2">
                                  <p className="font-semibold text-ink truncate max-w-xs">{product.name}</p>
                                  {product.custom_image_url && (
                                    <button
                                      type="button"
                                      onClick={() => deleteImageMutation.mutate(product.id)}
                                      title="Revert to master catalog image"
                                      className="text-[10px] text-terracotta-600 hover:underline inline-flex items-center gap-0.5 shrink-0 cursor-pointer"
                                    >
                                      <RotateCcw className="h-2.5 w-2.5" />
                                    </button>
                                  )}
                                </div>
                                {unitLabel && <p className="text-xs text-ink-soft">{unitLabel}</p>}
                              </div>
                            </div>
                          </td>

                          {/* Category */}
                          <td className="px-4 py-3.5 text-xs text-ink-soft">
                            <span className="px-2 py-0.5 rounded bg-sand border border-border font-medium">
                              {product.category || 'General'}
                            </span>
                          </td>

                          {/* Price */}
                          <td className="px-4 py-3.5 font-bold text-ink num">
                            {formatCurrency(product.price)}
                          </td>

                          {/* Active Toggle */}
                          <td className="px-4 py-3.5">
                            <button
                              type="button"
                              aria-label={product.is_active ? `Deactivate ${product.name}` : `Activate ${product.name}`}
                              onClick={() =>
                                toggleProductActive.mutate({
                                  productId: product.id,
                                  isActive: !product.is_active,
                                })
                              }
                              className={`text-xs font-semibold px-2.5 py-1 rounded-full border transition-colors inline-flex items-center gap-1.5 cursor-pointer ${
                                product.is_active
                                  ? 'bg-sage-tint text-leaf border-leaf/30'
                                  : 'bg-sand text-ink-soft border-border'
                              }`}
                            >
                              {product.is_active ? (
                                <>
                                  <Eye className="h-3 w-3" aria-hidden="true" /> Active
                                </>
                              ) : (
                                <>
                                  <EyeOff className="h-3 w-3" aria-hidden="true" /> Hidden
                                </>
                              )}
                            </button>
                          </td>

                          {/* Inline Stock Stepper */}
                          <td className="px-5 py-3.5 text-right">
                            {editingStockId === product.id ? (
                              <div className="inline-flex flex-col items-end gap-1">
                                <div className="inline-flex items-center gap-1">
                                  <Button
                                    size="icon"
                                    variant="outline"
                                    aria-label="Decrease stock"
                                    disabled={stockLoading || stockVersion === null}
                                    className="h-8 w-8 rounded-lg border-border bg-surface text-ink hover:bg-sand"
                                    onClick={() => {
                                      const cur = parseInt(editingStockValue, 10) || 0
                                      setEditingStockValue(String(Math.max(0, cur - 1)))
                                    }}
                                  >
                                    <Minus className="h-3.5 w-3.5" />
                                  </Button>
                                  <input
                                    type="number"
                                    min="0"
                                    aria-label={`Update inventory stock for ${product.name}`}
                                    disabled={stockLoading || stockVersion === null}
                                    className="w-16 h-8 px-2 text-xs border border-border rounded-lg bg-surface text-center font-bold text-ink num focus:ring-1 focus:ring-leaf"
                                    value={editingStockValue}
                                    onChange={(e) => setEditingStockValue(e.target.value)}
                                    autoFocus
                                  />
                                  <Button
                                    size="icon"
                                    variant="outline"
                                    aria-label="Increase stock"
                                    disabled={stockLoading || stockVersion === null}
                                    className="h-8 w-8 rounded-lg border-border bg-surface text-ink hover:bg-sand"
                                    onClick={() => {
                                      const cur = parseInt(editingStockValue, 10) || 0
                                      setEditingStockValue(String(cur + 1))
                                    }}
                                  >
                                    <Plus className="h-3.5 w-3.5" />
                                  </Button>
                                  <Button
                                    size="icon"
                                    aria-label={`Save stock for ${product.name}`}
                                    className="h-8 w-8 bg-leaf text-white rounded-lg hover:bg-leaf/90 ml-1"
                                    disabled={stockLoading || stockVersion === null}
                                    onClick={() => handleSaveStock(product.id)}
                                  >
                                    <Check className="h-3.5 w-3.5" aria-hidden="true" />
                                  </Button>
                                  <Button
                                    size="icon"
                                    variant="ghost"
                                    aria-label="Cancel editing stock"
                                    className="h-8 w-8 text-ink-soft rounded-lg"
                                    onClick={() => {
                                      setEditingStockId(null)
                                      setStockFeedback(null)
                                    }}
                                  >
                                    <X className="h-3.5 w-3.5" aria-hidden="true" />
                                  </Button>
                                </div>
                                {stockFeedback && (
                                  <p role="alert" className="text-[10px] text-brick-ink max-w-[180px] truncate">
                                    {stockFeedback}
                                  </p>
                                )}
                              </div>
                            ) : (
                              <button
                                type="button"
                                aria-label={`Manage stock for ${product.name}`}
                                onClick={() => handleStartEditStock(product.id)}
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-sand hover:bg-sand/80 text-xs font-semibold text-ink transition cursor-pointer"
                              >
                                <Pencil className="h-3 w-3 text-ink-soft" />
                                <span>Adjust Stock</span>
                              </button>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              {/* Mobile Stacked Rows (visible on small screens) */}
              <div className="md:hidden space-y-3">
                {products.map((product) => {
                  const thumbUrl = getProductImage(product.name, product.category, product.image_url)
                  const unitLabel = extractProductUnit(product.name)

                  return (
                    <div
                      key={product.id}
                      className="rounded-[14px] border border-border bg-surface p-4 space-y-3 shadow-none"
                    >
                      <div className="flex items-start gap-3">
                        {/* 48px Product Thumbnail */}
                        <div className="relative group/thumb h-12 w-12 rounded-xl overflow-hidden bg-sand border border-border shrink-0 flex items-center justify-center">
                          <ProductImage
                            src={product.thumb_url || thumbUrl}
                            alt={product.name}
                            category={product.category}
                            className="w-full h-full"
                          />
                          <label
                            className="absolute inset-0 bg-ink/70 text-white opacity-0 group-hover/thumb:opacity-100 flex flex-col items-center justify-center cursor-pointer transition-opacity text-[8px] font-semibold"
                            title="Upload custom image"
                          >
                            <Upload className="h-3 w-3 mb-0.5" />
                            <span>Upload</span>
                            <input
                              type="file"
                              accept="image/jpeg,image/png,image/webp"
                              className="hidden"
                              onChange={(e) => {
                                const f = e.target.files?.[0]
                                if (f) uploadImageMutation.mutate({ productId: product.id, file: f })
                              }}
                            />
                          </label>
                        </div>

                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-sand text-ink-soft border border-border">
                              {product.category || 'General'}
                            </span>
                            <button
                              type="button"
                              onClick={() =>
                                toggleProductActive.mutate({
                                  productId: product.id,
                                  isActive: !product.is_active,
                                })
                              }
                              className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border transition-colors inline-flex items-center gap-1 cursor-pointer ${
                                product.is_active
                                  ? 'bg-sage-tint text-leaf border-leaf/30'
                                  : 'bg-sand text-ink-soft border-border'
                              }`}
                            >
                              {product.is_active ? 'Active' : 'Hidden'}
                            </button>
                          </div>
                          <h3 className="font-semibold text-sm text-ink truncate mt-1">
                            {product.name}
                          </h3>
                          {unitLabel && <p className="text-xs text-ink-soft">{unitLabel}</p>}
                        </div>
                      </div>

                      {/* Price & Stock Stepper on Mobile */}
                      <div className="flex items-center justify-between pt-2 border-t border-border gap-2">
                        <div>
                          <span className="text-[10px] text-ink-soft block uppercase">Price</span>
                          <span className="num font-bold text-base text-ink">
                            {formatCurrency(product.price)}
                          </span>
                        </div>

                        <div className="text-right">
                          {editingStockId === product.id ? (
                            <div className="space-y-1">
                              <div className="inline-flex items-center gap-1">
                                <Button
                                  size="icon"
                                  variant="outline"
                                  className="h-8 w-8 rounded-lg border-border bg-sand text-ink"
                                  onClick={() => {
                                    const cur = parseInt(editingStockValue, 10) || 0
                                    setEditingStockValue(String(Math.max(0, cur - 1)))
                                  }}
                                >
                                  <Minus className="h-3 w-3" />
                                </Button>
                                <input
                                  type="number"
                                  min="0"
                                  disabled={stockLoading || stockVersion === null}
                                  className="w-14 h-8 px-1 text-xs border border-border rounded-lg bg-surface text-center font-bold text-ink num"
                                  value={editingStockValue}
                                  onChange={(e) => setEditingStockValue(e.target.value)}
                                  autoFocus
                                />
                                <Button
                                  size="icon"
                                  variant="outline"
                                  className="h-8 w-8 rounded-lg border-border bg-sand text-ink"
                                  onClick={() => {
                                    const cur = parseInt(editingStockValue, 10) || 0
                                    setEditingStockValue(String(cur + 1))
                                  }}
                                >
                                  <Plus className="h-3 w-3" />
                                </Button>
                                <Button
                                  size="icon"
                                  className="h-8 w-8 bg-leaf text-white rounded-lg hover:bg-leaf/90"
                                  disabled={stockLoading || stockVersion === null}
                                  onClick={() => handleSaveStock(product.id)}
                                >
                                  <Check className="h-3 w-3" />
                                </Button>
                                <Button
                                  size="icon"
                                  variant="ghost"
                                  className="h-8 w-8 text-ink-soft"
                                  onClick={() => {
                                    setEditingStockId(null)
                                    setStockFeedback(null)
                                  }}
                                >
                                  <X className="h-3 w-3" />
                                </Button>
                              </div>
                              {stockFeedback && (
                                <p role="alert" className="text-[10px] text-brick-ink">
                                  {stockFeedback}
                                </p>
                              )}
                            </div>
                          ) : (
                            <button
                              type="button"
                              onClick={() => handleStartEditStock(product.id)}
                              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-border bg-sand text-xs font-semibold text-ink cursor-pointer"
                            >
                              <Pencil className="h-3 w-3 text-ink-soft" />
                              <span>Adjust Stock</span>
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 3: SETTINGS */}
      {activeTab === 'settings' && (
        <div id="panel-settings" role="tabpanel" aria-labelledby="tab-settings" className="rounded-[14px] border border-border bg-surface p-5 sm:p-6 shadow-none max-w-2xl space-y-5">
          <div>
            <h2 className="font-display text-lg font-semibold text-ink">Shop Profile & Location</h2>
            <p className="text-xs text-ink-soft mt-0.5">
              Verified merchant information displayed on the Dukaanly discovery marketplace.
            </p>
          </div>

          <div className="space-y-4 text-sm">
            <div>
              <span className="font-semibold text-ink-soft text-xs uppercase tracking-wider block mb-1">
                Store Name
              </span>
              <p className="p-3 bg-sand rounded-xl border border-border font-semibold text-ink">
                {shop.name}
              </p>
            </div>
            <div>
              <span className="font-semibold text-ink-soft text-xs uppercase tracking-wider block mb-1">
                Description
              </span>
              <p className="p-3 bg-sand rounded-xl border border-border text-ink-soft">
                {shop.description || 'No description set'}
              </p>
            </div>
            <div>
              <span className="font-semibold text-ink-soft text-xs uppercase tracking-wider block mb-1">
                Storefront Address
              </span>
              <p className="p-3 bg-sand rounded-xl border border-border text-ink">
                {shop.address}
              </p>
            </div>
            <div>
              <span className="font-semibold text-ink-soft text-xs uppercase tracking-wider block mb-1">
                Geospatial Coordinates (PostGIS)
              </span>
              <p className="p-3 bg-sand rounded-xl border border-border font-mono text-xs text-ink-soft num">
                {shop.location
                  ? `Lat: ${shop.location.latitude}, Lng: ${shop.location.longitude}`
                  : 'Coordinates recorded'}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Add Product Modal */}
      {isAddProductOpen && (
        <div
          className="fixed inset-0 z-50 overflow-y-auto bg-black/40 p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget) closeAddProductModal()
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="add-product-title"
            className="my-auto min-h-full flex items-center justify-center"
          >
            <div ref={modalContainerRef} className="max-h-[calc(100dvh-2rem)] w-full max-w-md overflow-y-auto rounded-[14px] border border-border bg-surface p-6 space-y-4 shadow-none">
              <div className="flex justify-between items-center border-b border-border pb-3">
                <h3 id="add-product-title" className="font-display font-semibold text-lg text-ink">Add New Product</h3>
                <button
                  type="button"
                  aria-label="Close add product dialog"
                  onClick={closeAddProductModal}
                  className="text-ink-soft hover:text-ink p-1 rounded-lg cursor-pointer"
                >
                  <X className="h-5 w-5" aria-hidden="true" />
                </button>
              </div>

              {productError && (
                <div role="alert" className="p-3 bg-brick-tint/40 text-brick-ink text-xs rounded-xl border border-brick-ink/30">
                  {productError}
                </div>
              )}

              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  const priceNum = parseFloat(newProductPrice)
                  const stockNum = Number(newProductStock)
                  if (
                    !newProductName.trim() ||
                    !Number.isFinite(priceNum) ||
                    priceNum <= 0 ||
                    !Number.isInteger(stockNum) ||
                    stockNum < 0
                  ) {
                    setProductError('Please provide a valid product name, price, and initial stock quantity.')
                    return
                  }
                  createProductMutation.mutate({
                    name: newProductName.trim(),
                    category: newProductCategory.trim(),
                    price: priceNum,
                    description: newProductDesc.trim(),
                    stock: stockNum,
                  })
                }}
                className="space-y-3.5"
              >
                <div>
                  <label htmlFor="new-product-name" className="text-xs font-semibold text-ink block mb-1">
                    Product Name *
                  </label>
                  <input
                    ref={initialInputRef}
                    id="new-product-name"
                    type="text"
                    required
                    placeholder="e.g. Aashirvaad Whole Wheat Atta 5kg"
                    className="w-full h-10 px-3 border border-border rounded-xl text-sm bg-sand text-ink focus:outline-none focus:border-leaf"
                    value={newProductName}
                    onChange={(e) => setNewProductName(e.target.value)}
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label htmlFor="new-product-category" className="text-xs font-semibold text-ink block mb-1">
                      Category
                    </label>
                    <select
                      id="new-product-category"
                      className="w-full h-10 px-2.5 border border-border rounded-xl text-xs font-semibold bg-sand text-ink focus:outline-none focus:border-leaf"
                      value={newProductCategory}
                      onChange={(e) => setNewProductCategory(e.target.value)}
                    >
                      <option value="Groceries">Groceries</option>
                      <option value="Dairy">Dairy</option>
                      <option value="Edible Oils">Edible Oils</option>
                      <option value="Snacks">Snacks</option>
                      <option value="Fruits & Vegetables">Fruits & Veg</option>
                      <option value="Household">Household</option>
                    </select>
                  </div>
                  <div>
                    <label htmlFor="new-product-price" className="text-xs font-semibold text-ink block mb-1">
                      Price (₹) *
                    </label>
                    <input
                      id="new-product-price"
                      type="number"
                      step="0.01"
                      min="1"
                      required
                      placeholder="245.00"
                      className="w-full h-10 px-3 border border-border rounded-xl text-sm bg-sand text-ink num focus:outline-none focus:border-leaf"
                      value={newProductPrice}
                      onChange={(e) => setNewProductPrice(e.target.value)}
                    />
                  </div>
                </div>

                <div>
                  <label htmlFor="new-product-stock" className="text-xs font-semibold text-ink block mb-1">
                    Initial Stock Quantity
                  </label>
                  <input
                    id="new-product-stock"
                    type="number"
                    min="0"
                    required
                    placeholder="50"
                    className="w-full h-10 px-3 border border-border rounded-xl text-sm bg-sand text-ink num focus:outline-none focus:border-leaf"
                    value={newProductStock}
                    onChange={(e) => setNewProductStock(e.target.value)}
                  />
                </div>

                <div>
                  <label htmlFor="new-product-desc" className="text-xs font-semibold text-ink block mb-1">
                    Description
                  </label>
                  <textarea
                    id="new-product-desc"
                    rows={2}
                    placeholder="Fresh quality daily essential from the store."
                    className="w-full p-2.5 border border-border rounded-xl text-sm bg-sand text-ink resize-none focus:outline-none focus:border-leaf"
                    value={newProductDesc}
                    onChange={(e) => setNewProductDesc(e.target.value)}
                  />
                </div>

                <div className="flex justify-end gap-2.5 pt-3 border-t border-border">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={closeAddProductModal}
                    className="rounded-xl text-ink-soft cursor-pointer"
                  >
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    size="sm"
                    disabled={createProductMutation.isPending}
                    className="bg-leaf hover:bg-leaf/90 text-white rounded-xl font-semibold px-4 cursor-pointer"
                  >
                    {createProductMutation.isPending ? 'Saving...' : 'Add to Catalog'}
                  </Button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Adjust Kitchen Preparation Time Modal */}
      {prepModalDeliveryId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
          role="dialog"
          aria-modal="true"
          aria-labelledby="prep-modal-title"
        >
          <div className="bg-surface rounded-[14px] max-w-sm w-full p-5 sm:p-6 shadow-none border border-border space-y-4">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 id="prep-modal-title" className="font-display font-semibold text-base text-ink flex items-center gap-2">
                <Clock className="h-4.5 w-4.5 text-ink-soft" /> Adjust Prep Time
              </h3>
              <button
                onClick={() => setPrepModalDeliveryId(null)}
                className="text-ink-soft hover:text-ink rounded-lg p-1 cursor-pointer"
                aria-label="Close modal"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <p className="text-xs text-ink-soft">
              Updating estimated prep time recalculates the live delivery arrival window for customer and rider.
            </p>

            <div className="space-y-2">
              <label className="text-xs font-semibold text-ink block">Estimated Preparation Minutes</label>
              <div className="grid grid-cols-4 gap-2">
                {[5, 10, 15, 20, 25, 30, 45, 60].map((mins) => (
                  <button
                    key={mins}
                    type="button"
                    onClick={() => setPrepMinutes(mins)}
                    className={`py-2 text-xs font-semibold rounded-xl border transition-colors cursor-pointer num ${
                      prepMinutes === mins
                        ? 'bg-sage-tint text-leaf border-leaf'
                        : 'bg-sand border-border text-ink hover:border-border-strong'
                    }`}
                  >
                    {mins}m
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-ink block">Delay Explanation (Optional)</label>
              <input
                type="text"
                placeholder="e.g. Rush hour order volume, waiting on fresh batch"
                value={prepDelayReason}
                onChange={(e) => setPrepDelayReason(e.target.value)}
                className="w-full px-3 py-2 text-xs border border-border rounded-xl bg-sand text-ink focus:outline-none focus:border-leaf"
                maxLength={120}
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setPrepModalDeliveryId(null)}
                className="text-xs rounded-xl text-ink-soft cursor-pointer"
              >
                Cancel
              </Button>
              <Button
                size="sm"
                className="bg-leaf hover:bg-leaf/90 text-white text-xs font-semibold rounded-xl cursor-pointer"
                disabled={updatePrepMutation.isPending}
                onClick={() => {
                  updatePrepMutation.mutate(
                    {
                      deliveryId: prepModalDeliveryId,
                      prep: {
                        estimated_minutes: prepMinutes,
                        delay_reason: prepDelayReason.trim() || undefined,
                      },
                    },
                    {
                      onSuccess: () => {
                        setPrepModalDeliveryId(null)
                        setPrepDelayReason('')
                        refetchOrders()
                      },
                    }
                  )
                }}
              >
                {updatePrepMutation.isPending ? 'Updating...' : 'Save & Update ETA'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
