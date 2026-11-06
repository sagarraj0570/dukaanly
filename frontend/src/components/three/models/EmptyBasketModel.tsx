import { useSubtleRotation, THREE_PALETTE } from '../common'

interface EmptyBasketModelProps {
  reduceMotion?: boolean
  scale?: number
  position?: [number, number, number]
  type?: 'cart' | 'search' | 'orders' | 'inventory' | 'store'
}

export function EmptyBasketModel({
  reduceMotion = false,
  scale = 1,
  position = [0, 0, 0],
  type = 'cart',
}: EmptyBasketModelProps) {
  const ref = useSubtleRotation(0.2, reduceMotion)

  return (
    <group ref={ref} position={position} scale={scale}>
      {/* Open Basket Structure */}
      <mesh castShadow position={[0, -0.15, 0]}>
        <boxGeometry args={[1.5, 0.6, 1.1]} />
        <meshStandardMaterial
          color={THREE_PALETTE.primary}
          roughness={0.4}
          metalness={0.1}
        />
      </mesh>

      {/* Hollow Interior */}
      <mesh position={[0, -0.1, 0]}>
        <boxGeometry args={[1.36, 0.55, 0.96]} />
        <meshStandardMaterial color={THREE_PALETTE.softGreen} roughness={0.6} />
      </mesh>

      {/* Rim */}
      <mesh position={[0, 0.16, 0]}>
        <boxGeometry args={[1.56, 0.06, 1.16]} />
        <meshStandardMaterial color={THREE_PALETTE.accent} roughness={0.3} />
      </mesh>

      {/* Handle */}
      <mesh position={[0, 0.5, 0]} castShadow>
        <torusGeometry args={[0.55, 0.045, 12, 24, Math.PI]} />
        <meshStandardMaterial color={THREE_PALETTE.deep} roughness={0.3} metalness={0.2} />
      </mesh>

      {/* Contextual Floating Icon Badge */}
      {type === 'search' && (
        <group position={[0, 0.5, 0.2]} scale={0.4}>
          <mesh castShadow>
            <torusGeometry args={[0.4, 0.08, 12, 24]} />
            <meshStandardMaterial color={THREE_PALETTE.gold} roughness={0.3} metalness={0.7} />
          </mesh>
          <mesh position={[0.3, -0.3, 0]} rotation={[0, 0, -Math.PI / 4]}>
            <cylinderGeometry args={[0.06, 0.06, 0.5, 12]} />
            <meshStandardMaterial color={THREE_PALETTE.deep} roughness={0.4} />
          </mesh>
        </group>
      )}

      {type === 'orders' && (
        <group position={[0, 0.35, 0]} scale={0.45}>
          <mesh castShadow>
            <boxGeometry args={[0.8, 0.6, 0.7]} />
            <meshStandardMaterial color={THREE_PALETTE.cardboard} roughness={0.6} />
          </mesh>
          <mesh position={[0, 0.31, 0]}>
            <boxGeometry args={[0.16, 0.02, 0.71]} />
            <meshStandardMaterial color={THREE_PALETTE.cardboardDark} />
          </mesh>
        </group>
      )}
    </group>
  )
}
export default EmptyBasketModel
