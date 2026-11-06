import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/store/useAuthStore'
import { LogOut, Navigation, CheckCircle2 } from 'lucide-react'

export const RiderLayout = () => {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()

  const scrollToSection = (id: string) => {
    if (location.pathname !== '/rider') {
      navigate('/rider')
      setTimeout(() => {
        document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
      }, 100)
    } else {
      document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
    }
  }

  return (
    <div className="flex flex-col min-h-screen bg-paper text-ink">
      {/* Skip Navigation Link */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:px-4 focus:py-2 focus:bg-leaf focus:text-white focus:rounded-lg focus:shadow-lg focus:outline-none focus:ring-2 focus:ring-leaf"
      >
        Skip to main content
      </a>

      {/* Top Header */}
      <header className="sticky top-0 z-40 bg-paper border-b border-border">
        <div className="flex items-center justify-between px-4 sm:px-6 py-3 max-w-4xl mx-auto">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => navigate('/rider')}
              className="flex items-center gap-2.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf rounded-lg cursor-pointer"
            >
              <span className="font-display font-bold text-xl sm:text-2xl tracking-tight text-ink">
                Dukaan<span className="text-leaf">ly</span>
              </span>
              <span className="text-[10px] sm:text-[11px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-turmeric-tint text-turmeric-ink border border-turmeric-ink/20">
                Rider
              </span>
            </button>

            {/* Desktop inline section tabs */}
            <div className="hidden md:flex items-center gap-1 ml-6 border-l border-border pl-6">
              <button
                type="button"
                onClick={() => {
                  if (location.pathname !== '/rider') navigate('/rider')
                  else window.scrollTo({ top: 0, behavior: 'smooth' })
                }}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
                  location.pathname === '/rider'
                    ? 'bg-sage-tint text-leaf'
                    : 'text-ink-soft hover:text-ink hover:bg-sand'
                }`}
              >
                Active Deliveries
              </button>
              <button
                type="button"
                onClick={() => scrollToSection('rider-history')}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold text-ink-soft hover:text-ink hover:bg-sand transition cursor-pointer"
              >
                Completed
              </button>
            </div>
          </div>

          <div className="flex items-center gap-2 sm:gap-3">
            <div className="flex items-center gap-1.5 bg-sand border border-border rounded-full px-2.5 sm:px-3 py-1">
              <span className="h-2 w-2 rounded-full bg-leaf" />
              <span className="text-xs font-semibold text-ink">
                {user?.name?.split(' ')[0] || 'Rider'}
              </span>
            </div>
            <button
              type="button"
              onClick={logout}
              className="p-1.5 sm:p-2 rounded-xl text-ink-soft hover:text-ink hover:bg-sand transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf cursor-pointer"
              title="Sign out"
              aria-label="Sign out"
            >
              <LogOut className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main id="main-content" tabIndex={-1} className="flex-1 w-full max-w-4xl mx-auto pt-5 pb-24 md:pb-10 px-4 sm:px-6 focus:outline-none">
        <Outlet />
      </main>

      {/* Bottom Field Bar (Mobile only: below 768px) */}
      <nav
        aria-label="Rider bottom navigation"
        className="fixed bottom-0 left-0 right-0 z-40 bg-surface/95 backdrop-blur-md border-t border-border shadow-elevated pb-safe md:hidden"
      >
        <div className="max-w-md mx-auto grid grid-cols-2 px-4 py-1">
          <button
            type="button"
            aria-current={location.pathname === '/rider' ? 'page' : undefined}
            onClick={() => {
              if (location.pathname !== '/rider') navigate('/rider')
              else window.scrollTo({ top: 0, behavior: 'smooth' })
            }}
            className={`flex flex-col items-center gap-1 py-2 text-[11px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf rounded-xl cursor-pointer ${
              location.pathname === '/rider' ? 'text-leaf' : 'text-ink-soft'
            }`}
          >
            <div
              className={`p-1.5 rounded-xl transition-colors ${
                location.pathname === '/rider' ? 'bg-sage-tint' : ''
              }`}
            >
              <Navigation className="h-4 w-4" aria-hidden="true" />
            </div>
            Active
          </button>

          <button
            type="button"
            onClick={() => scrollToSection('rider-history')}
            className="flex flex-col items-center gap-1 py-2 text-[11px] font-semibold text-ink-soft hover:text-ink transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf rounded-xl cursor-pointer"
          >
            <div className="p-1.5 rounded-xl">
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
            </div>
            Completed
          </button>
        </div>
      </nav>
    </div>
  )
}
