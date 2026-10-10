import { Outlet } from 'react-router-dom'
import { useAuthStore } from '@/store/useAuthStore'
import { ShoppingCart, User as UserIcon, LogOut, Store } from 'lucide-react'
import { Button } from '@/components/ui/button'

import { useCart } from '@/hooks/useCart'
import { useNavigate } from 'react-router-dom'

const CartButton = () => {
  const { data } = useCart()
  const navigate = useNavigate()
  
  const itemCount = data?.items?.reduce((total, item) => total + item.quantity, 0) || 0

  return (
    <Button variant="ghost" size="icon" className="relative" onClick={() => navigate('/customer/cart')}>
      <ShoppingCart className="h-5 w-5" />
      {itemCount > 0 && (
        <span className="absolute top-0 right-0 inline-flex items-center justify-center px-1.5 py-0.5 text-xs font-bold leading-none text-white transform translate-x-1/4 -translate-y-1/4 bg-red-600 rounded-full">
          {itemCount}
        </span>
      )}
    </Button>
  )
}

export const CustomerLayout = () => {
  const { user, logout } = useAuthStore()

  return (
    <div className="flex flex-col min-h-screen bg-white">
      <header className="border-b sticky top-0 bg-white z-10">
        <div className="flex items-center justify-between px-4 py-3 max-w-7xl mx-auto">
          <div className="flex items-center gap-2 cursor-pointer" onClick={() => window.location.href = '/customer'}>
            <Store className="h-6 w-6 text-primary" />
            <span className="font-bold text-xl">Dukaanly</span>
          </div>
          <nav className="flex items-center gap-2 sm:gap-4">
            <Button variant="ghost" size="sm" onClick={() => window.location.href = '/customer/orders'}>
              Orders
            </Button>
            <CartButton />
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
