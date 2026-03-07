import { useState, useEffect } from 'react'
import Modal from './Modal'
import { getRelease } from '../../api/releases'
import useSystemHealth from '../../hooks/useSystemHealth'
import './WhatsNew.css'

const STORAGE_KEY = 'claudevn_last_viewed_version'

function getLastViewedVersion() {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

function setLastViewedVersion(version) {
  try {
    localStorage.setItem(STORAGE_KEY, version)
  } catch {
    // localStorage unavailable
  }
}

function renderMarkdown(text) {
  const lines = text.split('\n')
  const elements = []
  let listItems = []
  let key = 0

  const flushList = () => {
    if (listItems.length > 0) {
      elements.push(<ul key={key++}>{listItems}</ul>)
      listItems = []
    }
  }

  for (const line of lines) {
    // Skip the top-level title (# v0.4.0 ...) and release date
    if (line.startsWith('# ') || line.startsWith('**Release Date:')) continue

    if (line.startsWith('## ')) {
      flushList()
      elements.push(<h3 key={key++} className="whats-new-section">{line.slice(3)}</h3>)
    } else if (line.startsWith('### ')) {
      flushList()
      elements.push(<h4 key={key++} className="whats-new-subsection">{line.slice(4)}</h4>)
    } else if (line.startsWith('- **')) {
      // Bold label with description: - **Label** — description
      const match = line.match(/^- \*\*(.+?)\*\*\s*[—–-]\s*(.+)/)
      if (match) {
        listItems.push(
          <li key={key++}><strong>{match[1]}</strong> — {renderInline(match[2])}</li>
        )
      } else {
        const boldMatch = line.match(/^- \*\*(.+?)\*\*(.*)/)
        if (boldMatch) {
          listItems.push(
            <li key={key++}><strong>{boldMatch[1]}</strong>{boldMatch[2]}</li>
          )
        } else {
          listItems.push(<li key={key++}>{renderInline(line.slice(2))}</li>)
        }
      }
    } else if (line.startsWith('- ')) {
      listItems.push(<li key={key++}>{renderInline(line.slice(2))}</li>)
    } else if (line.trim() === '') {
      flushList()
    } else if (line.trim()) {
      flushList()
      elements.push(<p key={key++} className="whats-new-text">{renderInline(line)}</p>)
    }
  }
  flushList()

  return elements
}

function renderInline(text) {
  // Handle inline code, bold, and issue references
  const parts = []
  let remaining = text
  let key = 0

  while (remaining.length > 0) {
    // Match inline code
    const codeMatch = remaining.match(/`([^`]+)`/)
    // Match bold
    const boldMatch = remaining.match(/\*\*([^*]+)\*\*/)
    // Match issue reference
    const issueMatch = remaining.match(/#(\d+)/)

    // Find the earliest match
    const matches = [
      codeMatch && { type: 'code', match: codeMatch },
      boldMatch && { type: 'bold', match: boldMatch },
      issueMatch && { type: 'issue', match: issueMatch },
    ].filter(Boolean).sort((a, b) => a.match.index - b.match.index)

    if (matches.length === 0) {
      parts.push(remaining)
      break
    }

    const first = matches[0]
    if (first.match.index > 0) {
      parts.push(remaining.slice(0, first.match.index))
    }

    if (first.type === 'code') {
      parts.push(<code key={key++}>{first.match[1]}</code>)
    } else if (first.type === 'bold') {
      parts.push(<strong key={key++}>{first.match[1]}</strong>)
    } else if (first.type === 'issue') {
      parts.push(<span key={key++} className="whats-new-issue">#{first.match[1]}</span>)
    }

    remaining = remaining.slice(first.match.index + first.match[0].length)
  }

  return parts
}

function WhatsNew() {
  const { health } = useSystemHealth({ pollInterval: 0, useWebSocket: false })
  const [isOpen, setIsOpen] = useState(false)
  const [content, setContent] = useState(null)
  const [loading, setLoading] = useState(false)

  const currentVersion = health?.version

  useEffect(() => {
    if (!currentVersion) return

    const lastViewed = getLastViewedVersion()
    if (lastViewed === currentVersion) return

    // New version detected — fetch release notes and show modal
    setLoading(true)
    getRelease(currentVersion)
      .then(data => {
        setContent(data.content)
        setIsOpen(true)
      })
      .catch(() => {
        // No release notes for this version — skip
      })
      .finally(() => setLoading(false))
  }, [currentVersion])

  const handleClose = () => {
    setIsOpen(false)
    if (currentVersion) {
      setLastViewedVersion(currentVersion)
    }
  }

  if (!isOpen || !content) return null

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={`What's New in v${currentVersion}`}
      width="560px"
    >
      <div className="whats-new-content">
        {loading ? (
          <p className="whats-new-loading">Loading...</p>
        ) : (
          renderMarkdown(content)
        )}
      </div>
      <div className="whats-new-footer">
        <button className="btn btn-primary" onClick={handleClose}>
          Got it
        </button>
      </div>
    </Modal>
  )
}

export default WhatsNew
