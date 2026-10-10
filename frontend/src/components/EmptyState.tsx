import { Store } from 'lucide-react'
import type { ReactNode } from 'react'

interface EmptyStateProps {
  title: string
  message: string
  icon?: ReactNode
  action?: ReactNode
}

export const EmptyState = ({ title, message, icon, action }: EmptyStateProps) => {
  return (
    <div className="flex flex-col items-center justify-center p-8 text-center min-h-[300px] border rounded-lg bg-gray-50 border-dashed">
      <div className="h-12 w-12 bg-gray-100 rounded-full flex items-center justify-center mb-4 text-gray-400">
        {icon || <Store className="h-6 w-6" />}
      </div>
      <h3 className="text-lg font-semibold text-gray-900 mb-1">{title}</h3>
      <p className="text-sm text-gray-500 max-w-sm mb-4">{message}</p>
      {action && <div>{action}</div>}
    </div>
  )
}
