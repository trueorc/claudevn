import { useState, useEffect, useCallback } from 'react'
import { Server } from 'lucide-react'
import Modal from '../common/Modal'
import ConfirmDialog from '../common/ConfirmDialog'
import { StatusBadge } from '../common/Badge'
import { getComputeInstance, deregisterComputeInstance, updateComputeProjects, drainComputeInstance, getDrainStatus, cancelDrain } from '../../api/compute'
import { useProjectContext } from '../../contexts/ProjectContext'
import '../common/Modal.css'
import './Network.css'

function ComputeDetailModal({ isOpen, onClose, instanceId, onDeregister }) {
  const [instance, setInstance] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showConfirm, setShowConfirm] = useState(false)
  const [deregistering, setDeregistering] = useState(false)
  const [savingProjects, setSavingProjects] = useState(false)
  const [selectedProjects, setSelectedProjects] = useState([])
  const [allProjectsMode, setAllProjectsMode] = useState(false)
  const [draining, setDraining] = useState(false)
  const [drainStatus, setDrainStatus] = useState(null)
  const [showDrainConfirm, setShowDrainConfirm] = useState(false)
  const [cancellingDrain, setCancellingDrain] = useState(false)
  const { projects } = useProjectContext()

  const isDraining = instance?.status === 'draining'
  const isOffline = instance?.status === 'offline'
  const canDeregister = isDraining || isOffline

  const fetchDrainStatus = useCallback(async () => {
    if (!instanceId || !isDraining) return
    try {
      const status = await getDrainStatus(instanceId)
      setDrainStatus(status)
    } catch {
      // Ignore errors for drain status polling
    }
  }, [instanceId, isDraining])

  useEffect(() => {
    if (isOpen && instanceId) {
      setLoading(true)
      setError(null)
      setDrainStatus(null)
      getComputeInstance(instanceId)
        .then((data) => {
          setInstance(data)
          const pids = data.project_ids || []
          setAllProjectsMode(pids.includes('*'))
          setSelectedProjects(pids.filter(id => id !== '*'))
        })
        .catch((err) => setError(err.message))
        .finally(() => setLoading(false))
    }
  }, [isOpen, instanceId])

  // Poll drain status while draining
  useEffect(() => {
    if (!isDraining || !isOpen) return
    fetchDrainStatus()
    const interval = setInterval(fetchDrainStatus, 5000)
    return () => clearInterval(interval)
  }, [isDraining, isOpen, fetchDrainStatus])

  const handleSaveProjects = async () => {
    setSavingProjects(true)
    setError(null)
    try {
      const projectIds = allProjectsMode ? ['*'] : selectedProjects
      const updated = await updateComputeProjects(instanceId, projectIds)
      setInstance(updated)
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingProjects(false)
    }
  }

  const toggleProject = (projectId) => {
    setSelectedProjects(prev =>
      prev.includes(projectId)
        ? prev.filter(id => id !== projectId)
        : [...prev, projectId]
    )
  }

  const handleDrain = async () => {
    setDraining(true)
    setError(null)
    try {
      const updated = await drainComputeInstance(instanceId)
      setInstance(updated)
      setShowDrainConfirm(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setDraining(false)
    }
  }

  const handleCancelDrain = async () => {
    setCancellingDrain(true)
    setError(null)
    try {
      const updated = await cancelDrain(instanceId)
      setInstance(updated)
      setDrainStatus(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setCancellingDrain(false)
    }
  }

  const handleDeregister = async () => {
    setDeregistering(true)
    try {
      await deregisterComputeInstance(instanceId)
      setShowConfirm(false)
      onClose()
      onDeregister?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setDeregistering(false)
    }
  }

  if (!isOpen) return null

  return (
    <>
      <Modal isOpen={isOpen} onClose={onClose} title="Compute Instance" width="550px">
        {loading ? (
          <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
            Loading...
          </div>
        ) : error ? (
          <div style={{ padding: '24px', textAlign: 'center', color: 'var(--status-offline)' }}>
            {error}
          </div>
        ) : instance ? (
          <div className="detail-content">
            <div className="detail-header">
              <Server size={20} style={{ color: 'var(--text-muted)' }} />
              <span className="detail-name">{instance.name || instance.instance_id}</span>
              <StatusBadge status={instance.status} />
            </div>

            <div className="detail-section">
              <div className="detail-row">
                <span className="detail-label">Instance ID</span>
                <span className="detail-value mono">{instance.instance_id}</span>
              </div>
              {instance.endpoint && (
                <div className="detail-row">
                  <span className="detail-label">Endpoint</span>
                  <span className="detail-value mono">{instance.endpoint}</span>
                </div>
              )}
              <div className="detail-row">
                <span className="detail-label">Status</span>
                <span className="detail-value">{instance.status}</span>
              </div>
              {instance.last_heartbeat && (
                <div className="detail-row">
                  <span className="detail-label">Last Heartbeat</span>
                  <span className="detail-value">{new Date(instance.last_heartbeat).toLocaleString()}</span>
                </div>
              )}
              {instance.registered_at && (
                <div className="detail-row">
                  <span className="detail-label">Registered</span>
                  <span className="detail-value">{new Date(instance.registered_at).toLocaleString()}</span>
                </div>
              )}
            </div>

            {isDraining && (
              <div className="detail-section">
                <h4 className="detail-section-title">Drain Status</h4>
                <div className="draining-notice">
                  This compute is draining. No new work will be assigned. In-flight work will complete naturally.
                </div>
                {instance.drain_started_at && (
                  <div className="detail-row">
                    <span className="detail-label">Drain Started</span>
                    <span className="detail-value">{new Date(instance.drain_started_at).toLocaleString()}</span>
                  </div>
                )}
                {drainStatus && (
                  <>
                    <div className="detail-row">
                      <span className="detail-label">In-flight Work</span>
                      <span className="detail-value">{drainStatus.in_flight_count}</span>
                    </div>
                    {drainStatus.drain_complete && (
                      <div className="drain-complete-notice">
                        Drain complete. No in-flight work remains. Safe to deregister.
                      </div>
                    )}
                  </>
                )}
                <button
                  onClick={handleCancelDrain}
                  className="btn btn-primary"
                  disabled={cancellingDrain}
                  style={{ marginTop: '8px' }}
                >
                  {cancellingDrain ? 'Cancelling...' : 'Cancel Drain'}
                </button>
              </div>
            )}

            {instance.capabilities && (
              <div className="detail-section">
                <h4 className="detail-section-title">Capabilities</h4>
                {instance.capabilities.agents?.length > 0 && (
                  <div className="detail-row">
                    <span className="detail-label">Agents</span>
                    <span className="detail-value">{instance.capabilities.agents.join(', ')}</span>
                  </div>
                )}
                {instance.capabilities.tools?.length > 0 && (
                  <div className="detail-row">
                    <span className="detail-label">Tools</span>
                    <span className="detail-value">{instance.capabilities.tools.join(', ')}</span>
                  </div>
                )}
                {instance.capabilities.max_concurrent_tasks !== undefined && (
                  <div className="detail-row">
                    <span className="detail-label">Max Concurrent Tasks</span>
                    <span className="detail-value">{instance.capabilities.max_concurrent_tasks}</span>
                  </div>
                )}
              </div>
            )}

            {instance.metadata && Object.keys(instance.metadata).length > 0 && (
              <div className="detail-section">
                <h4 className="detail-section-title">Metadata</h4>
                {Object.entries(instance.metadata).map(([key, value]) => (
                  <div className="detail-row" key={key}>
                    <span className="detail-label">{key}</span>
                    <span className="detail-value">{String(value)}</span>
                  </div>
                ))}
              </div>
            )}

            {!isDraining && (
              <div className="detail-section">
                <h4 className="detail-section-title">Project Tags</h4>
                {(!instance.project_ids || instance.project_ids.length === 0) && (
                  <div className="benched-notice">
                    This compute is benched (no projects assigned). It will not receive any work.
                  </div>
                )}
                <div className="project-tags-control">
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={allProjectsMode}
                      onChange={(e) => {
                        setAllProjectsMode(e.target.checked)
                        if (e.target.checked) setSelectedProjects([])
                      }}
                    />
                    All Projects
                  </label>
                </div>
                {!allProjectsMode && projects && projects.length > 0 && (
                  <div className="project-tags-list">
                    {projects.map(project => (
                      <label key={project.project_id} className="checkbox-label">
                        <input
                          type="checkbox"
                          checked={selectedProjects.includes(project.project_id)}
                          onChange={() => toggleProject(project.project_id)}
                        />
                        {project.name || project.project_id}
                      </label>
                    ))}
                  </div>
                )}
                <button
                  onClick={handleSaveProjects}
                  className="btn btn-primary"
                  disabled={savingProjects}
                  style={{ marginTop: '8px' }}
                >
                  {savingProjects ? 'Saving...' : 'Save Project Tags'}
                </button>
              </div>
            )}

            <div className="detail-actions">
              {!isDraining && (
                <button
                  onClick={() => setShowDrainConfirm(true)}
                  className="btn btn-warning"
                  style={{ marginRight: '8px' }}
                >
                  Drain Instance
                </button>
              )}
              <button
                onClick={() => setShowConfirm(true)}
                className="btn btn-danger"
                disabled={!canDeregister}
                title={canDeregister ? 'Remove this instance from the registry' : 'Drain the instance first before deregistering'}
              >
                Deregister Instance
              </button>
            </div>
          </div>
        ) : null}
      </Modal>

      <ConfirmDialog
        isOpen={showDrainConfirm}
        onClose={() => setShowDrainConfirm(false)}
        onConfirm={handleDrain}
        title="Drain Compute Instance"
        message={`Are you sure you want to drain "${instance?.name || instanceId}"? This will remove all project tags and stop new work from being assigned. In-flight work will complete naturally.`}
        confirmText="Start Drain"
        variant="warning"
        loading={draining}
      />

      <ConfirmDialog
        isOpen={showConfirm}
        onClose={() => setShowConfirm(false)}
        onConfirm={handleDeregister}
        title="Deregister Compute Instance"
        message={`Are you sure you want to deregister "${instance?.name || instanceId}"? This will disconnect the instance from the serving network.${isDraining ? '' : ' Any in-progress work may be orphaned.'}`}
        confirmText="Deregister"
        variant="danger"
        loading={deregistering}
      />
    </>
  )
}

export default ComputeDetailModal
