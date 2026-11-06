import * as React from "react"
import { cn } from "cn"

export type StatusStampTone = "success" | "warning" | "danger" | "neutral"

export interface StatusStampProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: StatusStampTone
  children: React.ReactNode
  className?: string
}

export function orderStatusTone(status: string): StatusStampTone {
  const normalized = (status || "").toLowerCase().trim()
  switch (normalized) {
    case "pending":
    case "confirmed":
    case "preparing":
    case "offered":
      return "warning"
    case "ready_for_pickup":
    case "out_for_delivery":
    case "assigned":
    case "picked_up":
      return "neutral"
    case "delivered":
    case "accepted":
      return "success"
    case "cancelled":
    case "rejected":
    case "expired":
      return "danger"
    default:
      return "neutral"
  }
}

const toneStyles: Record<StatusStampTone, { color: string; bg: string }> = {
  success: {
    color: "var(--leaf)",
    bg: "var(--sage-tint)",
  },
  warning: {
    color: "var(--turmeric-ink)",
    bg: "var(--turmeric-tint)",
  },
  danger: {
    color: "var(--brick-ink)",
    bg: "var(--brick-tint)",
  },
  neutral: {
    color: "var(--ink-soft)",
    bg: "var(--sand)",
  },
}

export const StatusStamp: React.FC<StatusStampProps> = ({
  tone = "neutral",
  children,
  className,
  style,
  ...props
}) => {
  const currentTone = toneStyles[tone] || toneStyles.neutral

  return (
    <span
      className={cn(
        "inline-block uppercase text-[12px] font-bold tracking-[0.08em] px-2.5 py-1 border-[1.5px] border-current rounded-[6px] select-none leading-none rotate-[-2deg]",
        className
      )}
      style={{
        color: currentTone.color,
        backgroundColor: currentTone.bg,
        ...style,
      }}
      {...props}
    >
      {children}
    </span>
  )
}
StatusStamp.displayName = "StatusStamp"
