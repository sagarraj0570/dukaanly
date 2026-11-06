import { useState, useEffect, lazy, Suspense } from 'react'
import { Link } from 'react-router-dom'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import {
  Store,
  ArrowRight,
  ShieldCheck,
  Zap,
  MapPin,
  Sparkles,
} from 'lucide-react'

import DesktopOnlyNotice from '@/components/landing/DesktopOnlyNotice'
import NavHeader from '@/components/landing/NavHeader'
import CategorySection from '@/components/landing/CategorySection'
import { FeaturedStores } from '@/components/landing/FeaturedStores'
import { FeaturedProducts } from '@/components/landing/FeaturedProducts'
import HowItWorks from '@/components/landing/HowItWorks'
import BrandSection from '@/components/landing/BrandSection'
import FinalCTA from '@/components/landing/FinalCTA'
import Footer from '@/components/landing/Footer'
import { checkWebGLSupport, useReducedMotionPreference } from '@/components/three/common'

// Lazy-load Three.js 3D Hero scene to optimize initial page paint
const HeroScene = lazy(() => import('@/components/three/HeroScene'))

export const LandingPage = () => {
  useDocumentTitle('Dukaanly - Hyperlocal Commerce Platform')

  const [reduceMotion, setReduceMotion] = useState(() => useReducedMotionPreference())
  const [hasWebGL, setHasWebGL] = useState(() => checkWebGLSupport())

  useEffect(() => {
    // Check user's motion preference safely
    let cleanup: (() => void) | undefined
    if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
      const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
      setReduceMotion(motionQuery.matches)
      const handleMotionChange = (e: MediaQueryListEvent) => setReduceMotion(e.matches)
      motionQuery.addEventListener('change', handleMotionChange)
      cleanup = () => motionQuery.removeEventListener('change', handleMotionChange)
    }

    setHasWebGL(checkWebGLSupport())

    return () => {
      cleanup?.()
    }
  }, [])

  const scrollToStores = () => {
    const el = document.getElementById('featured-stores')
    if (el) {
      el.scrollIntoView({ behavior: 'smooth' })
    }
  }

  return (
    <div className="min-h-screen bg-surface-alt text-text-primary selection:bg-primary-200/50 selection:text-primary-900">
      {/* Mobile Notice shown below 1024px */}
      <DesktopOnlyNotice />

      {/* Main Desktop Experience */}
      <div className="hidden lg:flex lg:flex-col min-h-screen">
        <NavHeader />

        {/* ─── Hero Section ────────────────────────────────────────────── */}
        <section className="relative overflow-hidden pt-12 pb-20 border-b border-border">
          {/* Subtle gradient background mesh */}
          <div className="pointer-events-none absolute -top-40 -right-40 h-[650px] w-[650px] rounded-full bg-gradient-to-br from-primary-200/30 via-primary-50/50 to-transparent blur-3xl" />
          <div className="pointer-events-none absolute -bottom-32 -left-32 h-[500px] w-[500px] rounded-full bg-gradient-to-tr from-primary-50/70 to-transparent blur-3xl" />

          <div className="relative mx-auto max-w-7xl px-8">
            <div className="grid grid-cols-12 items-center gap-12">
              {/* Left Column: Editorial Headline & Value Props */}
              <div className="col-span-7 flex flex-col justify-center">
                {/* Hyperlocal pill */}
                <div className="inline-flex items-center gap-2 self-start rounded-full bg-primary-50 border border-primary-200 px-3.5 py-1.5 text-xs font-semibold text-primary-700 mb-6 shadow-xs">
                  <Sparkles className="h-3.5 w-3.5 text-primary-700" />
                  <span>Hyperlocal Commerce · Patna Pilot</span>
                </div>

                <h1 className="text-5xl font-extrabold tracking-tight text-primary-900 leading-[1.15]">
                  Your neighbourhood shops, delivered to your door.
                </h1>

                <p className="mt-6 text-lg text-text-secondary max-w-xl leading-relaxed">
                  Browse verified local kirana, dairy parlours, bakeries, and pharmacies in Patna.
                  Real-time stock checks, honest retail pricing, and live GPS rider tracking.
                </p>

                {/* CTAs */}
                <div className="mt-8 flex items-center gap-4">
                  <Link
                    to="/login"
                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-primary-700 px-7 py-3.5 text-base font-semibold text-white shadow-md transition-all hover:bg-primary-600 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
                  >
                    Start Shopping
                    <ArrowRight className="h-4 w-4" />
                  </Link>

                  <button
                    type="button"
                    onClick={scrollToStores}
                    className="inline-flex items-center justify-center gap-2 rounded-xl border border-border bg-white px-6 py-3.5 text-base font-semibold text-text-primary shadow-xs transition-colors hover:bg-primary-50 hover:text-primary-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                  >
                    <Store className="h-4 w-4 text-primary-700" />
                    Browse Stores
                  </button>
                </div>

                {/* Trust Metrics Bar */}
                <div className="mt-12 grid grid-cols-3 gap-6 pt-8 border-t border-border">
                  <div className="flex items-start gap-3">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary-50 text-primary-700">
                      <ShieldCheck className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-sm font-bold text-primary-900">Verified Partners</p>
                      <p className="text-xs text-text-secondary">Independently verified</p>
                    </div>
                  </div>

                  <div className="flex items-start gap-3">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary-50 text-primary-700">
                      <Zap className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-sm font-bold text-primary-900">Live Inventory</p>
                      <p className="text-xs text-text-secondary">Optimistic concurrency</p>
                    </div>
                  </div>

                  <div className="flex items-start gap-3">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary-50 text-primary-700">
                      <MapPin className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-sm font-bold text-primary-900">PostGIS Tracking</p>
                      <p className="text-xs text-text-secondary">Real road navigation</p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Right Column: Three.js 3D Hero Scene */}
              <div className="col-span-5 relative flex items-center justify-center h-[520px]">
                <div className="relative h-full w-full rounded-3xl bg-gradient-to-br from-primary-50/60 via-surface-alt to-primary-50/30 border border-border overflow-hidden shadow-soft">
                  {hasWebGL ? (
                    <Suspense
                      fallback={
                        <div className="flex h-full w-full items-center justify-center">
                          <div className="flex flex-col items-center gap-2 text-text-secondary">
                            <Store className="h-10 w-10 text-primary-700 animate-pulse" />
                            <span className="text-xs font-medium">Loading 3D Market…</span>
                          </div>
                        </div>
                      }
                    >
                      <HeroScene
                        reduceMotion={reduceMotion}
                        className="h-full w-full cursor-grab active:cursor-grabbing"
                      />
                    </Suspense>
                  ) : (
                    /* Fallback when WebGL is unavailable */
                    <div className="flex h-full w-full flex-col items-center justify-center p-8 text-center">
                      <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-primary-50 text-primary-700 mb-4">
                        <Store className="h-10 w-10" />
                      </div>
                      <h2 className="text-xl font-bold text-primary-900">Hyperlocal Commerce</h2>
                      <p className="text-xs text-text-secondary max-w-xs mt-2">
                        Connecting customers, local kirana stores, and delivery riders in real time.
                      </p>
                    </div>
                  )}

                  {/* Subtle float caption overlay */}
                  <div className="pointer-events-none absolute bottom-4 left-4 right-4 flex items-center justify-between rounded-xl bg-white/70 backdrop-blur-md px-3.5 py-2 text-[11px] text-text-secondary border border-border">
                    <span className="font-medium text-primary-900">Real-time Hyperlocal Network</span>
                    <span className="text-primary-700 font-semibold">● Live in Patna</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ─── Category Discovery ─────────────────────────────────────── */}
        <CategorySection />

        {/* ─── Featured Stores (Real API) ─────────────────────────────── */}
        <div id="featured-stores">
          <FeaturedStores />
        </div>

        {/* ─── Featured Products (Real API) ───────────────────────────── */}
        <FeaturedProducts />

        {/* ─── How It Works ───────────────────────────────────────────── */}
        <HowItWorks />

        {/* ─── Brand Value Proposition ─────────────────────────────────── */}
        <BrandSection />

        {/* ─── Final CTA ──────────────────────────────────────────────── */}
        <FinalCTA />

        {/* ─── Footer ─────────────────────────────────────────────────── */}
        <Footer />
      </div>
    </div>
  )
}

export default LandingPage
