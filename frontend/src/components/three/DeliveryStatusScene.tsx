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
import { DeliveryVehicleModel } from './models/DeliveryVehicleModel'
import { DeliveryParcelModel } from './models/DeliveryParcelModel'
import { StorefrontModel } from './models/StorefrontModel'
import { Truck, CheckCircle2, Store } from 'lucide-react'

export interface DeliveryStatusSceneProps {
  status?: string
  className?: string
}

export function DeliveryStatusScene({
  status = 'assigned',
  className = 'h-36 w-full',
}: DeliveryStatusSceneProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [hasWebGL, setHasWebGL] = useState(() => checkWebGLSupport())
  const [reduceMotion, setReduceMotion] = useState(() => useReducedMotionPreference())
  const frameloop = useCanvasVisibility(containerRef, reduceMotion)

  useEffect(() => {
    setHasWebGL(checkWebGLSupport())
    setReduceMotion(useReducedMotionPreference())
  }, [])

  const renderFallbackIcon = () => {
    switch (status) {
      case 'delivered':
        return <CheckCircle2 className="h-10 w-10 text-primary-700" />
      case 'out_for_delivery':
      case 'picked_up':
      case 'assigned':
        return <Truck className="h-10 w-10 text-primary-700" />
      case 'pending':
      default:
        return <Store className="h-10 w-10 text-primary-700" />
    }
  }

  const fallback = (
    <div className={`flex items-center justify-center rounded-2xl bg-primary-50 border border-border ${className}`}>
      <div className="flex flex-col items-center gap-1.5 p-3 text-center">
        {renderFallbackIcon()}
        <span className="text-xs font-semibold capitalize text-primary-900">
          {status.replace(/_/g, ' ')}
        </span>
      </div>
    </div>
  )

  if (!hasWebGL) {
    return fallback
  }

  const isMoving = status === 'out_for_delivery'
  const isDelivered = status === 'delivered'
  const isPending = status === 'pending'

  return (
    <ThreeErrorBoundary fallback={fallback}>
      <div
        ref={containerRef}
        className={`relative ${className}`}
        role="img"
        aria-label={`Delivery status illustration: ${status.replace(/_/g, ' ')}`}
      >
        <Canvas
          frameloop={frameloop}
          gl={STANDARD_GL_PROPS}
          camera={{ position: [0, 0, 4.0], fov: 40 }}
          dpr={STANDARD_DPR}
          style={{ background: 'transparent' }}
          onCreated={({ gl }) => {
            gl.domElement.addEventListener('webglcontextlost', handleContextLost)
          }}
        >
          <Suspense fallback={null}>
            <ambientLight intensity={0.7} color={THREE_PALETTE.surfaceAlt} />
            <directionalLight position={[5, 7, 4]} intensity={1.1} color={THREE_PALETTE.warmKey} />
            <directionalLight position={[-4, 2, -3]} intensity={0.35} color={THREE_PALETTE.accent} />

            <Float
              speed={reduceMotion ? 0 : isMoving ? 3 : 1.8}
              rotationIntensity={reduceMotion ? 0 : 0.25}
              floatIntensity={reduceMotion ? 0 : 0.5}
              floatingRange={[-0.08, 0.08]}
            >
              {isDelivered ? (
                <DeliveryParcelModel
                  reduceMotion={reduceMotion}
                  celebrate={true}
                  scale={1.05}
                />
              ) : isPending ? (
                <StorefrontModel reduceMotion={reduceMotion} scale={0.8} />
              ) : (
                <DeliveryVehicleModel
                  reduceMotion={reduceMotion}
                  isMoving={isMoving}
                  scale={1.0}
                />
              )}
            </Float>
          </Suspense>
        </Canvas>
      </div>
    </ThreeErrorBoundary>
  )
}
export default DeliveryStatusScene
