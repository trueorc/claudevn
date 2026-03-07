import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import useChatTransition from './useChatTransition'

function createWrapper(initialEntries = ['/dashboard']) {
  return ({ children }) =>
    createElement(MemoryRouter, { initialEntries }, children)
}

describe('useChatTransition', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns isDashboard=true on /dashboard', () => {
    const { result } = renderHook(() => useChatTransition(), {
      wrapper: createWrapper(['/dashboard']),
    })
    expect(result.current.isDashboard).toBe(true)
  })

  it('returns isDashboard=true on /', () => {
    const { result } = renderHook(() => useChatTransition(), {
      wrapper: createWrapper(['/']),
    })
    expect(result.current.isDashboard).toBe(true)
  })

  it('returns isDashboard=false on other routes', () => {
    const { result } = renderHook(() => useChatTransition(), {
      wrapper: createWrapper(['/backlog']),
    })
    expect(result.current.isDashboard).toBe(false)
  })

  it('starts with no transition class', () => {
    const { result } = renderHook(() => useChatTransition(), {
      wrapper: createWrapper(['/dashboard']),
    })
    expect(result.current.transitionClass).toBe('')
  })

  it('saves scroll position via callback', () => {
    const { result } = renderHook(() => useChatTransition(), {
      wrapper: createWrapper(['/dashboard']),
    })
    act(() => {
      result.current.saveScrollPosition(42)
    })
    expect(result.current.scrollPositionRef.current).toBe(42)
  })

  it('provides a stable scrollPositionRef initialized to 0', () => {
    const { result } = renderHook(() => useChatTransition(), {
      wrapper: createWrapper(['/dashboard']),
    })
    expect(result.current.scrollPositionRef.current).toBe(0)
  })
})
