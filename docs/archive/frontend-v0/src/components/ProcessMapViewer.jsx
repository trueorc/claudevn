import { useState, useEffect } from 'react';
import {
  getProcessMap,
  getProcessMapProgress,
  addActivity,
  updateActivityStatus,
  getProcessMapHistory,
  createFacilitatedSession,
  selectParticipants,
  assignParticipant,
  startFacilitation,
  getActivityExchanges,
  checkConsistency,
  generateProgressReport,
  synthesizeResults,
  getCoordinatingEvents,
} from '../api';
import './ProcessMapViewer.css';

function ProcessMapViewer() {
  const [sessionId, setSessionId] = useState('');
  const [processMap, setProcessMap] = useState(null);
  const [progress, setProgress] = useState(null);
  const [history, setHistory] = useState([]);
  const [selectedActivity, setSelectedActivity] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  
  // Participant selection state
  const [selectionResult, setSelectionResult] = useState(null);
  const [showSelectionModal, setShowSelectionModal] = useState(false);
  const [selectionLoading, setSelectionLoading] = useState(false);
  
  // Conversation/exchange state
  const [exchanges, setExchanges] = useState([]);
  const [showExchangesModal, setShowExchangesModal] = useState(false);
  const [exchangesActivityId, setExchangesActivityId] = useState(null);
  const [facilitationLoading, setFacilitationLoading] = useState(false);
  
  // Coordinating team dashboard state
  const [coordinatingEvents, setCoordinatingEvents] = useState([]);
  const [showDashboard, setShowDashboard] = useState(false);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [latestReport, setLatestReport] = useState(null);
  const [latestDeliverable, setLatestDeliverable] = useState(null);
  
  // Form state for adding activities
  const [showAddForm, setShowAddForm] = useState(false);
  const [newActivityGoal, setNewActivityGoal] = useState('');
  const [newActivityDescription, setNewActivityDescription] = useState('');
  const [newActivityDeps, setNewActivityDeps] = useState('');
  
  // Form state for creating facilitated sessions
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [businessGoal, setBusinessGoal] = useState('');
  const [creating, setCreating] = useState(false);

  const loadProcessMap = async () => {
    if (!sessionId) {
      setError('Please enter a session ID');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const [mapData, progressData] = await Promise.all([
        getProcessMap(sessionId),
        getProcessMapProgress(sessionId),
      ]);
      
      setProcessMap(mapData);
      setProgress(progressData);
    } catch (err) {
      setError(err.message);
      setProcessMap(null);
      setProgress(null);
    } finally {
      setLoading(false);
    }
  };

  const loadHistory = async () => {
    if (!sessionId) return;

    try {
      const historyData = await getProcessMapHistory(sessionId);
      setHistory(historyData);
    } catch (err) {
      console.error('Failed to load history:', err);
    }
  };

  const handleAddActivity = async (e) => {
    e.preventDefault();
    
    if (!newActivityGoal.trim()) {
      alert('Please enter an activity goal');
      return;
    }

    setLoading(true);
    try {
      const deps = newActivityDeps
        .split(',')
        .map(d => d.trim())
        .filter(d => d.length > 0);

      await addActivity(
        sessionId,
        newActivityGoal,
        newActivityDescription || null,
        deps
      );

      // Reset form
      setNewActivityGoal('');
      setNewActivityDescription('');
      setNewActivityDeps('');
      setShowAddForm(false);

      // Reload map
      await loadProcessMap();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleStatusChange = async (activityId, newStatus) => {
    setLoading(true);
    try {
      await updateActivityStatus(sessionId, activityId, newStatus);
      await loadProcessMap();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status) => {
    const colors = {
      proposed: '#3b82f6',      // Blue
      in_progress: '#f59e0b',   // Orange
      goal_met: '#10b981',      // Green
      blocked: '#ef4444',       // Red
      revisit: '#8b5cf6',       // Purple
    };
    return colors[status] || '#6b7280';
  };

  const getStatusLabel = (status) => {
    const labels = {
      proposed: 'Proposed',
      in_progress: 'In Progress',
      goal_met: 'Goal Met',
      blocked: 'Blocked',
      revisit: 'Revisit',
    };
    return labels[status] || status;
  };

  const handleCreateFacilitatedSession = async (e) => {
    e.preventDefault();
    
    if (!businessGoal.trim()) {
      alert('Please enter a business goal');
      return;
    }

    setCreating(true);
    setError(null);
    
    try {
      const result = await createFacilitatedSession(businessGoal);
      
      // Set session ID and load the process map
      setSessionId(result.session_id);
      setBusinessGoal('');
      setShowCreateForm(false);
      
      // Load the newly created process map
      const [mapData, progressData] = await Promise.all([
        getProcessMap(result.session_id),
        getProcessMapProgress(result.session_id),
      ]);
      
      setProcessMap(mapData);
      setProgress(progressData);
      
      // Show success message
      alert(`✅ Facilitated session created!\n\nSession ID: ${result.session_id}\nActivities generated: ${result.initial_activities}\n\n${result.message}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  };

  const handleSelectParticipants = async (activityId) => {
    setSelectionLoading(true);
    setError(null);
    
    try {
      // For now, use generic capabilities - in real scenario, this would be determined by activity
      const result = await selectParticipants(sessionId, activityId, ['analysis', 'writing', 'data_processing'], null);
      
      setSelectionResult({
        activityId,
        ...result
      });
      setShowSelectionModal(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setSelectionLoading(false);
    }
  };

  const handleAcceptRecommendation = async (agentId, agentName, capabilities, reason) => {
    setSelectionLoading(true);
    
    try {
      await assignParticipant(
        sessionId,
        selectionResult.activityId,
        agentId,
        agentName,
        'participant',
        capabilities,
        reason
      );
      
      // Reload map
      await loadProcessMap();
      
      // Close modal
      setShowSelectionModal(false);
      setSelectionResult(null);
      
      alert(`✅ ${agentName} assigned successfully!`);
    } catch (err) {
      setError(err.message);
    } finally {
      setSelectionLoading(false);
    }
  };

  const handleStartFacilitation = async (activityId) => {
    setFacilitationLoading(true);
    setError(null);
    
    try {
      const result = await startFacilitation(sessionId, activityId);
      
      // Reload map
      await loadProcessMap();
      
      alert(`✅ Facilitation started!\n\n${result.facilitator_decision?.reasoning || 'Activity is now in progress.'}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setFacilitationLoading(false);
    }
  };

  const handleViewConversation = async (activityId) => {
    setExchangesActivityId(activityId);
    setFacilitationLoading(true);
    
    try {
      const activityExchanges = await getActivityExchanges(sessionId, activityId);
      setExchanges(activityExchanges);
      setShowExchangesModal(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setFacilitationLoading(false);
    }
  };

  const loadCoordinatingDashboard = async () => {
    if (!sessionId) return;
    
    setDashboardLoading(true);
    try {
      const eventsData = await getCoordinatingEvents(sessionId);
      setCoordinatingEvents(eventsData.events || []);
      
      // Extract latest report and deliverable
      const progressEvents = eventsData.events.filter(e => e.event_type === 'progress_report');
      if (progressEvents.length > 0) {
        setLatestReport(progressEvents[progressEvents.length - 1].data);
      }
      
      const synthEvents = eventsData.events.filter(e => e.event_type === 'result_synthesis');
      if (synthEvents.length > 0) {
        setLatestDeliverable(synthEvents[synthEvents.length - 1].data);
      }
      
      setShowDashboard(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setDashboardLoading(false);
    }
  };

  const handleCheckConsistency = async () => {
    setDashboardLoading(true);
    try {
      await checkConsistency(sessionId);
      alert('✅ Consistency check complete! View the dashboard for results.');
      await loadCoordinatingDashboard();
    } catch (err) {
      setError(err.message);
    } finally {
      setDashboardLoading(false);
    }
  };

  const handleGenerateProgressReport = async () => {
    setDashboardLoading(true);
    try {
      const result = await generateProgressReport(sessionId);
      setLatestReport(result.report);
      alert('✅ Progress report generated!');
      await loadCoordinatingDashboard();
    } catch (err) {
      setError(err.message);
    } finally {
      setDashboardLoading(false);
    }
  };

  const handleSynthesizeResults = async () => {
    setDashboardLoading(true);
    try {
      const result = await synthesizeResults(sessionId);
      setLatestDeliverable(result.deliverable);
      alert('✅ Final deliverable synthesized!');
      await loadCoordinatingDashboard();
    } catch (err) {
      setError(err.message);
    } finally {
      setDashboardLoading(false);
    }
  };

  return (
    <div className="process-map-viewer">
      <div className="viewer-header">
        <h2>Process Map Viewer</h2>
        <p className="subtitle">Visualize and manage facilitated process maps</p>
      </div>

      {/* Create New Session */}
      <div className="create-session-section">
        <button 
          className="create-session-btn"
          onClick={() => setShowCreateForm(!showCreateForm)}
          disabled={creating}
        >
          {showCreateForm ? '✕ Cancel' : '✨ Create New Facilitated Session'}
        </button>
        
        {showCreateForm && (
          <form className="create-session-form" onSubmit={handleCreateFacilitatedSession}>
            <div className="form-group">
              <label>Business Goal:</label>
              <input
                type="text"
                value={businessGoal}
                onChange={(e) => setBusinessGoal(e.target.value)}
                placeholder="e.g., Increase customer retention by 20%"
                required
                autoFocus
              />
            </div>
            <button type="submit" disabled={creating}>
              {creating ? 'Creating...' : '🚀 Create Session'}
            </button>
            <p className="form-hint">
              The Process Mapper agent will analyze your goal and generate initial activities automatically.
            </p>
          </form>
        )}
      </div>

      {/* Session ID Input */}
      <div className="session-input-section">
        <div className="input-group">
          <label htmlFor="sessionId">Or Load Existing Session:</label>
          <input
            id="sessionId"
            type="text"
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value)}
            placeholder="Enter session ID (e.g., sess-123)"
          />
          <button onClick={loadProcessMap} disabled={loading || !sessionId}>
            {loading ? 'Loading...' : 'Load Process Map'}
          </button>
          {sessionId && processMap && (
            <button onClick={loadHistory} className="secondary">
              View History
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="error-message">
          <strong>Error:</strong> {error}
        </div>
      )}

      {processMap && (
        <>
          {/* Process Map Info */}
          <div className="map-info">
            <div className="info-grid">
              <div className="info-item">
                <label>Business Goal:</label>
                <div className="info-value">{processMap.business_goal}</div>
              </div>
              <div className="info-item">
                <label>Map Version:</label>
                <div className="info-value">v{processMap.map_version}</div>
              </div>
              <div className="info-item">
                <label>Status:</label>
                <div className="info-value status-badge">{processMap.status}</div>
              </div>
              <div className="info-item">
                <label>Created By:</label>
                <div className="info-value">{processMap.created_by}</div>
              </div>
            </div>
          </div>

          {/* Progress */}
          {progress && (
            <div className="progress-section">
              <h3>Progress</h3>
              <div className="progress-bar">
                <div 
                  className="progress-fill"
                  style={{ width: `${progress.progress_percent}%` }}
                >
                  {Math.round(progress.progress_percent)}%
                </div>
              </div>
              <div className="progress-stats">
                <span>✅ Completed: {progress.completed}</span>
                <span>🔄 In Progress: {progress.in_progress}</span>
                <span>🚫 Blocked: {progress.blocked}</span>
                <span>📋 Proposed: {progress.proposed}</span>
                <span>📊 Total: {progress.total_activities}</span>
              </div>
            </div>
          )}

          {/* Activities */}
          <div className="activities-section">
            <div className="section-header">
              <h3>Activities</h3>
              <button 
                className="add-btn"
                onClick={() => setShowAddForm(!showAddForm)}
              >
                {showAddForm ? '✕ Cancel' : '+ Add Activity'}
              </button>
            </div>

            {showAddForm && (
              <form className="add-activity-form" onSubmit={handleAddActivity}>
                <div className="form-group">
                  <label>Activity Goal:</label>
                  <input
                    type="text"
                    value={newActivityGoal}
                    onChange={(e) => setNewActivityGoal(e.target.value)}
                    placeholder="What should this activity accomplish?"
                    required
                  />
                </div>
                <div className="form-group">
                  <label>Description (optional):</label>
                  <textarea
                    value={newActivityDescription}
                    onChange={(e) => setNewActivityDescription(e.target.value)}
                    placeholder="Additional context..."
                    rows="2"
                  />
                </div>
                <div className="form-group">
                  <label>Dependencies (optional):</label>
                  <input
                    type="text"
                    value={newActivityDeps}
                    onChange={(e) => setNewActivityDeps(e.target.value)}
                    placeholder="Comma-separated activity IDs (e.g., act-1, act-2)"
                  />
                </div>
                <button type="submit" disabled={loading}>
                  Add Activity
                </button>
              </form>
            )}

            <div className="activities-grid">
              {Object.entries(processMap.activities).map(([id, activity]) => (
                <div
                  key={id}
                  className={`activity-card ${selectedActivity === id ? 'selected' : ''}`}
                  onClick={() => setSelectedActivity(selectedActivity === id ? null : id)}
                  style={{ borderLeftColor: getStatusColor(activity.status) }}
                >
                  <div className="activity-header">
                    <div className="activity-id">{activity.activity_id}</div>
                    <div 
                      className="activity-status"
                      style={{ backgroundColor: getStatusColor(activity.status) }}
                    >
                      {getStatusLabel(activity.status)}
                    </div>
                  </div>
                  
                  <div className="activity-goal">
                    <strong>Goal:</strong> {activity.goal}
                  </div>

                  {activity.description && (
                    <div className="activity-description">
                      {activity.description}
                    </div>
                  )}

                  {activity.depends_on && activity.depends_on.length > 0 && (
                    <div className="activity-deps">
                      <strong>Depends on:</strong> {activity.depends_on.join(', ')}
                    </div>
                  )}

                  {activity.assigned_agents && activity.assigned_agents.length > 0 && (
                    <div className="activity-agents">
                      <strong>Assigned:</strong>{' '}
                      {activity.assigned_agents.map(a => a.agent_name).join(', ')}
                    </div>
                  )}

                  {selectedActivity === id && (
                    <div className="activity-actions">
                      <select
                        onChange={(e) => handleStatusChange(id, e.target.value)}
                        value={activity.status}
                        onClick={(e) => e.stopPropagation()}
                      >
                        <option value="proposed">Proposed</option>
                        <option value="in_progress">In Progress</option>
                        <option value="goal_met">Goal Met</option>
                        <option value="blocked">Blocked</option>
                        <option value="revisit">Revisit</option>
                      </select>
                      <button
                        className="select-participants-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleSelectParticipants(id);
                        }}
                        disabled={selectionLoading}
                      >
                        {selectionLoading ? '🔍 Selecting...' : '🤖 Select Participants'}
                      </button>
                      {activity.assigned_agents && activity.assigned_agents.length > 0 && (
                        <>
                          {activity.status === 'proposed' && (
                            <button
                              className="start-facilitation-btn"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleStartFacilitation(id);
                              }}
                              disabled={facilitationLoading}
                            >
                              {facilitationLoading ? '⏳ Starting...' : '🚀 Start Facilitation'}
                            </button>
                          )}
                          {activity.exchanges && activity.exchanges.length > 0 && (
                            <button
                              className="view-conversation-btn"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleViewConversation(id);
                              }}
                              disabled={facilitationLoading}
                            >
                              💬 View Conversation ({activity.exchanges.length})
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Coordinating Team Dashboard */}
          <div className="coordinating-dashboard-section">
            <div className="section-header">
              <h3>🎯 Coordinating Team Dashboard</h3>
              <div className="dashboard-actions">
                <button onClick={handleCheckConsistency} disabled={dashboardLoading} className="dashboard-btn consistency">
                  🔍 Check Consistency
                </button>
                <button onClick={handleGenerateProgressReport} disabled={dashboardLoading} className="dashboard-btn progress">
                  📊 Generate Progress Report
                </button>
                <button onClick={handleSynthesizeResults} disabled={dashboardLoading} className="dashboard-btn synthesis">
                  📝 Synthesize Results
                </button>
                <button onClick={loadCoordinatingDashboard} disabled={dashboardLoading} className="dashboard-btn view">
                  👁️ {showDashboard ? 'Refresh' : 'View'} Dashboard
                </button>
              </div>
            </div>

            {showDashboard && (
              <div className="dashboard-content">
                {latestReport && (
                  <div className="dashboard-card progress-report">
                    <h4>📊 Latest Progress Report</h4>
                    <div className="report-summary">
                      <strong>Executive Summary:</strong>
                      <p>{latestReport.executive_summary}</p>
                    </div>
                    {latestReport.overall_health && (
                      <div className={`health-indicator ${latestReport.overall_health}`}>
                        Status: {latestReport.overall_health?.replace('_', ' ').toUpperCase()}
                      </div>
                    )}
                    {latestReport.completion_estimate && (
                      <div className="completion-estimate">
                        Completion: {latestReport.completion_estimate}
                      </div>
                    )}
                    {latestReport.blockers && latestReport.blockers.length > 0 && (
                      <div className="blockers-list">
                        <strong>⚠️ Blockers:</strong>
                        {latestReport.blockers.map((blocker, i) => (
                          <div key={i} className={`blocker-item severity-${blocker.severity}`}>
                            <span className="blocker-activity">{blocker.activity_id}:</span> {blocker.blocker}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {latestDeliverable && (
                  <div className="dashboard-card deliverable">
                    <h4>📝 Final Deliverable</h4>
                    {latestDeliverable.deliverable && (
                      <>
                        <div className="deliverable-title">
                          <strong>{latestDeliverable.deliverable.title}</strong>
                        </div>
                        <div className="deliverable-summary">
                          {latestDeliverable.deliverable.executive_summary}
                        </div>
                        {latestDeliverable.deliverable.key_findings && (
                          <div className="key-findings">
                            <strong>Key Findings:</strong>
                            <ul>
                              {latestDeliverable.deliverable.key_findings.map((finding, i) => (
                                <li key={i}>{finding}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )}

                {coordinatingEvents.length > 0 && (
                  <div className="dashboard-card events">
                    <h4>🔔 Coordinating Events ({coordinatingEvents.length})</h4>
                    <div className="events-timeline">
                      {coordinatingEvents.slice(-5).reverse().map((event, i) => (
                        <div key={i} className="event-item">
                          <div className="event-header">
                            <span className="event-type">{event.event_type}</span>
                            <span className="event-time">{new Date(event.timestamp).toLocaleString()}</span>
                          </div>
                          <div className="event-agent">{event.agent_id}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Reevaluations */}
          {processMap.reevaluations && processMap.reevaluations.length > 0 && (
            <div className="reevaluations-section">
              <h3>Process Evolution ({processMap.reevaluations.length} reevaluations)</h3>
              <div className="reevaluations-list">
                {processMap.reevaluations.map((reeval) => (
                  <div key={reeval.event_id} className="reevaluation-item">
                    <div className="reeval-header">
                      <span className="reeval-version">
                        v{reeval.previous_version} → v{reeval.new_version}
                      </span>
                      <span className="reeval-timestamp">
                        {new Date(reeval.timestamp).toLocaleString()}
                      </span>
                    </div>
                    <div className="reeval-trigger">
                      <strong>Triggered by:</strong> {reeval.triggered_by}
                    </div>
                    <div className="reeval-reasoning">
                      <strong>Reasoning:</strong> {reeval.reasoning}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* History Modal */}
      {history.length > 0 && (
        <div className="history-modal" onClick={() => setHistory([])}>
          <div className="history-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Process Map History</h3>
              <button onClick={() => setHistory([])}>✕</button>
            </div>
            <div className="history-list">
              {history.map((version) => (
                <div key={version.map_version} className="history-item">
                  <div className="history-header">
                    <strong>Version {version.map_version}</strong>
                    <span>{new Date(version.updated_at).toLocaleString()}</span>
                  </div>
                  <div>Activities: {Object.keys(version.activities).length}</div>
                  <div>Completed: {version.completed_activities.length}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Exchanges/Conversation Modal */}
      {showExchangesModal && (
        <div className="history-modal" onClick={() => setShowExchangesModal(false)}>
          <div className="history-content exchanges-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>💬 Activity Conversation</h3>
              <button onClick={() => setShowExchangesModal(false)}>✕</button>
            </div>
            
            <div className="exchanges-content">
              {exchanges.length === 0 ? (
                <div className="no-exchanges">
                  No conversation exchanges yet. Start facilitation to begin.
                </div>
              ) : (
                <div className="exchanges-list">
                  {exchanges.map((exchange, idx) => (
                    <div key={exchange.exchange_id || idx} className="exchange-item">
                      <div className="exchange-header">
                        <span className="exchange-intent">{exchange.intent}</span>
                        <span className="exchange-time">
                          {new Date(exchange.timestamp).toLocaleString()}
                        </span>
                      </div>
                      
                      <div className="exchange-flow">
                        <div className="exchange-participant from">
                          <strong>From:</strong> {exchange.from_agent || 'Unknown'}
                        </div>
                        <div className="exchange-arrow">→</div>
                        <div className="exchange-participant to">
                          <strong>To:</strong> {exchange.to_agent || 'N/A'}
                        </div>
                      </div>
                      
                      {exchange.prompt && (
                        <div className="exchange-prompt">
                          <strong>Prompt:</strong>
                          <p>{exchange.prompt}</p>
                        </div>
                      )}
                      
                      {exchange.response && (
                        <div className="exchange-response">
                          <strong>Response:</strong>
                          <p>{exchange.response}</p>
                        </div>
                      )}
                      
                      <div className="exchange-outcome">
                        <span className={`outcome-badge ${exchange.outcome}`}>
                          {exchange.outcome}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Participant Selection Modal */}
      {showSelectionModal && selectionResult && (
        <div className="history-modal" onClick={() => setShowSelectionModal(false)}>
          <div className="history-content selection-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>🤖 Agent Selector Recommendations</h3>
              <button onClick={() => setShowSelectionModal(false)}>✕</button>
            </div>
            
            <div className="selection-content">
              {selectionResult.message && (
                <div className="selection-message">
                  {selectionResult.message}
                </div>
              )}
              
              {selectionResult.recommendations ? (
                <>
                  <div className="recommendation-section">
                    <h4>Analysis Results</h4>
                    <div className="recommendation-item">
                      <strong>Required Capabilities:</strong>
                      <div className="capability-list">
                        {selectionResult.recommendations.required_capabilities?.map((cap, i) => (
                          <span key={i} className="capability-badge">{cap}</span>
                        ))}
                      </div>
                    </div>
                    {selectionResult.recommendations.domain_expertise && (
                      <div className="recommendation-item">
                        <strong>Domain Expertise:</strong> {selectionResult.recommendations.domain_expertise}
                      </div>
                    )}
                    <div className="recommendation-item">
                      <strong>Reasoning:</strong>
                      <p>{selectionResult.recommendations.reasoning}</p>
                    </div>
                  </div>
                  
                  <div className="candidates-section">
                    <h4>Recommended Agents</h4>
                    
                    {selectionResult.recommendations.recommended_primary && (
                      <div className="agent-recommendation primary">
                        <div className="recommendation-label">🏆 Primary Recommendation</div>
                        {selectionResult.candidates.find(c => c.agent_id === selectionResult.recommendations.recommended_primary) && (
                          <div className="agent-details">
                            <div className="agent-name">
                              {selectionResult.candidates.find(c => c.agent_id === selectionResult.recommendations.recommended_primary).agent_name || selectionResult.recommendations.recommended_primary}
                            </div>
                            <div className="agent-capabilities">
                              {selectionResult.candidates.find(c => c.agent_id === selectionResult.recommendations.recommended_primary).capabilities?.map((cap, i) => (
                                <span key={i} className="capability-badge">{cap}</span>
                              ))}
                            </div>
                            <button
                              className="assign-btn"
                              onClick={() => {
                                const agent = selectionResult.candidates.find(c => c.agent_id === selectionResult.recommendations.recommended_primary);
                                handleAcceptRecommendation(
                                  agent.agent_id,
                                  agent.agent_name || agent.agent_id,
                                  agent.capabilities || [],
                                  selectionResult.recommendations.reasoning
                                );
                              }}
                              disabled={selectionLoading}
                            >
                              ✅ Assign This Agent
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                    
                    {selectionResult.recommendations.recommended_backup && (
                      <div className="agent-recommendation backup">
                        <div className="recommendation-label">🔄 Backup Option</div>
                        {selectionResult.candidates.find(c => c.agent_id === selectionResult.recommendations.recommended_backup) && (
                          <div className="agent-details">
                            <div className="agent-name">
                              {selectionResult.candidates.find(c => c.agent_id === selectionResult.recommendations.recommended_backup).agent_name || selectionResult.recommendations.recommended_backup}
                            </div>
                            <div className="agent-capabilities">
                              {selectionResult.candidates.find(c => c.agent_id === selectionResult.recommendations.recommended_backup).capabilities?.map((cap, i) => (
                                <span key={i} className="capability-badge">{cap}</span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                  
                  <div className="all-candidates">
                    <h4>All Candidates ({selectionResult.candidates.length})</h4>
                    <div className="candidates-list">
                      {selectionResult.candidates.map((candidate, i) => (
                        <div key={i} className="candidate-item">
                          <div className="candidate-name">{candidate.agent_name || candidate.agent_id}</div>
                          <div className="candidate-caps">
                            {candidate.capabilities?.map((cap, j) => (
                              <span key={j} className="capability-badge small">{cap}</span>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              ) : (
                <div className="no-recommendations">
                  No candidates found matching the activity requirements.
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ProcessMapViewer;

