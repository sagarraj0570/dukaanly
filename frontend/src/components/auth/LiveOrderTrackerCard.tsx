import React from 'react'
import { Bike, Store, MapPin } from 'lucide-react'

interface LiveOrderTrackerCardProps {
  className?: string
  style?: React.CSSProperties
}

export const LiveOrderTrackerCard: React.FC<LiveOrderTrackerCardProps> = ({
  className = '',
  style,
}) => {
  return (
    <div
      style={style}
      className={`relative select-none bg-white/15 backdrop-blur-md border border-white/25 rounded-2xl p-4 shadow-[0_8px_24px_rgba(15,61,46,0.22)] text-white ${className}`}
    >
      {/* Top row: Status pulse & ETA chip */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-400" />
          </span>
          <div>
            <h4 className="text-xs font-bold text-white tracking-tight leading-none">
              Order on the way
            </h4>
            <p className="text-[10px] text-white/75 mt-0.5 font-medium">
              Order #DK-4821
            </p>
          </div>
        </div>

        {/* ETA Chip in Marigold */}
        <div className="flex items-center gap-1 bg-accent-500 text-primary-950 font-extrabold text-[11px] px-2.5 py-1 rounded-full shadow-xs">
          <span>ETA</span>
          <span>18-25 min</span>
        </div>
      </div>

      {/* Mini animated route line */}
      <div className="relative mt-3.5 mb-2 h-10 w-full flex items-center">
        {/* Origin Store Pin */}
        <div className="z-10 flex flex-col items-center shrink-0">
          <div className="h-6 w-6 rounded-full bg-white/20 border border-white/40 flex items-center justify-center text-emerald-300">
            <Store className="h-3 w-3" />
          </div>
          <span className="text-[9px] text-white/70 font-medium mt-0.5">Shop</span>
        </div>

        {/* Route Line SVG with dash offset */}
        <div className="relative flex-1 mx-1.5 h-6">
          <svg
            viewBox="0 0 160 24"
            className="w-full h-full overflow-visible"
            fill="none"
            preserveAspectRatio="none"
          >
            {/* Background static path track */}
            <path
              d="M 4 12 Q 45 2 80 14 T 156 12"
              stroke="rgba(255, 255, 255, 0.25)"
              strokeWidth="2.5"
              strokeLinecap="round"
            />
            {/* Animated dashed active route */}
            <path
              d="M 4 12 Q 45 2 80 14 T 156 12"
              stroke="var(--accent-500, #F5A524)"
              strokeWidth="2.5"
              strokeLinecap="round"
              className="animate-route-dash"
            />
          </svg>

          {/* Rider Marker along route */}
          <div
            className="absolute top-1/2 left-[58%] -translate-y-1/2 -translate-x-1/2 h-6 w-6 rounded-full bg-white text-primary-700 shadow-md flex items-center justify-center ring-2 ring-accent-500"
            aria-label="Rider in transit"
          >
            <Bike className="h-3.5 w-3.5" />
          </div>
        </div>

        {/* Destination Customer Pin */}
        <div className="z-10 flex flex-col items-center shrink-0">
          <div className="h-6 w-6 rounded-full bg-accent-500/30 border border-accent-300 flex items-center justify-center text-accent-200">
            <MapPin className="h-3 w-3" />
          </div>
          <span className="text-[9px] text-white/70 font-medium mt-0.5">You</span>
        </div>
      </div>

      {/* Footer detail */}
      <div className="flex items-center justify-between text-[10px] text-white/80 pt-1.5 border-t border-white/10 font-medium">
        <span>Kankarbagh Daily → Boring Rd</span>
        <span className="text-emerald-300 font-semibold">2 items in bag</span>
      </div>
    </div>
  )
}

export default LiveOrderTrackerCard
