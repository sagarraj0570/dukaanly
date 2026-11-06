import * as React from "react"
import { cn } from "cn"

export type BazaarPatternVariant = "strip" | "fill"

export interface BazaarPatternProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: BazaarPatternVariant
  className?: string
}

const SVG_PATTERN_DATA_URI =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'%3E%3Cpath d='M12 3l5 5-5 5-5-5z' fill='none' stroke='%231E2A24' stroke-opacity='0.06' stroke-width='1'/%3E%3Ccircle cx='12' cy='19' r='1.2' fill='%231E2A24' fill-opacity='0.06'/%3E%3C/svg%3E\")"

export const BazaarPattern: React.FC<BazaarPatternProps> = ({
  variant = "strip",
  className,
  style,
  ...props
}) => {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "pointer-events-none select-none",
        variant === "strip" ? "h-[12px] w-full block" : "absolute inset-0 w-full h-full",
        className
      )}
      style={{
        backgroundImage: SVG_PATTERN_DATA_URI,
        backgroundRepeat: "repeat",
        backgroundSize: "24px 24px",
        ...style,
      }}
      {...props}
    />
  )
}
BazaarPattern.displayName = "BazaarPattern"
