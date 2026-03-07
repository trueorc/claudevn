import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { useAuth } from './auth/AuthContext'

const ThemeContext = createContext(null)

const THEMES = ['dark', 'light', 'retro', 'ocean', 'neon']
const DEFAULT_THEME = 'dark'

function getStorageKey(user) {
  const id = user?.sub || user?.email || 'default'
  return `claudevn_theme_${id}`
}

function loadTheme(user) {
  const key = getStorageKey(user)
  const stored = localStorage.getItem(key)
  if (stored && THEMES.includes(stored)) return stored
  return DEFAULT_THEME
}

function applyTheme(theme) {
  if (theme === DEFAULT_THEME) {
    document.documentElement.removeAttribute('data-theme')
  } else {
    document.documentElement.setAttribute('data-theme', theme)
  }
}

export function ThemeProvider({ children }) {
  const { user } = useAuth()
  const [theme, setThemeState] = useState(() => loadTheme(user))

  useEffect(() => {
    const loaded = loadTheme(user)
    setThemeState(loaded)
    applyTheme(loaded)
  }, [user])

  const setTheme = useCallback((newTheme) => {
    if (!THEMES.includes(newTheme)) return
    setThemeState(newTheme)
    applyTheme(newTheme)
    const key = getStorageKey(user)
    localStorage.setItem(key, newTheme)
  }, [user])

  return (
    <ThemeContext.Provider value={{ theme, setTheme, themes: THEMES }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within ThemeProvider')
  }
  return context
}
