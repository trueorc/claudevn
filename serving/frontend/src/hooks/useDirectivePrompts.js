import { useMemo } from 'react'

/**
 * Context-aware directive prompt suggestions.
 *
 * Takes issue stats (from useIssues) and returns an array of prompt objects
 * that are relevant to the current project state. Prompts are limited to
 * a maximum of 4 so they remain helpful without being overwhelming.
 *
 * Each prompt has:
 *   - label  {string}  Short text shown on the chip
 *   - text   {string}  Full text populated into the input when clicked
 */

const MAX_PROMPTS = 4

function useDirectivePrompts(stats) {
  return useMemo(() => {
    // No project / stats not yet loaded → return nothing so callers can hide the section
    if (!stats) return []

    const byStatus = stats.by_status || {}
    const total = stats.total || 0

    // Counts by lifecycle bucket
    const pendingCount =
      (byStatus.open || 0) +
      (byStatus.pending || 0) +
      (byStatus.new || 0) +
      (byStatus.todo || 0)

    const activeCount =
      (byStatus.in_progress || 0) +
      (byStatus.active || 0) +
      (byStatus.running || 0)

    const reviewCount =
      (byStatus.in_review || 0) +
      (byStatus.testing || 0) +
      (byStatus.review || 0)

    const prompts = []

    // --- Empty project ---
    if (total === 0) {
      prompts.push({
        label: 'Describe what you want to build',
        text: 'Describe what you want to build',
      })
      prompts.push({
        label: 'Import existing requirements',
        text: 'Import existing requirements',
      })
      return prompts.slice(0, MAX_PROMPTS)
    }

    // --- Has items awaiting review / testing ---
    if (reviewCount > 0) {
      prompts.push({
        label: 'Review completed work',
        text: 'Review completed work',
      })
    }

    // --- Has active compute ---
    if (activeCount > 0) {
      prompts.push({
        label: 'Check execution progress',
        text: 'Check execution progress',
      })
    }

    // --- Has pending / new issues ---
    if (pendingCount > 0) {
      prompts.push({
        label: 'Decompose goals into work items',
        text: 'Decompose my goals into work items',
      })
      prompts.push({
        label: 'Prioritize backlog',
        text: 'Prioritize the backlog',
      })
    }

    // --- Default / fallback (always append if we have room) ---
    if (prompts.length < MAX_PROMPTS) {
      prompts.push({
        label: 'Focus on P0 items first',
        text: 'Focus on P0 items first',
      })
    }
    if (prompts.length < MAX_PROMPTS) {
      prompts.push({
        label: 'Review execution progress',
        text: 'Review execution progress',
      })
    }

    return prompts.slice(0, MAX_PROMPTS)
  }, [stats])
}

export default useDirectivePrompts
