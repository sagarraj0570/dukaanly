import React from 'react'
import { CheckCircle2 } from 'lucide-react'

interface TrustChipProps {
  className?: string
  style?: React.CSSProperties
}

export const TrustChip: React.FC<TrustChipProps> = ({ className = '', style }) => {
  return (
    <div
      style={style}
      className={`inline-flex items-center gap-2 bg-white/20 backdrop-blur-md border border-white/30 rounded-full px-3.5 py-1.5 shadow-[0_6px_18px_rgba(15,61,46,0.18)] text-white select-none ${className}`}
    >
      <div className="h-5 w-5 rounded-full bg-emerald-500/30 flex items-center justify-center text-emerald-300">
        <CheckCircle2 className="h-3.5 w-3.5" />
      </div>
      <div className="flex items-center gap-1.5 text-xs font-semibold tracking-wide">
        <span>Verified local shops</span>
        <span className="text-white/40">•</span>
        <span className="text-[11px] text-accent-200 font-medium">Patna Kirana Partners</span>
      </div>
    </div>
  )
}

export default TrustChip
