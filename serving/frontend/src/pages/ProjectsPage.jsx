import { useState, useCallback, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
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
import './ProjectsPage.css'

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
  const [cameFromNoProject, setCameFromNoProject] = useState(false)
  const { filters, setFilters } = useProjectFilters()
  const { refreshProjects, activeProject, activeProjectId, setActiveProject, projects } = useProjectContext()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()

  useEffect(() => {
    if (searchParams.get('create') === 'true') {
      setShowCreateModal(true)
      setCameFromNoProject(!activeProject)
      const next = new URLSearchParams(searchParams)
      next.delete('create')
      setSearchParams(next, { replace: true })
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

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
          <div className="project-detail-header-row">
            <button
              onClick={() => setSelectedProject(null)}
              className="back-btn"
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
            className="btn btn-secondary"
          >
            <Pencil size={14} />
            Edit
          </button>
        </header>

        {selectedProject.description && (
          <p className="project-detail-description">
            {selectedProject.description}
          </p>
        )}

        {selectedProject.labels && selectedProject.labels.length > 0 && (
          <div className="project-detail-labels">
            <ProjectLabels labels={selectedProject.labels} />
          </div>
        )}

        {selectedProject.metadata && Object.keys(selectedProject.metadata).length > 0 && (
          <section className="project-detail-section">
            <h2 className="project-detail-section-title">
              Metadata
            </h2>
            <ProjectMetadata metadata={selectedProject.metadata} />
          </section>
        )}

        <div className="project-detail-grid">
          <section>
            <div className="project-detail-repo-header">
              <h2 className="project-detail-section-title">
                Repositories
              </h2>
              <button
                onClick={() => setShowRepoModal(true)}
                className="btn btn-sm btn-secondary"
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
          className="btn btn-primary"
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
        onSelectActive={(project) => {
          setActiveProject(project)
          navigate('/dashboard')
        }}
        activeProjectId={activeProjectId}
        filters={filters}
      />

      <ProjectFormModal
        isOpen={showCreateModal}
        onClose={() => {
          setShowCreateModal(false)
          setCameFromNoProject(false)
        }}
        onSuccess={async () => {
          const prevIds = new Set(projects.map((p) => p.project_id))
          const updated = await refreshProjects()
          setRefreshKey((k) => k + 1)
          if (cameFromNoProject) {
            // Find the newly created project (not in previous list) and auto-select it
            const newProject = (updated || []).find((p) => !prevIds.has(p.project_id))
            if (newProject) {
              setActiveProject(newProject)
            }
            navigate('/dashboard')
          }
        }}
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
