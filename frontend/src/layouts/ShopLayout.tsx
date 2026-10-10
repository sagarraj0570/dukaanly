import { Outlet } from 'react-router-dom'
import { useAuthStore } from '@/store/useAuthStore'
import { LogOut, Package, Store, ClipboardList } from 'lucide-react'
import { Button } from '@/components/ui/button'

export const ShopLayout = () => {
  const { user, logout } = useAuthStore()

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r hidden md:flex flex-col">
        <div className="h-16 flex items-center px-6 border-b">
          <span className="font-bold text-xl text-primary">Shop Portal</span>
        </div>
        <nav className="flex-1 p-4 space-y-2">
          <Button variant="ghost" className="w-full justify-start">
            <Store className="mr-2 h-4 w-4" /> My Shop
          </Button>
          <Button variant="ghost" className="w-full justify-start">
            <Package className="mr-2 h-4 w-4" /> Products & Inventory
          </Button>
          <Button variant="ghost" className="w-full justify-start">
            <ClipboardList className="mr-2 h-4 w-4" /> Orders
          </Button>
        </nav>
        <div className="p-4 border-t">
          <div className="flex items-center gap-2 mb-4 px-2">
            <span className="text-sm font-medium">{user?.name}</span>
          </div>
          <Button variant="outline" className="w-full justify-start" onClick={logout}>
            <LogOut className="mr-2 h-4 w-4" /> Logout
          </Button>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-16 bg-white border-b flex items-center justify-between px-4 md:hidden">
          <span className="font-bold text-lg">Shop Portal</span>
          <Button variant="ghost" size="icon" onClick={logout}>
            <LogOut className="h-5 w-5" />
          </Button>
        </header>
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
