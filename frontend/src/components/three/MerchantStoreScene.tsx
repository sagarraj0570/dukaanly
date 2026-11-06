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
import { StorefrontModel } from './models/StorefrontModel'
import { Store } from 'lucide-react'

interface MerchantStoreSceneProps {
  className?: string
}

export function MerchantStoreScene({ className = 'h-24 w-28 shrink-0' }: MerchantStoreSceneProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [hasWebGL, setHasWebGL] = useState(() => checkWebGLSupport())
  const [reduceMotion, setReduceMotion] = useState(() => useReducedMotionPreference())
  const frameloop = useCanvasVisibility(containerRef, reduceMotion)

  useEffect(() => {
    setHasWebGL(checkWebGLSupport())
    setReduceMotion(useReducedMotionPreference())
  }, [])

  const fallback = (
    <div className={`flex items-center justify-center rounded-2xl bg-primary-50 border border-border ${className}`}>
      <Store className="h-8 w-8 text-primary-700" />
    </div>
  )

  if (!hasWebGL) {
    return fallback
  }

  return (
    <ThreeErrorBoundary fallback={fallback}>
      <div
        ref={containerRef}
        className={`relative ${className}`}
        role="img"
        aria-label="Merchant storefront 3D visual"
      >
        <Canvas
          frameloop={frameloop}
          gl={STANDARD_GL_PROPS}
          camera={{ position: [0, 0, 3.6], fov: 42 }}
          dpr={STANDARD_DPR}
          style={{ background: 'transparent' }}
          onCreated={({ gl }) => {
            gl.domElement.addEventListener('webglcontextlost', handleContextLost)
          }}
        >
          <Suspense fallback={null}>
            <ambientLight intensity={0.7} color={THREE_PALETTE.surfaceAlt} />
            <directionalLight position={[4, 6, 3]} intensity={1.1} color={THREE_PALETTE.warmKey} />
            <directionalLight position={[-3, 2, -3]} intensity={0.35} color={THREE_PALETTE.accent} />

            <Float
              speed={reduceMotion ? 0 : 1.8}
              rotationIntensity={reduceMotion ? 0 : 0.25}
              floatIntensity={reduceMotion ? 0 : 0.5}
              floatingRange={[-0.06, 0.06]}
            >
              <StorefrontModel reduceMotion={reduceMotion} scale={0.9} />
            </Float>
          </Suspense>
        </Canvas>
      </div>
    </ThreeErrorBoundary>
  )
}
export default MerchantStoreScene
