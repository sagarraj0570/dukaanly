import { AlertCircle, RefreshCw } from 'lucide-react'
import { Button } from './ui/button'

interface ErrorStateProps {
  title?: string
  message?: string
  onRetry?: () => void
}

export const ErrorState = ({
  title = 'Something went wrong',
  message = 'We encountered an error while loading this data.',
  onRetry,
}: ErrorStateProps) => {
  return (
    <div className="flex flex-col items-center justify-center p-12 text-center min-h-[280px] rounded-xl border border-red-100 bg-red-50/50">
      <div className="h-14 w-14 bg-red-100 rounded-2xl flex items-center justify-center mb-4">
        <AlertCircle className="h-7 w-7 text-red-500" />
      </div>
      <h3 className="text-lg font-semibold text-foreground mb-1.5">{title}</h3>
      <p className="text-sm text-muted-foreground max-w-md leading-relaxed mb-5">{message}</p>
      {onRetry && (
        <Button variant="outline" onClick={onRetry} size="sm" className="gap-2">
          <RefreshCw className="h-3.5 w-3.5" />
          Try Again
        </Button>
      )}
    </div>
  )
}
