import { useState, useEffect } from 'react';
import { getAggregatedCapabilities, submitTask, runDemoBusinessProcess } from '../api';
import './TaskSubmission.css';

function TaskSubmission() {
  const [capabilities, setCapabilities] = useState(null);
  const [selectedAgent, setSelectedAgent] = useState('');
  const [prompt, setPrompt] = useState('');
  const [outputFormat, setOutputFormat] = useState('markdown');
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [showDemo, setShowDemo] = useState(false);

  useEffect(() => {
    loadCapabilities();
  }, []);

  const loadCapabilities = async () => {
    try {
      setLoading(true);
      const data = await getAggregatedCapabilities();
      setCapabilities(data);
      
      // Set first agent as default
      // agents is a dict, so get the keys
      if (data.agents && Object.keys(data.agents).length > 0) {
        setSelectedAgent(Object.keys(data.agents)[0]);
      }
      
      setError(null);
    } catch (err) {
      setError(`Failed to load agents: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!selectedAgent || !prompt.trim()) {
      setError('Please select an agent and enter a prompt');
      return;
    }

    try {
      setSubmitting(true);
      setError(null);
      setResult(null);

      const taskRequest = {
        agent_id: selectedAgent,
        prompt: prompt.trim(),
        output_format: outputFormat,
        context: {
          submitted_from: 'ui',
          timestamp: new Date().toISOString()
        }
      };

      const response = await submitTask(taskRequest);
      setResult(response);
    } catch (err) {
      setError(`Task submission failed: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDemoProcess = async () => {
    try {
      setSubmitting(true);
      setError(null);
      setResult(null);

      const response = await runDemoBusinessProcess();
      setResult(response);
      setShowDemo(true);
    } catch (err) {
      setError(`Demo process failed: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const loadExamplePrompt = (type) => {
    const examples = {
      math: "Calculate the compound interest for a $10,000 investment at 5% annual rate compounded monthly for 3 years. Show your work step by step.",
      analysis: `Analyze this sales data and provide insights:

Region | Product | Q1 Sales | Q2 Sales | Q3 Sales | Q4 Sales
-------|---------|----------|----------|----------|----------
North  | Widget A| $45000   | $52000   | $48000   | $61000
North  | Widget B| $32000   | $35000   | $38000   | $42000
South  | Widget A| $38000   | $41000   | $39000   | $47000
South  | Widget B| $28000   | $30000   | $33000   | $36000

Provide:
1. Total sales by region
2. Best performing product
3. Growth trends
4. Recommendations`,
      content: "Write a professional email announcing a new AI-powered workflow automation platform to potential enterprise customers. Highlight benefits like cost savings, efficiency gains, and seamless integration. Target audience: CTOs and IT Directors.",
      planning: `Plan a comprehensive project for developing a new mobile app with the following requirements:
- User authentication and profiles
- Real-time messaging
- Push notifications
- Data analytics dashboard
- Cloud storage integration

Provide a step-by-step project plan with timelines and resource requirements.`
    };

    setPrompt(examples[type] || '');
    
    // Set appropriate agent
    if (type === 'analysis' && capabilities?.agents?.includes('data-analyst-v1')) {
      setSelectedAgent('data-analyst-v1');
    } else if (type === 'content' && capabilities?.agents?.includes('content-writer-v1')) {
      setSelectedAgent('content-writer-v1');
    } else if (type === 'planning' && capabilities?.agents?.includes('task-coordinator-v1')) {
      setSelectedAgent('task-coordinator-v1');
    }
  };

  const clearForm = () => {
    setPrompt('');
    setResult(null);
    setError(null);
    setShowDemo(false);
  };

  if (loading) {
    return <div className="task-submission loading">Loading agents...</div>;
  }

  return (
    <div className="task-submission">
      <h1>🤖 AI Task Submission</h1>
      
      <div className="task-info">
        <p>Submit tasks to AI agents for processing. Choose from available agents and provide your prompt.</p>
        {capabilities && (
          <div className="capabilities-summary">
            <strong>{capabilities.agents?.length || 0}</strong> agents available
            {' | '}
            <strong>{capabilities.tools?.length || 0}</strong> tools available
          </div>
        )}
      </div>

      {error && (
        <div className="error-message">
          <strong>Error:</strong> {error}
        </div>
      )}

      <div className="task-form-container">
        <form onSubmit={handleSubmit} className="task-form">
          <div className="form-group">
            <label htmlFor="agent-select">Select Agent:</label>
            <select
              id="agent-select"
              value={selectedAgent}
              onChange={(e) => setSelectedAgent(e.target.value)}
              disabled={submitting}
            >
              {capabilities?.agents && Object.keys(capabilities.agents).map(agent => (
                <option key={agent} value={agent}>{agent}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="prompt-input">Prompt:</label>
            <textarea
              id="prompt-input"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Enter your task prompt here..."
              rows="10"
              disabled={submitting}
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="format-select">Output Format:</label>
            <select
              id="format-select"
              value={outputFormat}
              onChange={(e) => setOutputFormat(e.target.value)}
              disabled={submitting}
            >
              <option value="text">Text</option>
              <option value="markdown">Markdown</option>
              <option value="json">JSON</option>
            </select>
          </div>

          <div className="form-actions">
            <button type="submit" disabled={submitting || !selectedAgent || !prompt.trim()}>
              {submitting ? '⏳ Submitting...' : '🚀 Submit Task'}
            </button>
            <button type="button" onClick={clearForm} disabled={submitting}>
              🗑️ Clear
            </button>
          </div>
        </form>

        <div className="examples-section">
          <h3>📝 Example Prompts</h3>
          <div className="example-buttons">
            <button onClick={() => loadExamplePrompt('math')} disabled={submitting}>
              💰 Financial Calculation
            </button>
            <button onClick={() => loadExamplePrompt('analysis')} disabled={submitting}>
              📊 Data Analysis
            </button>
            <button onClick={() => loadExamplePrompt('content')} disabled={submitting}>
              ✍️ Content Generation
            </button>
            <button onClick={() => loadExamplePrompt('planning')} disabled={submitting}>
              📋 Project Planning
            </button>
          </div>

          <div className="demo-section">
            <h3>🎬 Demo Workflows</h3>
            <button 
              className="demo-button"
              onClick={handleDemoProcess} 
              disabled={submitting}
            >
              {submitting ? '⏳ Running Demo...' : '▶️ Run Multi-Agent Business Process'}
            </button>
            <p className="demo-description">
              Runs a complete 3-step workflow: Task Planning → Data Analysis → Report Generation
            </p>
          </div>
        </div>
      </div>

      {result && (
        <div className="result-container">
          <h2>📤 Task Result</h2>
          
          {showDemo ? (
            // Demo business process result
            <div className="demo-result">
              <div className="result-metadata">
                <div className="meta-item">
                  <strong>Process:</strong> {result.process}
                </div>
                <div className="meta-item">
                  <strong>Status:</strong> <span className="status-badge">{result.status}</span>
                </div>
                <div className="meta-item">
                  <strong>Steps Completed:</strong> {result.summary?.successful_steps || 0} / {result.summary?.total_steps || 0}
                </div>
              </div>

              {result.steps && result.steps.map((step, index) => (
                <div key={index} className="step-result">
                  <h3>Step {step.step}: {step.agent}</h3>
                  <div className="step-info">
                    <span className="task-id">Task ID: {step.task_id}</span>
                    <span className={`status-badge ${step.status}`}>{step.status}</span>
                  </div>
                  {step.output && (
                    <div className="step-output">
                      <h4>Output:</h4>
                      <pre>{JSON.stringify(step.output, null, 2)}</pre>
                    </div>
                  )}
                </div>
              ))}

              {result.summary && (
                <div className="summary-section">
                  <h3>Summary</h3>
                  <pre>{JSON.stringify(result.summary, null, 2)}</pre>
                </div>
              )}
            </div>
          ) : (
            // Single task result
            <div className="single-task-result">
              <div className="result-metadata">
                <div className="meta-item">
                  <strong>Task ID:</strong> {result.task_id}
                </div>
                <div className="meta-item">
                  <strong>Agent:</strong> {result.agent_id}
                </div>
                <div className="meta-item">
                  <strong>Status:</strong> <span className={`status-badge ${result.status}`}>{result.status}</span>
                </div>
                <div className="meta-item">
                  <strong>Compute Instance:</strong> {result.compute_instance_id}
                </div>
              </div>

              {result.output && (
                <div className="task-output">
                  <h3>Output:</h3>
                  {typeof result.output === 'string' ? (
                    <pre className="output-text">{result.output}</pre>
                  ) : (
                    <pre className="output-json">{JSON.stringify(result.output, null, 2)}</pre>
                  )}
                </div>
              )}

              {result.error && (
                <div className="error-section">
                  <h3>Error:</h3>
                  <pre className="error-text">{result.error}</pre>
                </div>
              )}

              {result.metadata && Object.keys(result.metadata).length > 0 && (
                <div className="metadata-section">
                  <h3>Metadata:</h3>
                  <pre>{JSON.stringify(result.metadata, null, 2)}</pre>
                </div>
              )}

              {result.agent_definition && (
                <div className="agent-info">
                  <h3>Agent Details:</h3>
                  <pre>{JSON.stringify(result.agent_definition, null, 2)}</pre>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default TaskSubmission;
