import { Outlet, ScrollRestoration } from 'react-router-dom'

export const RootLayout = () => {
  return (
    <div className="min-h-screen flex flex-col bg-bg text-text-primary">
      <ScrollRestoration />
      <Outlet />
    </div>
  )
}
