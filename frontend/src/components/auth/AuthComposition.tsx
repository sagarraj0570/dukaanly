import React, { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { Store, ArrowLeft, MapPin, Bike } from 'lucide-react'
import PatnaSkyline from './PatnaSkyline'
import LiveOrderTrackerCard from './LiveOrderTrackerCard'
import ProductStackCard from './ProductStackCard'
import TrustChip from './TrustChip'

export const AuthComposition: React.FC = () => {
  const containerRef = useRef<HTMLDivElement>(null)
  const [reduceMotion, setReduceMotion] = useState(false)
  const [mouseOffset, setMouseOffset] = useState({ x: 0, y: 0 })

  useEffect(() => {
    if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
      const query = window.matchMedia('(prefers-reduced-motion: reduce)')
      setReduceMotion(query.matches)
      const handler = (e: MediaQueryListEvent) => setReduceMotion(e.matches)
      query.addEventListener('change', handler)
      return () => query.removeEventListener('change', handler)
    }
  }, [])

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (reduceMotion || !containerRef.current) return
    const rect = containerRef.current.getBoundingClientRect()
    // Normalized offset from -1 to 1
    const x = ((e.clientX - rect.left) / rect.width - 0.5) * 2
    const y = ((e.clientY - rect.top) / rect.height - 0.5) * 2
    // Max 8px parallax
    setMouseOffset({ x: x * 8, y: y * 8 })
  }

  const handleMouseLeave = () => {
    setMouseOffset({ x: 0, y: 0 })
  }

  return (
    <div
      ref={containerRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      className="relative h-full w-full flex flex-col justify-between p-8 xl:p-12 overflow-hidden bg-gradient-to-br from-primary-700 via-primary-600 to-primary-900 text-white select-none"
    >
      {/* ─── Background Ambient Glows & Noise Mesh ──────────────────── */}
      {/* Marigold Glow in bottom right */}
      <div
        className="pointer-events-none absolute -bottom-24 -right-24 h-96 w-96 rounded-full blur-3xl opacity-25"
        style={{ background: 'var(--accent-500, #F5A524)' }}
      />
      {/* Soft Mint Glow in top left */}
      <div
        className="pointer-events-none absolute -top-24 -left-24 h-80 w-80 rounded-full blur-3xl opacity-20"
        style={{ background: 'var(--primary-200, #BFE5D0)' }}
      />
      {/* Faint Noise Overlay */}
      <div className="pointer-events-none absolute inset-0 opacity-[0.035] bg-gray-100/10 mix-blend-overlay" />

      {/* ─── Top: Logo & Back Link ─────────────────────────────────── */}
      <div className="relative z-20 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5 group">
          <div className="h-10 w-10 rounded-xl bg-white/20 backdrop-blur-md border border-white/30 text-white flex items-center justify-center shadow-xs transition-transform group-hover:scale-105">
            <Store className="h-5 w-5" />
          </div>
          <div>
            <span className="text-xl font-bold tracking-tight text-white">
              Dukaan<span className="text-accent-300">ly</span>
            </span>
            <p className="text-[10px] text-white/80 uppercase font-semibold tracking-wider">
              Patna Hyperlocal
            </p>
          </div>
        </Link>

        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-white/90 hover:text-white transition-all py-1.5 px-3.5 rounded-full bg-white/10 hover:bg-white/20 backdrop-blur-sm border border-white/15"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to Home
        </Link>
      </div>

      {/* ─── Headline & Hero Value Narrative ───────────────────────── */}
      <div className="relative z-20 mt-6 xl:mt-8">
        <h1 className="text-3xl xl:text-4xl font-extrabold tracking-tight text-white leading-[1.15]">
          Your neighbourhood,<br />
          <span className="text-accent-300 drop-shadow-xs">delivered.</span>
        </h1>
        <p className="text-sm xl:text-base text-white/85 mt-2.5 max-w-md font-normal leading-relaxed">
          Fresh groceries and daily essentials from trusted shops near you.
        </p>
      </div>

      {/* ─── Centerpiece: Layered Floating Frosted Glass Cards ──────── */}
      <div className="relative z-20 flex-1 my-6 min-h-[330px] flex items-center justify-center">
        {/* Parallax Container */}
        <div className="relative w-full max-w-[420px] h-[340px]">
          {/* Card 1: Live Order Tracker Card (Top Left) */}
          <div
            className={`absolute top-0 left-0 w-[290px] xl:w-[310px] ${
              reduceMotion ? '' : 'auth-float-1'
            }`}
            style={{
              transform: reduceMotion
                ? undefined
                : `translate3d(${mouseOffset.x * -0.6}px, ${mouseOffset.y * -0.6}px, 0)`,
              transition: 'transform 0.2s cubic-bezier(0.22, 1, 0.36, 1)',
            }}
          >
            <LiveOrderTrackerCard />
          </div>

          {/* Card 2: Product Stack Card (Bottom Right, Layered Over) */}
          <div
            className={`absolute bottom-2 right-0 w-[270px] xl:w-[290px] ${
              reduceMotion ? '' : 'auth-float-2'
            }`}
            style={{
              transform: reduceMotion
                ? undefined
                : `translate3d(${mouseOffset.x * 0.8}px, ${mouseOffset.y * 0.8}px, 0)`,
              transition: 'transform 0.2s cubic-bezier(0.22, 1, 0.36, 1)',
            }}
          >
            <ProductStackCard />
          </div>

          {/* Card 3: Trust Chip (Center Floating Pill) */}
          <div
            className={`absolute top-[48%] -left-3 ${
              reduceMotion ? '' : 'auth-float-3'
            }`}
            style={{
              transform: reduceMotion
                ? undefined
                : `translate3d(${mouseOffset.x * 0.4}px, ${mouseOffset.y * 0.4}px, 0)`,
              transition: 'transform 0.2s cubic-bezier(0.22, 1, 0.36, 1)',
            }}
          >
            <TrustChip />
          </div>
        </div>
      </div>

      {/* ─── Bottom: Stylized Patna Skyline & Customer Benefit Chips ── */}
      <div className="relative z-20 space-y-4">
        {/* 3 Customer-Facing Benefit Chips */}
        <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-white/15">
          <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/10 backdrop-blur-sm border border-white/20 text-xs font-medium text-white shadow-xs">
            <Store className="h-3.5 w-3.5 text-emerald-300 shrink-0" />
            <span>Real shops, real prices</span>
          </div>

          <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/10 backdrop-blur-sm border border-white/20 text-xs font-medium text-white shadow-xs">
            <MapPin className="h-3.5 w-3.5 text-accent-300 shrink-0" />
            <span>Live order tracking</span>
          </div>

          <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/10 backdrop-blur-sm border border-white/20 text-xs font-medium text-white shadow-xs">
            <Bike className="h-3.5 w-3.5 text-emerald-300 shrink-0" />
            <span>Fast local delivery</span>
          </div>
        </div>
      </div>

      {/* ─── Bottom Edge: Golghar Skyline SVG Silhouette ────────────── */}
      <div className="absolute bottom-0 left-0 right-0 z-10 pointer-events-none opacity-85">
        <PatnaSkyline className="h-32 xl:h-36" />
      </div>
    </div>
  )
}

export default AuthComposition
