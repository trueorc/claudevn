import { Routes, Route, Navigate } from 'react-router-dom'
import { AppProvider } from './contexts/AppContext'
import { ToastProvider } from './contexts/ToastContext'
import { ProjectProvider } from './contexts/ProjectContext'
import { ToastContainer } from './components/common/Toast'
import Sidebar from './components/layout/Sidebar'
import AuthExpiredBanner from './components/common/AuthExpiredBanner'
import NetworkHealthPage from './pages/NetworkHealthPage'
import SkillsPage from './pages/SkillsPage'
import ProjectsPage from './pages/ProjectsPage'
import BacklogPage from './pages/BacklogPage'
import ExecutionPlanPage from './pages/ExecutionPlanPage'
import GoalsPage from './pages/GoalsPage'
import ProfilePage from './pages/ProfilePage'
import AuthSetupPage from './pages/AuthSetupPage'
import { useAuth } from './hooks/useAuth'

function AuthenticatedApp({ expired, expiringAt, onReauth }) {
  return (
    <ProjectProvider>
      <div className="app">
        <Sidebar />
        <main className="main-content">
          {(expired || expiringAt) && (
            <AuthExpiredBanner
              expired={expired}
              expiringAt={expiringAt}
              onReauth={onReauth}
            />
          )}
          <Routes>
            <Route path="/" element={<Navigate to="/projects" replace />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/directives" element={<GoalsPage />} />
            <Route path="/plan" element={<ExecutionPlanPage />} />
            <Route path="/backlog" element={<BacklogPage />} />
            <Route path="/marketplace" element={<SkillsPage />} />
            <Route path="/network" element={<NetworkHealthPage />} />
            <Route path="/settings/profile" element={<ProfilePage />} />
            {/* Redirects from old routes */}
            <Route path="/goals" element={<Navigate to="/directives" replace />} />
            <Route path="/skills" element={<Navigate to="/marketplace" replace />} />
            <Route path="/health" element={<Navigate to="/network" replace />} />
            <Route path="/work" element={<Navigate to="/backlog" replace />} />
            <Route path="/workmap" element={<Navigate to="/plan" replace />} />
            <Route path="/traces" element={<Navigate to="/plan" replace />} />
            <Route path="/focus" element={<Navigate to="/plan" replace />} />
            <Route path="/capabilities" element={<Navigate to="/network" replace />} />
            <Route path="/conflicts" element={<Navigate to="/network" replace />} />
          </Routes>
        </main>
      </div>
      <ToastContainer />
    </ProjectProvider>
  )
}

function App() {
  const { status, loading, authenticated, expired, expiringAt, error, message, submitToken, reauth, skipSetup } = useAuth()

  if (loading) {
    return (
      <div className="auth-setup-page">
        <div className="auth-setup-card">
          <div className="auth-setup-spinner" />
          <p style={{ color: 'var(--text-secondary, #888)', marginTop: '1rem', fontSize: '0.9rem' }}>
            Connecting...
          </p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="auth-setup-page">
        <div className="auth-setup-card">
          <div className="auth-setup-header">
            <h1>ClaudeVN</h1>
            <p className="auth-setup-subtitle">Cannot connect to server</p>
          </div>
          <div className="auth-setup-error">
            <p>{error}</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <ToastProvider>
      <AppProvider>
        {authenticated ? (
          <AuthenticatedApp expired={expired} expiringAt={expiringAt} onReauth={reauth} />
        ) : (
          <AuthSetupPage
            status={status}
            message={message}
            submitToken={submitToken}
            skipSetup={skipSetup}
          />
        )}
      </AppProvider>
    </ToastProvider>
  )
}

export default App
