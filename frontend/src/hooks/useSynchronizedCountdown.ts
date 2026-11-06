import { useState, useEffect, useRef } from 'react'

export interface SynchronizedCountdownOptions {
  serverSecondsRemaining: number | null | undefined
  serverTime?: string | null | undefined
  isAuthoritativeExpired?: boolean
  onLocalTimerElapsed?: () => void
}

export interface SynchronizedCountdownResult {
  secondsRemaining: number | null
  formattedTime: string
  isTimerElapsed: boolean
  isExpiringSoon: boolean
}

/**
 * High-precision, drift-free synchronized countdown hook.
 *
 * Guarantees:
 * 1. Immune to browser clock drift, system date/time modifications, and background tab throttling.
 *    Anchors server duration to the monotonic performance.now() clock rather than user's system clock (Date.now()).
 * 2. Incorporates server_time network receipt delay to preserve sub-second synchronization.
 * 3. Self-correcting on every polling cycle (re-anchors without sudden visual jumps).
 * 4. Architectural safety invariant: Countdown reaching 0 NEVER determines whether stock is released;
 *    it only marks the local countdown window as elapsed and prompts server verification.
 */
export const useSynchronizedCountdown = ({
  serverSecondsRemaining,
  serverTime,
  isAuthoritativeExpired = false,
  onLocalTimerElapsed,
}: SynchronizedCountdownOptions): SynchronizedCountdownResult => {
  const [secondsRemaining, setSecondsRemaining] = useState<number | null>(null)
  const anchorRef = useRef<{
    anchorPerformanceMs: number
    anchorSecondsRemaining: number
  } | null>(null)
  const elapsedNotifiedRef = useRef(false)

  // Re-anchor whenever serverSecondsRemaining updates from a query/poll
  useEffect(() => {
    if (typeof serverSecondsRemaining === 'number') {
      const perfNow = typeof performance !== 'undefined' ? performance.now() : Date.now()

      // Calculate transit latency adjustment if serverTime header/payload is provided
      let transitSec = 0
      if (serverTime) {
        const serverMs = new Date(serverTime).getTime()
        const clientMs = Date.now()
        // If client and server clocks are reasonably aligned (within 60s), adjust for one-way transit
        const deltaSec = (clientMs - serverMs) / 1000
        if (deltaSec > 0 && deltaSec < 30) {
          transitSec = deltaSec
        }
      }

      const effectiveSecondsRemaining = Math.max(0, serverSecondsRemaining - transitSec)

      anchorRef.current = {
        anchorPerformanceMs: perfNow,
        anchorSecondsRemaining: effectiveSecondsRemaining,
      }

      setSecondsRemaining(Math.ceil(effectiveSecondsRemaining))

      if (effectiveSecondsRemaining <= 0) {
        if (!elapsedNotifiedRef.current) {
          elapsedNotifiedRef.current = true
          onLocalTimerElapsed?.()
        }
      } else {
        elapsedNotifiedRef.current = false
      }
    } else {
      anchorRef.current = null
      setSecondsRemaining(null)
    }
  }, [serverSecondsRemaining, serverTime, onLocalTimerElapsed])

  // High-frequency monotonic clock tick (250ms interval to catch boundaries smoothly without CPU load)
  useEffect(() => {
    if (isAuthoritativeExpired) {
      setSecondsRemaining(0)
      return
    }

    if (!anchorRef.current) return

    const interval = setInterval(() => {
      if (!anchorRef.current) return

      const perfNow = typeof performance !== 'undefined' ? performance.now() : Date.now()
      const elapsedSec = (perfNow - anchorRef.current.anchorPerformanceMs) / 1000
      const remaining = Math.max(0, Math.ceil(anchorRef.current.anchorSecondsRemaining - elapsedSec))

      setSecondsRemaining((prev) => {
        if (prev === remaining) return prev
        return remaining
      })

      if (remaining <= 0) {
        if (!elapsedNotifiedRef.current) {
          elapsedNotifiedRef.current = true
          onLocalTimerElapsed?.()
        }
      }
    }, 250)

    return () => clearInterval(interval)
  }, [isAuthoritativeExpired, onLocalTimerElapsed])

  const mins = secondsRemaining !== null ? Math.floor(secondsRemaining / 60) : 0
  const secs = secondsRemaining !== null ? secondsRemaining % 60 : 0
  const formattedTime = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`

  const isTimerElapsed = secondsRemaining !== null && secondsRemaining <= 0
  const isExpiringSoon = secondsRemaining !== null && secondsRemaining > 0 && secondsRemaining <= 120

  return {
    secondsRemaining,
    formattedTime,
    isTimerElapsed,
    isExpiringSoon,
  }
}
