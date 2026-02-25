import { describe, it, expect, vi, beforeEach } from 'vitest'
import { getSSHKeys, getSSHKey, generateSSHKey, deleteSSHKey, getRepoStatus, syncRepo, pushRepo, cloneRepo } from './sshKeys'

vi.mock('./index.js', () => ({
  request: vi.fn(),
}))

import { request } from './index.js'

describe('sshKeys API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('getSSHKeys', () => {
    it('calls GET /git/ssh-keys', async () => {
      const mockKeys = [{ key_id: 'sshk_abc', description: 'test' }]
      request.mockResolvedValue(mockKeys)

      const result = await getSSHKeys()

      expect(request).toHaveBeenCalledWith('/git/ssh-keys')
      expect(result).toEqual(mockKeys)
    })
  })

  describe('getSSHKey', () => {
    it('calls GET /git/ssh-keys/:id', async () => {
      const mockKey = { key_id: 'sshk_abc', public_key: 'ssh-ed25519 AAAA...' }
      request.mockResolvedValue(mockKey)

      const result = await getSSHKey('sshk_abc')

      expect(request).toHaveBeenCalledWith('/git/ssh-keys/sshk_abc')
      expect(result).toEqual(mockKey)
    })
  })

  describe('generateSSHKey', () => {
    it('calls POST /git/ssh-keys with description', async () => {
      const mockResult = { key_id: 'sshk_new', public_key: 'ssh-ed25519 BBBB...' }
      request.mockResolvedValue(mockResult)

      const result = await generateSSHKey('My key')

      expect(request).toHaveBeenCalledWith('/git/ssh-keys', {
        method: 'POST',
        body: JSON.stringify({ description: 'My key' })
      })
      expect(result).toEqual(mockResult)
    })

    it('defaults description to empty string', async () => {
      request.mockResolvedValue({})

      await generateSSHKey()

      expect(request).toHaveBeenCalledWith('/git/ssh-keys', {
        method: 'POST',
        body: JSON.stringify({ description: '' })
      })
    })
  })

  describe('deleteSSHKey', () => {
    it('calls DELETE /git/ssh-keys/:id', async () => {
      const mockResult = { key_id: 'sshk_abc', deleted: true, referencing_repos: [] }
      request.mockResolvedValue(mockResult)

      const result = await deleteSSHKey('sshk_abc')

      expect(request).toHaveBeenCalledWith('/git/ssh-keys/sshk_abc', { method: 'DELETE' })
      expect(result).toEqual(mockResult)
    })
  })

  describe('getRepoStatus', () => {
    it('calls GET /projects/:pid/repos/:rid/status', async () => {
      const mockStatus = { repo_id: 'r1', clone_status: 'cloned' }
      request.mockResolvedValue(mockStatus)

      const result = await getRepoStatus('p1', 'r1')

      expect(request).toHaveBeenCalledWith('/projects/p1/repos/r1/status')
      expect(result).toEqual(mockStatus)
    })
  })

  describe('syncRepo', () => {
    it('calls POST /projects/:pid/repos/:rid/pull', async () => {
      const mockResult = { success: true, message: 'Synced' }
      request.mockResolvedValue(mockResult)

      const result = await syncRepo('p1', 'r1')

      expect(request).toHaveBeenCalledWith('/projects/p1/repos/r1/pull', { method: 'POST' })
      expect(result).toEqual(mockResult)
    })
  })

  describe('pushRepo', () => {
    it('calls POST /projects/:pid/repos/:rid/push with branch param', async () => {
      const mockResult = { success: true, message: 'Pushed' }
      request.mockResolvedValue(mockResult)

      const result = await pushRepo('p1', 'r1', 'main')

      expect(request).toHaveBeenCalledWith('/projects/p1/repos/r1/push?branch=main', { method: 'POST' })
      expect(result).toEqual(mockResult)
    })
  })

  describe('cloneRepo', () => {
    it('calls POST /projects/:pid/repos/:rid/clone', async () => {
      const mockResult = { success: true, message: 'Cloned' }
      request.mockResolvedValue(mockResult)

      const result = await cloneRepo('p1', 'r1')

      expect(request).toHaveBeenCalledWith('/projects/p1/repos/r1/clone', { method: 'POST' })
      expect(result).toEqual(mockResult)
    })
  })
})
