import { useState } from 'react';
import Dashboard from './components/Dashboard';
import ComputeRegistry from './components/ComputeRegistry';
import ProcessMapViewer from './components/ProcessMapViewer';
import ObservabilityDashboard from './components/ObservabilityDashboard';
import TaskSubmission from './components/TaskSubmission';
import './App.css';

function App() {
  const [activeView, setActiveView] = useState('dashboard');

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-content">
          <h1>ClaudeVN Serving Component</h1>
          <nav className="main-nav">
            <button
              className={activeView === 'dashboard' ? 'active' : ''}
              onClick={() => setActiveView('dashboard')}
            >
              Dashboard
            </button>
            <button
              className={activeView === 'tasks' ? 'active' : ''}
              onClick={() => setActiveView('tasks')}
            >
              AI Tasks
            </button>
            <button
              className={activeView === 'registry' ? 'active' : ''}
              onClick={() => setActiveView('registry')}
            >
              Compute Registry
            </button>
            <button
              className={activeView === 'process-maps' ? 'active' : ''}
              onClick={() => setActiveView('process-maps')}
            >
              Process Maps
            </button>
            <button
              className={activeView === 'observability' ? 'active' : ''}
              onClick={() => setActiveView('observability')}
            >
              Observability
            </button>
          </nav>
        </div>
      </header>

      <main className="app-main">
        {activeView === 'dashboard' && <Dashboard />}
        {activeView === 'tasks' && <TaskSubmission />}
        {activeView === 'registry' && <ComputeRegistry />}
        {activeView === 'process-maps' && <ProcessMapViewer />}
        {activeView === 'observability' && <ObservabilityDashboard />}
      </main>

      <footer className="app-footer">
        <p>ClaudeVN Serving Component v0.2.1 | Port 8002</p>
      </footer>
    </div>
  );
}

export default App;
