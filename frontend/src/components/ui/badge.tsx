import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

const badgeVariants = cva(
  "inline-flex items-center gap-1 font-semibold tracking-[0.04em] uppercase transition-colors select-none",
  {
    variants: {
      variant: {
        neutral: "bg-sand text-ink border border-border",
        success: "bg-sage-tint text-leaf",
        warning: "bg-turmeric-tint text-ink",
        danger: "bg-brick-tint text-brick-ink",
        count: "bg-turmeric text-ink rounded-full tabular-nums normal-case font-bold",
      },
      size: {
        default: "text-[12px] px-2.5 py-0.5 rounded-[8px]",
        sm: "text-[11px] px-2 py-0.5 rounded-[6px]",
        count: "text-[11px] h-5 min-w-5 px-1.5 flex items-center justify-center rounded-full",
      },
    },
    defaultVariants: {
      variant: "neutral",
      size: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, size, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant, size }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
