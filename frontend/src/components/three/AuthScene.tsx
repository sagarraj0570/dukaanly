import { useRef, useMemo, Suspense } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { Float } from '@react-three/drei'
import type { Mesh, Group } from 'three'
import * as THREE from 'three'
import {
  STANDARD_GL_PROPS,
  STANDARD_DPR,
  THREE_PALETTE,
  useCanvasVisibility,
  handleContextLost,
} from './common'

const BRAND = {
  primary: THREE_PALETTE.primary,
  deep: THREE_PALETTE.primaryDark,
  accent: THREE_PALETTE.primaryLight,
  ivory: THREE_PALETTE.ivory,
  cream: THREE_PALETTE.cream,
  gold: THREE_PALETTE.accent,
  goldDark: THREE_PALETTE.accentDark,
} as const

function useGentleTurn(speed = 0.2, reduceMotion = false) {
  const ref = useRef<Mesh | Group>(null!)
  useFrame((_, delta) => {
    if (reduceMotion || !ref.current) return
    ref.current.rotation.y += delta * speed
    ref.current.rotation.x += delta * (speed * 0.25)
  })
  return ref
}

function FloatingBag({ reduceMotion }: { reduceMotion: boolean }) {
  const ref = useGentleTurn(0.2, reduceMotion)

  return (
    <Float
      speed={reduceMotion ? 0 : 2}
      rotationIntensity={reduceMotion ? 0 : 0.4}
      floatIntensity={reduceMotion ? 0 : 0.8}
      floatingRange={[-0.15, 0.15]}
    >
      <group ref={ref} position={[-0.3, 0.3, 0.2]} scale={0.85}>
        <mesh castShadow>
          <boxGeometry args={[1.5, 1.9, 0.9]} />
          <meshStandardMaterial color={BRAND.primary} roughness={0.3} metalness={0.08} />
        </mesh>
        <mesh position={[0, 1.0, 0]}>
          <boxGeometry args={[1.6, 0.14, 1.0]} />
          <meshStandardMaterial color={BRAND.deep} roughness={0.3} />
        </mesh>
        <mesh position={[-0.4, 1.5, 0]}>
          <torusGeometry args={[0.32, 0.05, 12, 24, Math.PI]} />
          <meshStandardMaterial color={BRAND.deep} roughness={0.4} />
        </mesh>
        <mesh position={[0.4, 1.5, 0]}>
          <torusGeometry args={[0.32, 0.05, 12, 24, Math.PI]} />
          <meshStandardMaterial color={BRAND.deep} roughness={0.4} />
        </mesh>
        <mesh position={[0, -0.25, 0.46]}>
          <boxGeometry args={[1.1, 0.18, 0.02]} />
          <meshStandardMaterial color={BRAND.accent} roughness={0.4} />
        </mesh>
      </group>
    </Float>
  )
}

function FloatingCoin({ reduceMotion }: { reduceMotion: boolean }) {
  const ref = useGentleTurn(0.35, reduceMotion)

  return (
    <Float
      speed={reduceMotion ? 0 : 2.5}
      rotationIntensity={reduceMotion ? 0 : 0.5}
      floatIntensity={reduceMotion ? 0 : 0.9}
      floatingRange={[-0.1, 0.1]}
    >
      <group ref={ref} position={[1.5, 1.3, 0.4]} scale={0.55}>
        <mesh castShadow>
          <cylinderGeometry args={[0.5, 0.5, 0.1, 32]} />
          <meshStandardMaterial color={BRAND.gold} roughness={0.25} metalness={0.7} />
        </mesh>
        <mesh>
          <torusGeometry args={[0.5, 0.04, 12, 32]} />
          <meshStandardMaterial color={BRAND.goldDark} roughness={0.2} metalness={0.8} />
        </mesh>
      </group>
    </Float>
  )
}

function FloatingParcel({ reduceMotion }: { reduceMotion: boolean }) {
  const ref = useGentleTurn(0.18, reduceMotion)

  return (
    <Float
      speed={reduceMotion ? 0 : 1.8}
      rotationIntensity={reduceMotion ? 0 : 0.3}
      floatIntensity={reduceMotion ? 0 : 0.6}
      floatingRange={[-0.12, 0.12]}
    >
      <group ref={ref} position={[1.2, -1.0, -0.2]} scale={0.65}>
        <mesh castShadow>
          <boxGeometry args={[1.4, 1.0, 1.1]} />
          <meshStandardMaterial color="#D4A76A" roughness={0.6} />
        </mesh>
        <mesh position={[0, 0.51, 0]}>
          <boxGeometry args={[0.22, 0.02, 1.12]} />
          <meshStandardMaterial color="#C09050" roughness={0.5} />
        </mesh>
        <mesh position={[0, 0, 0.56]}>
          <circleGeometry args={[0.2, 24]} />
          <meshStandardMaterial color={BRAND.primary} roughness={0.4} />
        </mesh>
      </group>
    </Float>
  )
}

function FloatingStoreAesthetic({ reduceMotion }: { reduceMotion: boolean }) {
  const ref = useGentleTurn(0.15, reduceMotion)

  const awningGeo = useMemo(() => {
    const shape = new THREE.Shape()
    shape.moveTo(-0.7, 0)
    shape.lineTo(0.7, 0)
    shape.lineTo(0.6, -0.25)
    shape.quadraticCurveTo(0.3, -0.4, 0, -0.25)
    shape.quadraticCurveTo(-0.3, -0.4, -0.6, -0.25)
    shape.lineTo(-0.7, 0)
    return new THREE.ExtrudeGeometry(shape, { depth: 0.5, bevelEnabled: false })
  }, [])

  return (
    <Float
      speed={reduceMotion ? 0 : 1.6}
      rotationIntensity={reduceMotion ? 0 : 0.25}
      floatIntensity={reduceMotion ? 0 : 0.5}
      floatingRange={[-0.1, 0.1]}
    >
      <group ref={ref} position={[-1.4, -1.1, -0.4]} scale={0.6}>
        <mesh castShadow>
          <boxGeometry args={[1.4, 1.0, 0.8]} />
          <meshStandardMaterial color={BRAND.ivory} roughness={0.4} />
        </mesh>
        <mesh position={[0, 0.5, -0.25]} geometry={awningGeo}>
          <meshStandardMaterial color={BRAND.primary} roughness={0.4} side={THREE.DoubleSide} />
        </mesh>
        <mesh position={[0, -0.15, 0.41]}>
          <boxGeometry args={[0.38, 0.65, 0.02]} />
          <meshStandardMaterial color={BRAND.deep} roughness={0.4} />
        </mesh>
      </group>
    </Float>
  )
}

function SceneContent({ reduceMotion }: { reduceMotion: boolean }) {
  return (
    <>
      <ambientLight intensity={0.65} color="#FFFBF0" />
      <directionalLight position={[6, 8, 4]} intensity={1.1} color="#FFF3DC" />
      <directionalLight position={[-4, 3, -4]} intensity={0.4} color="#DDF2E7" />
      <pointLight position={[0, -2, 3]} intensity={0.3} color={BRAND.gold} />

      <FloatingBag reduceMotion={reduceMotion} />
      <FloatingCoin reduceMotion={reduceMotion} />
      <FloatingParcel reduceMotion={reduceMotion} />
      <FloatingStoreAesthetic reduceMotion={reduceMotion} />
    </>
  )
}

interface AuthSceneProps {
  reduceMotion?: boolean
  className?: string
}

export function AuthScene({ reduceMotion = false, className }: AuthSceneProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const frameloop = useCanvasVisibility(containerRef, reduceMotion)

  return (
    <div ref={containerRef} className={className}>
      <Canvas
        frameloop={frameloop}
        gl={STANDARD_GL_PROPS}
        camera={{ position: [0, 0, 5.5], fov: 42 }}
        dpr={STANDARD_DPR}
        style={{ background: 'transparent' }}
        onCreated={({ gl }) => {
          gl.domElement.addEventListener('webglcontextlost', handleContextLost)
        }}
      >
        <Suspense fallback={null}>
          <SceneContent reduceMotion={reduceMotion} />
        </Suspense>
      </Canvas>
    </div>
  )
}

export default AuthScene
