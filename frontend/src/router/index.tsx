import { createBrowserRouter, Navigate } from 'react-router-dom'
import { RootLayout } from '@/layouts/RootLayout'
import { CustomerLayout } from '@/layouts/CustomerLayout'
import { ShopLayout } from '@/layouts/ShopLayout'
import { RiderLayout } from '@/layouts/RiderLayout'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { Login } from '@/pages/Login'
import { CustomerDashboard } from '@/pages/CustomerDashboard'
import { ShopDetail } from '@/pages/ShopDetail'
import { ProductDetail } from '@/pages/ProductDetail'
import { CustomerCart } from '@/pages/CustomerCart'
import { CustomerCheckout } from '@/pages/CustomerCheckout'
import { CustomerPayment } from '@/pages/CustomerPayment'
import { CustomerOrderConfirmation } from '@/pages/CustomerOrderConfirmation'
import { ShopDashboard } from '@/pages/ShopDashboard'
import { RiderDashboard } from '@/pages/RiderDashboard'
import { RiderDeliveryDetail } from '@/pages/RiderDeliveryDetail'

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <Login />
  },
  {
    path: '/',
    element: <RootLayout />,
    children: [
      {
        path: '/',
        element: <Navigate to="/login" replace />
      },
      // Customer Routes
      {
        path: '/customer',
        element: <ProtectedRoute allowedRoles={['customer']} />,
        children: [
          {
            element: <CustomerLayout />,
            children: [
              { index: true, element: <CustomerDashboard /> },
              { path: 'shops/:id', element: <ShopDetail /> },
              { path: 'products/:id', element: <ProductDetail /> },
              { path: 'cart', element: <CustomerCart /> },
              { path: 'checkout', element: <CustomerCheckout /> },
              { path: 'payment/:id', element: <CustomerPayment /> },
              { path: 'orders/:id/confirmation', element: <CustomerOrderConfirmation /> }
            ]
          }
        ]
      },
      // Shop Owner Routes
      {
        path: '/shop',
        element: <ProtectedRoute allowedRoles={['shop_owner']} />,
        children: [
          {
            element: <ShopLayout />,
            children: [
              { index: true, element: <ShopDashboard /> }
            ]
          }
        ]
      },
      // Rider Routes
      {
        path: '/rider',
        element: <ProtectedRoute allowedRoles={['rider']} />,
        children: [
          {
            element: <RiderLayout />,
            children: [
              { index: true, element: <RiderDashboard /> },
              { path: 'deliveries/:id', element: <RiderDeliveryDetail /> }
            ]
          }
        ]
      }
    ]
  },
  {
    path: '/unauthorized',
    element: <div className="p-8 text-center text-red-500 text-xl font-bold">403 - Unauthorized Access</div>
  },
  {
    path: '*',
    element: <div className="p-8 text-center text-xl font-bold">404 - Not Found</div>
  }
])
