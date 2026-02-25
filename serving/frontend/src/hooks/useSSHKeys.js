import { useState, useEffect, useCallback } from 'react'
import { getSSHKeys, generateSSHKey, deleteSSHKey, getSSHKey } from '../api/sshKeys'

export function useSSHKeys() {
  const [keys, setKeys] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      setLoading(true)
      const data = await getSSHKeys()
      setKeys(data)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const generate = useCallback(async (description) => {
    const result = await generateSSHKey(description)
    await load()
    return result
  }, [load])

  const remove = useCallback(async (keyId) => {
    const result = await deleteSSHKey(keyId)
    await load()
    return result
  }, [load])

  const getKey = useCallback(async (keyId) => {
    return getSSHKey(keyId)
  }, [])

  return { keys, loading, error, generate, remove, getKey, refresh: load }
}
