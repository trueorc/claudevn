import { useState, useEffect, useRef, useCallback } from 'react'
import { useLocation } from 'react-router-dom'

/**
 * Tracks navigation direction between dashboard and other pages
 * to enable smooth chat panel transition animations.
 *
 * Returns:
 *   - transitionClass: CSS class to apply for the current animation direction
 *   - isDashboard: whether the current route is the dashboard
 *   - scrollPositionRef: ref to store/restore scroll position across transitions
 */
export default function useChatTransition() {
  const location = useLocation()
  const isDashboard = location.pathname === '/dashboard' || location.pathname === '/'
  const prevIsDashboardRef = useRef(isDashboard)
  const [transitionClass, setTransitionClass] = useState('')
  const scrollPositionRef = useRef(0)

  useEffect(() => {
    const wasDashboard = prevIsDashboardRef.current
    prevIsDashboardRef.current = isDashboard

    if (wasDashboard && !isDashboard) {
      // Leaving dashboard → sidebar appears
      setTransitionClass('chat-transition-to-sidebar')
    } else if (!wasDashboard && isDashboard) {
      // Entering dashboard → center chat appears
      setTransitionClass('chat-transition-to-center')
    } else {
      return
    }

    const timer = setTimeout(() => setTransitionClass(''), 350)
    return () => clearTimeout(timer)
  }, [isDashboard])

  const saveScrollPosition = useCallback((scrollTop) => {
    scrollPositionRef.current = scrollTop
  }, [])

  return { transitionClass, isDashboard, scrollPositionRef, saveScrollPosition }
}
