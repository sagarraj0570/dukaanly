import * as React from "react"
import { cn } from "cn"

function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-[12px] bg-sand", className)}
      {...props}
    />
  )
}

export { Skeleton }
