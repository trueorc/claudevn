import { useState, useEffect, useCallback } from 'react'

const STORAGE_KEY = 'claudevn-project-filters'

const DEFAULT_FILTERS = {
  search: '',
  status: 'all',
  sort: 'name_asc'
}

function getFiltersFromURL() {
  const params = new URLSearchParams(window.location.search)
  return {
    search: params.get('search') || '',
    status: params.get('status') || 'all',
    sort: params.get('sort') || 'name_asc'
  }
}

function getFiltersFromStorage() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      return JSON.parse(stored)
    }
  } catch {
    // Ignore storage errors
  }
  return null
}

function saveFiltersToStorage(filters) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(filters))
  } catch {
    // Ignore storage errors
  }
}

function updateURL(filters) {
  const params = new URLSearchParams()

  if (filters.search) {
    params.set('search', filters.search)
  }
  if (filters.status && filters.status !== 'all') {
    params.set('status', filters.status)
  }
  if (filters.sort && filters.sort !== 'name_asc') {
    params.set('sort', filters.sort)
  }

  const newURL = params.toString()
    ? `${window.location.pathname}?${params.toString()}`
    : window.location.pathname

  window.history.replaceState(null, '', newURL)
}

function useProjectFilters() {
  const [filters, setFiltersState] = useState(() => {
    // Priority: URL params > localStorage > defaults
    const urlFilters = getFiltersFromURL()
    const hasURLParams = urlFilters.search || urlFilters.status !== 'all' || urlFilters.sort !== 'name_asc'

    if (hasURLParams) {
      return urlFilters
    }

    const storedFilters = getFiltersFromStorage()
    if (storedFilters) {
      return { ...DEFAULT_FILTERS, ...storedFilters }
    }

    return DEFAULT_FILTERS
  })

  const setFilters = useCallback((newFilters) => {
    setFiltersState(newFilters)
    updateURL(newFilters)
    saveFiltersToStorage(newFilters)
  }, [])

  // Handle browser back/forward
  useEffect(() => {
    const handlePopState = () => {
      setFiltersState(getFiltersFromURL())
    }

    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  return { filters, setFilters }
}

export default useProjectFilters
