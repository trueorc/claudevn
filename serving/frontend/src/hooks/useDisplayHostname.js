import { useState, useCallback } from 'react'

const STORAGE_KEY = 'claudevn_display_hostname'
const DEFAULT_HOSTNAME = ''

function getStored() {
  try {
    return localStorage.getItem(STORAGE_KEY) || DEFAULT_HOSTNAME
  } catch {
    return DEFAULT_HOSTNAME
  }
}

export function useDisplayHostname() {
  const [displayHostname, setDisplayHostname] = useState(getStored)

  const save = useCallback((value) => {
    const trimmed = value.trim()
    setDisplayHostname(trimmed)
    try {
      if (trimmed) {
        localStorage.setItem(STORAGE_KEY, trimmed)
      } else {
        localStorage.removeItem(STORAGE_KEY)
      }
    } catch {
      // localStorage unavailable
    }
  }, [])

  return { displayHostname, setDisplayHostname: save }
}

export function transformRepoUrl(url, displayHostname) {
  if (!url || !displayHostname) return url
  try {
    const parsed = new URL(url)
    parsed.hostname = displayHostname
    return parsed.toString().replace(/\/$/, '')
  } catch {
    return url
  }
}

export function getDisplayHostname() {
  return getStored()
}
