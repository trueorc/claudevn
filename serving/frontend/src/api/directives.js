import { request } from './index.js'

/**
 * Submit text for directive interpretation and processing.
 *
 * Maps to POST /unified-directives which classifies intent
 * (new_work, priority_shift, combined, clarification) and
 * processes accordingly.
 */
export async function interpretDirective(text, projectId) {
  return request('/unified-directives', {
    method: 'POST',
    body: JSON.stringify({ text, project_id: projectId }),
  })
}

/**
 * Confirm/apply a previously submitted directive.
 *
 * The unified backend processes directives during submit, so this
 * fetches the current directive state as an acknowledgement.
 */
export async function applyDirective(directiveId, projectId) {
  return request(
    `/unified-directives/${encodeURIComponent(directiveId)}?project_id=${encodeURIComponent(projectId)}`
  )
}

/**
 * Reject a pending directive by recording the rejection as a comment.
 */
export async function rejectDirective(directiveId, projectId) {
  return request(
    `/unified-directives/${encodeURIComponent(directiveId)}/comments?project_id=${encodeURIComponent(projectId)}`,
    {
      method: 'POST',
      body: JSON.stringify({ content: 'Directive rejected by user' }),
    }
  )
}
