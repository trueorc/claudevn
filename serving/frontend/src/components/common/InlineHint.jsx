import { useState, useEffect } from 'react'
import { X } from 'lucide-react'
import './InlineHint.css'

/**
 * InlineHint - A dismissable first-visit hint banner.
 * Stores dismissal state in localStorage by hintKey so it never re-appears.
 *
 * Props:
 *   hintKey  {string}     Unique key for localStorage persistence (required)
 *   children {ReactNode}  Hint content
 */
function InlineHint({ hintKey, children }) {
  const storageKey = `hint_dismissed_${hintKey}`

  const [visible, setVisible] = useState(() => {
    try {
      return localStorage.getItem(storageKey) !== 'true'
    } catch {
      return true
    }
  })

  const dismiss = () => {
    try {
      localStorage.setItem(storageKey, 'true')
    } catch { /* ignore storage errors */ }
    setVisible(false)
  }

  if (!visible) return null

  return (
    <div className="inline-hint">
      <span className="inline-hint-text">{children}</span>
      <button
        className="inline-hint-dismiss"
        onClick={dismiss}
        aria-label="Dismiss hint"
        title="Dismiss"
      >
        <X size={12} />
      </button>
    </div>
  )
}

/**
 * PageSubtitle - Static secondary text beneath a page header.
 * Not dismissable — always visible.
 */
function PageSubtitle({ children }) {
  return <p className="page-subtitle">{children}</p>
}

export { PageSubtitle }
export default InlineHint
