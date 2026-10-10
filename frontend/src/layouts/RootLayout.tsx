import { Outlet } from 'react-router-dom'

export const RootLayout = () => {
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Global Header or Notification Banner could go here */}
      <main className="flex-1 w-full max-w-7xl mx-auto p-4 sm:p-6 lg:p-8">
        <Outlet />
      </main>
    </div>
  )
}
