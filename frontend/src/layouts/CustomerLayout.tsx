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
  ChevronDown,
  Sparkles,
  Navigation,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useCart } from '@/hooks/useCart'
import { useState, useEffect, useRef } from 'react'
import { LocationModal } from '@/components/LocationModal'
import { useLocationStore } from '@/store/useLocationStore'
import { ShoppingAssistantModal } from '@/components/ai/ShoppingAssistantModal'

const CartButton = () => {
  const { data } = useCart()
  const navigate = useNavigate()
  const itemCount = data?.items?.reduce((total, item) => total + item.quantity, 0) || 0

  return (
    <button
      type="button"
      onClick={() => navigate('/customer/cart')}
      aria-label={`Shopping cart${itemCount > 0 ? `, ${itemCount} items` : ''}`}
      className="relative inline-flex items-center justify-center h-10 w-10 rounded-xl border border-border bg-surface text-ink hover:bg-sand transition-colors shrink-0 cursor-pointer"
    >
      <ShoppingCart className="h-4.5 w-4.5 text-ink" />
      {itemCount > 0 && (
        <span className="absolute -top-1.5 -right-1.5 flex h-5 min-w-[20px] px-1 items-center justify-center rounded-full bg-leaf text-[11px] font-bold text-white ring-2 ring-surface num">
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
  const [isLocationModalOpen, setIsLocationModalOpen] = useState(false)
  const [isLocationPopoverOpen, setIsLocationPopoverOpen] = useState(false)
  const [isAiAssistantOpen, setIsAiAssistantOpen] = useState(false)

  const popoverRef = useRef<HTMLDivElement>(null)

  const {
    addressLabel,
    radiusMeters,
    requestGpsLocation,
    setDemoPatnaLocation,
  } = useLocationStore()
  const radiusKm = Math.round(radiusMeters / 1000)

  useEffect(() => {
    setSearchInput(urlQuery)
  }, [urlQuery])

  // Handle click outside location popover
  useEffect(() => {
    if (!isLocationPopoverOpen) return
    const handleClickOutside = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setIsLocationPopoverOpen(false)
      }
    }
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsLocationPopoverOpen(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleEscape)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleEscape)
    }
  }, [isLocationPopoverOpen])

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

  const isOrdersActive = location.pathname.startsWith('/customer/orders')

  return (
    <div className="flex flex-col min-h-screen bg-paper text-ink">
      {/* Skip Navigation Link */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:px-4 focus:py-2 focus:bg-leaf focus:text-white focus:rounded-lg focus:outline-none"
      >
        Skip to main content
      </a>

      {/* Header */}
      <header className="sticky top-0 z-40 w-full border-b border-border bg-surface">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-2.5 sm:gap-4">
          {/* Left: Brand + Single Location Pill in Header */}
          <div className="flex items-center gap-2 sm:gap-3 shrink-0">
            <button
              type="button"
              onClick={() => navigate('/customer')}
              aria-label="Dukaanly Home"
              className="flex items-center gap-2 shrink-0 group text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf rounded-xl cursor-pointer"
            >
              <div className="h-9 w-9 rounded-xl bg-leaf flex items-center justify-center text-white shrink-0">
                <Store className="h-5 w-5" aria-hidden="true" />
              </div>
              <span className="font-display font-semibold text-xl tracking-tight text-ink hidden min-[400px]:inline">
                Dukaan<span className="text-leaf">ly</span>
              </span>
            </button>

            {/* Single Location Pill with Quick-Switch Popover */}
            <div className="relative shrink-0" ref={popoverRef}>
              <button
                type="button"
                onClick={() => setIsLocationPopoverOpen((prev) => !prev)}
                aria-expanded={isLocationPopoverOpen}
                aria-label={`Delivery location: ${addressLabel || 'Boring Road, Patna (demo)'}`}
                className="flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-full bg-sand hover:bg-border/60 border border-border text-xs font-semibold text-ink max-w-[145px] sm:max-w-[210px] md:max-w-[240px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf cursor-pointer"
              >
                <MapPin className="h-3.5 w-3.5 text-leaf shrink-0" aria-hidden="true" />
                <span className="truncate">{addressLabel || 'Boring Road, Patna (demo)'}</span>
                <ChevronDown
                  className={`h-3 w-3 text-ink-soft shrink-0 transition-transform ${
                    isLocationPopoverOpen ? 'rotate-180' : ''
                  }`}
                  aria-hidden="true"
                />
              </button>

              {/* Popover */}
              {isLocationPopoverOpen && (
                <div
                  role="menu"
                  className="absolute left-0 top-full mt-2 w-72 rounded-[14px] border border-border bg-surface p-2 shadow-lg z-50 text-xs animate-in fade-in-50 zoom-in-95 duration-100"
                >
                  <div className="px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-ink-soft">
                    Delivery Location
                  </div>

                  <button
                    type="button"
                    role="menuitem"
                    onClick={async () => {
                      setIsLocationPopoverOpen(false)
                      await requestGpsLocation()
                    }}
                    className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-xl text-left hover:bg-sand transition text-xs font-semibold text-ink cursor-pointer"
                  >
                    <div className="h-7 w-7 rounded-lg bg-sand flex items-center justify-center shrink-0 text-leaf">
                      <Navigation className="h-3.5 w-3.5" />
                    </div>
                    <div className="min-w-0">
                      <span className="block text-ink font-semibold">Use my GPS</span>
                      <span className="block text-[10px] text-ink-soft font-normal">Detect current location</span>
                    </div>
                  </button>

                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setDemoPatnaLocation()
                      setIsLocationPopoverOpen(false)
                    }}
                    className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-xl text-left hover:bg-sand transition text-xs font-semibold text-ink cursor-pointer mt-0.5"
                  >
                    <div className="h-7 w-7 rounded-lg bg-sage-tint flex items-center justify-center shrink-0 text-leaf">
                      <MapPin className="h-3.5 w-3.5" />
                    </div>
                    <div className="min-w-0">
                      <span className="block text-ink font-semibold">Use Patna demo location (Boring Road)</span>
                      <span className="block text-[10px] text-leaf font-medium">Near partner shops (&lt; 250m)</span>
                    </div>
                  </button>

                  <div className="border-t border-border mt-1.5 pt-1.5 px-2.5 flex items-center justify-between">
                    <button
                      type="button"
                      onClick={() => {
                        setIsLocationPopoverOpen(false)
                        setIsLocationModalOpen(true)
                      }}
                      className="text-[11px] text-ink-soft hover:text-ink hover:underline cursor-pointer font-medium"
                    >
                      More Patna areas...
                    </button>
                    <span className="text-[10px] text-ink-soft font-mono num">
                      Radius: {radiusKm}km
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Center: The Single Global Search Bar */}
          <form
            onSubmit={handleSearchSubmit}
            className="flex flex-1 max-w-sm sm:max-w-md mx-1 sm:mx-2 relative min-w-0"
            role="search"
          >
            <Search className="h-4 w-4 text-ink-soft absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none shrink-0" aria-hidden="true" />
            <input
              type="search"
              value={searchInput}
              onChange={(e) => handleSearchChange(e.target.value)}
              placeholder="Search shops or products"
              aria-label="Search shops or products"
              className="w-full h-10 pl-9 pr-7 sm:pr-8 rounded-full bg-sand/60 border border-border text-xs sm:text-sm text-ink placeholder:text-ink-soft focus:bg-surface focus:border-leaf focus:outline-none transition-colors"
            />
            {searchInput && (
              <button
                type="button"
                onClick={clearHeaderSearch}
                aria-label="Clear search"
                className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-soft hover:text-ink p-0.5 rounded-full cursor-pointer"
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            )}
          </form>

          {/* Right: Orders, AI Assistant, Cart, Profile, Logout */}
          <nav aria-label="Main navigation" className="flex items-center gap-1.5 sm:gap-2 shrink-0">
            <button
              type="button"
              onClick={() => navigate('/customer/orders')}
              aria-current={isOrdersActive ? 'page' : undefined}
              className={`hidden md:inline-flex items-center gap-1.5 h-10 px-3 rounded-xl text-xs sm:text-sm font-semibold border transition-colors cursor-pointer ${
                isOrdersActive
                  ? 'bg-sage-tint text-leaf border-leaf/30'
                  : 'bg-surface text-ink border-transparent hover:bg-sand hover:border-border'
              }`}
            >
              <Package className="h-4 w-4 text-ink-soft" aria-hidden="true" />
              <span>Orders</span>
            </button>

            <button
              type="button"
              onClick={() => setIsAiAssistantOpen(true)}
              aria-label="Open AI Shopping Assistant"
              className="hidden sm:inline-flex items-center gap-1.5 h-10 px-3 rounded-xl text-xs sm:text-sm font-semibold border border-leaf/30 bg-sage-tint text-leaf hover:bg-sage-tint/80 transition-colors shrink-0 cursor-pointer"
            >
              <Sparkles className="h-4 w-4" />
              <span className="hidden lg:inline">AI Assistant</span>
            </button>

            <CartButton />

            <div className="hidden sm:flex items-center gap-1.5 pl-1.5 border-l border-border">
              <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full bg-sand border border-border">
                <div className="h-5 w-5 rounded-full bg-leaf text-white flex items-center justify-center text-[10px] font-bold shrink-0">
                  {user?.name ? user.name.charAt(0).toUpperCase() : <UserIcon className="h-3 w-3" />}
                </div>
                <span className="text-xs font-semibold text-ink max-w-[100px] truncate">
                  {user?.name?.replace(/\s*\(.*\)/, '') || 'Account'}
                </span>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={logout}
                className="h-9 w-9 text-ink-soft hover:text-brick-ink hover:bg-brick-tint/20 rounded-xl cursor-pointer"
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
              className="sm:hidden h-9 w-9 text-ink-soft hover:text-brick-ink rounded-xl"
              title="Sign out"
              aria-label="Sign out"
            >
              <LogOut className="h-4 w-4" aria-hidden="true" />
            </Button>
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main id="main-content" tabIndex={-1} className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 pb-6 focus:outline-none">
        <Outlet />
      </main>

      {/* Customer Footer */}
      <footer className="border-t border-border bg-surface mt-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 sm:py-5 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-ink-soft">
          <div className="flex items-center gap-2">
            <div className="h-6 w-6 rounded-lg bg-leaf flex items-center justify-center text-white shrink-0">
              <Store className="h-3.5 w-3.5" aria-hidden="true" />
            </div>
            <span className="font-semibold text-ink">Dukaanly</span>
            <span>·</span>
            <span>Patna Hyperlocal Neighbourhood Commerce</span>
          </div>
          <span className="text-[11px] text-ink-soft">
            Local kirana, medical & confectionery stores in your neighbourhood
          </span>
        </div>
      </footer>

      <LocationModal
        isOpen={isLocationModalOpen}
        onClose={() => setIsLocationModalOpen(false)}
      />

      <ShoppingAssistantModal
        isOpen={isAiAssistantOpen}
        onClose={() => setIsAiAssistantOpen(false)}
      />
    </div>
  )
}
export default CustomerLayout
