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
    <div className="flex flex-col items-center justify-center p-12 text-center min-h-[280px] rounded-xl border border-dashed border-border bg-muted/30">
      <div className="h-16 w-16 bg-primary/10 rounded-2xl flex items-center justify-center mb-5 text-primary">
        {icon || <Store className="h-7 w-7" />}
      </div>
      <h3 className="text-lg font-semibold text-foreground mb-1.5">{title}</h3>
      <p className="text-sm text-muted-foreground max-w-sm leading-relaxed mb-5">{message}</p>
      {action && <div>{action}</div>}
    </div>
  )
}
