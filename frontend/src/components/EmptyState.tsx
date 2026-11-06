import { lazy, Suspense, type ReactNode } from 'react'
import { Store } from 'lucide-react'

// Lazy-load 3D EmptyState component
const EmptyState3D = lazy(() => import('@/components/three/EmptyState3D'))

export interface EmptyStateProps {
  title: string
  message: string
  icon?: ReactNode
  action?: ReactNode
  illustrationType?: 'cart' | 'search' | 'orders' | 'inventory' | 'store'
}

export const EmptyState = ({
  title,
  message,
  icon,
  action,
  illustrationType,
}: EmptyStateProps) => {
  return (
    <div className="flex flex-col items-center justify-center p-12 text-center min-h-[280px] rounded-2xl border border-dashed border-border bg-surface-alt/40">
      {illustrationType ? (
        <div className="mb-4 flex items-center justify-center min-h-[128px]">
          <Suspense
            fallback={
              <div className="h-16 w-16 bg-primary-50 rounded-2xl flex items-center justify-center text-primary-700 border border-primary-200">
                {icon || <Store className="h-7 w-7" />}
              </div>
            }
          >
            <EmptyState3D type={illustrationType} className="h-32 w-36" />
          </Suspense>
        </div>
      ) : (
        <div className="h-16 w-16 bg-primary-50 rounded-2xl flex items-center justify-center mb-5 text-primary-700 border border-primary-200">
          {icon || <Store className="h-7 w-7" />}
        </div>
      )}

      <h3 className="text-lg font-semibold text-text-primary mb-1.5">{title}</h3>
      <p className="text-sm text-text-secondary max-w-sm leading-relaxed mb-5">{message}</p>
      {action && <div>{action}</div>}
    </div>
  )
}
export default EmptyState
