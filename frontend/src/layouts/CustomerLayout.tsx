import { Outlet, useNavigate, useLocation, useSearchParams } from 'react-router-dom'
import { useAuthStore } from '@/store/useAuthStore'
import {
  ShoppingCart,
  User as UserIcon,
  LogOut,
  Store,
  Package,
  MapPin,
  Search,
  X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useCart } from '@/hooks/useCart'
import { useShops } from '@/hooks/useShops'
import { useState, useEffect } from 'react'

const CartButton = () => {
  const { data } = useCart()
  const navigate = useNavigate()
  const itemCount = data?.items?.reduce((total, item) => total + item.quantity, 0) || 0

  return (
    <button
      type="button"
      onClick={() => navigate('/customer/cart')}
      aria-label={`Shopping cart${itemCount > 0 ? `, ${itemCount} items` : ''}`}
      className="relative inline-flex items-center justify-center h-10 w-10 rounded-xl border border-border bg-white text-foreground hover:bg-[#EDF5EE] hover:border-[#A8D5B5] transition-colors shrink-0"
    >
      <ShoppingCart className="h-4.5 w-4.5 text-[#202923]" />
      {itemCount > 0 && (
        <span className="absolute -top-1.5 -right-1.5 flex h-5 min-w-[20px] px-1 items-center justify-center rounded-full bg-[#176B45] text-[11px] font-bold text-white shadow-sm ring-2 ring-white">
          {itemCount}
        </span>
      )}
    </button>
  )
}

export const CustomerLayout = () => {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams, setSearchParams] = useSearchParams()
  const urlQuery = searchParams.get('q') || ''
  const [searchInput, setSearchInput] = useState(urlQuery)

  // Derive neighbourhood label from actual loaded shops when available
  const { data: shopsData } = useShops(1, 12)
  const firstAddress = shopsData?.items?.[0]?.address
  const locationLabel = firstAddress
    ? firstAddress.split(',').slice(-2).join(',').trim() || firstAddress
    : null

  useEffect(() => {
    setSearchInput(urlQuery)
  }, [urlQuery])

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = searchInput.trim()
    if (location.pathname !== '/customer') {
      navigate(trimmed ? `/customer?q=${encodeURIComponent(trimmed)}` : '/customer')
    } else {
      if (trimmed) {
        setSearchParams({ q: trimmed })
      } else {
        setSearchParams({})
      }
    }
  }

  const handleSearchChange = (value: string) => {
    setSearchInput(value)
    if (location.pathname === '/customer') {
      if (value.trim()) {
        setSearchParams({ q: value }, { replace: true })
      } else {
        setSearchParams({}, { replace: true })
      }
    }
  }

  const clearHeaderSearch = () => {
    setSearchInput('')
    if (location.pathname === '/customer') {
      setSearchParams({}, { replace: true })
    }
  }

  const isShopsActive =
    location.pathname === '/customer' ||
    location.pathname.startsWith('/customer/shops') ||
    location.pathname.startsWith('/customer/products')
  const isOrdersActive = location.pathname.startsWith('/customer/orders')
  const isCartActive =
    location.pathname.startsWith('/customer/cart') ||
    location.pathname.startsWith('/customer/checkout')

  return (
    <div className="flex flex-col min-h-screen bg-[#FAF9F6] text-[#202923]">
      {/* Skip Navigation Link */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:px-4 focus:py-2 focus:bg-[#176B45] focus:text-white focus:rounded-lg focus:shadow-lg focus:outline-none focus:ring-2 focus:ring-white"
      >
        Skip to main content
      </a>

      {/* Compact Commerce Header */}
      <header className="sticky top-0 z-40 w-full border-b border-[#E5E9E4] bg-white/95 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-3 sm:gap-4">
          {/* Left: Brand + Location Pill */}
          <div className="flex items-center gap-3 lg:gap-4 shrink-0">
            <button
              type="button"
              onClick={() => navigate('/customer')}
              aria-label="Dukaanly Home"
              className="flex items-center gap-2.5 shrink-0 group text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45] rounded-xl"
            >
              <div className="h-9 w-9 rounded-xl bg-[#176B45] flex items-center justify-center shadow-sm group-hover:bg-[#104B32] transition-colors">
                <Store className="h-5 w-5 text-white" aria-hidden="true" />
              </div>
              <span className="font-bold text-xl tracking-tight text-[#202923]">
                Dukaan<span className="text-[#176B45]">ly</span>
              </span>
            </button>

            {locationLabel && (
              <div
                className="hidden lg:flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[#FAF9F6] border border-[#E5E9E4] text-xs font-medium text-[#202923] max-w-[220px]"
                title={firstAddress || ''}
              >
                <MapPin className="h-3.5 w-3.5 text-[#176B45] shrink-0" aria-hidden="true" />
                <span className="truncate">{locationLabel}</span>
              </div>
            )}
          </div>

          {/* Center: Global Shop/Catalog Search */}
          <form
            onSubmit={handleSearchSubmit}
            className="hidden md:flex flex-1 max-w-md mx-2 relative"
            role="search"
          >
            <Search className="h-4 w-4 text-[#69736C] absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" aria-hidden="true" />
            <input
              type="search"
              value={searchInput}
              onChange={(e) => handleSearchChange(e.target.value)}
              placeholder="Search shops or address..."
              aria-label="Search for shops or address"
              className="w-full h-10 pl-10 pr-8 rounded-full bg-[#FAF9F6] border border-[#E5E9E4] text-sm text-[#202923] placeholder:text-[#69736C] focus:bg-white focus:border-[#176B45] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45] transition-colors"
            />
            {searchInput && (
              <button
                type="button"
                onClick={clearHeaderSearch}
                aria-label="Clear search"
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#69736C] hover:text-[#202923] p-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45] rounded-full"
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            )}
          </form>

          {/* Right: Orders, Cart, Profile, Logout */}
          <nav aria-label="Main navigation" className="flex items-center gap-2 sm:gap-2.5 shrink-0">
            <button
              type="button"
              onClick={() => navigate('/customer/orders')}
              aria-current={isOrdersActive ? 'page' : undefined}
              className={`hidden sm:inline-flex items-center gap-1.5 h-10 px-3.5 rounded-xl text-sm font-medium border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45] ${
                isOrdersActive
                  ? 'bg-[#EDF5EE] text-[#176B45] border-[#A8D5B5]'
                  : 'bg-white text-[#202923] border-transparent hover:bg-[#FAF9F6] hover:border-[#E5E9E4]'
              }`}
            >
              <Package className="h-4 w-4 text-[#176B45]" aria-hidden="true" />
              <span>Orders</span>
            </button>

            <CartButton />

            <div className="hidden sm:flex items-center gap-2 pl-2 border-l border-[#E5E9E4]">
              <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-full bg-[#FAF9F6] border border-[#E5E9E4]">
                <div className="h-6 w-6 rounded-full bg-[#176B45] text-white flex items-center justify-center text-xs font-bold shrink-0">
                  {user?.name ? user.name.charAt(0).toUpperCase() : <UserIcon className="h-3.5 w-3.5" />}
                </div>
                <span className="text-xs font-semibold text-[#202923] max-w-[110px] truncate">
                  {user?.name?.replace(/\s*\(.*\)/, '') || 'Account'}
                </span>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={logout}
                className="h-9 w-9 text-[#69736C] hover:text-red-600 hover:bg-red-50 rounded-xl"
                title="Sign out"
                aria-label="Sign out"
              >
                <LogOut className="h-4 w-4" />
              </Button>
            </div>

            {/* Mobile Sign Out */}
            <Button
              variant="ghost"
              size="icon"
              onClick={logout}
              className="sm:hidden h-9 w-9 text-[#69736C] hover:text-red-600 rounded-xl"
              title="Sign out"
              aria-label="Sign out"
            >
              <LogOut className="h-4 w-4" aria-hidden="true" />
            </Button>
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main id="main-content" tabIndex={-1} className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 pb-24 sm:pb-12 focus:outline-none">
        <Outlet />
      </main>

      {/* Desktop Footer */}
      <footer className="hidden sm:block border-t border-[#E5E9E4] bg-white mt-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-[#69736C]">
          <div className="flex items-center gap-2.5">
            <div className="h-6 w-6 rounded-lg bg-[#176B45] flex items-center justify-center">
              <Store className="h-3.5 w-3.5 text-white" aria-hidden="true" />
            </div>
            <span className="font-semibold text-[#202923]">Dukaanly</span>
            <span>·</span>
            <span>Local shops. Stronger communities.</span>
          </div>
          <div className="flex items-center gap-4">
            <span>Hyperlocal Neighbourhood Commerce</span>
          </div>
        </div>
      </footer>

      {/* Mobile Bottom Navigation */}
      <nav
        aria-label="Mobile navigation"
        className="sm:hidden fixed bottom-0 left-0 right-0 z-40 bg-white border-t border-[#E5E9E4] shadow-elevated pb-safe"
      >
        <div className="grid grid-cols-3 h-14">
          <button
            type="button"
            onClick={() => navigate('/customer')}
            aria-label="Home"
            aria-current={isShopsActive ? 'page' : undefined}
            className={`flex flex-col items-center justify-center gap-0.5 text-[11px] font-semibold transition-colors ${
              isShopsActive ? 'text-[#176B45]' : 'text-[#69736C]'
            }`}
          >
            <Store className="h-5 w-5" aria-hidden="true" />
            <span>Home</span>
          </button>
          <button
            type="button"
            onClick={() => navigate('/customer/orders')}
            aria-label="Orders"
            aria-current={isOrdersActive ? 'page' : undefined}
            className={`flex flex-col items-center justify-center gap-0.5 text-[11px] font-semibold transition-colors ${
              isOrdersActive ? 'text-[#176B45]' : 'text-[#69736C]'
            }`}
          >
            <Package className="h-5 w-5" aria-hidden="true" />
            <span>Orders</span>
          </button>
          <button
            type="button"
            onClick={() => navigate('/customer/cart')}
            aria-label="Cart"
            aria-current={isCartActive ? 'page' : undefined}
            className={`flex flex-col items-center justify-center gap-0.5 text-[11px] font-semibold transition-colors ${
              isCartActive ? 'text-[#176B45]' : 'text-[#69736C]'
            }`}
          >
            <ShoppingCart className="h-5 w-5" aria-hidden="true" />
            <span>Cart</span>
          </button>
        </div>
      </nav>
    </div>
  )
}
