import { useState, useEffect } from 'react';
import { getComputeLogs, getMarketplaceLogs } from '../api';
import './LogsModal.css';

function LogsModal({ instanceId, instanceName, instanceType, onClose }) {
  const [logs, setLogs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lineCount, setLineCount] = useState(100);
  const [autoRefresh, setAutoRefresh] = useState(false);

  const loadLogs = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const data = instanceType === 'compute' 
        ? await getComputeLogs(instanceId, lineCount)
        : await getMarketplaceLogs(instanceId, lineCount);
      
      setLogs(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLogs();
  }, [instanceId, instanceType, lineCount]);

  useEffect(() => {
    if (autoRefresh) {
      const interval = setInterval(loadLogs, 5000);
      return () => clearInterval(interval);
    }
  }, [autoRefresh, instanceId, instanceType, lineCount]);

  const handleCopyLogs = () => {
    if (logs?.lines) {
      navigator.clipboard.writeText(logs.lines.join('\n'));
      alert('Logs copied to clipboard!');
    }
  };

  const handleDownloadLogs = () => {
    if (logs?.lines) {
      const blob = new Blob([logs.lines.join('\n')], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${instanceId}-logs.txt`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
  };

  return (
    <div className="logs-modal-overlay" onClick={onClose}>
      <div className="logs-modal" onClick={(e) => e.stopPropagation()}>
        <div className="logs-modal-header">
          <div className="logs-modal-title">
            <h2>📋 Logs: {instanceName}</h2>
            <span className="logs-instance-type">{instanceType}</span>
          </div>
          <button className="logs-modal-close" onClick={onClose}>×</button>
        </div>

        <div className="logs-modal-controls">
          <div className="logs-control-group">
            <label>Lines:</label>
            <select value={lineCount} onChange={(e) => setLineCount(parseInt(e.target.value))}>
              <option value="50">50</option>
              <option value="100">100</option>
              <option value="200">200</option>
              <option value="500">500</option>
              <option value="1000">1000</option>
            </select>
          </div>

          <div className="logs-control-group">
            <label>
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
              />
              Auto-refresh (5s)
            </label>
          </div>

          <div className="logs-actions">
            <button onClick={loadLogs} disabled={loading} className="logs-btn-refresh">
              🔄 Refresh
            </button>
            <button onClick={handleCopyLogs} disabled={!logs} className="logs-btn-copy">
              📋 Copy
            </button>
            <button onClick={handleDownloadLogs} disabled={!logs} className="logs-btn-download">
              ⬇️ Download
            </button>
          </div>
        </div>

        {logs && (
          <div className="logs-info">
            <span>Showing {logs.lines.length} of {logs.total_lines} lines</span>
            <span className="logs-file-path">{logs.log_file}</span>
          </div>
        )}

        <div className="logs-modal-content">
          {loading && <div className="logs-loading">Loading logs...</div>}
          
          {error && (
            <div className="logs-error">
              <h3>Error Loading Logs</h3>
              <p>{error}</p>
              <button onClick={loadLogs}>Retry</button>
            </div>
          )}
          
          {logs && !loading && !error && (
            <div className="logs-viewer">
              {logs.lines.length === 0 ? (
                <div className="logs-empty">No logs available</div>
              ) : (
                <pre className="logs-content">
                  {logs.lines.map((line, index) => (
                    <div key={index} className="log-line">
                      <span className="log-line-number">{logs.total_lines - logs.lines.length + index + 1}</span>
                      <span className="log-line-content">{line}</span>
                    </div>
                  ))}
                </pre>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default LogsModal;

