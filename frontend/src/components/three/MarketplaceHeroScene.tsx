import { Suspense, useState, useEffect, useRef } from 'react'
import { Canvas } from '@react-three/fiber'
import { Float } from '@react-three/drei'
import * as THREE from 'three'
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
import { ShoppingBasketModel } from './models/ShoppingBasketModel'
import { ShoppingBasket } from 'lucide-react'

interface MarketplaceHeroSceneProps {
  className?: string
}

export function MarketplaceHeroScene({ className = 'h-full w-full' }: MarketplaceHeroSceneProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [hasWebGL, setHasWebGL] = useState(() => checkWebGLSupport())
  const [reduceMotion, setReduceMotion] = useState(() => useReducedMotionPreference())
  const frameloop = useCanvasVisibility(containerRef, reduceMotion)

  useEffect(() => {
    setHasWebGL(checkWebGLSupport())
    setReduceMotion(useReducedMotionPreference())
  }, [])

  const fallback = (
    <div className="w-full h-full flex flex-col items-center justify-center bg-gradient-to-br from-primary-50 to-bg p-6 text-center">
      <ShoppingBasket className="h-14 w-14 text-primary-700 mb-2" aria-hidden="true" />
      <p className="font-bold text-base text-primary-900">Dukaanly Fresh</p>
      <p className="text-xs text-text-secondary font-medium">Local shops · Stronger communities</p>
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
        aria-label="Fresh local groceries 3D display"
      >
        <Canvas
          frameloop={frameloop}
          gl={{
            ...STANDARD_GL_PROPS,
            toneMapping: THREE.ACESFilmicToneMapping,
            outputColorSpace: THREE.SRGBColorSpace,
          }}
          camera={{ position: [0, 0, 4.2], fov: 42 }}
          dpr={STANDARD_DPR}
          style={{ background: 'transparent' }}
          onCreated={({ gl }) => {
            gl.domElement.addEventListener('webglcontextlost', handleContextLost)
          }}
        >
          <Suspense fallback={null}>
            {/* Warm key light */}
            <directionalLight position={[5, 7, 4]} intensity={1.15} color="#FFF3DC" />
            {/* Cool fill light */}
            <directionalLight position={[-4, 3, -3]} intensity={0.4} color="#DDF2E7" />
            {/* Indian market ambient bounce */}
            <hemisphereLight args={['#E8F5EE', '#F5EBD3', 0.65]} />
            <pointLight position={[0, -2, 3]} intensity={0.2} color={THREE_PALETTE.marigold} />

            {/* Soft contact shadow tinted green rgba(15, 61, 46, 0.18) */}
            <mesh position={[0, -1.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
              <circleGeometry args={[1.05, 32]} />
              <meshBasicMaterial color="#0F3D2E" opacity={0.18} transparent />
            </mesh>

            <Float
              speed={reduceMotion ? 0 : 2}
              rotationIntensity={reduceMotion ? 0 : 0.3}
              floatIntensity={reduceMotion ? 0 : 0.6}
              floatingRange={[-0.1, 0.1]}
            >
              <ShoppingBasketModel reduceMotion={reduceMotion} scale={1.1} />
            </Float>
          </Suspense>
        </Canvas>
      </div>
    </ThreeErrorBoundary>
  )
}
export default MarketplaceHeroScene
