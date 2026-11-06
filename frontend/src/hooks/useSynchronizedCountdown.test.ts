import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useSynchronizedCountdown } from './useSynchronizedCountdown'

describe('useSynchronizedCountdown', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('initializes formatted time and remaining seconds from authoritative server remaining duration', () => {
    const { result } = renderHook(() =>
      useSynchronizedCountdown({
        serverSecondsRemaining: 900,
        serverTime: new Date().toISOString(),
      })
    )

    expect(result.current.secondsRemaining).toBe(900)
    expect(result.current.formattedTime).toBe('15:00')
    expect(result.current.isTimerElapsed).toBe(false)
    expect(result.current.isExpiringSoon).toBe(false)
  })

  it('is immune to client Date.now() drift by relying on monotonic time advancement', () => {
    let mockPerfNow = 1000
    vi.spyOn(performance, 'now').mockImplementation(() => mockPerfNow)

    const { result } = renderHook(() =>
      useSynchronizedCountdown({
        serverSecondsRemaining: 60,
      })
    )

    expect(result.current.secondsRemaining).toBe(60)

    // Advance monotonic performance.now by 10 seconds
    mockPerfNow += 10000
    act(() => {
      vi.advanceTimersByTime(10000)
    })

    expect(result.current.secondsRemaining).toBe(50)
    expect(result.current.formattedTime).toBe('00:50')
  })

  it('triggers onLocalTimerElapsed callback when countdown reaches zero without unilaterally releasing stock', () => {
    let mockPerfNow = 1000
    vi.spyOn(performance, 'now').mockImplementation(() => mockPerfNow)
    const onElapsed = vi.fn()

    const { result } = renderHook(() =>
      useSynchronizedCountdown({
        serverSecondsRemaining: 2,
        onLocalTimerElapsed: onElapsed,
      })
    )

    expect(result.current.secondsRemaining).toBe(2)
    expect(onElapsed).not.toHaveBeenCalled()

    // Advance time by 3 seconds
    mockPerfNow += 3000
    act(() => {
      vi.advanceTimersByTime(3000)
    })

    expect(result.current.secondsRemaining).toBe(0)
    expect(result.current.isTimerElapsed).toBe(true)
    expect(onElapsed).toHaveBeenCalledTimes(1)
  })

  it('re-anchors cleanly when polling returns updated serverSecondsRemaining', () => {
    let mockPerfNow = 1000
    vi.spyOn(performance, 'now').mockImplementation(() => mockPerfNow)

    const { result, rerender } = renderHook(
      ({ remaining }) =>
        useSynchronizedCountdown({
          serverSecondsRemaining: remaining,
        }),
      { initialProps: { remaining: 100 } }
    )

    expect(result.current.secondsRemaining).toBe(100)

    // Advance 5 seconds locally
    mockPerfNow += 5000
    act(() => {
      vi.advanceTimersByTime(5000)
    })
    expect(result.current.secondsRemaining).toBe(95)

    // Polling response arrives reporting 94 seconds remaining
    rerender({ remaining: 94 })
    expect(result.current.secondsRemaining).toBe(94)
  })

  it('flags isExpiringSoon when remaining time is 2 minutes or less', () => {
    const { result } = renderHook(() =>
      useSynchronizedCountdown({
        serverSecondsRemaining: 120,
      })
    )

    expect(result.current.isExpiringSoon).toBe(true)
  })
})
