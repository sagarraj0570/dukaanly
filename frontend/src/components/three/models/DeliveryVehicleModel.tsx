import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { THREE_PALETTE } from '../common'
import type { Group } from 'three'

interface DeliveryVehicleModelProps {
  reduceMotion?: boolean
  scale?: number
  position?: [number, number, number]
  isMoving?: boolean
}

export function DeliveryVehicleModel({
  reduceMotion = false,
  scale = 1,
  position = [0, 0, 0],
  isMoving = true,
}: DeliveryVehicleModelProps) {
  const groupRef = useRef<Group>(null!)
  const frontWheelRef = useRef<Group>(null!)
  const backWheelRef = useRef<Group>(null!)

  useFrame((_, delta) => {
    if (reduceMotion || !groupRef.current) return
    // Gentle hovering sway
    groupRef.current.rotation.y += delta * 0.15

    if (isMoving && frontWheelRef.current && backWheelRef.current) {
      frontWheelRef.current.rotation.x += delta * 4
      backWheelRef.current.rotation.x += delta * 4
    }
  })

  return (
    <group ref={groupRef} position={position} scale={scale}>
      {/* Scooter Chassis / Body */}
      <mesh castShadow position={[0, -0.05, 0]}>
        <boxGeometry args={[0.5, 0.35, 1.4]} />
        <meshStandardMaterial
          color={THREE_PALETTE.primary}
          roughness={0.3}
          metalness={0.2}
        />
      </mesh>

      {/* Footrest Floorboard */}
      <mesh position={[0, -0.2, 0.1]}>
        <boxGeometry args={[0.65, 0.08, 0.6]} />
        <meshStandardMaterial color={THREE_PALETTE.deep} roughness={0.5} />
      </mesh>

      {/* Seat */}
      <mesh position={[0, 0.22, -0.2]}>
        <boxGeometry args={[0.42, 0.12, 0.5]} />
        <meshStandardMaterial color={THREE_PALETTE.darkTire} roughness={0.8} />
      </mesh>

      {/* Front Steering Column */}
      <mesh position={[0, 0.35, 0.55]} rotation={[-0.2, 0, 0]}>
        <cylinderGeometry args={[0.04, 0.05, 0.8, 12]} />
        <meshStandardMaterial color={THREE_PALETTE.silver} metalness={0.8} roughness={0.2} />
      </mesh>

      {/* Handlebars */}
      <mesh position={[0, 0.72, 0.48]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.03, 0.03, 0.75, 12]} />
        <meshStandardMaterial color={THREE_PALETTE.silver} metalness={0.8} />
      </mesh>

      {/* Headlight */}
      <mesh position={[0, 0.58, 0.65]}>
        <sphereGeometry args={[0.1, 16, 16]} />
        <meshStandardMaterial
          color="#FFFBF0"
          emissive="#FFF5CC"
          emissiveIntensity={0.6}
          roughness={0.1}
        />
      </mesh>

      {/* Front Wheel */}
      <group ref={frontWheelRef} position={[0, -0.4, 0.65]}>
        <mesh rotation={[0, 0, Math.PI / 2]} castShadow>
          <torusGeometry args={[0.26, 0.08, 12, 24]} />
          <meshStandardMaterial color={THREE_PALETTE.darkTire} roughness={0.9} />
        </mesh>
        <mesh rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.16, 0.16, 0.08, 12]} />
          <meshStandardMaterial color={THREE_PALETTE.silver} metalness={0.7} />
        </mesh>
      </group>

      {/* Back Wheel */}
      <group ref={backWheelRef} position={[0, -0.4, -0.55]}>
        <mesh rotation={[0, 0, Math.PI / 2]} castShadow>
          <torusGeometry args={[0.26, 0.08, 12, 24]} />
          <meshStandardMaterial color={THREE_PALETTE.darkTire} roughness={0.9} />
        </mesh>
        <mesh rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.16, 0.16, 0.08, 12]} />
          <meshStandardMaterial color={THREE_PALETTE.silver} metalness={0.7} />
        </mesh>
      </group>

      {/* Delivery Parcel Cargo Box mounted at back */}
      <group position={[0, 0.35, -0.55]} scale={0.65}>
        <mesh castShadow>
          <boxGeometry args={[0.85, 0.75, 0.75]} />
          <meshStandardMaterial
            color={THREE_PALETTE.primary}
            roughness={0.3}
            metalness={0.1}
          />
        </mesh>
        {/* Brand circle emblem on courier box */}
        <mesh position={[0, 0, 0.38]}>
          <circleGeometry args={[0.2, 24]} />
          <meshStandardMaterial color={THREE_PALETTE.accent} roughness={0.4} />
        </mesh>
      </group>
    </group>
  )
}
export default DeliveryVehicleModel
