import { useState, useEffect, useCallback } from 'react'
import { getBucketTree } from '../api/workmap'

function useBucketTree(projectId, options = {}) {
  const { pollInterval = 30000 } = options

  const [bucketTree, setBucketTree] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    if (!projectId) {
      setBucketTree(null)
      setLoading(false)
      return
    }

    try {
      const data = await getBucketTree(projectId)
      setBucketTree(data)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [projectId])

  const refresh = useCallback(() => {
    load()
  }, [load])

  useEffect(() => {
    load()

    if (pollInterval > 0) {
      const interval = setInterval(load, pollInterval)
      return () => clearInterval(interval)
    }
  }, [load, pollInterval])

  // Build a map from item_id to bucket name(s) for quick lookup
  const itemBucketMap = bucketTree?.buckets
    ? bucketTree.buckets.reduce((map, bucket) => {
        const name = bucket.definition?.name || bucket.bucket_id
        for (const item of bucket.items || []) {
          if (!map[item.item_id]) {
            map[item.item_id] = []
          }
          map[item.item_id].push({
            name,
            description: bucket.definition?.description || '',
            rank: bucket.rank,
            bucket_id: bucket.bucket_id
          })
        }
        return map
      }, {})
    : {}

  return {
    bucketTree,
    buckets: bucketTree?.buckets || [],
    itemBucketMap,
    loading,
    error,
    refresh
  }
}

export { useBucketTree }
export default useBucketTree
