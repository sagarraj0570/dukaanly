import { useRef, useState, useEffect, Component, type ReactNode } from 'react'
import { useFrame } from '@react-three/fiber'
import type { Mesh, Group } from 'three'

export const THREE_PALETTE = {
  primary: '#1B7F55', // mid-tone fresh brand green
  primaryLight: '#2E9A6B', // lighter rim/edge
  primaryDark: '#0F3D2E',
  deep: '#0F3D2E', // deep green
  marigold: '#F5A524', // warm accent marigold
  marigoldLight: '#FBDD9B',
  marigoldDark: '#D98A00',
  accentDark: '#D98A00',
  terracotta: '#C8472B',
  accent: '#BFE5D0', // soft mint accent
  ivory: '#FAF9F6',
  cream: '#F5F0E4',
  softGreen: '#F1FAF5',
  surfaceAlt: '#FAF9F6',
  surfaceLight: '#FAF9F6',
  warmKey: '#FFFBF0',
  muted: '#65736C',
  gold: '#F5A524',
  goldDark: '#D98A00',
  cardboard: '#D4A76A',
  cardboardDark: '#C09050',
  red: '#D64545',
  appleRed: '#B72D2D',
  breadGolden: '#E5A84B',
  darkTire: '#2C3E50',
  silver: '#BDC3C7',
} as const

export const STANDARD_GL_PROPS = {
  alpha: true,
  antialias: true,
  powerPreference: 'low-power' as const,
  preserveDrawingBuffer: false,
}

export const STANDARD_DPR: [number, number] = [1, 1.5]

export function useSubtleRotation(speed = 0.2, reduceMotion = false) {
  const ref = useRef<Mesh | Group>(null!)
  useFrame((_, delta) => {
    if (reduceMotion || !ref.current) return
    ref.current.rotation.y += delta * speed
    ref.current.rotation.x += delta * (speed * 0.2)
  })
  return ref
}

export function checkWebGLSupport(): boolean {
  if (typeof window === 'undefined') return false
  try {
    const canvas = document.createElement('canvas')
    return Boolean(
      window.WebGLRenderingContext &&
        (canvas.getContext('webgl') || canvas.getContext('experimental-webgl'))
    )
  } catch {
    return false
  }
}

export function useReducedMotionPreference(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false
  }
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export function useCanvasVisibility(
  containerRef: React.RefObject<HTMLElement | null>,
  reduceMotion = false
): 'always' | 'demand' | 'never' {
  const [isInView, setIsInView] = useState(true)
  const [isDocumentVisible, setIsDocumentVisible] = useState(() =>
    typeof document !== 'undefined' ? document.visibilityState === 'visible' : true
  )

  useEffect(() => {
    if (typeof document === 'undefined') return
    const handleVisibility = () => {
      setIsDocumentVisible(document.visibilityState === 'visible')
    }
    document.addEventListener('visibilitychange', handleVisibility)
    return () => document.removeEventListener('visibilitychange', handleVisibility)
  }, [])

  useEffect(() => {
    const el = containerRef.current
    if (!el || typeof IntersectionObserver === 'undefined') return

    const observer = new IntersectionObserver(
      ([entry]) => {
        setIsInView(entry.isIntersecting)
      },
      { threshold: 0.01, rootMargin: '50px' }
    )

    observer.observe(el)
    return () => observer.disconnect()
  }, [containerRef])

  if (reduceMotion) return 'demand'
  if (!isDocumentVisible || !isInView) return 'never'
  return 'always'
}

export function handleContextLost(event: Event) {
  event.preventDefault()
  console.warn('WebGL context lost; preserving UI and awaiting context restoration.')
}

export interface ThreeErrorBoundaryProps {
  fallback: ReactNode
  children: ReactNode
}

export interface ThreeErrorBoundaryState {
  hasError: boolean
}

export class ThreeErrorBoundary extends Component<ThreeErrorBoundaryProps, ThreeErrorBoundaryState> {
  state: ThreeErrorBoundaryState = { hasError: false }

  static getDerivedStateFromError(): ThreeErrorBoundaryState {
    return { hasError: true }
  }

  componentDidCatch(error: unknown) {
    console.warn('Three.js scene encountered error; falling back to 2D view.', error)
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback
    }
    return this.props.children
  }
}
