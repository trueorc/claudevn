import { createContext, useContext, useState, useEffect, useRef } from 'react'
import { useProjectContext } from './ProjectContext'
import useConversation, { INTENT_MODES, MSG_TYPES } from '../hooks/useConversation'

const ConversationContext = createContext(null)

function storageKey(projectId) {
  return `claudevn_conversation_${projectId}`
}

function serializeMessages(messages) {
  try {
    return JSON.stringify(
      messages.map(m => ({
        ...m,
        timestamp: m.timestamp instanceof Date ? m.timestamp.toISOString() : m.timestamp,
      }))
    )
  } catch {
    return '[]'
  }
}

function deserializeMessages(raw) {
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function ConversationProvider({ children }) {
  const { activeProject } = useProjectContext()
  const projectId = activeProject?.project_id || null

  const conversation = useConversation(projectId)
  const { messages, clear: clearConversation } = conversation

  // Stored messages loaded from sessionStorage when the project changes.
  // These are shown as a "fallback" while useConversation's internal state
  // is still empty (i.e. before the user sends any new message in this session).
  const [storedMessages, setStoredMessages] = useState([])
  // Track which project's stored messages we've loaded so we only load once
  const loadedProjectRef = useRef(null)

  // On project change: load stored messages for the new project
  useEffect(() => {
    if (projectId === loadedProjectRef.current) return
    loadedProjectRef.current = projectId

    if (projectId) {
      const raw = sessionStorage.getItem(storageKey(projectId))
      setStoredMessages(raw ? deserializeMessages(raw) : [])
    } else {
      setStoredMessages([])
    }
  }, [projectId])

  // Persist live messages to sessionStorage whenever they change.
  // We only persist when the live messages array is non-empty so we don't
  // overwrite stored messages with the empty-array state that useConversation
  // briefly emits when it clears itself on project change.
  useEffect(() => {
    if (!projectId) return
    if (messages.length === 0) return
    sessionStorage.setItem(storageKey(projectId), serializeMessages(messages))
    // Once live messages exist, we no longer need the stored fallback
    setStoredMessages([])
  }, [messages, projectId])

  // The effective message list: prefer live messages; fall back to stored messages
  // if the live list is empty (e.g. right after a page refresh).
  const effectiveMessages = messages.length > 0 ? messages : storedMessages

  // Wrap clear to also remove from sessionStorage and clear our stored state
  const clear = () => {
    if (projectId) {
      sessionStorage.removeItem(storageKey(projectId))
    }
    setStoredMessages([])
    clearConversation()
  }

  const value = {
    ...conversation,
    messages: effectiveMessages,
    clear,
    projectId,
  }

  return (
    <ConversationContext.Provider value={value}>
      {children}
    </ConversationContext.Provider>
  )
}

export function useConversationContext() {
  const context = useContext(ConversationContext)
  if (!context) {
    throw new Error('useConversationContext must be used within a ConversationProvider')
  }
  return context
}

export { INTENT_MODES, MSG_TYPES }
export default ConversationContext
