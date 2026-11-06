import React from 'react'

/**
 * Hand-authored vector illustration of the iconic Patna skyline.
 * Highlights Golghar (the historic beehive stupa-granary with spiral stairs)
 * alongside low-rise bazaar storefronts, roadside trees, delivery rider silhouette,
 * and the gentle curve of the Ganga river.
 *
 * Uses tone-on-tone low-contrast rendering so it creates depth without visual clutter.
 */
export const PatnaSkyline: React.FC<{ className?: string }> = ({ className = '' }) => {
  return (
    <svg
      viewBox="0 0 600 200"
      preserveAspectRatio="xMidYMax slice"
      className={`w-full pointer-events-none select-none text-primary-200/25 ${className}`}
      fill="currentColor"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="skylineGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.45" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0.15" />
        </linearGradient>
        <linearGradient id="riverGrad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.1" />
          <stop offset="50%" stopColor="currentColor" stopOpacity="0.25" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0.1" />
        </linearGradient>
      </defs>

      {/* Far Background: Distant tree silhouettes & bridge curve */}
      <g opacity="0.6">
        {/* Mahatma Gandhi Setu bridge suggestion curve */}
        <path
          d="M0 155 Q150 125 320 135 T600 120"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeDasharray="4 4"
          opacity="0.4"
        />
        {/* River banks & distant foliage */}
        <circle cx="50" cy="148" r="16" fill="currentColor" opacity="0.2" />
        <circle cx="75" cy="145" r="14" fill="currentColor" opacity="0.25" />
        <circle cx="490" cy="146" r="18" fill="currentColor" opacity="0.2" />
        <circle cx="520" cy="142" r="15" fill="currentColor" opacity="0.25" />
      </g>

      {/* Midground: Golghar Hero Monument & Neighbourhood Bazaar */}
      {/* ─── Golghar (Patna's landmark granary) ─── */}
      <g transform="translate(180, 50)">
        {/* Plinth Base */}
        <rect x="0" y="115" width="130" height="12" rx="3" fill="url(#skylineGrad)" />
        <rect x="10" y="105" width="110" height="10" rx="2" fill="url(#skylineGrad)" />

        {/* Beehive / Stupa Dome */}
        <path
          d="M20 105 C20 40 40 18 65 18 C90 18 110 40 110 105 Z"
          fill="url(#skylineGrad)"
        />

        {/* Top Cupola / Observation Deck */}
        <rect x="58" y="12" width="14" height="6" rx="1.5" fill="currentColor" opacity="0.6" />
        <path d="M55 12 L65 4 L75 12 Z" fill="currentColor" opacity="0.7" />

        {/* Spiral Staircase Curves wrapping around the exterior */}
        <path
          d="M22 102 C25 80 45 65 65 65 C85 65 105 80 108 102"
          fill="none"
          stroke="rgba(255,255,255,0.28)"
          strokeWidth="2.5"
        />
        <path
          d="M28 80 C35 55 50 40 65 40 C80 40 95 55 102 80"
          fill="none"
          stroke="rgba(255,255,255,0.22)"
          strokeWidth="2"
        />
        <path
          d="M38 55 C45 35 55 26 65 26 C75 26 85 35 92 55"
          fill="none"
          stroke="rgba(255,255,255,0.2)"
          strokeWidth="1.5"
        />
      </g>

      {/* ─── Left Bazaar Buildings ─── */}
      <g transform="translate(10, 80)">
        {/* Storefront 1 */}
        <rect x="10" y="55" width="45" height="45" rx="3" fill="url(#skylineGrad)" />
        {/* Slanted Awning */}
        <path d="M5 55 L32 40 L60 55 Z" fill="currentColor" opacity="0.5" />
        {/* Door and window lines */}
        <rect x="22" y="70" width="14" height="30" rx="1" fill="rgba(255,255,255,0.15)" />
        <rect x="40" y="65" width="10" height="12" rx="1" fill="rgba(255,255,255,0.15)" />

        {/* Storefront 2 (Two-story Kirana) */}
        <rect x="65" y="35" width="55" height="65" rx="3" fill="url(#skylineGrad)" />
        <rect x="72" y="44" width="16" height="14" rx="1.5" fill="rgba(255,255,255,0.18)" />
        <rect x="96" y="44" width="16" height="14" rx="1.5" fill="rgba(255,255,255,0.18)" />
        <rect x="78" y="72" width="28" height="28" rx="2" fill="rgba(255,255,255,0.15)" />
        {/* Awning stripe */}
        <path d="M60 70 L92 63 L125 70 Z" fill="currentColor" opacity="0.45" />

        {/* Street tree */}
        <circle cx="140" cy="55" r="18" fill="currentColor" opacity="0.35" />
        <rect x="138" y="68" width="4" height="32" rx="1" fill="currentColor" opacity="0.5" />
      </g>

      {/* ─── Right Bazaar & Modern Hyperlocal Buildings ─── */}
      <g transform="translate(330, 75)">
        {/* Roadside tree */}
        <circle cx="20" cy="50" r="16" fill="currentColor" opacity="0.3" />
        <rect x="18" y="62" width="4" height="38" rx="1" fill="currentColor" opacity="0.45" />

        {/* Building 3 with signboard */}
        <rect x="45" y="30" width="60" height="70" rx="3" fill="url(#skylineGrad)" />
        <rect x="52" y="38" width="46" height="10" rx="2" fill="rgba(255,255,255,0.22)" />
        <rect x="54" y="56" width="18" height="16" rx="1.5" fill="rgba(255,255,255,0.16)" />
        <rect x="78" y="56" width="18" height="16" rx="1.5" fill="rgba(255,255,255,0.16)" />
        <rect x="62" y="78" width="26" height="22" rx="2" fill="rgba(255,255,255,0.14)" />

        {/* Building 4 with rooftop solar & water tank */}
        <rect x="115" y="45" width="55" height="55" rx="3" fill="url(#skylineGrad)" />
        <rect x="125" y="32" width="16" height="13" rx="2" fill="currentColor" opacity="0.5" />
        <line x1="148" y1="35" x2="162" y2="45" stroke="currentColor" strokeWidth="2" opacity="0.5" />

        {/* Street lamp */}
        <line x1="185" y1="52" x2="185" y2="100" stroke="currentColor" strokeWidth="2" opacity="0.4" />
        <circle cx="185" cy="50" r="4" fill="var(--accent-500, #F5A524)" opacity="0.75" />

        {/* Building 5 (Boutique/Medical store) */}
        <rect x="198" y="50" width="50" height="50" rx="3" fill="url(#skylineGrad)" />
        <path d="M194 50 L223 38 L252 50 Z" fill="currentColor" opacity="0.4" />
      </g>

      {/* ─── Foreground: Road & Ganga River Waves Line ─── */}
      <g transform="translate(0, 168)">
        {/* River Water Surface with gentle ripples */}
        <path
          d="M0 12 C60 6 120 18 180 12 C240 6 300 18 360 12 C420 6 480 18 540 12 C570 9 590 11 600 12 L600 32 L0 32 Z"
          fill="url(#riverGrad)"
        />
        <path
          d="M20 20 C80 16 140 24 200 20 C260 16 320 24 380 20 C440 16 500 24 560 20"
          fill="none"
          stroke="rgba(255,255,255,0.22)"
          strokeWidth="1.5"
          opacity="0.7"
        />
        <path
          d="M60 25 C120 22 180 28 240 25 C300 22 360 28 420 25 C480 22 540 28 580 25"
          fill="none"
          stroke="rgba(255,255,255,0.15)"
          strokeWidth="1"
          opacity="0.5"
        />
      </g>
    </svg>
  )
}

export default PatnaSkyline
