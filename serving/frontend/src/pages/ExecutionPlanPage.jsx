import { useState } from 'react'
import { FolderOpen, List, GitBranch, Network } from 'lucide-react'
import SummaryBar from '../components/plan/SummaryBar'
import ProfileSwitcher from '../components/plan/ProfileSwitcher'
import ActiveWorkView from '../components/plan/ActiveWorkView'
import DependencyGraphView from '../components/plan/DependencyGraphView'
import IssueDependencyGraphView from '../components/plan/IssueDependencyGraphView'
import CharacterizationBanner from '../components/plan/CharacterizationBanner'
import WhyThisOrder from '../components/plan/WhyThisOrder'
import IssueDetailModal from '../components/workmap/IssueDetailModal'
import EmptyState from '../components/common/EmptyState'
import usePlanSummary from '../hooks/usePlanSummary'
import useBucketTree from '../hooks/useBucketTree'
import useCharacterizationStatuses from '../hooks/useCharacterizationStatuses'
import { useProjectContext } from '../contexts/ProjectContext'
import './ExecutionPlanPage.css'

function ExecutionPlanPage() {
  const { activeProject } = useProjectContext()
  const activeProjectId = activeProject?.project_id || null
  const [selectedIssue, setSelectedIssue] = useState(null)
  const [viewMode, setViewMode] = useState('list')

  const {
    data,
    loading,
    error,
    refresh
  } = usePlanSummary(activeProjectId)

  const { itemBucketMap, buckets: bucketList } = useBucketTree(activeProjectId)

  const {
    statusMap: charStatusMap,
    loading: charLoading,
  } = useCharacterizationStatuses(activeProjectId)

  const handleItemClick = (item) => {
    setSelectedIssue(item)
  }

  const handleDetailSuccess = () => {
    refresh()
  }

  // Show project selection prompt if no project selected
  if (!activeProjectId) {
    return (
      <div className="page">
        <header className="page-header">
          <div className="header-content">
            <h1 className="page-title">Plan</h1>
          </div>
        </header>
        <EmptyState
          icon={FolderOpen}
          title="Select a Project"
          description="Please select a project from the sidebar to view the plan."
        />
      </div>
    )
  }

  return (
    <div className="page">
      <header className="page-header">
        <div className="header-content">
          <h1 className="page-title">Plan</h1>
          <div className="plan-header-controls">
            <ProfileSwitcher
              projectId={activeProjectId}
              activePreset={data?.active_preset}
              activePresetLabel={data?.active_preset_label}
              activePresetColor={data?.active_preset_color}
              onPresetChange={refresh}
            />
            <div className="plan-view-toggle">
              <button
                className={`plan-view-btn ${viewMode === 'list' ? 'plan-view-btn--active' : ''}`}
                onClick={() => setViewMode('list')}
                title="List View"
              >
                <List size={16} />
              </button>
              <button
                className={`plan-view-btn ${viewMode === 'graph' ? 'plan-view-btn--active' : ''}`}
                onClick={() => setViewMode('graph')}
                title="Goal Graph View"
              >
                <GitBranch size={16} />
              </button>
              <button
                className={`plan-view-btn ${viewMode === 'deps' ? 'plan-view-btn--active' : ''}`}
                onClick={() => setViewMode('deps')}
                title="Issue Dependency Graph"
              >
                <Network size={16} />
              </button>
            </div>
          </div>
        </div>
      </header>

      {error && (
        <div className="error-banner">
          {error}
        </div>
      )}

      <SummaryBar data={data} loading={loading} />

      <CharacterizationBanner statusMap={charStatusMap} loading={charLoading} />

      {viewMode === 'list' && (
        <ActiveWorkView
          data={data}
          loading={loading}
          onItemClick={handleItemClick}
          itemBucketMap={itemBucketMap}
        />
      )}
      {viewMode === 'graph' && (
        <DependencyGraphView
          data={data}
          loading={loading}
        />
      )}
      {viewMode === 'deps' && (
        <IssueDependencyGraphView
          data={data}
          loading={loading}
        />
      )}

      <WhyThisOrder
        buckets={bucketList}
        traces={data?.recent_traces || []}
        traceCount={data?.trace_count || 0}
      />

      <IssueDetailModal
        isOpen={Boolean(selectedIssue)}
        onClose={() => setSelectedIssue(null)}
        issue={selectedIssue}
        onSuccess={handleDetailSuccess}
        viewOnly
      />
    </div>
  )
}

export default ExecutionPlanPage
