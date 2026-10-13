import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/store/useAuthStore'
import { LogOut, Package, Store, ClipboardList, LayoutDashboard, Menu, X } from 'lucide-react'
import { useState, useEffect } from 'react'

export const ShopLayout = () => {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMobileMenuOpen(false)
    }
    if (mobileMenuOpen) {
      window.addEventListener('keydown', handleKeyDown)
      return () => window.removeEventListener('keydown', handleKeyDown)
    }
  }, [mobileMenuOpen])

  const sideNavItems = [
    { label: 'Dashboard', href: '/shop', icon: LayoutDashboard },
    { label: 'Products & Inventory', href: '/shop', icon: Package },
    { label: 'Orders', href: '/shop', icon: ClipboardList },
  ]

  return (
    <div className="flex h-screen bg-[#FAF9F6] overflow-hidden">
      {/* Desktop Sidebar */}
      <aside className="hidden md:flex w-60 lg:w-64 flex-col bg-white border-r border-[#E5E9E4] shrink-0">
        {/* Logo */}
        <div className="h-16 flex items-center px-5 border-b border-[#E5E9E4] shrink-0">
          <button
            onClick={() => navigate('/shop')}
            className="flex items-center gap-2.5 group text-left"
          >
            <div className="h-8 w-8 rounded-xl bg-gradient-to-br from-[#176B45] to-[#104B32] flex items-center justify-center shadow-xs">
              <Store className="h-4 w-4 text-white" />
            </div>
            <div className="flex flex-col">
              <span className="font-bold text-base text-[#202923] leading-none">
                Dukaan<span className="text-[#176B45]">ly</span>
              </span>
              <span className="text-[10px] font-bold uppercase tracking-wider text-[#176B45] mt-0.5">
                Merchant Operations
              </span>
            </div>
          </button>
        </div>

        {/* Nav Links */}
        <nav aria-label="Merchant sidebar navigation" className="flex-1 p-3.5 space-y-1 overflow-y-auto">
          {sideNavItems.map(({ label, href, icon: Icon }) => {
            const isActive = location.pathname === href || location.pathname.startsWith(href + '/')
            return (
              <button
                key={label}
                type="button"
                onClick={() => navigate(href)}
                aria-current={isActive ? 'page' : undefined}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold transition-all duration-150 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45] ${
                  isActive
                    ? 'bg-[#EDF5EE] text-[#176B45] shadow-xs'
                    : 'text-[#69736C] hover:text-[#202923] hover:bg-[#FAF9F6]'
                }`}
              >
                <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                {label}
              </button>
            )
          })}
        </nav>

        {/* User footer */}
        <div className="p-3.5 border-t border-[#E5E9E4] shrink-0">
          <div className="flex items-center gap-2.5 px-2.5 py-2 rounded-xl bg-[#FAF9F6] border border-[#E5E9E4] mb-2">
            <div className="h-7 w-7 rounded-lg bg-[#EDF5EE] border border-[#A8D5B5] flex items-center justify-center shrink-0">
              <span className="text-xs font-bold text-[#176B45]">
                {user?.name?.charAt(0).toUpperCase()}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-bold text-[#202923] truncate">{user?.name}</p>
              <p className="text-[10px] text-[#69736C]">Shop Owner</p>
            </div>
          </div>
          <button
            type="button"
            onClick={logout}
            aria-label="Sign out"
            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm font-semibold text-[#69736C] hover:text-red-700 hover:bg-red-50 transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45]"
          >
            <LogOut className="h-4 w-4 shrink-0" aria-hidden="true" />
            Sign out
          </button>
        </div>
      </aside>

      {/* Mobile overlay */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 md:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* Mobile Sidebar */}
      <aside
        id="mobile-sidebar"
        role="dialog"
        aria-modal="true"
        aria-label="Merchant navigation"
        aria-hidden={!mobileMenuOpen}
        className={`fixed inset-y-0 left-0 z-50 w-64 flex flex-col bg-white border-r border-[#E5E9E4] shadow-elevated transform transition-transform duration-200 md:hidden ${
          mobileMenuOpen ? 'translate-x-0' : '-translate-x-full pointer-events-none'
        }`}
      >
        <div className="h-16 flex items-center justify-between px-4 border-b border-[#E5E9E4]">
          <div className="flex items-center gap-2">
            <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-[#176B45] to-[#104B32] flex items-center justify-center">
              <Store className="h-3.5 w-3.5 text-white" aria-hidden="true" />
            </div>
            <span className="font-bold text-sm text-[#202923]">Merchant Portal</span>
          </div>
          <button
            type="button"
            onClick={() => setMobileMenuOpen(false)}
            aria-label="Close navigation menu"
            className="p-1.5 rounded-lg hover:bg-[#FAF9F6]"
          >
            <X className="h-4 w-4 text-[#69736C]" aria-hidden="true" />
          </button>
        </div>
        <nav aria-label="Mobile merchant navigation" className="flex-1 p-3 space-y-1 overflow-y-auto">
          {sideNavItems.map(({ label, href, icon: Icon }) => {
            const isActive = location.pathname === href || location.pathname.startsWith(href + '/')
            return (
              <button
                key={label}
                type="button"
                onClick={() => { navigate(href); setMobileMenuOpen(false) }}
                aria-current={isActive ? 'page' : undefined}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold transition-all text-left ${
                  isActive
                    ? 'bg-[#EDF5EE] text-[#176B45]'
                    : 'text-[#69736C] hover:text-[#202923] hover:bg-[#FAF9F6]'
                }`}
              >
                <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                {label}
              </button>
            )
          })}
        </nav>
        <div className="p-3 border-t border-[#E5E9E4]">
          <button
            type="button"
            onClick={logout}
            aria-label="Sign out"
            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm font-semibold text-[#69736C] hover:bg-red-50 hover:text-red-700"
          >
            <LogOut className="h-4 w-4" aria-hidden="true" /> Sign out
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Mobile top bar */}
        <header className="h-14 bg-white border-b border-[#E5E9E4] flex items-center justify-between px-4 md:hidden shrink-0">
          <button
            type="button"
            onClick={() => setMobileMenuOpen(true)}
            aria-label="Open navigation menu"
            aria-expanded={mobileMenuOpen}
            aria-controls="mobile-sidebar"
            className="p-2 rounded-lg hover:bg-[#FAF9F6]"
          >
            <Menu className="h-5 w-5 text-[#202923]" aria-hidden="true" />
          </button>
          <div className="flex items-center gap-2">
            <div className="h-6 w-6 rounded bg-gradient-to-br from-[#176B45] to-[#104B32] flex items-center justify-center">
              <Store className="h-3.5 w-3.5 text-white" aria-hidden="true" />
            </div>
            <span className="font-bold text-sm text-[#202923]">Merchant Console</span>
          </div>
          <button
            type="button"
            onClick={logout}
            aria-label="Sign out"
            className="p-2 rounded-lg hover:bg-[#FAF9F6] text-[#69736C]"
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
          </button>
        </header>

        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 bg-[#FAF9F6]">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
