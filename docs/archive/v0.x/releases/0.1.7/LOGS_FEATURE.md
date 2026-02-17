# Log Viewing Feature - Release 0.1.7

## Overview

Added comprehensive log viewing functionality to the serving UI, allowing users to view logs from both compute instances and marketplace instances directly from the dashboard.

## Features

### 1. Backend API Endpoints

#### Compute Service
- **Endpoint**: `GET /logs`
- **Parameters**: `lines` (default: 100, max: 1000)
- **Returns**: Last N lines from compute service log file
- **File**: `/Users/mlyons/Development/claudevn/compute/api/logs.py`

#### Marketplace Service
- **Endpoint**: `GET /api/v1/logs`
- **Parameters**: `lines` (default: 100, max: 1000)
- **Returns**: Last N lines from marketplace service log file
- **File**: `/Users/mlyons/Development/claudevn/marketplace/api/logs.py`

#### Serving Service (Proxy)
- **Compute Logs**: `GET /api/v1/logs/compute/{instance_id}`
- **Marketplace Logs**: `GET /api/v1/logs/marketplace/{marketplace_id}`
- **Parameters**: `lines` (default: 100, max: 1000)
- **Returns**: Proxied logs from the respective instance
- **File**: `/Users/mlyons/Development/claudevn/serving/api/logs.py`

### 2. Frontend Components

#### LogsModal Component
A beautiful, feature-rich modal for displaying logs:

**Features**:
- View last 50-1000 lines of logs
- Auto-refresh capability (5-second intervals)
- Copy logs to clipboard
- Download logs as text file
- Syntax-highlighted log viewer with dark theme
- Line numbers for easy reference
- Real-time log information (showing X of Y lines)

**File**: `/Users/mlyons/Development/claudevn/serving/frontend/src/components/LogsModal.jsx`

#### Integration Points

1. **ComputeRegistry Component**
   - Added "View Logs" button to instance details panel
   - File: `/Users/mlyons/Development/claudevn/serving/frontend/src/components/ComputeRegistry.jsx`

2. **Dashboard Component**
   - Added "View Logs" button to compute instance cards
   - Added "View Logs" button to marketplace cards
   - File: `/Users/mlyons/Development/claudevn/serving/frontend/src/components/Dashboard.jsx`

### 3. API Client Functions

Added two new API functions to `serving/frontend/src/api.js`:
- `getComputeLogs(instanceId, lines)` - Fetch logs from a compute instance
- `getMarketplaceLogs(marketplaceId, lines)` - Fetch logs from a marketplace instance

## User Workflow

1. **From Dashboard or ComputeRegistry**: Click on any registered compute instance or marketplace
2. Click the **"📋 View Logs"** button
3. A modal opens displaying the last 100 lines of logs (default)
4. **Adjust view**: Change the number of lines (50, 100, 200, 500, 1000)
5. **Auto-refresh**: Enable auto-refresh to see new logs every 5 seconds
6. **Actions**:
   - 🔄 Refresh: Manually refresh logs
   - 📋 Copy: Copy all visible logs to clipboard
   - ⬇️ Download: Download logs as a text file

## Technical Details

### Log File Locations

**Compute Service**:
- Default (local): `./logs/compute.log`
- Docker: `/app/logs/compute.log`
- Configurable via `COMPUTE_LOG_FILE` environment variable

**Marketplace Service**:
- Default (local): `./logs/marketplace.log`
- Docker: `/app/logs/marketplace.log`
- Configurable via `MARKETPLACE_LOG_FILE` environment variable

**Note**: In Docker deployments, logs are written to both stdout (for `docker logs` command) and to log files (for the API endpoint).

### Log Retrieval Mechanism

The system uses a **pull-based approach**:
1. Serving UI makes a request to serving API
2. Serving API proxies the request to the target compute/marketplace instance
3. Compute/Marketplace reads the last N lines from its local log file
4. Logs are returned through the chain back to the UI
5. No streaming - one-time retrieval (as requested)

### Error Handling

- **404**: Log file not found or endpoint not available
- **503**: Instance is offline or unreachable
- **500**: Unexpected error reading log file

The UI displays friendly error messages and provides retry options.

## Styling

- Dark theme log viewer (VS Code-inspired)
- Responsive design
- Beautiful gradient buttons
- Smooth animations and transitions
- Line number gutter for easy reference
- Syntax highlighting for log levels (ERROR, WARNING, INFO, DEBUG)

## Testing Checklist

To test the feature:

1. **Start all services**:
   ```bash
   ./start_all.sh
   ```

2. **Open serving UI**: http://localhost:8002

3. **Test Compute Logs**:
   - Go to Dashboard or ComputeRegistry
   - Click on a registered compute instance
   - Click "View Logs" button
   - Verify logs are displayed
   - Test line count selector (50, 100, 200, 500, 1000)
   - Test auto-refresh toggle
   - Test copy and download buttons

4. **Test Marketplace Logs**:
   - Go to Dashboard
   - Find a registered marketplace
   - Click "View Logs" button
   - Verify logs are displayed
   - Test all features as above

5. **Test Error Cases**:
   - Stop a compute instance
   - Try to view its logs (should show offline error)
   - Restart and verify it works again

## Files Modified/Created

### Backend
- ✅ Created: `compute/api/logs.py`
- ✅ Modified: `compute/app.py` (added logs router)
- ✅ Created: `marketplace/api/logs.py`
- ✅ Modified: `marketplace/app.py` (added logs router)
- ✅ Created: `serving/api/logs.py`
- ✅ Modified: `serving/app.py` (added logs router)

### Frontend
- ✅ Created: `serving/frontend/src/components/LogsModal.jsx`
- ✅ Created: `serving/frontend/src/components/LogsModal.css`
- ✅ Modified: `serving/frontend/src/api.js` (added log API functions)
- ✅ Modified: `serving/frontend/src/components/ComputeRegistry.jsx`
- ✅ Modified: `serving/frontend/src/components/ComputeRegistry.css`
- ✅ Modified: `serving/frontend/src/components/Dashboard.jsx`
- ✅ Modified: `serving/frontend/src/components/Dashboard.css`

## Future Enhancements

Potential improvements for future releases:
- Real-time log streaming (WebSocket-based)
- Log filtering by level (ERROR, WARNING, INFO, DEBUG)
- Search/grep functionality within logs
- Log level highlighting
- Export to different formats (JSON, CSV)
- Historical log retrieval (older log files)
- Log aggregation across multiple instances

## Dependencies

No new dependencies were added. The implementation uses:
- FastAPI (existing)
- httpx (existing in serving)
- React hooks (existing)
- Standard Python file I/O

## Performance Considerations

- Log files are read from disk on each request (acceptable for non-streaming use case)
- Maximum 1000 lines per request to prevent memory issues
- Timeout of 30 seconds for proxy requests
- Frontend implements debouncing for rapid line count changes

## Security Considerations

- Log files are read with error handling for security (errors='replace')
- No sensitive data should be logged (responsibility of each service)
- Logs are only accessible via authenticated API calls (future: add authentication)
- No arbitrary file access - only configured log files are readable

## Conclusion

This feature provides a convenient way for operators and developers to troubleshoot issues by viewing logs directly from the serving UI without needing SSH access to containers or servers. The last 100 lines is typically sufficient for immediate troubleshooting, with the option to view up to 1000 lines for deeper investigation.

