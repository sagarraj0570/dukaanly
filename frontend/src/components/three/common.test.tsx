import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import {
  checkWebGLSupport,
  useReducedMotionPreference,
  THREE_PALETTE,
  STANDARD_GL_PROPS,
  STANDARD_DPR,
  handleContextLost,
  ThreeErrorBoundary,
} from './common'

describe('Three.js Common Utilities', () => {
  it('defines the approved brand palette', () => {
    expect(THREE_PALETTE.primary).toBe('#1B7F55')
    expect(THREE_PALETTE.primaryLight).toBe('#2E9A6B')
    expect(THREE_PALETTE.deep).toBe('#0F3D2E')
    expect(THREE_PALETTE.marigold).toBe('#F5A524')
    expect(THREE_PALETTE.accent).toBe('#BFE5D0')
    expect(THREE_PALETTE.softGreen).toBe('#F1FAF5')
  })

  it('provides standard low-power GL settings and DPR clamping', () => {
    expect(STANDARD_GL_PROPS.powerPreference).toBe('low-power')
    expect(STANDARD_GL_PROPS.alpha).toBe(true)
    expect(STANDARD_DPR).toEqual([1, 1.5])
  })

  it('correctly handles WebGL detection in test environment', () => {
    const supported = checkWebGLSupport()
    expect(typeof supported).toBe('boolean')
  })

  it('correctly checks reduced motion preference without crashing', () => {
    const preference = useReducedMotionPreference()
    expect(typeof preference).toBe('boolean')
  })

  it('handles context lost event without throwing', () => {
    const mockEvent = { preventDefault: vi.fn() } as unknown as Event
    expect(() => handleContextLost(mockEvent)).not.toThrow()
    expect(mockEvent.preventDefault).toHaveBeenCalled()
  })

  it('ThreeErrorBoundary renders children when there is no error', () => {
    render(
      <ThreeErrorBoundary fallback={<div>Fallback UI</div>}>
        <div>Active 3D Scene</div>
      </ThreeErrorBoundary>
    )
    expect(screen.getByText('Active 3D Scene')).toBeTruthy()
  })

  it('ThreeErrorBoundary catches errors and renders fallback', () => {
    const BuggyComponent = () => {
      throw new Error('WebGL Context Lost')
    }
    const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    render(
      <ThreeErrorBoundary fallback={<div>Safe 2D Fallback</div>}>
        <BuggyComponent />
      </ThreeErrorBoundary>
    )

    expect(screen.getByText('Safe 2D Fallback')).toBeTruthy()
    consoleSpy.mockRestore()
  })
})
