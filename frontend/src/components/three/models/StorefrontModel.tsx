import { useMemo } from 'react'
import { useSubtleRotation, THREE_PALETTE } from '../common'
import * as THREE from 'three'

interface StorefrontModelProps {
  reduceMotion?: boolean
  scale?: number
  position?: [number, number, number]
}

export function StorefrontModel({
  reduceMotion = false,
  scale = 1,
  position = [0, 0, 0],
}: StorefrontModelProps) {
  const ref = useSubtleRotation(0.16, reduceMotion)

  const awningGeometry = useMemo(() => {
    const shape = new THREE.Shape()
    shape.moveTo(-0.9, 0)
    shape.lineTo(0.9, 0)
    shape.lineTo(0.75, -0.35)
    shape.quadraticCurveTo(0.45, -0.55, 0.3, -0.35)
    shape.quadraticCurveTo(0.15, -0.55, 0, -0.35)
    shape.quadraticCurveTo(-0.15, -0.55, -0.3, -0.35)
    shape.quadraticCurveTo(-0.45, -0.55, -0.75, -0.35)
    shape.lineTo(-0.9, 0)
    return new THREE.ExtrudeGeometry(shape, { depth: 0.6, bevelEnabled: false })
  }, [])

  return (
    <group ref={ref} position={position} scale={scale}>
      {/* Store Building Base */}
      <mesh castShadow position={[0, 0, 0]}>
        <boxGeometry args={[1.7, 1.4, 1.1]} />
        <meshStandardMaterial color={THREE_PALETTE.ivory} roughness={0.4} />
      </mesh>

      {/* Roof Parapet */}
      <mesh position={[0, 0.72, 0]}>
        <boxGeometry args={[1.78, 0.12, 1.18]} />
        <meshStandardMaterial color={THREE_PALETTE.deep} roughness={0.3} />
      </mesh>

      {/* Store Awning */}
      <mesh
        position={[0, 0.62, -0.28]}
        castShadow
        geometry={awningGeometry}
      >
        <meshStandardMaterial
          color={THREE_PALETTE.primary}
          roughness={0.4}
          side={THREE.DoubleSide}
        />
      </mesh>

      {/* Store Signboard */}
      <group position={[0, 0.85, 0.3]}>
        <mesh castShadow>
          <boxGeometry args={[1.2, 0.28, 0.06]} />
          <meshStandardMaterial color={THREE_PALETTE.deep} roughness={0.3} />
        </mesh>
        <mesh position={[0, 0, 0.04]}>
          <boxGeometry args={[0.9, 0.16, 0.02]} />
          <meshStandardMaterial color={THREE_PALETTE.accent} roughness={0.4} />
        </mesh>
      </group>

      {/* Front Entrance Door */}
      <mesh position={[0, -0.25, 0.56]}>
        <boxGeometry args={[0.42, 0.8, 0.02]} />
        <meshStandardMaterial color={THREE_PALETTE.deep} roughness={0.4} />
      </mesh>

      {/* Left Shop Display Window */}
      <mesh position={[-0.52, 0.05, 0.56]}>
        <boxGeometry args={[0.42, 0.5, 0.02]} />
        <meshStandardMaterial
          color={THREE_PALETTE.accent}
          roughness={0.2}
          metalness={0.2}
        />
      </mesh>

      {/* Right Shop Display Window */}
      <mesh position={[0.52, 0.05, 0.56]}>
        <boxGeometry args={[0.42, 0.5, 0.02]} />
        <meshStandardMaterial
          color={THREE_PALETTE.accent}
          roughness={0.2}
          metalness={0.2}
        />
      </mesh>
    </group>
  )
}
export default StorefrontModel
