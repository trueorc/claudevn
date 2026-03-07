import { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react'
import { useProjectContext } from './ProjectContext'
import { useAuth } from './auth/AuthContext'
import useConversation, { INTENT_MODES, MSG_TYPES } from '../hooks/useConversation'
import {
  getConversation,
  sendMessage as sendMessageApi,
  clearConversation as clearConversationApi,
} from '../api/conversation'
import ObservabilityWebSocket from '../services/observabilityWebSocket'

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

/**
 * Convert a server message record to the shape useConversation works with.
 */
function serverMsgToLocal(msg) {
  return {
    id: msg.message_id,
    type: msg.type,
    content: msg.content,
    timestamp: msg.created_at,
    userId: msg.user_id,
    displayName: msg.display_name,
    metadata: msg.metadata,
  }
}

/**
 * Determine which messages are safe to persist to the server.
 * Ephemeral messages (thinking, in-flight previews) are excluded because
 * they represent transient UI state rather than durable conversation turns.
 */
const PERSISTABLE_TYPES = new Set([
  MSG_TYPES.USER,
  MSG_TYPES.GOAL_CREATED,
  MSG_TYPES.GOAL_COMPLETE,
  MSG_TYPES.DIRECTIVE_APPLIED,
  MSG_TYPES.DIRECTIVE_REJECTED,
  MSG_TYPES.ERROR,
])

// Module-level singleton WebSocket so all ConversationProvider instances
// (if any) share a single connection and we don't reconnect on re-renders.
let _sharedWs = null

function getSharedWs() {
  if (!_sharedWs) {
    _sharedWs = new ObservabilityWebSocket()
    _sharedWs.connect()
  }
  return _sharedWs
}

export function ConversationProvider({ children }) {
  const { activeProject } = useProjectContext()
  const { user } = useAuth()
  const currentUserId = user?.sub || null
  const projectId = activeProject?.project_id || null

  const conversation = useConversation(projectId)
  const { messages, clear: clearConversation } = conversation

  // Stored messages loaded from server (or sessionStorage fallback) when project changes.
  // Shown while useConversation's internal state is still empty (e.g. after page refresh).
  const [storedMessages, setStoredMessages] = useState([])

  // Remote messages received via WebSocket from other users/tabs.
  // Merged into the effective list when the live (useConversation) list has messages.
  const [remoteMessages, setRemoteMessages] = useState([])

  // Track which project's stored messages we've loaded so we only load once per project.
  const loadedProjectRef = useRef(null)

  // Track message IDs that have already been persisted to the server so we don't double-post.
  const persistedIdsRef = useRef(new Set())

  // Keep a stable ref to projectId so the WS callback (registered once) sees
  // the current value without re-registering the handler on every project change.
  const projectIdRef = useRef(projectId)
  useEffect(() => {
    projectIdRef.current = projectId
  }, [projectId])

  // Clear remote messages when the project changes.
  useEffect(() => {
    setRemoteMessages([])
  }, [projectId])

  // Register a single, stable WebSocket listener for conversation_message events.
  // The handler reads projectIdRef and persistedIdsRef via closure so it always
  // has current values without needing to be re-registered.
  useEffect(() => {
    const ws = getSharedWs()

    const handleConversationMessage = (eventData) => {
      // eventData shape: { project_id, message: ConversationMessage }
      const incomingProjectId = eventData?.project_id
      const serverMsg = eventData?.message
      if (!serverMsg || !incomingProjectId) return

      // Ignore messages for other projects.
      if (projectIdRef.current !== incomingProjectId) return

      const localMsg = serverMsgToLocal(serverMsg)

      // Deduplicate: skip messages we already have (sent by this tab and
      // already added to the live list via useConversation).
      if (persistedIdsRef.current.has(localMsg.id)) return

      // Mark as known so the outgoing-sync effect won't POST it back to the server.
      persistedIdsRef.current.add(localMsg.id)

      // Skip if we already have this exact message in remoteMessages
      setRemoteMessages(prev => {
        if (prev.some(m => m.id === localMsg.id)) return prev
        return [...prev, localMsg]
      })
    }

    ws.on('conversation_message', handleConversationMessage)

    return () => {
      ws.off('conversation_message', handleConversationMessage)
    }
  }, []) // Intentionally empty — handler is stable via refs

  // Load from sessionStorage when server is unavailable.
  const loadFromSession = useCallback((pid) => {
    const raw = sessionStorage.getItem(storageKey(pid))
    setStoredMessages(raw ? deserializeMessages(raw) : [])
  }, [])

  // On project change: load stored messages from server, fall back to sessionStorage.
  useEffect(() => {
    if (projectId === loadedProjectRef.current) return
    loadedProjectRef.current = projectId
    persistedIdsRef.current = new Set()

    if (!projectId) {
      setStoredMessages([])
      return
    }

    let cancelled = false

    getConversation(projectId)
      .then(data => {
        if (cancelled) return
        if (data?.messages?.length > 0) {
          const converted = data.messages.map(serverMsgToLocal)
          // Mark all server-loaded messages as already persisted.
          converted.forEach(m => persistedIdsRef.current.add(m.id))
          setStoredMessages(converted)
        } else {
          // Server returned empty — fall back to sessionStorage in case the
          // user has a cached session (e.g. server was recently cleared).
          loadFromSession(projectId)
        }
      })
      .catch(err => {
        if (cancelled) return
        console.warn('Failed to load conversation from server, using local cache:', err)
        loadFromSession(projectId)
      })

    return () => { cancelled = true }
  }, [projectId, loadFromSession])

  // Persist live messages to sessionStorage and, for persistable types, to the server.
  // We only act when the live messages array is non-empty so we don't overwrite stored
  // messages with the empty-array state that useConversation emits on project change.
  useEffect(() => {
    if (!projectId || messages.length === 0) return

    // Write-through cache to sessionStorage.
    sessionStorage.setItem(storageKey(projectId), serializeMessages(messages))

    // Once live messages exist, the stored fallback is no longer needed.
    setStoredMessages([])

    // POST any persistable messages that haven't been sent to the server yet.
    messages.forEach(msg => {
      if (!PERSISTABLE_TYPES.has(msg.type)) return
      if (persistedIdsRef.current.has(msg.id)) return

      // Mark immediately to prevent duplicate POSTs if the effect fires again
      // before the async call completes.
      persistedIdsRef.current.add(msg.id)

      const metadata = {}
      if (msg.mode) metadata.mode = msg.mode
      if (msg.goal) metadata.goal = msg.goal
      if (msg.directive) metadata.directive_id = msg.directive?.directive_id

      sendMessageApi(projectId, {
        type: msg.type,
        content: msg.content,
        metadata,
      }).then(serverMsg => {
        // Track the server-assigned message_id so the WebSocket echo
        // (which arrives with the server ID, not our local numeric ID)
        // is recognized as a duplicate and skipped.
        if (serverMsg?.message_id) {
          persistedIdsRef.current.add(serverMsg.message_id)
        }
      }).catch(err => {
        console.warn('Failed to persist message to server:', err)
        // On failure, remove from the persisted set so it can be retried.
        persistedIdsRef.current.delete(msg.id)
      })
    })
  }, [messages, projectId])

  // Wrap clear to also remove from sessionStorage, server, and clear stored state.
  const clear = useCallback(() => {
    if (projectId) {
      sessionStorage.removeItem(storageKey(projectId))
      clearConversationApi(projectId).catch(err => {
        console.warn('Failed to clear conversation on server:', err)
      })
    }
    persistedIdsRef.current = new Set()
    setStoredMessages([])
    setRemoteMessages([])
    clearConversation()
  }, [projectId, clearConversation])

  // Merge message sources into a single ordered list.
  //
  // Priority:
  //   1. If there are live messages (useConversation is active), use those as
  //      the base and append any remote messages not already in the live list.
  //   2. If no live messages, show stored messages (server load / sessionStorage).
  //
  // Remote messages are deduplicated by id against the live list.
  const effectiveMessages = (() => {
    if (messages.length > 0) {
      const liveIds = new Set(messages.map(m => m.id))
      // Build a set of content fingerprints from live messages to catch
      // our own messages echoed back via WebSocket with a different (server) ID.
      const liveFingerprints = new Set(
        messages.map(m => `${m.type}:${m.content}`)
      )
      const newRemote = remoteMessages.filter(m => {
        if (liveIds.has(m.id)) return false
        // Content-match dedup: only for our own echoed messages.
        // If the remote message is from the current user and matches content
        // already in the live list, it's our own echo from the server.
        if (m.userId === currentUserId && liveFingerprints.has(`${m.type}:${m.content}`)) return false
        return true
      })
      if (newRemote.length === 0) return messages
      // Merge and sort by timestamp so remote messages appear in arrival order.
      return [...messages, ...newRemote].sort(
        (a, b) => new Date(a.timestamp) - new Date(b.timestamp)
      )
    }
    return storedMessages
  })()

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
