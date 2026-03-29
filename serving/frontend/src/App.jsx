import { Routes, Route, Navigate } from 'react-router-dom'
import { AppProvider } from './contexts/AppContext'
import { ToastProvider } from './contexts/ToastContext'
import { ProjectProvider } from './contexts/ProjectContext'
import { ConversationProvider } from './contexts/ConversationContext'
import { AuthProvider, useAuth as useUserAuth } from './contexts/auth/AuthContext'
import { ThemeProvider } from './contexts/ThemeContext'
import { ToastContainer } from './components/common/Toast'
import IconBar from './components/layout/IconBar'
import ChatRail from './components/layout/ChatRail'
import AuthExpiredBanner from './components/common/AuthExpiredBanner'
import DashboardPage from './pages/DashboardPage'
import NetworkHealthPage from './pages/NetworkHealthPage'
import SkillsPage from './pages/SkillsPage'
import ProjectsPage from './pages/ProjectsPage'
import BacklogPage from './pages/BacklogPage'
import ExecutionPlanPage from './pages/ExecutionPlanPage'
import GoalsPage from './pages/GoalsPage'
import ProfilePage from './pages/ProfilePage'
import SSHKeysPage from './pages/SSHKeysPage'
import SettingsPage from './pages/SettingsPage'
import AuthSetupPage from './pages/AuthSetupPage'
import TimingPage from './pages/TimingPage'
import VerificationPage from './pages/VerificationPage'
import NotificationsPage from './pages/NotificationsPage'
import UserManagementPage from './pages/UserManagementPage'
import LoginPage from './pages/LoginPage'
import SetPasswordPage from './pages/SetPasswordPage'
import ForgotPasswordPage from './pages/ForgotPasswordPage'
import WhatsNew from './components/common/WhatsNew'
import { useAuth } from './hooks/useAuth'

function AuthenticatedApp({ expired, expiringAt, onReauth }) {
  return (
    <ProjectProvider>
      <ConversationProvider>
        <div className="app">
          <IconBar />
          <ChatRail />
          <main className="main-content">
            {(expired || expiringAt) && (
              <AuthExpiredBanner
                expired={expired}
                expiringAt={expiringAt}
                onReauth={onReauth}
              />
            )}
            <Routes>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              {/* Core: Control Center */}
              <Route path="/dashboard" element={<DashboardPage />} />
              {/* Process: Plan → Execute → Verify */}
              <Route path="/plan" element={<GoalsPage />} />
              <Route path="/execute" element={<ExecutionPlanPage />} />
              <Route path="/verify" element={<VerificationPage />} />
              {/* Administrative */}
              <Route path="/backlog" element={<BacklogPage />} />
              <Route path="/marketplace" element={<SkillsPage />} />
              <Route path="/network" element={<NetworkHealthPage />} />
              <Route path="/projects" element={<ProjectsPage />} />
              <Route path="/timing" element={<TimingPage />} />
              <Route path="/notifications" element={<NotificationsPage />} />
              <Route path="/settings" element={<Navigate to="/settings/general" replace />} />
              <Route path="/settings/profile" element={<ProfilePage />} />
              <Route path="/settings/ssh-keys" element={<SSHKeysPage />} />
              <Route path="/settings/general" element={<SettingsPage />} />
              <Route path="/settings/users" element={<UserManagementPage />} />
              {/* Redirects from old routes */}
              <Route path="/directives" element={<Navigate to="/plan" replace />} />
              <Route path="/goals" element={<Navigate to="/plan" replace />} />
              <Route path="/skills" element={<Navigate to="/marketplace" replace />} />
              <Route path="/health" element={<Navigate to="/network" replace />} />
              <Route path="/work" element={<Navigate to="/backlog" replace />} />
              <Route path="/workmap" element={<Navigate to="/execute" replace />} />
              <Route path="/traces" element={<Navigate to="/execute" replace />} />
              <Route path="/focus" element={<Navigate to="/execute" replace />} />
              <Route path="/capabilities" element={<Navigate to="/network" replace />} />
              <Route path="/conflicts" element={<Navigate to="/network" replace />} />
            </Routes>
          </main>
        </div>
        <WhatsNew />
        <ToastContainer />
      </ConversationProvider>
    </ProjectProvider>
  )
}

function CognitoGate({ children }) {
  const { loading: cognitoLoading, isAuthenticated: cognitoAuthed, isBypass } = useUserAuth()

  if (cognitoLoading) {
    return (
      <div className="auth-setup-page">
        <div className="auth-setup-card">
          <div className="auth-setup-spinner" />
          <p style={{ color: 'var(--text-secondary)', marginTop: 'var(--space-lg)', fontSize: 'var(--font-size-base)' }}>
            Connecting...
          </p>
        </div>
      </div>
    )
  }

  // In cognito mode, unauthenticated users see login/set-password/forgot-password routes
  if (!cognitoAuthed && !isBypass) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/set-password" element={<SetPasswordPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  // Cognito authenticated (or bypass mode) — proceed to Claude token auth
  return children
}

function ClaudeTokenGate() {
  const { status, loading, authenticated, expired, expiringAt, error, message, submitToken, reauth, skipSetup } = useAuth()

  if (loading) {
    return (
      <div className="auth-setup-page">
        <div className="auth-setup-card">
          <div className="auth-setup-spinner" />
          <p style={{ color: 'var(--text-secondary)', marginTop: 'var(--space-lg)', fontSize: 'var(--font-size-base)' }}>
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

  if (authenticated) {
    return <AuthenticatedApp expired={expired} expiringAt={expiringAt} onReauth={reauth} />
  }

  return (
    <AuthSetupPage
      status={status}
      message={message}
      submitToken={submitToken}
      skipSetup={skipSetup}
    />
  )
}

function App() {
  return (
    <AuthProvider>
      <ThemeProvider>
        <ToastProvider>
          <AppProvider>
            <CognitoGate>
              <ClaudeTokenGate />
            </CognitoGate>
          </AppProvider>
        </ToastProvider>
      </ThemeProvider>
    </AuthProvider>
  )
}

export default App
