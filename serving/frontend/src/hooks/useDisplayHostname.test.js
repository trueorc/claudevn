import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useDisplayHostname, transformRepoUrl, getDisplayHostname } from './useDisplayHostname'

const STORAGE_KEY = 'claudevn_display_hostname'

describe('useDisplayHostname', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('returns empty string by default', () => {
    const { result } = renderHook(() => useDisplayHostname())
    expect(result.current.displayHostname).toBe('')
  })

  it('reads from localStorage on init', () => {
    localStorage.setItem(STORAGE_KEY, 'localhost')
    const { result } = renderHook(() => useDisplayHostname())
    expect(result.current.displayHostname).toBe('localhost')
  })

  it('saves to localStorage', () => {
    const { result } = renderHook(() => useDisplayHostname())
    act(() => {
      result.current.setDisplayHostname('demo.claudevn.com')
    })
    expect(result.current.displayHostname).toBe('demo.claudevn.com')
    expect(localStorage.getItem(STORAGE_KEY)).toBe('demo.claudevn.com')
  })

  it('clears localStorage when set to empty string', () => {
    localStorage.setItem(STORAGE_KEY, 'localhost')
    const { result } = renderHook(() => useDisplayHostname())
    act(() => {
      result.current.setDisplayHostname('')
    })
    expect(result.current.displayHostname).toBe('')
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('trims whitespace', () => {
    const { result } = renderHook(() => useDisplayHostname())
    act(() => {
      result.current.setDisplayHostname('  localhost  ')
    })
    expect(result.current.displayHostname).toBe('localhost')
    expect(localStorage.getItem(STORAGE_KEY)).toBe('localhost')
  })
})

describe('transformRepoUrl', () => {
  it('returns original URL when displayHostname is empty', () => {
    expect(transformRepoUrl('http://serving:8002/git/repo.git', '')).toBe('http://serving:8002/git/repo.git')
  })

  it('returns original URL when displayHostname is null', () => {
    expect(transformRepoUrl('http://serving:8002/git/repo.git', null)).toBe('http://serving:8002/git/repo.git')
  })

  it('returns original URL when url is empty', () => {
    expect(transformRepoUrl('', 'localhost')).toBe('')
  })

  it('replaces hostname in URL', () => {
    expect(transformRepoUrl('http://serving:8002/git/repo.git', 'localhost'))
      .toBe('http://localhost:8002/git/repo.git')
  })

  it('replaces hostname for different domains', () => {
    expect(transformRepoUrl('http://serving:8002/git/repo.git', 'demo.claudevn.com'))
      .toBe('http://demo.claudevn.com:8002/git/repo.git')
  })

  it('handles invalid URLs gracefully', () => {
    expect(transformRepoUrl('not-a-url', 'localhost')).toBe('not-a-url')
  })

  it('handles URLs without port', () => {
    expect(transformRepoUrl('https://serving/git/repo.git', 'localhost'))
      .toBe('https://localhost/git/repo.git')
  })
})

describe('getDisplayHostname', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('returns empty string when nothing stored', () => {
    expect(getDisplayHostname()).toBe('')
  })

  it('returns stored value', () => {
    localStorage.setItem(STORAGE_KEY, 'localhost')
    expect(getDisplayHostname()).toBe('localhost')
  })
})
