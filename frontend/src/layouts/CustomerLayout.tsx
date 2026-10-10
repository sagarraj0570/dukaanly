import { Outlet } from 'react-router-dom'
import { useAuthStore } from '@/store/useAuthStore'
import { ShoppingCart, User as UserIcon, LogOut, Store } from 'lucide-react'
import { Button } from '@/components/ui/button'

export const CustomerLayout = () => {
  const { user, logout } = useAuthStore()

  return (
    <div className="flex flex-col min-h-screen bg-white">
      <header className="border-b sticky top-0 bg-white z-10">
        <div className="flex items-center justify-between px-4 py-3 max-w-7xl mx-auto">
          <div className="flex items-center gap-2">
            <Store className="h-6 w-6 text-primary" />
            <span className="font-bold text-xl">Dukaanly</span>
          </div>
          <nav className="flex items-center gap-4">
            <Button variant="ghost" size="icon">
              <ShoppingCart className="h-5 w-5" />
            </Button>
            <div className="flex items-center gap-2">
              <UserIcon className="h-5 w-5 text-gray-500" />
              <span className="text-sm font-medium hidden sm:inline">{user?.name}</span>
            </div>
            <Button variant="ghost" size="icon" onClick={logout}>
              <LogOut className="h-5 w-5" />
            </Button>
          </nav>
        </div>
      </header>
      <main className="flex-1 w-full max-w-7xl mx-auto p-4 sm:p-6 lg:p-8">
        <Outlet />
      </main>
    </div>
  )
}
