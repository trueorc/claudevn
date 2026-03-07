import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { ThemeProvider, useTheme } from './ThemeContext'

// Mock the AuthContext
vi.mock('./auth/AuthContext', () => ({
  useAuth: () => ({ user: { email: 'test@example.com', sub: 'user-123' } }),
}))

const wrapper = ({ children }) => <ThemeProvider>{children}</ThemeProvider>

describe('ThemeContext', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
  })

  it('defaults to dark theme', () => {
    const { result } = renderHook(() => useTheme(), { wrapper })
    expect(result.current.theme).toBe('dark')
  })

  it('provides list of available themes', () => {
    const { result } = renderHook(() => useTheme(), { wrapper })
    expect(result.current.themes).toEqual(['dark', 'light', 'retro', 'ocean', 'neon'])
  })

  it('changes theme and persists to localStorage', () => {
    const { result } = renderHook(() => useTheme(), { wrapper })
    act(() => {
      result.current.setTheme('light')
    })
    expect(result.current.theme).toBe('light')
    expect(localStorage.getItem('claudevn_theme_user-123')).toBe('light')
  })

  it('applies data-theme attribute for non-dark themes', () => {
    const { result } = renderHook(() => useTheme(), { wrapper })
    act(() => {
      result.current.setTheme('ocean')
    })
    expect(document.documentElement.getAttribute('data-theme')).toBe('ocean')
  })

  it('removes data-theme attribute for dark theme', () => {
    const { result } = renderHook(() => useTheme(), { wrapper })
    act(() => {
      result.current.setTheme('neon')
    })
    expect(document.documentElement.getAttribute('data-theme')).toBe('neon')
    act(() => {
      result.current.setTheme('dark')
    })
    expect(document.documentElement.getAttribute('data-theme')).toBeNull()
  })

  it('loads saved theme from localStorage', () => {
    localStorage.setItem('claudevn_theme_user-123', 'retro')
    const { result } = renderHook(() => useTheme(), { wrapper })
    expect(result.current.theme).toBe('retro')
  })

  it('ignores invalid theme values in localStorage', () => {
    localStorage.setItem('claudevn_theme_user-123', 'invalid-theme')
    const { result } = renderHook(() => useTheme(), { wrapper })
    expect(result.current.theme).toBe('dark')
  })

  it('ignores invalid theme values in setTheme', () => {
    const { result } = renderHook(() => useTheme(), { wrapper })
    act(() => {
      result.current.setTheme('nonexistent')
    })
    expect(result.current.theme).toBe('dark')
  })

  it('throws when used outside ThemeProvider', () => {
    expect(() => {
      renderHook(() => useTheme())
    }).toThrow('useTheme must be used within ThemeProvider')
  })
})

describe('ThemeContext per-user isolation', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
  })

  it('uses user sub as storage key', () => {
    const { result } = renderHook(() => useTheme(), { wrapper })
    act(() => {
      result.current.setTheme('ocean')
    })
    expect(localStorage.getItem('claudevn_theme_user-123')).toBe('ocean')
    // Other user keys should not be affected
    expect(localStorage.getItem('claudevn_theme_default')).toBeNull()
  })
})
