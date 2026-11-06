import * as React from "react"
import { cn } from "cn"

interface TabsContextValue {
  value: string
  onValueChange: (val: string) => void
}

const TabsContext = React.createContext<TabsContextValue | null>(null)

export interface TabsProps extends React.HTMLAttributes<HTMLDivElement> {
  defaultValue?: string
  value?: string
  onValueChange?: (value: string) => void
}

export const Tabs: React.FC<TabsProps> = ({
  defaultValue = "",
  value: controlledValue,
  onValueChange,
  className,
  children,
  ...props
}) => {
  const [uncontrolledValue, setUncontrolledValue] = React.useState(defaultValue)
  const isControlled = controlledValue !== undefined
  const value = isControlled ? controlledValue : uncontrolledValue

  const handleValueChange = React.useCallback(
    (newVal: string) => {
      if (!isControlled) setUncontrolledValue(newVal)
      onValueChange?.(newVal)
    },
    [isControlled, onValueChange]
  )

  return (
    <TabsContext.Provider value={{ value, onValueChange: handleValueChange }}>
      <div className={cn("w-full", className)} {...props}>
        {children}
      </div>
    </TabsContext.Provider>
  )
}

export const TabsList = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "flex items-center gap-6 border-b border-border bg-transparent",
      className
    )}
    role="tablist"
    {...props}
  />
))
TabsList.displayName = "TabsList"

export const TabsTrigger = React.forwardRef<
  HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement> & { value: string }
>(({ className, value, children, ...props }, ref) => {
  const ctx = React.useContext(TabsContext)
  const isActive = ctx?.value === value

  return (
    <button
      ref={ref}
      type="button"
      role="tab"
      aria-selected={isActive}
      onClick={() => ctx?.onValueChange(value)}
      className={cn(
        "relative pb-3 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf",
        isActive
          ? "text-ink border-b-2 border-leaf -mb-[1px]"
          : "text-ink-soft hover:text-ink border-b-2 border-transparent",
        className
      )}
      {...props}
    >
      {children}
    </button>
  )
})
TabsTrigger.displayName = "TabsTrigger"

export const TabsContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & { value: string }
>(({ className, value, children, ...props }, ref) => {
  const ctx = React.useContext(TabsContext)
  if (ctx?.value !== value) return null

  return (
    <div
      ref={ref}
      role="tabpanel"
      className={cn("pt-4 focus-visible:outline-none", className)}
      {...props}
    >
      {children}
    </div>
  )
})
TabsContent.displayName = "TabsContent"
