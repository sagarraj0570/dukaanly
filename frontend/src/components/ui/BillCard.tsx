import * as React from "react"
import { cn } from "cn"

export interface BillRow {
  label: string
  value: string
  sub?: string
  emphasis?: boolean
}

export interface BillCardProps {
  title?: string
  rows: BillRow[]
  footer?: { label: string; value: string }
  note?: string
  className?: string
}

export const BillCard: React.FC<BillCardProps> = ({
  title,
  rows,
  footer,
  note,
  className,
}) => {
  return (
    <div
      className={cn(
        "rounded-[14px] border border-border bg-surface p-5 text-ink shadow-none",
        className
      )}
    >
      {(title || note) && (
        <div className="mb-4 border-b border-border pb-3">
          {title && (
            <h3 className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">
              {title}
            </h3>
          )}
          {note && (
            <p className="mt-0.5 text-xs text-ink-soft">
              {note}
            </p>
          )}
        </div>
      )}

      <dl className="space-y-2.5">
        {rows.map((row, idx) => (
          <div
            key={idx}
            className={cn(
              "text-sm",
              row.emphasis && "font-bold"
            )}
          >
            <div className="flex items-baseline gap-2">
              <dt className="text-ink">
                <span>{row.label}</span>
                {row.sub && (
                  <span className="block text-xs font-normal text-ink-soft">
                    {row.sub}
                  </span>
                )}
              </dt>
              <span
                aria-hidden="true"
                className="flex-1 border-b-[1.5px] border-dotted translate-y-[-3px]"
                style={{ borderColor: "var(--border-strong)" }}
              />
              <dd className="num font-semibold text-ink ml-0 shrink-0">
                {row.value}
              </dd>
            </div>
          </div>
        ))}

        {footer && (
          <div
            className="mt-4 pt-3.5 flex items-baseline justify-between gap-2"
            style={{ borderTop: "1.5px dashed var(--border-strong)" }}
          >
            <dt className="font-display text-[18px] font-semibold text-ink">
              {footer.label}
            </dt>
            <span
              aria-hidden="true"
              className="flex-1 border-b-[1.5px] border-dotted translate-y-[-4px]"
              style={{ borderColor: "var(--border-strong)" }}
            />
            <dd className="font-display text-[22px] font-bold num text-ink ml-0 shrink-0">
              {footer.value}
            </dd>
          </div>
        )}
      </dl>
    </div>
  )
}
BillCard.displayName = "BillCard"
