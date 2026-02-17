import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useAuth } from './useAuth'

vi.mock('../api/auth', () => ({
  getAuthStatus: vi.fn(),
  submitToken: vi.fn(),
}))

import { getAuthStatus, submitToken } from '../api/auth'

const flushPromises = () => act(() => new Promise(resolve => setTimeout(resolve, 0)))

describe('useAuth', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('basic auth flow', () => {
    it('starts in loading state', () => {
      getAuthStatus.mockReturnValue(new Promise(() => {})) // never resolves
      const { result } = renderHook(() => useAuth())
      expect(result.current.loading).toBe(true)
      expect(result.current.authenticated).toBe(false)
      expect(result.current.error).toBe(null)
    })

    it('sets authenticated when status returns authenticated', async () => {
      getAuthStatus.mockResolvedValue({ status: 'authenticated', authenticated: true })
      const { result } = renderHook(() => useAuth())

      await flushPromises()

      expect(result.current.loading).toBe(false)
      expect(result.current.authenticated).toBe(true)
      expect(result.current.expired).toBe(false)
      expect(result.current.error).toBe(null)
    })

    it('handles auth disabled (404 returns authenticated: true from api)', async () => {
      getAuthStatus.mockResolvedValue({ status: 'disabled', authenticated: true })
      const { result } = renderHook(() => useAuth())

      await flushPromises()

      expect(result.current.loading).toBe(false)
      expect(result.current.authenticated).toBe(true)
      expect(result.current.error).toBe(null)
    })
  })

  describe('error handling', () => {
    it('does NOT bypass auth gate on network error', async () => {
      getAuthStatus.mockRejectedValue(new Error('Failed to fetch'))
      const { result } = renderHook(() => useAuth())

      await flushPromises()

      expect(result.current.loading).toBe(false)
      expect(result.current.authenticated).toBe(false)
      expect(result.current.error).toBe('Failed to fetch')
    })

    it('does NOT bypass auth gate on 500 error', async () => {
      getAuthStatus.mockRejectedValue(new Error('Auth status request failed: Internal Server Error'))
      const { result } = renderHook(() => useAuth())

      await flushPromises()

      expect(result.current.loading).toBe(false)
      expect(result.current.authenticated).toBe(false)
      expect(result.current.error).toBe('Auth status request failed: Internal Server Error')
    })

    it('provides fallback error message when error has no message', async () => {
      getAuthStatus.mockRejectedValue({})
      const { result } = renderHook(() => useAuth())

      await flushPromises()

      expect(result.current.loading).toBe(false)
      expect(result.current.authenticated).toBe(false)
      expect(result.current.error).toBe('Cannot connect to server')
    })

    it('clears error on successful retry after failure', async () => {
      getAuthStatus.mockRejectedValueOnce(new Error('Failed to fetch'))
      const { result } = renderHook(() => useAuth())

      await flushPromises()
      expect(result.current.error).toBe('Failed to fetch')

      getAuthStatus.mockResolvedValue({ status: 'authenticated', authenticated: true })

      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 3100))
      })

      expect(result.current.error).toBe(null)
      expect(result.current.authenticated).toBe(true)
    }, 10000)
  })

  describe('token submission', () => {
    it('provides submitToken function', () => {
      getAuthStatus.mockReturnValue(new Promise(() => {}))
      const { result } = renderHook(() => useAuth())
      expect(typeof result.current.submitToken).toBe('function')
    })

    it('calls submitToken API and sets message', async () => {
      getAuthStatus.mockResolvedValue({ status: 'not_configured', authenticated: false })
      submitToken.mockResolvedValue({ message: 'Token stored successfully' })

      const { result } = renderHook(() => useAuth())
      await flushPromises()

      await act(async () => {
        await result.current.submitToken('sk-ant-oat01-test')
      })

      expect(submitToken).toHaveBeenCalledWith('sk-ant-oat01-test')
      expect(result.current.message).toBe('Token stored successfully')
    })

    it('sets error message on submission failure', async () => {
      getAuthStatus.mockResolvedValue({ status: 'not_configured', authenticated: false })
      submitToken.mockRejectedValue(new Error('Invalid token format'))

      const { result } = renderHook(() => useAuth())
      await flushPromises()

      await act(async () => {
        await result.current.submitToken('bad-token')
      })

      expect(result.current.message).toBe('Invalid token format')
    })
  })

  describe('credential expiration', () => {
    beforeEach(() => {
      vi.useFakeTimers({ shouldAdvanceTime: true })
    })

    afterEach(() => {
      vi.useRealTimers()
    })

    it('switches to slow polling after authentication', async () => {
      getAuthStatus.mockResolvedValue({ status: 'authenticated', authenticated: true })

      const { result } = renderHook(() => useAuth())

      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })

      expect(result.current.authenticated).toBe(true)
      getAuthStatus.mockClear()

      // Fast interval (3s) should NOT trigger (polling switched to 60s)
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000)
      })
      expect(getAuthStatus).not.toHaveBeenCalled()

      // At 60s mark, should trigger
      await act(async () => {
        await vi.advanceTimersByTimeAsync(57000)
      })
      expect(getAuthStatus).toHaveBeenCalledTimes(1)
    })

    it('detects credential expiration and sets expired=true', async () => {
      getAuthStatus.mockResolvedValue({ status: 'authenticated', authenticated: true })

      const { result } = renderHook(() => useAuth())

      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })

      expect(result.current.authenticated).toBe(true)

      // Credentials expire
      getAuthStatus.mockResolvedValue({ status: 'expired', authenticated: false })

      await act(async () => {
        await vi.advanceTimersByTimeAsync(60000)
      })

      expect(result.current.expired).toBe(true)
      expect(result.current.authenticated).toBe(true) // stays visible
    })

    it('clears expired state when credentials become valid again', async () => {
      getAuthStatus.mockResolvedValue({ status: 'authenticated', authenticated: true })

      const { result } = renderHook(() => useAuth())

      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })

      // Expire
      getAuthStatus.mockResolvedValue({ status: 'expired', authenticated: false })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(60000)
      })
      expect(result.current.expired).toBe(true)

      // Re-authenticate (fast polling at 3s during expired)
      getAuthStatus.mockResolvedValue({ status: 'authenticated', authenticated: true })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000)
      })

      expect(result.current.expired).toBe(false)
      expect(result.current.authenticated).toBe(true)
    })

    it('reauth resets state', async () => {
      getAuthStatus.mockResolvedValue({ status: 'authenticated', authenticated: true })

      const { result } = renderHook(() => useAuth())

      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })

      expect(result.current.authenticated).toBe(true)

      act(() => {
        result.current.reauth()
      })

      expect(result.current.authenticated).toBe(false)
      expect(result.current.expired).toBe(false)
    })
  })
})
