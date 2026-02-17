import { describe, it, expect, vi, beforeEach } from 'vitest'
import { interpretDirective, applyDirective, rejectDirective } from './directives'

vi.mock('./index.js', () => ({
  request: vi.fn(),
}))

import { request } from './index.js'

describe('directives API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('interpretDirective', () => {
    it('POSTs to unified-directives with text and project_id', async () => {
      const mockDirective = { directive_id: 'udir_abc123', intent: 'priority_shift' }
      request.mockResolvedValue(mockDirective)

      const result = await interpretDirective('Focus on testing', 'proj-1')

      expect(request).toHaveBeenCalledWith('/unified-directives', {
        method: 'POST',
        body: JSON.stringify({ text: 'Focus on testing', project_id: 'proj-1' }),
      })
      expect(result).toEqual(mockDirective)
    })

    it('propagates errors from request', async () => {
      request.mockRejectedValue(new Error('Network error'))

      await expect(interpretDirective('test', 'proj-1')).rejects.toThrow('Network error')
    })
  })

  describe('applyDirective', () => {
    it('GETs the directive by id and project_id', async () => {
      const mockDirective = { directive_id: 'udir_abc123', lifecycle_status: 'complete' }
      request.mockResolvedValue(mockDirective)

      const result = await applyDirective('udir_abc123', 'proj-1')

      expect(request).toHaveBeenCalledWith(
        '/unified-directives/udir_abc123?project_id=proj-1'
      )
      expect(result).toEqual(mockDirective)
    })

    it('encodes special characters in directiveId', async () => {
      request.mockResolvedValue({})

      await applyDirective('udir/special', 'proj-1')

      expect(request).toHaveBeenCalledWith(
        '/unified-directives/udir%2Fspecial?project_id=proj-1'
      )
    })
  })

  describe('rejectDirective', () => {
    it('POSTs a rejection comment to the directive', async () => {
      const mockDirective = { directive_id: 'udir_abc123', comments: [{ content: 'Directive rejected by user' }] }
      request.mockResolvedValue(mockDirective)

      const result = await rejectDirective('udir_abc123', 'proj-1')

      expect(request).toHaveBeenCalledWith(
        '/unified-directives/udir_abc123/comments?project_id=proj-1',
        {
          method: 'POST',
          body: JSON.stringify({ content: 'Directive rejected by user' }),
        }
      )
      expect(result).toEqual(mockDirective)
    })

    it('propagates errors from request', async () => {
      request.mockRejectedValue(new Error('Not found'))

      await expect(rejectDirective('udir_abc123', 'proj-1')).rejects.toThrow('Not found')
    })
  })
})
