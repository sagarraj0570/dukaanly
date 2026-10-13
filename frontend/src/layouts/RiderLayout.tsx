import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/store/useAuthStore'
import { LogOut, Bike, Navigation, CheckCircle2, ShieldCheck } from 'lucide-react'

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
    <div className="flex flex-col min-h-screen bg-[#FAF9F6] text-[#202923]">
      {/* Mobile-First Top Bar */}
      <header className="sticky top-0 z-40 bg-gradient-to-r from-[#176B45] to-[#104B32] text-white shadow-sm">
        <div className="flex items-center justify-between px-4 py-3.5 max-w-lg mx-auto">
          <button
            type="button"
            onClick={() => navigate('/rider')}
            className="flex items-center gap-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white rounded-lg"
          >
            <div className="h-9 w-9 rounded-xl bg-white/15 border border-white/20 flex items-center justify-center shadow-xs">
              <Bike className="h-5 w-5 text-white" aria-hidden="true" />
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-bold text-base tracking-tight leading-none">
                  Dukaanly
                </span>
                <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-[#A8D5B5]/25 text-[#A8D5B5] border border-[#A8D5B5]/30">
                  Rider
                </span>
              </div>
              <span className="text-white/90 text-[11px] block mt-0.5">
                Field Dispatch Console
              </span>
            </div>
          </button>

          <div className="flex items-center gap-2.5">
            <div className="flex items-center gap-1.5 bg-white/12 border border-white/15 rounded-full px-3 py-1">
              <span className="h-2 w-2 rounded-full bg-[#A8D5B5] animate-pulse" />
              <span className="text-xs font-semibold text-white">
                {user?.name?.split(' ')[0] || 'Rider'}
              </span>
            </div>
            <button
              type="button"
              onClick={logout}
              className="p-2 rounded-xl bg-white/10 hover:bg-white/20 text-white/90 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
              title="Sign out"
              aria-label="Sign out"
            >
              <LogOut className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        </div>
      </header>

      {/* Compact Mobile-First Main Container */}
      <main className="flex-1 w-full max-w-lg mx-auto pt-5 pb-28 px-4">
        <Outlet />
      </main>

      {/* Bottom Field Bar */}
      <nav
        aria-label="Rider bottom navigation"
        className="fixed bottom-0 left-0 right-0 z-40 bg-white/95 backdrop-blur-md border-t border-[#E5E9E4] shadow-elevated pb-safe"
      >
        <div className="max-w-lg mx-auto grid grid-cols-3 px-2">
          <button
            type="button"
            aria-current={location.pathname === '/rider' ? 'page' : undefined}
            onClick={() => navigate('/rider')}
            className={`flex flex-col items-center gap-1 py-2.5 text-[11px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45] rounded-xl ${
              location.pathname === '/rider' ? 'text-[#176B45]' : 'text-[#69736C]'
            }`}
          >
            <div
              className={`p-1.5 rounded-xl transition-colors ${
                location.pathname === '/rider' ? 'bg-[#EDF5EE]' : ''
              }`}
            >
              <Navigation className="h-4 w-4" aria-hidden="true" />
            </div>
            Active Queue
          </button>

          <button
            type="button"
            onClick={() => scrollToSection('rider-history')}
            className="flex flex-col items-center gap-1 py-2.5 text-[11px] font-semibold text-[#69736C] hover:text-[#176B45] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45] rounded-xl"
          >
            <div className="p-1.5 rounded-xl">
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
            </div>
            Completed
          </button>

          <button
            type="button"
            onClick={() => scrollToSection('rider-duty-card')}
            className="flex flex-col items-center gap-1 py-2.5 text-[11px] font-semibold text-[#69736C] hover:text-[#176B45] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#176B45] rounded-xl"
          >
            <div className="p-1.5 rounded-xl">
              <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            </div>
            Duty Status
          </button>
        </div>
      </nav>
    </div>
  )
}
