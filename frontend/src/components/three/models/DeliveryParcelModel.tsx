import { useSubtleRotation, THREE_PALETTE } from '../common'

interface DeliveryParcelModelProps {
  reduceMotion?: boolean
  scale?: number
  position?: [number, number, number]
  celebrate?: boolean
}

export function DeliveryParcelModel({
  reduceMotion = false,
  scale = 1,
  position = [0, 0, 0],
  celebrate = false,
}: DeliveryParcelModelProps) {
  const ref = useSubtleRotation(0.22, reduceMotion)

  return (
    <group ref={ref} position={position} scale={scale}>
      {/* Parcel Box Body */}
      <mesh castShadow>
        <boxGeometry args={[1.4, 1.1, 1.2]} />
        <meshStandardMaterial
          color={THREE_PALETTE.cardboard}
          roughness={0.65}
          metalness={0.0}
        />
      </mesh>

      {/* Main Top Sealing Tape */}
      <mesh position={[0, 0.555, 0]}>
        <boxGeometry args={[0.26, 0.015, 1.21]} />
        <meshStandardMaterial
          color={celebrate ? THREE_PALETTE.gold : THREE_PALETTE.cardboardDark}
          roughness={0.4}
        />
      </mesh>

      {/* Front Edge Tape Fold */}
      <mesh position={[0, 0.555, 0.605]}>
        <boxGeometry args={[0.26, 0.015, 0.02]} />
        <meshStandardMaterial
          color={celebrate ? THREE_PALETTE.gold : THREE_PALETTE.cardboardDark}
          roughness={0.4}
        />
      </mesh>

      {/* Cross Ribbon if Celebratory (Success state) */}
      {celebrate && (
        <mesh position={[0, 0.556, 0]} rotation={[0, Math.PI / 2, 0]}>
          <boxGeometry args={[0.26, 0.016, 1.41]} />
          <meshStandardMaterial color={THREE_PALETTE.gold} roughness={0.3} metalness={0.4} />
        </mesh>
      )}

      {/* Fragile / Verified Brand Seal */}
      <mesh position={[0.3, 0.1, 0.61]}>
        <circleGeometry args={[0.18, 24]} />
        <meshStandardMaterial color={THREE_PALETTE.primary} roughness={0.4} />
      </mesh>

      {/* Barcode / Shipping Label */}
      <mesh position={[-0.25, 0.05, 0.61]}>
        <boxGeometry args={[0.35, 0.25, 0.01]} />
        <meshStandardMaterial color={THREE_PALETTE.ivory} roughness={0.7} />
      </mesh>

      {/* Floating Checkmark Badge if Celebratory */}
      {celebrate && (
        <group position={[0, 0.95, 0]} scale={0.45}>
          <mesh castShadow>
            <sphereGeometry args={[0.5, 24, 24]} />
            <meshStandardMaterial color={THREE_PALETTE.primary} roughness={0.3} metalness={0.2} />
          </mesh>
          <mesh position={[0, 0, 0.42]}>
            <circleGeometry args={[0.26, 24]} />
            <meshStandardMaterial color={THREE_PALETTE.accent} roughness={0.3} />
          </mesh>
        </group>
      )}
    </group>
  )
}
export default DeliveryParcelModel
