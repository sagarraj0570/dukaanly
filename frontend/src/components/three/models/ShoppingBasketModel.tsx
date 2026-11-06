import { useSubtleRotation, THREE_PALETTE } from '../common'
import * as THREE from 'three'

interface ShoppingBasketModelProps {
  reduceMotion?: boolean
  scale?: number
  position?: [number, number, number]
}

export function ShoppingBasketModel({
  reduceMotion = false,
  scale = 1,
  position = [0, 0, 0],
}: ShoppingBasketModelProps) {
  const ref = useSubtleRotation(0.2, reduceMotion)

  return (
    <group ref={ref} position={position} scale={scale}>
      {/* Basket Main Base */}
      <mesh castShadow position={[0, -0.3, 0]}>
        <boxGeometry args={[1.5, 0.7, 1.1]} />
        <meshStandardMaterial
          color={THREE_PALETTE.primary}
          roughness={0.35}
          metalness={0.08}
        />
      </mesh>

      {/* Basket Inner Hollow Accent */}
      <mesh position={[0, -0.28, 0]}>
        <boxGeometry args={[1.4, 0.68, 1.0]} />
        <meshStandardMaterial color={THREE_PALETTE.deep} roughness={0.5} />
      </mesh>

      {/* Basket Rim */}
      <mesh position={[0, 0.06, 0]}>
        <boxGeometry args={[1.58, 0.08, 1.18]} />
        <meshStandardMaterial color={THREE_PALETTE.primaryLight} roughness={0.3} metalness={0.15} />
      </mesh>

      {/* Basket Handle (Arch) in warm marigold */}
      <mesh position={[0, 0.55, 0]} rotation={[0, 0, 0]} castShadow>
        <torusGeometry args={[0.55, 0.045, 12, 24, Math.PI]} />
        <meshStandardMaterial color={THREE_PALETTE.marigold} roughness={0.25} metalness={0.2} />
      </mesh>

      {/* Grocery Item 1: Milk Carton */}
      <group position={[-0.35, 0.2, -0.15]} rotation={[0, 0.2, 0.05]} scale={0.42}>
        <mesh castShadow>
          <boxGeometry args={[0.7, 1.3, 0.7]} />
          <meshStandardMaterial color="#FFFFFF" roughness={0.4} />
        </mesh>
        <mesh position={[0, 0.8, 0]} rotation={[0, Math.PI / 4, 0]}>
          <coneGeometry args={[0.45, 0.4, 4]} />
          <meshStandardMaterial color={THREE_PALETTE.softGreen} roughness={0.4} />
        </mesh>
        <mesh position={[0, 0, 0.36]}>
          <boxGeometry args={[0.6, 0.6, 0.02]} />
          <meshStandardMaterial color={THREE_PALETTE.primaryLight} roughness={0.3} />
        </mesh>
      </group>

      {/* Grocery Item 2: Red Apple */}
      <group position={[0.35, 0.12, 0.2]} scale={0.32}>
        <mesh castShadow>
          <sphereGeometry args={[0.7, 24, 24]} />
          <meshStandardMaterial color={THREE_PALETTE.red} roughness={0.25} />
        </mesh>
        <mesh position={[0, 0.75, 0]}>
          <cylinderGeometry args={[0.04, 0.05, 0.3, 8]} />
          <meshStandardMaterial color="#5D4037" roughness={0.7} />
        </mesh>
      </group>

      {/* Grocery Item 3: Baguette / Bread Loaf */}
      <mesh
        position={[0.1, 0.35, -0.2]}
        rotation={[0.3, 0.2, 0.4]}
        scale={[0.25, 0.75, 0.25]}
        castShadow
      >
        <capsuleGeometry args={[0.4, 0.8, 12, 16]} />
        <meshStandardMaterial color={THREE_PALETTE.breadGolden} roughness={0.65} />
      </mesh>

      {/* Grocery Item 4: Green Leaf Produce */}
      <mesh
        position={[-0.1, 0.2, 0.25]}
        rotation={[-0.2, 0.3, -0.4]}
        scale={0.25}
      >
        <sphereGeometry args={[0.6, 12, 8, 0, Math.PI]} />
        <meshStandardMaterial
          color={THREE_PALETTE.primaryLight}
          roughness={0.45}
          side={THREE.DoubleSide}
        />
      </mesh>
    </group>
  )
}
export default ShoppingBasketModel
