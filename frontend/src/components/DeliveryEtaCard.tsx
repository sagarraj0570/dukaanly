import React, { useState } from 'react'
import { Clock, AlertCircle, ChevronDown, ChevronUp, CheckCircle2, ShieldAlert } from 'lucide-react'
import type { DeliveryEtaResponse } from '@/hooks/useDeliveries'
import { StatusStamp } from '@/components/ui/StatusStamp'

interface DeliveryEtaCardProps {
  etaData: DeliveryEtaResponse | null | undefined
  isLoading?: boolean
  className?: string
}

export const DeliveryEtaCard: React.FC<DeliveryEtaCardProps> = ({
  etaData,
  isLoading = false,
  className = '',
}) => {
  const [showBreakdown, setShowBreakdown] = useState(false)

  if (isLoading && !etaData) {
    return (
      <div className={`bg-surface border border-border rounded-[14px] p-5 shadow-none animate-pulse space-y-3 ${className}`}>
        <div className="h-4 bg-sand rounded w-1/3" />
        <div className="h-8 bg-sand rounded w-1/2" />
        <div className="h-3 bg-sand rounded w-2/3" />
      </div>
    )
  }

  if (!etaData) {
    return null
  }

  const { status, eta, breakdown, delay_explanation } = etaData

  // Terminal state: Delivered
  if (status === 'delivered') {
    return (
      <div className={`bg-sage-tint/40 border border-border rounded-[14px] p-5 shadow-none ${className}`}>
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-full bg-sage-tint flex items-center justify-center text-leaf shrink-0 border border-leaf/30">
            <CheckCircle2 className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-display font-semibold text-base text-ink">Order Delivered</h3>
              <StatusStamp tone="success">Delivered</StatusStamp>
            </div>
            <p className="text-xs text-ink-soft mt-0.5">Delivered successfully. Thank you for ordering with Dukaanly!</p>
          </div>
        </div>
      </div>
    )
  }

  // Terminal state: Cancelled
  if (status === 'cancelled') {
    return (
      <div className={`bg-brick-tint/30 border border-border rounded-[14px] p-5 shadow-none ${className}`}>
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-full bg-brick-tint flex items-center justify-center text-brick-ink shrink-0 border border-brick-ink/30">
            <AlertCircle className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-display font-semibold text-base text-ink">Delivery Cancelled</h3>
              <StatusStamp tone="danger">Cancelled</StatusStamp>
            </div>
            <p className="text-xs text-ink-soft mt-0.5">This delivery was cancelled.</p>
          </div>
        </div>
      </div>
    )
  }

  // Calculate arrival window display
  let windowDisplay = ''
  if (eta.earliest_at && eta.latest_at) {
    const earliestMin = Math.max(1, Math.round((new Date(eta.earliest_at).getTime() - Date.now()) / 60000))
    const latestMin = Math.max(earliestMin + 2, Math.round((new Date(eta.latest_at).getTime() - Date.now()) / 60000))
    windowDisplay = `${earliestMin}–${latestMin} min`
  } else if (eta.remaining_seconds > 0) {
    const mins = Math.max(1, Math.round(eta.remaining_seconds / 60))
    windowDisplay = `~${mins} min`
  } else {
    windowDisplay = 'Arriving shortly'
  }

  const isFallback = eta.source === 'fallback_estimate'

  return (
    <div className={`bg-surface border border-border rounded-[14px] p-5 shadow-none space-y-4 ${className}`}>
      {/* Top Banner: Arrival Window */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border pb-4">
        <div>
          <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-ink-soft">
            <Clock className="h-3.5 w-3.5 text-ink-soft" />
            <span>Smart Delivery ETA</span>
          </div>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="font-display text-3xl sm:text-4xl font-semibold text-ink tracking-tight num">
              {windowDisplay}
            </span>
          </div>
          <p className="text-xs text-ink-soft mt-0.5">
            Estimated arrival &bull; Not a guaranteed delivery time
          </p>
        </div>

        {/* Source Badge & Status Pill */}
        <div className="flex sm:flex-col items-center sm:items-end gap-1.5">
          {isFallback && (
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-turmeric-tint text-turmeric-ink border border-turmeric-ink/30">
              <ShieldAlert className="h-3 w-3" />
              Traffic Fallback Estimate
            </span>
          )}
          {eta.calculated_at && (
            <span className="text-[11px] text-ink-soft">
              Updated {new Date(eta.calculated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
        </div>
      </div>

      {/* Delay Explanation Banner (if any) */}
      {delay_explanation && (
        <div className="bg-turmeric-tint/40 border border-turmeric-ink/20 rounded-xl p-3 flex items-start gap-2.5 text-xs text-turmeric-ink">
          <AlertCircle className="h-4 w-4 text-turmeric-ink shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            <span className="font-semibold text-ink">Update on your order:</span>
            <p className="text-ink-soft">{delay_explanation}</p>
          </div>
        </div>
      )}

      {/* Transparent Disclaimer */}
      <div className="text-xs text-ink-soft bg-sand p-3 rounded-xl border border-border flex items-center justify-between gap-2">
        <p className="text-[11px] leading-relaxed">
          Driving time is calculated from actual road routes, accounting for preparation, pickup, and handoff buffers.
        </p>
        <button
          type="button"
          onClick={() => setShowBreakdown((prev) => !prev)}
          className="shrink-0 text-[11px] font-bold text-ink hover:text-leaf inline-flex items-center gap-1 transition cursor-pointer"
        >
          <span>{showBreakdown ? 'Hide details' : 'View breakdown'}</span>
          {showBreakdown ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </button>
      </div>

      {/* Dynamic Breakdown Drawer */}
      {showBreakdown && breakdown && (
        <div className="pt-2 border-t border-border space-y-2 text-xs">
          <h4 className="font-semibold text-ink text-xs">ETA Component Breakdown</h4>
          <div className="grid grid-cols-2 gap-2 text-ink-soft">
            {breakdown.preparation_remaining_seconds > 0 && (
              <div className="p-2.5 bg-sand rounded-lg border border-border">
                <span className="block text-[11px] text-ink-soft">Remaining Prep</span>
                <span className="num font-semibold text-ink">~{Math.ceil(breakdown.preparation_remaining_seconds / 60)} mins</span>
              </div>
            )}
            {breakdown.assignment_wait_seconds > 0 && (
              <div className="p-2.5 bg-sand rounded-lg border border-border">
                <span className="block text-[11px] text-ink-soft">Rider Matching</span>
                <span className="num font-semibold text-ink">~{Math.ceil(breakdown.assignment_wait_seconds / 60)} mins</span>
              </div>
            )}
            {breakdown.pickup_travel_remaining_seconds > 0 && (
              <div className="p-2.5 bg-sand rounded-lg border border-border">
                <span className="block text-[11px] text-ink-soft">Rider to Shop</span>
                <span className="num font-semibold text-ink">~{Math.ceil(breakdown.pickup_travel_remaining_seconds / 60)} mins</span>
              </div>
            )}
            {breakdown.dropoff_travel_seconds > 0 && (
              <div className="p-2.5 bg-sand rounded-lg border border-border">
                <span className="block text-[11px] text-ink-soft">Delivery Road Travel</span>
                <span className="num font-semibold text-ink">~{Math.ceil(breakdown.dropoff_travel_seconds / 60)} mins</span>
              </div>
            )}
            {breakdown.handoff_buffer_seconds > 0 && (
              <div className="p-2.5 bg-sand rounded-lg border border-border">
                <span className="block text-[11px] text-ink-soft">Doorstep Handoff</span>
                <span className="num font-semibold text-ink">~{Math.ceil(breakdown.handoff_buffer_seconds / 60)} mins</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
