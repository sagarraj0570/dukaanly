import { Outlet, ScrollRestoration } from 'react-router-dom'

export const RootLayout = () => {
  return (
    <div className="min-h-screen flex flex-col bg-[#FAF9F6]">
      <ScrollRestoration />
      <Outlet />
    </div>
  )
}
