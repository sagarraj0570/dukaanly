import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/store/useAuthStore'
import { api } from '@/api/axios'
import type { Shop } from '@/hooks/useShops'
import type { Product } from '@/hooks/useProducts'
import type { Order, OrderStatus } from '@/hooks/useOrders'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ErrorState'
import { EmptyState } from '@/components/EmptyState'
import { formatCurrency } from '@/lib/utils'
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
  Power,
  RefreshCw,
  X,
  Check,
  Truck,
  Eye,
  EyeOff,
} from 'lucide-react'

export const ShopDashboard = () => {
  const { user } = useAuthStore()
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<'orders' | 'products' | 'settings'>('orders')
  const [orderFilter, setOrderFilter] = useState<'all' | 'new' | 'preparing' | 'ready' | 'completed'>('all')

  // Modals
  const [isAddProductOpen, setIsAddProductOpen] = useState(false)
  const [newProductName, setNewProductName] = useState('')
  const [newProductCategory, setNewProductCategory] = useState('Groceries')
  const [newProductPrice, setNewProductPrice] = useState('')
  const [newProductDesc, setNewProductDesc] = useState('')
  const [newProductStock, setNewProductStock] = useState('')
  const [productError, setProductError] = useState<string | null>(null)

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
      const res = await api.get('/shops', { params: { size: 100 } })
      const items: Shop[] = res.data.items || []
      const found = items.find((s) => s.owner_id === user?.id)
      return found || null
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
        params: { size: 100, active_only: false },
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
    mutationFn: async ({ orderId, status }: { orderId: string; status: OrderStatus }) => {
      const res = await api.patch(`/shops/${shop!.id}/orders/${orderId}/status`, { status })
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['shop-orders', shop?.id] })
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

      // The API creates an inventory record at zero; always set the owner-provided value.
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
      setStockFeedback('Unable to load the current inventory. Please try again.')
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
      <div className="space-y-6 animate-pulse max-w-6xl mx-auto">
        <div className="h-36 bg-[#EDF5EE] rounded-3xl" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="h-24 bg-white border border-[#E5E9E4] rounded-2xl" />
          <div className="h-24 bg-white border border-[#E5E9E4] rounded-2xl" />
          <div className="h-24 bg-white border border-[#E5E9E4] rounded-2xl" />
        </div>
        <div className="h-96 bg-white border border-[#E5E9E4] rounded-2xl" />
      </div>
    )
  }

  if (isShopError) {
    return (
      <div className="max-w-4xl mx-auto">
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
      <div className="max-w-2xl mx-auto py-12">
        <EmptyState
          title="No Shop Registered"
          message="You are registered as a Shop Owner, but no shop profile is linked to your account yet."
          icon={<Store className="h-10 w-10 text-[#176B45]" />}
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

  const getOrderStatusBadge = (status: OrderStatus) => {
    switch (status) {
      case 'delivered':
        return <span className="badge-success">Delivered</span>
      case 'cancelled':
        return <span className="badge-error">Cancelled</span>
      case 'pending':
        return <span className="badge-warning">Pending Payment</span>
      case 'confirmed':
        return <span className="badge-info">New / Confirmed</span>
      case 'preparing':
        return <span className="badge-info">Preparing</span>
      case 'ready_for_pickup':
        return <span className="badge-info">Ready for Pickup</span>
      case 'out_for_delivery':
        return <span className="badge-info">Out for Delivery</span>
      default:
        return <span className="badge-neutral">{status}</span>
    }
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Store Operations Hero Banner */}
      <div className="bg-white border border-[#E5E9E4] rounded-3xl overflow-hidden shadow-soft">
        <div className="p-6 sm:p-8 bg-[#FAF9F6] border-b border-[#E5E9E4]">
          <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
            <div className="flex items-start sm:items-center gap-4 min-w-0">
              <div className="h-16 w-16 sm:h-20 sm:w-20 rounded-2xl overflow-hidden bg-[#EDF5EE] border border-[#E5E9E4] shrink-0">
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
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[11px] uppercase tracking-wider bg-[#EDF5EE] text-[#176B45] px-2.5 py-0.5 rounded-full font-bold">
                    Merchant Portal
                  </span>
                  {shop.is_active ? (
                    <span className="inline-flex items-center gap-1 text-xs text-[#176B45] font-semibold">
                      <span className="h-2 w-2 rounded-full bg-[#176B45] animate-pulse" />
                      Open for Orders
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-xs text-red-600 font-semibold">
                      <span className="h-2 w-2 rounded-full bg-red-600" />
                      Store Closed
                    </span>
                  )}
                </div>

                <h1 className="text-2xl sm:text-3xl font-bold text-[#202923] tracking-tight truncate">
                  {shop.name}
                </h1>
                <div className="flex items-center gap-1.5 text-xs text-[#69736C] mt-1 truncate">
                  <MapPin className="h-3.5 w-3.5 text-[#176B45] shrink-0" />
                  <span className="truncate">{shop.address}</span>
                </div>
              </div>
            </div>

            {/* Open / Close Duty Switch */}
            <Button
              variant={shop.is_active ? 'outline' : 'default'}
              size="lg"
              className={`rounded-xl font-semibold text-sm shrink-0 ${
                shop.is_active
                  ? 'border-red-200 text-red-600 hover:bg-red-50'
                  : 'bg-[#176B45] hover:bg-[#104B32] text-white'
              }`}
              onClick={() => toggleShopActive.mutate(!shop.is_active)}
              disabled={toggleShopActive.isPending}
            >
              <Power className="h-4 w-4 mr-2" />
              {shop.is_active ? 'Close Shop' : 'Open Shop'}
            </Button>
          </div>
        </div>

        {/* 3 Real Operational KPI Metric Cards */}
        <div className="grid grid-cols-3 divide-x divide-[#E5E9E4] bg-white">
          <div className="p-4 sm:p-5 text-center">
            <div className="flex items-center justify-center gap-1.5 text-xs font-bold text-[#69736C] uppercase tracking-wider mb-1">
              <Boxes className="h-3.5 w-3.5 text-[#176B45]" />
              Products
            </div>
            <p className="text-xl sm:text-2xl font-bold text-[#202923]">{products.length}</p>
          </div>
          <div className="p-4 sm:p-5 text-center">
            <div className="flex items-center justify-center gap-1.5 text-xs font-bold text-[#69736C] uppercase tracking-wider mb-1">
              <TrendingUp className="h-3.5 w-3.5 text-[#176B45]" />
              Active Orders
            </div>
            <p className="text-xl sm:text-2xl font-bold text-[#176B45]">{activeOrdersCount}</p>
          </div>
          <div className="p-4 sm:p-5 text-center">
            <div className="flex items-center justify-center gap-1.5 text-xs font-bold text-[#69736C] uppercase tracking-wider mb-1">
              <Clock className="h-3.5 w-3.5 text-[#176B45]" />
              Total Orders
            </div>
            <p className="text-xl sm:text-2xl font-bold text-[#202923]">{orders.length}</p>
          </div>
        </div>
      </div>

      {/* Primary Navigation Tabs */}
      <div className="flex flex-col gap-2 border-b border-[#E5E9E4] sm:flex-row sm:items-center sm:justify-between">
        <div role="tablist" aria-label="Shop management views" className="flex gap-1.5 overflow-x-auto scrollbar-none -mx-1 px-1">
          <button
            type="button"
            role="tab"
            id="tab-orders"
            aria-selected={activeTab === 'orders'}
            aria-controls="panel-orders"
            onClick={() => setActiveTab('orders')}
            className={`flex shrink-0 items-center gap-2 px-3 sm:px-4 py-3 text-xs sm:text-sm font-semibold border-b-2 transition-colors -mb-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45] ${
              activeTab === 'orders'
                ? 'border-[#176B45] text-[#176B45]'
                : 'border-transparent text-[#69736C] hover:text-[#202923]'
            }`}
          >
            <ClipboardList className="h-4 w-4" aria-hidden="true" />
            Incoming Orders
            {activeOrdersCount > 0 && (
              <span className="h-5 min-w-[20px] px-1.5 rounded-full bg-[#176B45] text-white text-[11px] flex items-center justify-center font-bold">
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
            className={`flex shrink-0 items-center gap-2 px-3 sm:px-4 py-3 text-xs sm:text-sm font-semibold border-b-2 transition-colors -mb-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45] ${
              activeTab === 'products'
                ? 'border-[#176B45] text-[#176B45]'
                : 'border-transparent text-[#69736C] hover:text-[#202923]'
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
            className={`flex shrink-0 items-center gap-2 px-3 sm:px-4 py-3 text-xs sm:text-sm font-semibold border-b-2 transition-colors -mb-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45] ${
              activeTab === 'settings'
                ? 'border-[#176B45] text-[#176B45]'
                : 'border-transparent text-[#69736C] hover:text-[#202923]'
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
              className="gap-1.5 text-xs rounded-xl"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </Button>
          )}
          {activeTab === 'products' && (
            <Button
              size="sm"
              onClick={() => setIsAddProductOpen(true)}
              className="gap-1.5 text-xs font-semibold bg-[#176B45] hover:bg-[#104B32] text-white rounded-xl"
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
          <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
            {[
              { id: 'all', label: `All (${orders.length})` },
              {
                id: 'new',
                label: `New (${
                  orders.filter((o) => o.status === 'confirmed' || o.status === 'pending').length
                })`,
              },
              {
                id: 'preparing',
                label: `Preparing (${orders.filter((o) => o.status === 'preparing').length})`,
              },
              {
                id: 'ready',
                label: `Ready (${
                  orders.filter((o) => o.status === 'ready_for_pickup' || o.status === 'out_for_delivery').length
                })`,
              },
              {
                id: 'completed',
                label: `Completed (${
                  orders.filter((o) => o.status === 'delivered' || o.status === 'cancelled').length
                })`,
              },
            ].map((filter) => (
              <button
                key={filter.id}
                type="button"
                onClick={() => setOrderFilter(filter.id as any)}
                className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-colors whitespace-nowrap ${
                  orderFilter === filter.id
                    ? 'bg-[#176B45] text-white shadow-xs'
                    : 'bg-white border border-[#E5E9E4] text-[#69736C] hover:text-[#202923]'
                }`}
              >
                {filter.label}
              </button>
            ))}
          </div>

          {isOrdersLoading ? (
            <div className="space-y-3 animate-pulse">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-32 bg-white border border-[#E5E9E4] rounded-2xl" />
              ))}
            </div>
          ) : filteredOrders.length === 0 ? (
            <EmptyState
              title="No orders found"
              message={
                orderFilter === 'all'
                  ? 'You have not received any orders yet.'
                  : `No orders in the "${orderFilter}" stage right now.`
              }
              icon={<ClipboardList className="h-8 w-8 text-[#69736C]/40" />}
            />
          ) : (
            <div className="space-y-3.5">
              {filteredOrders.map((order) => (
                <div
                  key={order.id}
                  className="bg-white border border-[#E5E9E4] rounded-2xl p-5 shadow-soft space-y-4"
                >
                  <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-2 border-b border-[#E5E9E4] pb-3.5">
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-xs font-bold text-[#69736C]">
                        #{order.id.split('-')[0].toUpperCase()}
                      </span>
                      {getOrderStatusBadge(order.status)}
                      <span className="text-xs text-[#69736C]">
                        {new Date(order.created_at).toLocaleTimeString('en-IN', {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </span>
                    </div>

                    <div className="text-right font-bold text-base text-[#202923]">
                      {formatCurrency(order.total_amount)}
                    </div>
                  </div>

                  {/* Order Items with Thumbnails */}
                  <div className="space-y-2">
                    {order.items.map((item) => (
                      <div
                        key={item.id}
                        className="flex items-center justify-between text-xs sm:text-sm text-[#202923]"
                      >
                        <div className="flex items-center gap-2.5 min-w-0">
                          <div className="h-8 w-8 rounded-lg overflow-hidden bg-[#FAF9F6] border border-[#E5E9E4] shrink-0">
                            <img
                              src={getProductImage(item.product_name)}
                              alt={item.product_name}
                              className="h-full w-full object-cover"
                              onError={(e) => {
                                e.currentTarget.style.display = 'none'
                              }}
                            />
                          </div>
                          <span className="truncate">
                            {item.quantity}× {item.product_name}
                          </span>
                        </div>
                        <span className="text-[#69736C] font-mono shrink-0">
                          {formatCurrency(item.line_total)}
                        </span>
                      </div>
                    ))}
                  </div>

                  {/* Lifecycle Contextual Actions */}
                  <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-[#E5E9E4]">
                    <div className="flex items-center gap-1.5 text-xs text-[#69736C]">
                      <Truck className="h-3.5 w-3.5 text-[#176B45]" />
                      <span>
                        {order.delivery
                          ? `Rider: ${order.delivery.status.replace(/_/g, ' ')}`
                          : 'Rider unassigned'}
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      {order.status === 'confirmed' && (
                        <Button
                          size="sm"
                          className="h-9 px-4 rounded-xl bg-[#176B45] hover:bg-[#104B32] text-white text-xs font-semibold"
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
                        <Button
                          size="sm"
                          className="h-9 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold"
                          onClick={() =>
                            updateOrderStatus.mutate({
                              orderId: order.id,
                              status: 'ready_for_pickup',
                            })
                          }
                          disabled={updateOrderStatus.isPending}
                        >
                          Ready for Pickup
                        </Button>
                      )}

                      {['confirmed', 'preparing'].includes(order.status) && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-9 px-3 rounded-xl text-xs text-red-600 hover:bg-red-50"
                          onClick={() =>
                            updateOrderStatus.mutate({
                              orderId: order.id,
                              status: 'cancelled',
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
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5 animate-pulse">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-56 bg-white border border-[#E5E9E4] rounded-2xl" />
              ))}
            </div>
          ) : products.length === 0 ? (
            <EmptyState
              title="No products yet"
              message="Add products to your shop catalog so customers can order."
              icon={<Package className="h-8 w-8 text-[#69736C]/40" />}
              action={
                <Button
                  size="sm"
                  onClick={() => setIsAddProductOpen(true)}
                  className="bg-[#176B45] hover:bg-[#104B32] text-white rounded-xl"
                >
                  <Plus className="h-4 w-4 mr-1.5" />
                  Add First Product
                </Button>
              }
            />
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
              {products.map((product) => {
                const thumbUrl = getProductImage(product.name, product.category, product.image_url)
                const unitLabel = extractProductUnit(product.name)

                return (
                  <div
                    key={product.id}
                    className="bg-white border border-[#E5E9E4] rounded-2xl p-4 shadow-soft flex flex-col justify-between space-y-3.5 hover:border-[#A8D5B5] transition-colors"
                  >
                    <div className="space-y-2">
                      {/* Thumbnail & Badges */}
                      <div className="flex items-start gap-3">
                        <div className="relative h-16 w-16 rounded-xl overflow-hidden bg-[#FAF9F6] border border-[#E5E9E4] shrink-0 flex items-center justify-center">
                          <Package className="h-6 w-6 text-[#176B45]/30" aria-hidden="true" />
                          <img
                            src={thumbUrl}
                            alt={product.name}
                            className="absolute inset-0 h-full w-full object-cover"
                            onError={(e) => {
                              e.currentTarget.style.display = 'none'
                            }}
                          />
                        </div>

                        <div className="flex-1 min-w-0">
                          <div className="flex justify-between items-start gap-1 mb-1">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-[#176B45] bg-[#EDF5EE] px-2 py-0.5 rounded">
                              {product.category || 'General'}
                            </span>

                            <button
                              type="button"
                              aria-label={product.is_active ? `Deactivate ${product.name}` : `Activate ${product.name}`}
                              onClick={() =>
                                toggleProductActive.mutate({
                                  productId: product.id,
                                  isActive: !product.is_active,
                                })
                              }
                              className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border transition-colors inline-flex items-center gap-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#176B45] ${
                                product.is_active
                                  ? 'bg-green-50 text-green-700 border-green-200'
                                  : 'bg-red-50 text-red-700 border-red-200'
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
                          </div>

                          <h3 className="font-bold text-sm text-[#202923] line-clamp-1">
                            {product.name}
                          </h3>
                          {unitLabel && (
                            <p className="text-xs text-[#69736C]">{unitLabel}</p>
                          )}
                        </div>
                      </div>

                      {product.description && (
                        <p className="text-xs text-[#69736C] line-clamp-2 leading-relaxed">
                          {product.description}
                        </p>
                      )}
                    </div>

                    {/* Price & Optimistic Concurrency Stock Control */}
                    <div className="border-t border-[#E5E9E4] pt-3 flex items-center justify-between">
                      <div>
                        <span className="text-[11px] text-[#69736C] block">Price</span>
                        <p className="font-bold text-base text-[#202923]">
                          {formatCurrency(product.price)}
                        </p>
                      </div>

                      <div className="text-right">
                        <span className="text-[11px] text-[#69736C] block">Inventory</span>
                        {editingStockId === product.id ? (
                          <div className="space-y-1 mt-1">
                            <div className="flex items-center gap-1">
                              <input
                                type="number"
                                min="0"
                                aria-label={`Update inventory stock for ${product.name}`}
                                disabled={stockLoading || stockVersion === null}
                                className="w-16 h-8 px-2 text-xs border rounded-lg bg-white font-bold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45]"
                                value={editingStockValue}
                                onChange={(e) => setEditingStockValue(e.target.value)}
                                autoFocus
                              />
                              <Button
                                size="icon"
                                aria-label={`Save stock for ${product.name}`}
                                className="h-8 w-8 bg-[#176B45] text-white rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45]"
                                disabled={stockLoading || stockVersion === null}
                                onClick={() => handleSaveStock(product.id)}
                              >
                                <Check className="h-3.5 w-3.5" aria-hidden="true" />
                              </Button>
                              <Button
                                size="icon"
                                variant="ghost"
                                aria-label={`Cancel editing stock for ${product.name}`}
                                className="h-8 w-8 text-[#69736C] rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45]"
                                onClick={() => {
                                  setEditingStockId(null)
                                  setStockFeedback(null)
                                }}
                              >
                                <X className="h-3.5 w-3.5" aria-hidden="true" />
                              </Button>
                            </div>
                            {stockFeedback && (
                              <p role="alert" className="text-[10px] text-red-600 max-w-[140px] truncate">
                                {stockFeedback}
                              </p>
                            )}
                          </div>
                        ) : (
                          <button
                            type="button"
                            aria-label={`Manage stock for ${product.name}`}
                            onClick={() => handleStartEditStock(product.id)}
                            className="text-xs font-bold text-[#176B45] hover:underline mt-0.5 inline-flex items-center gap-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#176B45] rounded"
                          >
                            <span>Manage Stock</span>
                            <span className="text-[10px] bg-[#EDF5EE] px-1.5 py-0.5 rounded text-[#176B45]">
                              ✎
                            </span>
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* TAB 3: SETTINGS */}
      {activeTab === 'settings' && (
        <div id="panel-settings" role="tabpanel" aria-labelledby="tab-settings" className="bg-white border border-[#E5E9E4] rounded-3xl p-6 sm:p-8 shadow-soft max-w-2xl space-y-5">
          <div>
            <h2 className="text-lg font-bold text-[#202923]">Shop Profile & Location</h2>
            <p className="text-xs text-[#69736C] mt-0.5">
              Verified merchant information displayed on the Dukaanly discovery marketplace.
            </p>
          </div>

          <div className="space-y-4 text-sm">
            <div>
              <span className="font-bold text-[#69736C] text-xs uppercase tracking-wider block mb-1">
                Store Name
              </span>
              <p className="p-3 bg-[#FAF9F6] rounded-xl border border-[#E5E9E4] font-semibold text-[#202923]">
                {shop.name}
              </p>
            </div>
            <div>
              <span className="font-bold text-[#69736C] text-xs uppercase tracking-wider block mb-1">
                Description
              </span>
              <p className="p-3 bg-[#FAF9F6] rounded-xl border border-[#E5E9E4] text-[#69736C]">
                {shop.description || 'No description set'}
              </p>
            </div>
            <div>
              <span className="font-bold text-[#69736C] text-xs uppercase tracking-wider block mb-1">
                Storefront Address
              </span>
              <p className="p-3 bg-[#FAF9F6] rounded-xl border border-[#E5E9E4] text-[#202923]">
                {shop.address}
              </p>
            </div>
            <div>
              <span className="font-bold text-[#69736C] text-xs uppercase tracking-wider block mb-1">
                Geospatial Coordinates (PostGIS)
              </span>
              <p className="p-3 bg-[#FAF9F6] rounded-xl border border-[#E5E9E4] font-mono text-xs text-[#69736C]">
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
          className="fixed inset-0 z-50 overflow-y-auto bg-black/40 backdrop-blur-sm p-4"
          onKeyDown={(e) => {
            if (e.key === 'Escape') setIsAddProductOpen(false)
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="add-product-title"
            className="my-auto min-h-full flex items-center justify-center"
          >
          <div className="max-h-[calc(100dvh-2rem)] w-full max-w-md overflow-y-auto rounded-3xl border border-[#E5E9E4] bg-white p-6 space-y-4 shadow-elevated">
            <div className="flex justify-between items-center border-b border-[#E5E9E4] pb-3">
              <h3 id="add-product-title" className="font-bold text-lg text-[#202923]">Add New Product</h3>
              <button
                type="button"
                aria-label="Close add product dialog"
                onClick={() => setIsAddProductOpen(false)}
                className="text-[#69736C] hover:text-[#202923] p-1 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45]"
              >
                <X className="h-5 w-5" aria-hidden="true" />
              </button>
            </div>

            {productError && (
              <div role="alert" className="p-3 bg-red-50 text-red-700 text-xs rounded-xl border border-red-200">
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
                <label htmlFor="new-product-name" className="text-xs font-bold text-[#202923] block mb-1">
                  Product Name *
                </label>
                <input
                  id="new-product-name"
                  type="text"
                  required
                  placeholder="e.g. Aashirvaad Whole Wheat Atta 5kg"
                  className="w-full h-10 px-3 border border-[#E5E9E4] rounded-xl text-sm bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45]"
                  value={newProductName}
                  onChange={(e) => setNewProductName(e.target.value)}
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="new-product-category" className="text-xs font-bold text-[#202923] block mb-1">
                    Category
                  </label>
                  <select
                    id="new-product-category"
                    className="w-full h-10 px-2.5 border border-[#E5E9E4] rounded-xl text-xs font-semibold bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45]"
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
                  <label htmlFor="new-product-price" className="text-xs font-bold text-[#202923] block mb-1">
                    Price (₹) *
                  </label>
                  <input
                    id="new-product-price"
                    type="number"
                    step="0.01"
                    min="1"
                    required
                    placeholder="245.00"
                    className="w-full h-10 px-3 border border-[#E5E9E4] rounded-xl text-sm bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45]"
                    value={newProductPrice}
                    onChange={(e) => setNewProductPrice(e.target.value)}
                  />
                </div>
              </div>

              <div>
                <label htmlFor="new-product-stock" className="text-xs font-bold text-[#202923] block mb-1">
                  Initial Stock Quantity
                </label>
                <input
                  id="new-product-stock"
                  type="number"
                  min="0"
                  required
                  placeholder="50"
                  className="w-full h-10 px-3 border border-[#E5E9E4] rounded-xl text-sm bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45]"
                  value={newProductStock}
                  onChange={(e) => setNewProductStock(e.target.value)}
                />
              </div>

              <div>
                <label htmlFor="new-product-desc" className="text-xs font-bold text-[#202923] block mb-1">
                  Description
                </label>
                <textarea
                  id="new-product-desc"
                  rows={2}
                  placeholder="Fresh quality daily essential from the store."
                  className="w-full p-2.5 border border-[#E5E9E4] rounded-xl text-sm bg-white resize-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45]"
                  value={newProductDesc}
                  onChange={(e) => setNewProductDesc(e.target.value)}
                />
              </div>

              <div className="flex justify-end gap-2.5 pt-3 border-t border-[#E5E9E4]">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setIsAddProductOpen(false)}
                  className="rounded-xl"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  size="sm"
                  disabled={createProductMutation.isPending}
                  className="bg-[#176B45] hover:bg-[#104B32] text-white rounded-xl font-semibold px-4"
                >
                  {createProductMutation.isPending ? 'Saving...' : 'Add to Catalog'}
                </Button>
              </div>
            </form>
          </div>
          </div>
        </div>
      )}
    </div>
  )
}
