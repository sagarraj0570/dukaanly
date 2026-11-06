import { Suspense, useState, useEffect, useRef } from 'react'
import { Canvas } from '@react-three/fiber'
import { Float } from '@react-three/drei'
import {
  checkWebGLSupport,
  useReducedMotionPreference,
  useCanvasVisibility,
  handleContextLost,
  ThreeErrorBoundary,
  STANDARD_GL_PROPS,
  STANDARD_DPR,
  THREE_PALETTE,
} from './common'
import { EmptyBasketModel } from './models/EmptyBasketModel'
import { StorefrontModel } from './models/StorefrontModel'
import { ShoppingCart, Package, Search, Store, Boxes } from 'lucide-react'

export interface EmptyState3DProps {
  type?: 'cart' | 'search' | 'orders' | 'inventory' | 'store'
  className?: string
}

export function EmptyState3D({ type = 'cart', className = 'h-32 w-32' }: EmptyState3DProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [hasWebGL, setHasWebGL] = useState(() => checkWebGLSupport())
  const [reduceMotion, setReduceMotion] = useState(() => useReducedMotionPreference())
  const frameloop = useCanvasVisibility(containerRef, reduceMotion)

  useEffect(() => {
    setHasWebGL(checkWebGLSupport())
    setReduceMotion(useReducedMotionPreference())
  }, [])

  const renderFallbackIcon = () => {
    switch (type) {
      case 'cart':
        return <ShoppingCart className="h-10 w-10 text-primary-600" />
      case 'search':
        return <Search className="h-10 w-10 text-primary-600" />
      case 'orders':
        return <Package className="h-10 w-10 text-primary-600" />
      case 'inventory':
        return <Boxes className="h-10 w-10 text-primary-600" />
      case 'store':
      default:
        return <Store className="h-10 w-10 text-primary-600" />
    }
  }

  const fallback = (
    <div className={`flex items-center justify-center rounded-2xl bg-primary-50 ${className}`}>
      {renderFallbackIcon()}
    </div>
  )

  if (!hasWebGL) {
    return fallback
  }

  return (
    <ThreeErrorBoundary fallback={fallback}>
      <div
        ref={containerRef}
        className={`relative flex items-center justify-center ${className}`}
        role="img"
        aria-label={`Empty ${type} visual`}
      >
        <Canvas
          frameloop={frameloop}
          gl={STANDARD_GL_PROPS}
          camera={{ position: [0, 0, 3.8], fov: 42 }}
          dpr={STANDARD_DPR}
          style={{ background: 'transparent' }}
          onCreated={({ gl }) => {
            gl.domElement.addEventListener('webglcontextlost', handleContextLost)
          }}
        >
          <Suspense fallback={null}>
            <ambientLight intensity={0.65} color={THREE_PALETTE.warmKey} />
            <directionalLight position={[4, 6, 3]} intensity={1.1} color={THREE_PALETTE.marigoldLight} />
            <directionalLight position={[-3, 2, -3]} intensity={0.3} color={THREE_PALETTE.softGreen} />

            <Float
              speed={reduceMotion ? 0 : 2}
              rotationIntensity={reduceMotion ? 0 : 0.3}
              floatIntensity={reduceMotion ? 0 : 0.6}
              floatingRange={[-0.08, 0.08]}
            >
              {type === 'store' ? (
                <StorefrontModel reduceMotion={reduceMotion} scale={0.75} />
              ) : (
                <EmptyBasketModel reduceMotion={reduceMotion} type={type} scale={0.9} />
              )}
            </Float>
          </Suspense>
        </Canvas>
      </div>
    </ThreeErrorBoundary>
  )
}
export default EmptyState3D
