import { Outlet } from 'react-router-dom'
import { useAuthStore } from '@/store/useAuthStore'
import { LogOut, Bike, MapPin, History } from 'lucide-react'
import { Button } from '@/components/ui/button'

export const RiderLayout = () => {
  const { user, logout } = useAuthStore()

  return (
    <div className="flex flex-col min-h-screen bg-gray-100">
      <header className="bg-primary text-primary-foreground sticky top-0 z-10 shadow-md">
        <div className="flex items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2">
            <Bike className="h-6 w-6" />
            <span className="font-bold text-lg">Rider App</span>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm font-medium hidden sm:inline">{user?.name}</span>
            <Button variant="ghost" size="icon" className="text-primary-foreground hover:bg-primary/90" onClick={logout}>
              <LogOut className="h-5 w-5" />
            </Button>
          </div>
        </div>
      </header>
      <main className="flex-1 w-full max-w-lg mx-auto pb-20">
        {/* pb-20 for bottom navigation padding */}
        <Outlet />
      </main>
      
      {/* Mobile Bottom Navigation */}
      <nav className="fixed bottom-0 w-full bg-white border-t flex justify-around p-3 pb-safe z-10 sm:hidden">
        <button className="flex flex-col items-center text-primary">
          <MapPin className="h-6 w-6" />
          <span className="text-xs mt-1">Active</span>
        </button>
        <button className="flex flex-col items-center text-gray-400">
          <History className="h-6 w-6" />
          <span className="text-xs mt-1">History</span>
        </button>
      </nav>
    </div>
  )
}
