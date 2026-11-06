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
import { DeliveryParcelModel } from './models/DeliveryParcelModel'
import { CheckCircle2 } from 'lucide-react'

interface OrderSuccessSceneProps {
  className?: string
}

export function OrderSuccessScene({ className = 'h-36 w-36 mx-auto' }: OrderSuccessSceneProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [hasWebGL, setHasWebGL] = useState(() => checkWebGLSupport())
  const [reduceMotion, setReduceMotion] = useState(() => useReducedMotionPreference())
  const frameloop = useCanvasVisibility(containerRef, reduceMotion)

  useEffect(() => {
    setHasWebGL(checkWebGLSupport())
    setReduceMotion(useReducedMotionPreference())
  }, [])

  const fallback = (
    <div className={`flex items-center justify-center rounded-2xl bg-primary-50 border border-primary-200 ${className}`}>
      <CheckCircle2 className="h-14 w-14 text-primary-700" />
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
        aria-label="Order confirmed celebration illustration"
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
            <ambientLight intensity={0.75} color={THREE_PALETTE.surfaceAlt} />
            <directionalLight position={[4, 7, 3]} intensity={1.15} color={THREE_PALETTE.warmKey} />
            <directionalLight position={[-4, 2, -3]} intensity={0.4} color={THREE_PALETTE.accent} />
            <pointLight position={[0, -2, 3]} intensity={0.3} color={THREE_PALETTE.gold} />

            <Float
              speed={reduceMotion ? 0 : 2.2}
              rotationIntensity={reduceMotion ? 0 : 0.35}
              floatIntensity={reduceMotion ? 0 : 0.7}
              floatingRange={[-0.1, 0.1]}
            >
              <DeliveryParcelModel
                reduceMotion={reduceMotion}
                celebrate={true}
                scale={1.1}
              />
            </Float>
          </Suspense>
        </Canvas>
      </div>
    </ThreeErrorBoundary>
  )
}
export default OrderSuccessScene
