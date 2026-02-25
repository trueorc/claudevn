import { useState, useCallback, useMemo } from 'react'
import { Plus, ArrowLeft, Pencil } from 'lucide-react'
import ProjectList from '../components/projects/ProjectList'
import RepoList from '../components/projects/RepoList'
import ProjectActivity from '../components/projects/ProjectActivity'
import ProjectFormModal from '../components/projects/ProjectFormModal'
import DeleteProjectModal from '../components/projects/DeleteProjectModal'
import RepoFormModal from '../components/projects/RepoFormModal'
import ProjectFilterBar from '../components/projects/ProjectFilterBar'
import ConfirmDialog from '../components/common/ConfirmDialog'
import { StatusBadge } from '../components/common/Badge'
import { ProjectIcon, ProjectLabels } from '../components/projects/ProjectCard'
import { getProject, removeRepoFromProject } from '../api/projects'
import { useProjectContext } from '../contexts/ProjectContext'
import useProjectFilters from '../hooks/useProjectFilters'
import '../components/projects/Projects.css'

function ProjectMetadata({ metadata }) {
  if (!metadata || Object.keys(metadata).length === 0) return null

  const displayKeys = Object.keys(metadata).slice(0, 6)

  return (
    <div className="project-detail-meta">
      {displayKeys.map((key) => (
        <div key={key} className="project-detail-meta-item">
          <span className="project-detail-meta-label">{key}</span>
          <span className="project-detail-meta-value">
            {typeof metadata[key] === 'boolean'
              ? metadata[key] ? 'Yes' : 'No'
              : String(metadata[key])}
          </span>
        </div>
      ))}
    </div>
  )
}

function ProjectsPage() {
  const [selectedProject, setSelectedProject] = useState(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editingProject, setEditingProject] = useState(null)
  const [deletingProject, setDeletingProject] = useState(null)
  const [showRepoModal, setShowRepoModal] = useState(false)
  const [removingRepo, setRemovingRepo] = useState(null)
  const [removeLoading, setRemoveLoading] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const { filters, setFilters } = useProjectFilters()
  const { refreshProjects } = useProjectContext()

  const handleRefresh = () => {
    setRefreshKey((k) => k + 1)
    refreshProjects()
  }

  const handleEdit = (project) => {
    setEditingProject(project)
  }

  const handleEditSuccess = () => {
    handleRefresh()
    if (selectedProject && editingProject?.project_id === selectedProject.project_id) {
      refreshSelectedProject()
    }
  }

  const handleDelete = (project) => {
    setDeletingProject(project)
  }

  const handleDeleteSuccess = () => {
    if (selectedProject?.project_id === deletingProject?.project_id) {
      setSelectedProject(null)
    }
    handleRefresh()
  }

  const refreshSelectedProject = useCallback(async () => {
    if (selectedProject) {
      try {
        const updated = await getProject(selectedProject.project_id)
        setSelectedProject(updated)
      } catch (err) {
        console.error('Failed to refresh project:', err)
      }
    }
  }, [selectedProject])

  const handleRepoAdded = () => {
    refreshSelectedProject()
  }

  const handleRemoveRepo = (repo) => {
    setRemovingRepo(repo)
  }

  const confirmRemoveRepo = async () => {
    if (!removingRepo || !selectedProject) return

    setRemoveLoading(true)
    try {
      await removeRepoFromProject(selectedProject.project_id, removingRepo.repo_id)
      setRemovingRepo(null)
      refreshSelectedProject()
    } catch (err) {
      console.error('Failed to remove repo:', err)
    } finally {
      setRemoveLoading(false)
    }
  }

  if (selectedProject) {
    return (
      <div className="page">
        <header className="page-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <button
              onClick={() => setSelectedProject(null)}
              style={{
                display: 'flex',
                alignItems: 'center',
                padding: '6px',
                borderRadius: '4px',
                background: 'var(--bg-hover)'
              }}
            >
              <ArrowLeft size={16} />
            </button>
            <ProjectIcon
              icon={selectedProject.icon}
              iconColor={selectedProject.icon_color}
              name={selectedProject.name}
              size="lg"
            />
            <h1 className="page-title">{selectedProject.name}</h1>
            <StatusBadge status={selectedProject.status} />
          </div>
          <button
            onClick={() => setEditingProject(selectedProject)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 12px',
              background: 'var(--bg-hover)',
              borderRadius: '6px',
              fontSize: '13px',
              fontWeight: 500
            }}
          >
            <Pencil size={14} />
            Edit
          </button>
        </header>

        {selectedProject.description && (
          <p style={{ color: 'var(--text-secondary)', marginBottom: '16px' }}>
            {selectedProject.description}
          </p>
        )}

        {selectedProject.labels && selectedProject.labels.length > 0 && (
          <div style={{ marginBottom: '24px' }}>
            <ProjectLabels labels={selectedProject.labels} />
          </div>
        )}

        {selectedProject.metadata && Object.keys(selectedProject.metadata).length > 0 && (
          <section style={{ marginBottom: '24px' }}>
            <h2 style={{ fontSize: '14px', fontWeight: 500, marginBottom: '12px' }}>
              Metadata
            </h2>
            <ProjectMetadata metadata={selectedProject.metadata} />
          </section>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: '24px' }}>
          <section>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
              <h2 style={{ fontSize: '14px', fontWeight: 500 }}>
                Repositories
              </h2>
              <button
                onClick={() => setShowRepoModal(true)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '4px 10px',
                  background: 'var(--bg-hover)',
                  borderRadius: '4px',
                  fontSize: '12px',
                  fontWeight: 500
                }}
              >
                <Plus size={12} />
                Add Repo
              </button>
            </div>
            <RepoList repos={selectedProject.repos} onRemove={handleRemoveRepo} projectId={selectedProject.project_id} />
          </section>

          <aside>
            <ProjectActivity projectId={selectedProject.project_id} />
          </aside>
        </div>

        <RepoFormModal
          isOpen={showRepoModal}
          onClose={() => setShowRepoModal(false)}
          onSuccess={handleRepoAdded}
          projectId={selectedProject.project_id}
        />

        <ConfirmDialog
          isOpen={!!removingRepo}
          onClose={() => setRemovingRepo(null)}
          onConfirm={confirmRemoveRepo}
          title="Remove Repository"
          message={`Are you sure you want to remove "${removingRepo?.name}" from this project?`}
          confirmText="Remove"
          variant="danger"
          loading={removeLoading}
        />

        <ProjectFormModal
          isOpen={!!editingProject}
          onClose={() => setEditingProject(null)}
          onSuccess={handleEditSuccess}
          project={editingProject}
        />
      </div>
    )
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1 className="page-title">Projects</h1>
        <button
          onClick={() => setShowCreateModal(true)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '6px 12px',
            background: 'var(--primary)',
            color: 'white',
            borderRadius: '6px',
            fontSize: '13px',
            fontWeight: 500
          }}
        >
          <Plus size={14} />
          New Project
        </button>
      </header>

      <ProjectFilterBar filters={filters} onChange={setFilters} />

      <ProjectList
        key={refreshKey}
        onSelect={setSelectedProject}
        onEdit={handleEdit}
        onDelete={handleDelete}
        filters={filters}
      />

      <ProjectFormModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onSuccess={handleRefresh}
      />

      <ProjectFormModal
        isOpen={!!editingProject}
        onClose={() => setEditingProject(null)}
        onSuccess={handleEditSuccess}
        project={editingProject}
      />

      <DeleteProjectModal
        isOpen={!!deletingProject}
        onClose={() => setDeletingProject(null)}
        onSuccess={handleDeleteSuccess}
        project={deletingProject}
      />
    </div>
  )
}

export default ProjectsPage
