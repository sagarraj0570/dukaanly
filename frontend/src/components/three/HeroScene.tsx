import { useRef, useMemo, Suspense } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { Float, OrbitControls } from '@react-three/drei'
import type { Mesh, Group } from 'three'
import * as THREE from 'three'
import {
  STANDARD_GL_PROPS,
  STANDARD_DPR,
  THREE_PALETTE,
  useCanvasVisibility,
  handleContextLost,
} from './common'

// ─── Brand palette ──────────────────────────────────────────────
const COLORS = {
  primary: THREE_PALETTE.primary,
  deep: THREE_PALETTE.primaryDark,
  accent: THREE_PALETTE.primaryLight,
  marigold: THREE_PALETTE.accent,
  marigoldDark: THREE_PALETTE.accentDark,
  ivory: THREE_PALETTE.ivory,
  cream: THREE_PALETTE.cream,
  softGreen: THREE_PALETTE.surfaceLight,
  muted: THREE_PALETTE.muted,
  appleRed: THREE_PALETTE.appleRed,
} as const

// ─── Shared animation hook ─────────────────────────────────────
function useGentleSpin(speed = 0.15, reduceMotion = false) {
  const ref = useRef<Mesh | Group>(null!)
  useFrame((_, delta) => {
    if (reduceMotion || !ref.current) return
    ref.current.rotation.y += delta * speed
    ref.current.rotation.x += delta * speed * 0.3
  })
  return ref
}

// ─── 1. Shopping Bag ────────────────────────────────────────────
function ShoppingBag({ reduceMotion }: { reduceMotion: boolean }) {
  const ref = useGentleSpin(0.12, reduceMotion)

  return (
    <Float
      speed={reduceMotion ? 0 : 1.8}
      rotationIntensity={reduceMotion ? 0 : 0.3}
      floatIntensity={reduceMotion ? 0 : 0.6}
      floatingRange={[-0.15, 0.15]}
    >
      <group ref={ref} position={[-2.6, 0.8, 0.5]} scale={0.55}>
        {/* Bag body */}
        <mesh castShadow>
          <boxGeometry args={[1.4, 1.8, 0.9]} />
          <meshStandardMaterial color={COLORS.primary} roughness={0.35} metalness={0.05} />
        </mesh>

        {/* Bag opening - slightly wider top rim */}
        <mesh position={[0, 0.95, 0]} castShadow>
          <boxGeometry args={[1.5, 0.12, 1.0]} />
          <meshStandardMaterial color={COLORS.deep} roughness={0.3} metalness={0.1} />
        </mesh>

        {/* Handle left */}
        <mesh position={[-0.35, 1.45, 0]} castShadow>
          <torusGeometry args={[0.3, 0.05, 12, 24, Math.PI]} />
          <meshStandardMaterial color={COLORS.deep} roughness={0.4} />
        </mesh>

        {/* Handle right */}
        <mesh position={[0.35, 1.45, 0]} castShadow>
          <torusGeometry args={[0.3, 0.05, 12, 24, Math.PI]} />
          <meshStandardMaterial color={COLORS.deep} roughness={0.4} />
        </mesh>

        {/* Brand stripe */}
        <mesh position={[0, -0.2, 0.46]}>
          <boxGeometry args={[1.0, 0.15, 0.02]} />
          <meshStandardMaterial color={COLORS.accent} roughness={0.5} />
        </mesh>
      </group>
    </Float>
  )
}

// ─── 2. Milk Carton ─────────────────────────────────────────────
function MilkCarton({ reduceMotion }: { reduceMotion: boolean }) {
  const ref = useGentleSpin(0.1, reduceMotion)

  return (
    <Float
      speed={reduceMotion ? 0 : 2.2}
      rotationIntensity={reduceMotion ? 0 : 0.25}
      floatIntensity={reduceMotion ? 0 : 0.5}
      floatingRange={[-0.12, 0.12]}
    >
      <group ref={ref} position={[1.8, 1.4, -1.0]} scale={0.5}>
        {/* Carton body */}
        <mesh castShadow>
          <boxGeometry args={[0.8, 1.6, 0.8]} />
          <meshStandardMaterial color={COLORS.ivory} roughness={0.6} metalness={0.0} />
        </mesh>

        {/* Carton top / peaked roof */}
        <mesh position={[0, 1.0, 0]} rotation={[0, Math.PI / 4, 0]} castShadow>
          <coneGeometry args={[0.52, 0.5, 4]} />
          <meshStandardMaterial color={COLORS.cream} roughness={0.5} />
        </mesh>

        {/* Label band */}
        <mesh position={[0, -0.1, 0.41]}>
          <boxGeometry args={[0.72, 0.7, 0.02]} />
          <meshStandardMaterial color={COLORS.primary} roughness={0.4} />
        </mesh>

        {/* Small circle on label */}
        <mesh position={[0, 0.0, 0.43]}>
          <circleGeometry args={[0.12, 24]} />
          <meshStandardMaterial color={COLORS.accent} roughness={0.5} />
        </mesh>
      </group>
    </Float>
  )
}

// ─── 3. Apple / Fruit ───────────────────────────────────────────
function Apple({ reduceMotion }: { reduceMotion: boolean }) {
  const ref = useGentleSpin(0.18, reduceMotion)

  return (
    <Float
      speed={reduceMotion ? 0 : 1.5}
      rotationIntensity={reduceMotion ? 0 : 0.4}
      floatIntensity={reduceMotion ? 0 : 0.7}
      floatingRange={[-0.1, 0.1]}
    >
      <group ref={ref} position={[0.3, -1.2, 1.5]} scale={0.45}>
        {/* Apple body */}
        <mesh castShadow>
          <sphereGeometry args={[0.7, 32, 32]} />
          <meshStandardMaterial color={COLORS.appleRed} roughness={0.35} metalness={0.05} />
        </mesh>

        {/* Subtle dimple at top — slightly flattened */}
        <mesh position={[0, 0.62, 0]}>
          <sphereGeometry args={[0.18, 16, 16]} />
          <meshStandardMaterial color="#B72D2D" roughness={0.4} />
        </mesh>

        {/* Stem */}
        <mesh position={[0, 0.85, 0]} castShadow>
          <cylinderGeometry args={[0.03, 0.04, 0.35, 8]} />
          <meshStandardMaterial color="#5D4037" roughness={0.7} />
        </mesh>

        {/* Leaf */}
        <mesh position={[0.15, 0.95, 0.05]} rotation={[0.3, 0, 0.6]}>
          <sphereGeometry args={[0.15, 8, 6, 0, Math.PI]} />
          <meshStandardMaterial
            color={COLORS.primary}
            roughness={0.5}
            side={THREE.DoubleSide}
          />
        </mesh>
      </group>
    </Float>
  )
}

// ─── 4. Delivery Box ────────────────────────────────────────────
function DeliveryBox({ reduceMotion }: { reduceMotion: boolean }) {
  const ref = useGentleSpin(0.08, reduceMotion)

  return (
    <Float
      speed={reduceMotion ? 0 : 1.6}
      rotationIntensity={reduceMotion ? 0 : 0.2}
      floatIntensity={reduceMotion ? 0 : 0.55}
      floatingRange={[-0.1, 0.1]}
    >
      <group ref={ref} position={[2.8, -0.6, 0.8]} scale={0.5}>
        {/* Box body */}
        <mesh castShadow>
          <boxGeometry args={[1.6, 1.1, 1.2]} />
          <meshStandardMaterial color="#D4A76A" roughness={0.65} metalness={0.0} />
        </mesh>

        {/* Tape strip horizontal */}
        <mesh position={[0, 0.56, 0]}>
          <boxGeometry args={[0.25, 0.02, 1.22]} />
          <meshStandardMaterial color="#C09050" roughness={0.5} />
        </mesh>

        {/* Tape strip vertical front */}
        <mesh position={[0, 0.56, 0.61]}>
          <boxGeometry args={[0.25, 0.02, 0.02]} />
          <meshStandardMaterial color="#C09050" roughness={0.5} />
        </mesh>

        {/* Flap left */}
        <mesh position={[-0.55, 0.6, 0]} rotation={[0, 0, 0.15]}>
          <boxGeometry args={[0.5, 0.06, 1.18]} />
          <meshStandardMaterial color="#CAAA70" roughness={0.6} />
        </mesh>

        {/* Flap right */}
        <mesh position={[0.55, 0.6, 0]} rotation={[0, 0, -0.15]}>
          <boxGeometry args={[0.5, 0.06, 1.18]} />
          <meshStandardMaterial color="#CAAA70" roughness={0.6} />
        </mesh>

        {/* Delivery icon — small green circle label */}
        <mesh position={[0, 0.0, 0.62]}>
          <circleGeometry args={[0.22, 24]} />
          <meshStandardMaterial color={COLORS.primary} roughness={0.4} />
        </mesh>

        {/* Check mark on label - simple line */}
        <mesh position={[0, 0.0, 0.63]}>
          <circleGeometry args={[0.1, 24]} />
          <meshStandardMaterial color={COLORS.accent} roughness={0.5} />
        </mesh>
      </group>
    </Float>
  )
}

// ─── 5. Store / Shop Icon ───────────────────────────────────────
function StoreIcon({ reduceMotion }: { reduceMotion: boolean }) {
  const ref = useGentleSpin(0.14, reduceMotion)

  const awningGeo = useMemo(() => {
    const shape = new THREE.Shape()
    shape.moveTo(-0.9, 0)
    shape.lineTo(0.9, 0)
    shape.lineTo(0.75, -0.35)
    shape.quadraticCurveTo(0.45, -0.55, 0.3, -0.35)
    shape.quadraticCurveTo(0.15, -0.55, 0, -0.35)
    shape.quadraticCurveTo(-0.15, -0.55, -0.3, -0.35)
    shape.quadraticCurveTo(-0.45, -0.55, -0.75, -0.35)
    shape.lineTo(-0.9, 0)

    const extrudeSettings = { depth: 0.6, bevelEnabled: false }
    return new THREE.ExtrudeGeometry(shape, extrudeSettings)
  }, [])

  return (
    <Float
      speed={reduceMotion ? 0 : 2.0}
      rotationIntensity={reduceMotion ? 0 : 0.3}
      floatIntensity={reduceMotion ? 0 : 0.5}
      floatingRange={[-0.12, 0.12]}
    >
      <group ref={ref} position={[-1.5, -1.0, -0.8]} scale={0.5}>
        {/* Store body */}
        <mesh castShadow>
          <boxGeometry args={[1.6, 1.2, 1.0]} />
          <meshStandardMaterial color={COLORS.ivory} roughness={0.5} metalness={0.02} />
        </mesh>

        {/* Awning */}
        <mesh position={[0, 0.6, -0.3]} castShadow geometry={awningGeo}>
          <meshStandardMaterial
            color={COLORS.primary}
            roughness={0.4}
            side={THREE.DoubleSide}
          />
        </mesh>

        {/* Door */}
        <mesh position={[0, -0.2, 0.51]}>
          <boxGeometry args={[0.45, 0.7, 0.02]} />
          <meshStandardMaterial color={COLORS.deep} roughness={0.4} />
        </mesh>

        {/* Window left */}
        <mesh position={[-0.5, 0.1, 0.51]}>
          <boxGeometry args={[0.35, 0.4, 0.02]} />
          <meshStandardMaterial color={COLORS.accent} roughness={0.3} metalness={0.15} />
        </mesh>

        {/* Window right */}
        <mesh position={[0.5, 0.1, 0.51]}>
          <boxGeometry args={[0.35, 0.4, 0.02]} />
          <meshStandardMaterial color={COLORS.accent} roughness={0.3} metalness={0.15} />
        </mesh>
      </group>
    </Float>
  )
}

// ─── 6. Coin ────────────────────────────────────────────────────
function Coin({ reduceMotion }: { reduceMotion: boolean }) {
  const ref = useGentleSpin(0.25, reduceMotion)

  return (
    <Float
      speed={reduceMotion ? 0 : 2.5}
      rotationIntensity={reduceMotion ? 0 : 0.5}
      floatIntensity={reduceMotion ? 0 : 0.8}
      floatingRange={[-0.08, 0.08]}
    >
      <group ref={ref} position={[0.6, 1.8, 1.0]} scale={0.4}>
        {/* Coin body */}
        <mesh castShadow>
          <cylinderGeometry args={[0.5, 0.5, 0.1, 32]} />
          <meshStandardMaterial color={COLORS.marigold} roughness={0.2} metalness={0.7} />
        </mesh>

        {/* Coin rim */}
        <mesh>
          <torusGeometry args={[0.5, 0.04, 12, 32]} />
          <meshStandardMaterial color={COLORS.marigoldDark} roughness={0.25} metalness={0.8} />
        </mesh>

        {/* Inner embossed circle - top */}
        <mesh position={[0, 0.055, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.2, 0.25, 32]} />
          <meshStandardMaterial color={COLORS.marigoldDark} roughness={0.3} metalness={0.6} />
        </mesh>

        {/* Inner embossed circle - bottom */}
        <mesh position={[0, -0.055, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.2, 0.25, 32]} />
          <meshStandardMaterial color={COLORS.marigoldDark} roughness={0.3} metalness={0.6} />
        </mesh>
      </group>
    </Float>
  )
}

// ─── 7. Floating Leaf / Eco Badge ───────────────────────────────
function EcoBadge({ reduceMotion }: { reduceMotion: boolean }) {
  const ref = useGentleSpin(0.2, reduceMotion)

  return (
    <Float
      speed={reduceMotion ? 0 : 1.4}
      rotationIntensity={reduceMotion ? 0 : 0.35}
      floatIntensity={reduceMotion ? 0 : 0.65}
      floatingRange={[-0.1, 0.1]}
    >
      <group ref={ref} position={[-0.8, 2.0, -1.2]} scale={0.35}>
        {/* Badge circle */}
        <mesh castShadow>
          <sphereGeometry args={[0.6, 32, 32]} />
          <meshStandardMaterial
            color={COLORS.accent}
            roughness={0.3}
            metalness={0.1}
            transparent
            opacity={0.85}
          />
        </mesh>

        {/* Inner sphere — glass-like core */}
        <mesh>
          <sphereGeometry args={[0.4, 24, 24]} />
          <meshStandardMaterial
            color={COLORS.primary}
            roughness={0.15}
            metalness={0.2}
            transparent
            opacity={0.6}
          />
        </mesh>

        {/* Tiny leaf shape */}
        <mesh position={[0, 0.05, 0.35]} rotation={[0.2, 0, 0.3]}>
          <sphereGeometry args={[0.15, 8, 6, 0, Math.PI]} />
          <meshStandardMaterial
            color={COLORS.deep}
            roughness={0.5}
            side={THREE.DoubleSide}
          />
        </mesh>
      </group>
    </Float>
  )
}

// ─── Lighting rig ───────────────────────────────────────────────
function Lights() {
  return (
    <>
      <ambientLight intensity={0.65} color="#FFFBF0" />
      <directionalLight
        position={[8, 10, 5]}
        intensity={1.0}
        color="#FFF3DC"
        castShadow
        shadow-mapSize-width={1024}
        shadow-mapSize-height={1024}
      />
      <directionalLight position={[-5, 4, -6]} intensity={0.35} color="#DDF2E7" />
      <pointLight position={[0, -3, 4]} intensity={0.3} color={COLORS.marigold} />
    </>
  )
}

// ─── Scene content ──────────────────────────────────────────────
function SceneContent({ reduceMotion }: { reduceMotion: boolean }) {
  return (
    <>
      <Lights />
      <OrbitControls
        autoRotate
        autoRotateSpeed={reduceMotion ? 0 : 0.4}
        enableZoom={false}
        enablePan={false}
        enableRotate={false}
      />

      <ShoppingBag reduceMotion={reduceMotion} />
      <MilkCarton reduceMotion={reduceMotion} />
      <Apple reduceMotion={reduceMotion} />
      <DeliveryBox reduceMotion={reduceMotion} />
      <StoreIcon reduceMotion={reduceMotion} />
      <Coin reduceMotion={reduceMotion} />
      <EcoBadge reduceMotion={reduceMotion} />
    </>
  )
}

// ─── Public component ───────────────────────────────────────────
interface HeroSceneProps {
  reduceMotion?: boolean
  className?: string
}

export function HeroScene({ reduceMotion = false, className }: HeroSceneProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const frameloop = useCanvasVisibility(containerRef, reduceMotion)

  return (
    <div ref={containerRef} className={className}>
      <Canvas
        frameloop={frameloop}
        gl={STANDARD_GL_PROPS}
        camera={{ position: [0, 0, 7], fov: 45 }}
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

export default HeroScene
