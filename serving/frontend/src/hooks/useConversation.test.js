import { renderHook, waitFor, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import useConversation, { MSG_TYPES, INTENT_MODES } from './useConversation'

vi.mock('../api/workmap', () => ({
  createGoal: vi.fn(),
}))

vi.mock('../api/directives', () => ({
  interpretDirective: vi.fn(),
  applyDirective: vi.fn(),
  rejectDirective: vi.fn(),
}))

vi.mock('./useGoals', () => ({
  default: vi.fn(),
  WORKFLOW_STEPS: { INPUT: 'input', PROCESSING: 'processing', COMPLETE: 'complete' },
  PROCESSING_STAGES: {
    QUEUED: 'queued',
    DECOMPOSING: 'decomposing',
    CREATING_ISSUES: 'creating_issues',
    COMPLETE: 'complete',
    FAILED: 'failed',
  },
}))

import { createGoal } from '../api/workmap'
import { interpretDirective, applyDirective, rejectDirective } from '../api/directives'
import useGoals from './useGoals'

const mockReset = vi.fn()
const mockAutoProcess = vi.fn()
const mockResumePolling = vi.fn()
const mockRetryProcessing = vi.fn()

function setupUseGoals(overrides = {}) {
  useGoals.mockReturnValue({
    step: 'input',
    error: null,
    executionResult: null,
    processingStage: null,
    processingStartedAt: null,
    isTimedOut: false,
    isStalled: false,
    autoProcess: mockAutoProcess,
    resumePolling: mockResumePolling,
    retryProcessing: mockRetryProcessing,
    reset: mockReset,
    ...overrides,
  })
}

describe('useConversation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setupUseGoals()
  })

  describe('initialization', () => {
    it('returns empty state initially', () => {
      const { result } = renderHook(() => useConversation('proj-1'))
      expect(result.current.messages).toEqual([])
      expect(result.current.submitting).toBe(false)
      expect(result.current.pendingDirective).toBeNull()
      expect(result.current.applying).toBe(false)
      expect(result.current.lastCreatedGoal).toBeNull()
    })

    it('clears state on project change', () => {
      const { result, rerender } = renderHook(
        ({ projectId }) => useConversation(projectId),
        { initialProps: { projectId: 'proj-1' } }
      )
      rerender({ projectId: 'proj-2' })
      expect(result.current.messages).toEqual([])
      expect(mockReset).toHaveBeenCalled()
    })
  })

  describe('submit - new work mode', () => {
    it('creates a goal and starts auto-processing', async () => {
      const mockGoal = { goal_id: 'g-1', title: 'Test goal' }
      createGoal.mockResolvedValue(mockGoal)
      mockAutoProcess.mockResolvedValue()

      const { result } = renderHook(() => useConversation('proj-1'))

      let submitResult
      await act(async () => {
        submitResult = await result.current.submit('Build a feature', INTENT_MODES.NEW_WORK, { priority: 'P1' })
      })

      expect(createGoal).toHaveBeenCalledWith({
        title: 'Build a feature',
        description: 'Build a feature',
        priority: 'P1',
        project_id: 'proj-1',
      })
      expect(mockAutoProcess).toHaveBeenCalledWith('g-1')
      expect(submitResult).toEqual({ type: 'goal', goal: mockGoal })

      // Check messages: user, goal_created, goal_processing (thinking removed)
      const types = result.current.messages.map(m => m.type)
      expect(types).toContain(MSG_TYPES.USER)
      expect(types).toContain(MSG_TYPES.GOAL_CREATED)
      expect(types).toContain(MSG_TYPES.GOAL_PROCESSING)
      expect(types).not.toContain(MSG_TYPES.THINKING)
    })

    it('defaults priority to P2', async () => {
      createGoal.mockResolvedValue({ goal_id: 'g-1', title: 'Test' })
      mockAutoProcess.mockResolvedValue()

      const { result } = renderHook(() => useConversation('proj-1'))
      await act(async () => {
        await result.current.submit('Test', INTENT_MODES.NEW_WORK)
      })

      expect(createGoal).toHaveBeenCalledWith(
        expect.objectContaining({ priority: 'P2' })
      )
    })

    it('does nothing when projectId is null', async () => {
      const { result } = renderHook(() => useConversation(null))
      const res = await act(async () => {
        return await result.current.submit('test', INTENT_MODES.NEW_WORK)
      })
      expect(res).toBeNull()
      expect(createGoal).not.toHaveBeenCalled()
    })

    it('does nothing when text is empty', async () => {
      const { result } = renderHook(() => useConversation('proj-1'))
      const res = await act(async () => {
        return await result.current.submit('  ', INTENT_MODES.NEW_WORK)
      })
      expect(res).toBeNull()
    })
  })

  describe('submit - directive mode', () => {
    it('interprets directive and sets pending', async () => {
      const mockDirective = { directive_id: 'd-1', interpretation: { summary: 'test' } }
      interpretDirective.mockResolvedValue(mockDirective)

      const { result } = renderHook(() => useConversation('proj-1'))

      let submitResult
      await act(async () => {
        submitResult = await result.current.submit('Focus on testing', INTENT_MODES.DIRECTIVE)
      })

      expect(interpretDirective).toHaveBeenCalledWith('Focus on testing', 'proj-1')
      expect(submitResult).toEqual({ type: 'directive', directive: mockDirective })
      expect(result.current.pendingDirective).toEqual(mockDirective)

      const types = result.current.messages.map(m => m.type)
      expect(types).toContain(MSG_TYPES.USER)
      expect(types).toContain(MSG_TYPES.DIRECTIVE_PREVIEW)
      expect(types).not.toContain(MSG_TYPES.THINKING)
    })
  })

  describe('submit - auto mode', () => {
    it('falls back to goal creation when no adjustments and no backend goal', async () => {
      interpretDirective.mockResolvedValue({ interpretation: {} })
      const mockGoal = { goal_id: 'g-2', title: 'Auto goal' }
      createGoal.mockResolvedValue(mockGoal)
      mockAutoProcess.mockResolvedValue()

      const { result } = renderHook(() => useConversation('proj-1'))
      let submitResult
      await act(async () => {
        submitResult = await result.current.submit('Do something', INTENT_MODES.AUTO)
      })

      expect(submitResult).toEqual({ type: 'goal', goal: mockGoal })
      expect(createGoal).toHaveBeenCalled()
    })

    it('uses backend-created goal instead of creating a duplicate (#641)', async () => {
      const mockDirective = {
        directive_id: 'd-3',
        text: 'Build a user auth system',
        interpretation: {},
        outcome: { goal_id_created: 'g-backend' },
      }
      interpretDirective.mockResolvedValue(mockDirective)

      const { result } = renderHook(() => useConversation('proj-1'))
      let submitResult
      await act(async () => {
        submitResult = await result.current.submit('Build a user auth system', INTENT_MODES.AUTO)
      })

      // Should NOT call createGoal — backend already created one
      expect(createGoal).not.toHaveBeenCalled()
      // Should resume polling (not autoProcess) since backend already started processing (#723)
      expect(mockAutoProcess).not.toHaveBeenCalled()
      expect(mockResumePolling).toHaveBeenCalledWith('g-backend', 'queued')
      // Should return a goal result with the backend goal ID
      expect(submitResult.type).toBe('goal')
      expect(submitResult.goal.goal_id).toBe('g-backend')

      const types = result.current.messages.map(m => m.type)
      expect(types).toContain(MSG_TYPES.GOAL_CREATED)
      expect(types).toContain(MSG_TYPES.GOAL_PROCESSING)
      expect(types).not.toContain(MSG_TYPES.THINKING)
    })

    it('returns directive when adjustments found', async () => {
      const mockDirective = {
        directive_id: 'd-2',
        interpretation: {
          weight_adjustments: [{ category: 'domain', key: 'testing', proposed_weight: 0.8 }],
        },
      }
      interpretDirective.mockResolvedValue(mockDirective)

      const { result } = renderHook(() => useConversation('proj-1'))
      let submitResult
      await act(async () => {
        submitResult = await result.current.submit('Focus testing', INTENT_MODES.AUTO)
      })

      expect(submitResult).toEqual({ type: 'directive', directive: mockDirective })
      expect(createGoal).not.toHaveBeenCalled()
    })

    it('falls back to goal creation when directive interpretation throws', async () => {
      interpretDirective.mockRejectedValue(new Error('Parse failed'))
      const mockGoal = { goal_id: 'g-3', title: 'Fallback' }
      createGoal.mockResolvedValue(mockGoal)
      mockAutoProcess.mockResolvedValue()

      const { result } = renderHook(() => useConversation('proj-1'))
      await act(async () => {
        await result.current.submit('Do stuff', INTENT_MODES.AUTO)
      })

      expect(createGoal).toHaveBeenCalled()
    })
  })

  describe('submit - error handling', () => {
    it('adds error message on goal creation failure', async () => {
      createGoal.mockRejectedValue(new Error('Server error'))

      const { result } = renderHook(() => useConversation('proj-1'))
      await act(async () => {
        await result.current.submit('Test', INTENT_MODES.NEW_WORK)
      })

      const errorMsg = result.current.messages.find(m => m.type === MSG_TYPES.ERROR)
      expect(errorMsg).toBeDefined()
      expect(errorMsg.content).toBe('Server error')
      expect(result.current.submitting).toBe(false)
    })

    it('uses fallback message when error has no message', async () => {
      createGoal.mockRejectedValue(new Error())

      const { result } = renderHook(() => useConversation('proj-1'))
      await act(async () => {
        await result.current.submit('Test', INTENT_MODES.NEW_WORK)
      })

      const errorMsg = result.current.messages.find(m => m.type === MSG_TYPES.ERROR)
      expect(errorMsg.content).toBe('Something went wrong')
    })
  })

  describe('applyPending', () => {
    it('applies a pending directive', async () => {
      const mockDirective = { directive_id: 'd-1', interpretation: { summary: 'test' } }
      interpretDirective.mockResolvedValue(mockDirective)
      applyDirective.mockResolvedValue({ status: 'applied' })

      const { result } = renderHook(() => useConversation('proj-1'))

      await act(async () => {
        await result.current.submit('Focus testing', INTENT_MODES.DIRECTIVE)
      })
      expect(result.current.pendingDirective).toEqual(mockDirective)

      await act(async () => {
        await result.current.applyPending()
      })

      expect(applyDirective).toHaveBeenCalledWith('d-1', 'proj-1')
      expect(result.current.pendingDirective).toBeNull()
      const appliedMsg = result.current.messages.find(m => m.type === MSG_TYPES.DIRECTIVE_APPLIED)
      expect(appliedMsg).toBeDefined()
    })

    it('does nothing when no pending directive', async () => {
      const { result } = renderHook(() => useConversation('proj-1'))
      await act(async () => {
        await result.current.applyPending()
      })
      expect(applyDirective).not.toHaveBeenCalled()
    })

    it('adds error message on apply failure', async () => {
      const mockDirective = { directive_id: 'd-1', interpretation: { summary: 'test' } }
      interpretDirective.mockResolvedValue(mockDirective)
      applyDirective.mockRejectedValue(new Error('Apply failed'))

      const { result } = renderHook(() => useConversation('proj-1'))
      await act(async () => {
        await result.current.submit('test', INTENT_MODES.DIRECTIVE)
      })
      await act(async () => {
        await result.current.applyPending()
      })

      const errorMsg = result.current.messages.find(m => m.type === MSG_TYPES.ERROR)
      expect(errorMsg.content).toBe('Apply failed')
    })
  })

  describe('rejectPending', () => {
    it('rejects a pending directive', async () => {
      const mockDirective = { directive_id: 'd-1', interpretation: { summary: 'test' } }
      interpretDirective.mockResolvedValue(mockDirective)
      rejectDirective.mockResolvedValue({})

      const { result } = renderHook(() => useConversation('proj-1'))
      await act(async () => {
        await result.current.submit('test', INTENT_MODES.DIRECTIVE)
      })
      await act(async () => {
        await result.current.rejectPending()
      })

      expect(rejectDirective).toHaveBeenCalledWith('d-1', 'proj-1')
      expect(result.current.pendingDirective).toBeNull()
      const rejectedMsg = result.current.messages.find(m => m.type === MSG_TYPES.DIRECTIVE_REJECTED)
      expect(rejectedMsg).toBeDefined()
    })
  })

  describe('clear', () => {
    it('resets all state', async () => {
      createGoal.mockResolvedValue({ goal_id: 'g-1', title: 'T' })
      mockAutoProcess.mockResolvedValue()

      const { result } = renderHook(() => useConversation('proj-1'))
      await act(async () => {
        await result.current.submit('Test', INTENT_MODES.NEW_WORK)
      })
      expect(result.current.messages.length).toBeGreaterThan(0)

      act(() => {
        result.current.clear()
      })

      expect(result.current.messages).toEqual([])
      expect(result.current.pendingDirective).toBeNull()
      expect(result.current.lastCreatedGoal).toBeNull()
      expect(mockReset).toHaveBeenCalled()
    })
  })
})
