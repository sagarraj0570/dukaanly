import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/store/useAuthStore'
import { LogOut, Package, Store, ClipboardList, LayoutDashboard, Menu, X } from 'lucide-react'
import { useState, useEffect, useRef } from 'react'

export const ShopLayout = () => {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const drawerRef = useRef<HTMLElement>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!mobileMenuOpen) return

    closeButtonRef.current?.focus()

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setMobileMenuOpen(false)
        menuButtonRef.current?.focus()
      } else if (e.key === 'Tab' && drawerRef.current) {
        const focusables = drawerRef.current.querySelectorAll<HTMLElement>(
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
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [mobileMenuOpen])

  const sideNavItems = [
    { label: 'Dashboard', href: '/shop', icon: LayoutDashboard },
    { label: 'Products & Inventory', href: '/shop', icon: Package },
    { label: 'Orders', href: '/shop', icon: ClipboardList },
  ]

  return (
    <div className="flex h-screen h-[100dvh] min-h-[100dvh] bg-bg overflow-hidden">
      {/* Skip Navigation Link */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:px-4 focus:py-2 focus:bg-primary-700 focus:text-white focus:rounded-lg focus:shadow-lg focus:outline-none focus:ring-2 focus:ring-white"
      >
        Skip to main content
      </a>

      {/* Desktop Sidebar */}
      <aside className="hidden md:flex w-60 lg:w-64 flex-col bg-surface border-r border-border shrink-0">
        {/* Logo */}
        <div className="h-16 flex items-center px-5 border-b border-border shrink-0">
          <button
            onClick={() => navigate('/shop')}
            className="flex items-center gap-2.5 group text-left cursor-pointer"
          >
            <div className="h-8 w-8 rounded-xl bg-sage-tint border border-leaf/30 flex items-center justify-center text-leaf shadow-none">
              <Store className="h-4 w-4" />
            </div>
            <div className="flex flex-col">
              <span className="font-display font-bold text-lg text-ink leading-none">
                Dukaan<span className="text-leaf">ly</span>
              </span>
              <span className="text-[10px] font-bold uppercase tracking-wider text-leaf mt-0.5">
                Merchant Operations
              </span>
            </div>
          </button>
        </div>

        {/* Nav Links */}
        <nav aria-label="Merchant sidebar navigation" className="flex-1 p-3.5 space-y-1 overflow-y-auto">
          {sideNavItems.map(({ label, href, icon: Icon }, index) => {
            const isActive = index === 0 && location.pathname === '/shop'
            return (
              <button
                key={label}
                type="button"
                onClick={() => navigate(href)}
                aria-current={isActive ? 'page' : undefined}
                className={`w-full flex items-center gap-3 px-3 py-2.5 text-sm transition-all duration-150 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf cursor-pointer ${
                  isActive
                    ? 'bg-sage-tint text-leaf border-l-[3px] border-leaf rounded-r-xl rounded-l-none font-semibold'
                    : 'text-ink-soft hover:text-ink hover:bg-sand/60 border-l-[3px] border-transparent font-medium rounded-xl'
                }`}
              >
                <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                {label}
              </button>
            )
          })}
        </nav>

        {/* User footer */}
        <div className="p-3.5 border-t border-border shrink-0">
          <div className="flex items-center gap-2.5 px-3 py-2.5 rounded-xl bg-sand/40 border border-border mb-2">
            <div className="h-7 w-7 rounded-lg bg-sage-tint border border-leaf/30 flex items-center justify-center shrink-0">
              <span className="text-xs font-bold text-leaf">
                {(user?.name || 'R').charAt(0).toUpperCase()}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-ink truncate">{user?.name || 'Ramesh Kirana'}</p>
              <p className="text-[10px] text-ink-soft">Shop owner</p>
            </div>
          </div>
          <button
            type="button"
            onClick={logout}
            aria-label="Sign out"
            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm font-semibold text-ink-soft hover:text-brick-ink hover:bg-brick-tint/40 transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf cursor-pointer"
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
        ref={drawerRef}
        id="mobile-sidebar"
        role="dialog"
        aria-modal="true"
        aria-label="Merchant navigation"
        aria-hidden={!mobileMenuOpen}
        className={`fixed inset-y-0 left-0 z-50 w-64 flex flex-col bg-surface border-r border-border shadow-elevated transform transition-transform duration-200 md:hidden ${
          mobileMenuOpen ? 'translate-x-0' : '-translate-x-full pointer-events-none'
        }`}
      >
        <div className="h-16 flex items-center justify-between px-4 border-b border-border">
          <div className="flex items-center gap-2">
            <div className="h-7 w-7 rounded-lg bg-sage-tint border border-leaf/30 flex items-center justify-center text-leaf">
              <Store className="h-3.5 w-3.5" aria-hidden="true" />
            </div>
            <span className="font-display font-bold text-sm text-ink">Merchant Operations</span>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={() => { setMobileMenuOpen(false); menuButtonRef.current?.focus() }}
            aria-label="Close navigation menu"
            className="p-1.5 rounded-lg hover:bg-sand text-ink-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf cursor-pointer"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <nav aria-label="Mobile merchant navigation" className="flex-1 p-3 space-y-1 overflow-y-auto">
          {sideNavItems.map(({ label, href, icon: Icon }, index) => {
            const isActive = index === 0 && location.pathname === '/shop'
            return (
              <button
                key={label}
                type="button"
                onClick={() => { navigate(href); setMobileMenuOpen(false); menuButtonRef.current?.focus() }}
                aria-current={isActive ? 'page' : undefined}
                className={`w-full flex items-center gap-3 px-3 py-2.5 text-sm transition-all text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf cursor-pointer ${
                  isActive
                    ? 'bg-sage-tint text-leaf border-l-[3px] border-leaf rounded-r-xl rounded-l-none font-semibold'
                    : 'text-ink-soft hover:text-ink hover:bg-sand/60 border-l-[3px] border-transparent font-medium rounded-xl'
                }`}
              >
                <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                {label}
              </button>
            )
          })}
        </nav>
        <div className="p-3 border-t border-border">
          <button
            type="button"
            onClick={logout}
            aria-label="Sign out"
            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm font-semibold text-ink-soft hover:bg-brick-tint/40 hover:text-brick-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf cursor-pointer"
          >
            <LogOut className="h-4 w-4" aria-hidden="true" /> Sign out
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Mobile top bar */}
        <header className="h-14 bg-surface border-b border-border flex items-center justify-between px-3 md:hidden shrink-0">
          <button
            ref={menuButtonRef}
            type="button"
            onClick={() => setMobileMenuOpen(true)}
            aria-label="Open navigation menu"
            aria-expanded={mobileMenuOpen}
            aria-controls="mobile-sidebar"
            className="w-11 h-11 flex items-center justify-center rounded-lg hover:bg-sand text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf cursor-pointer"
          >
            <Menu className="h-5 w-5" aria-hidden="true" />
          </button>
          <div className="flex items-center gap-2">
            <div className="h-6 w-6 rounded bg-sage-tint border border-leaf/30 flex items-center justify-center text-leaf">
              <Store className="h-3.5 w-3.5" aria-hidden="true" />
            </div>
            <span className="font-display font-bold text-sm text-ink">Merchant Operations</span>
          </div>
          <button
            type="button"
            onClick={logout}
            aria-label="Sign out"
            className="w-11 h-11 flex items-center justify-center rounded-lg hover:bg-sand text-ink-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf cursor-pointer"
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
          </button>
        </header>

        <main id="main-content" tabIndex={-1} className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 bg-paper focus:outline-none">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
