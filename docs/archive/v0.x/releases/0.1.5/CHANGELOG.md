# Changelog - v0.1.5

## UI & Navigation Changes

### Marketplace UI
- **CHANGED:** Moved "Integrations" from main navigation bar to UserMenu dropdown
  - Now accessible via: User Menu → Profile/Manage/Integrations
  - Cleaner main navigation with only "Create Agent", "Approvals", and "API Docs"
  - Better organization of administrative features

### Serving UI
- **ENHANCED:** Complete visual redesign with distinct purple theme
  - Deep purple primary color (#7c3aed) vs Marketplace's teal
  - Modern gradient header with frosted glass navigation
  - Professional layout with proper max-width containers
  - Sticky header for better navigation
  - Polished components with smooth transitions
  
- **FIXED:** Layout rendering issues
  - Removed conflicting Vite template CSS (`display: flex; place-items: center;` on body)
  - Full-width content now renders properly
  - Eliminated white space on right side of screen
  - Responsive design for all screen sizes

- **ADDED:** Marketplace registration display
  - New "Registered Marketplaces" section on dashboard
  - Stat cards showing total, healthy, degraded, offline marketplaces
  - Detailed marketplace cards with:
    - Status indicators
    - Connection endpoints
    - Capability metrics (agent count, tool count)
    - Priority levels
    - Last heartbeat timestamps
  - Empty state with helpful guidance for new installations

## Backend Changes

### Serving Component

#### New Models (`serving/models/marketplace.py`)
- `MarketplaceInstance` - Core marketplace registration data
- `MarketplaceStatus` - Enum: healthy, degraded, offline
- `MarketplaceCapabilities` - Agent count, tool count, supported protocols
- `MarketplaceRegistrationRequest` - Registration payload
- `MarketplaceRegistrationResponse` - Registration response
- `MarketplaceHeartbeatRequest` - Heartbeat payload
- `MarketplaceUpdateInstanceRequest` - Update payload
- `MarketplaceListResponse` - List response with pagination
- `MarketplaceStats` - Aggregated statistics

#### New Service (`serving/services/marketplace_registry.py`)
- `MarketplaceRegistry` - Complete marketplace lifecycle management
  - Registration with validation
  - Status tracking (healthy/degraded/offline)
  - Capability indexing
  - Health checks with configurable thresholds
  - Persistent storage integration
  - Search by capabilities
  - Aggregated statistics

#### New API Endpoints (`serving/api/marketplaces.py`)
- `POST /api/v1/marketplaces/register` - Register new marketplace
- `POST /api/v1/marketplaces/{id}/heartbeat` - Send heartbeat
- `GET /api/v1/marketplaces` - List all marketplaces
- `GET /api/v1/marketplaces/{id}` - Get marketplace details
- `GET /api/v1/marketplaces/stats` - Get aggregated statistics
- `PUT /api/v1/marketplaces/{id}` - Update marketplace
- `DELETE /api/v1/marketplaces/{id}` - Deregister marketplace

#### Updated Services
- **HealthMonitor** (`serving/services/health_monitor.py`)
  - Now monitors both compute AND marketplace instances
  - Dual registry support in constructor
  - Parallel health checks for both resource types
  - Separate logging for compute vs marketplace status changes

- **RegistryStorage** (`serving/storage/registry_storage.py`)
  - Dual storage paths: `data/serving/registry/compute` and `data/serving/registry/marketplace`
  - Separate save/load methods for each registry type:
    - `save_compute_instance()` / `load_all_compute_instances()`
    - `save_marketplace_instance()` / `load_all_marketplace_instances()`
  - Backward compatible with existing compute storage

- **Application** (`serving/app.py`)
  - Initialize both ComputeRegistry and MarketplaceRegistry on startup
  - Pass both registries to HealthMonitor
  - Include marketplace API router at `/api/v1`
  - Graceful shutdown for both registries

### Marketplace Component

#### New Client (`marketplace/utils/serving_client.py`)
- `ServingClient` - HTTP client for Serving API
  - Asynchronous registration and heartbeat
  - Automatic capability reporting
  - Error handling with retries
  - Graceful deregistration on shutdown
  - Heartbeat loop with configurable interval (30s default)

#### New API Endpoints (`marketplace/api/integrations.py`)
- `GET /api/v1/integrations/status` - Get current registration status
- `POST /api/v1/integrations/register` - Register with serving
- `POST /api/v1/integrations/heartbeat` - Send manual heartbeat
- `DELETE /api/v1/integrations/deregister` - Deregister from serving

#### Updated Services
- **Agent API** (`marketplace/api/agents.py`)
  - Added `get_agent_count()` helper for capability reporting

- **Tool API** (`marketplace/api/tools.py`)
  - Added `get_tool_count()` helper for capability reporting

- **Application** (`marketplace/app.py`)
  - Auto-registration on startup if `AUTO_REGISTER_WITH_SERVING=true`
  - Read configuration from environment:
    - `SERVING_URL` - URL of serving component
    - `AUTO_REGISTER_WITH_SERVING` - Enable/disable auto-registration
    - `MARKETPLACE_NAME` - Display name for registration
  - Start heartbeat loop as background task
  - Graceful deregistration on shutdown

## Frontend Changes

### Marketplace Frontend

#### New Component (`marketplace/frontend/src/components/Integrations.jsx`)
- Full-featured integration management UI
- Registration form with validation:
  - Serving URL (required)
  - Marketplace name
  - Priority (1-999)
  - Description
- Real-time status display:
  - Connection state (connected/disconnected/error)
  - Marketplace ID
  - Endpoint
  - Capabilities (agents, tools)
  - Last heartbeat timestamp
- Manual controls:
  - Register button
  - Send heartbeat button
  - Deregister button
- Error handling and user feedback
- Professional styling matching marketplace theme

#### Updated Components
- **App.jsx**
  - Removed Integrations link from main navigation
  - Route still exists at `/integrations`
  
- **UserMenu.jsx**
  - Added `handleIntegrationsClick()` handler
  - Added "Integrations" menu item with 🔌 icon
  - Positioned between "Manage" and "Logout"

### Serving Frontend

#### Updated Components
- **Dashboard.jsx** (`serving/frontend/src/components/Dashboard.jsx`)
  - Fetch marketplace data via API
  - Display marketplace statistics (total, healthy, degraded, offline)
  - Render marketplace cards with:
    - Status-based border colors
    - Capability metrics
    - Connection details
    - Last heartbeat info
  - Empty state for no marketplaces
  - Auto-refresh every 10 seconds
  
- **Dashboard.css** (`serving/frontend/src/components/Dashboard.css`)
  - New marketplace-specific styles
  - Status-based color coding
  - Responsive grid layouts
  - Empty state styling

- **App.css** (`serving/frontend/src/App.css`)
  - Complete redesign with purple color scheme
  - CSS variables for theming
  - Modern gradient header
  - Frosted glass navigation buttons
  - Sticky header with shadow
  - Max-width containers for content
  - Responsive breakpoints

- **index.css** (`serving/frontend/src/index.css`)
  - **CRITICAL FIX:** Removed `display: flex; place-items: center;` from body
  - Clean reset for proper layout rendering

## Configuration Changes

### New Environment File
- **Created:** `.env` in root directory
  - `SERVING_URL=http://localhost:8002`
  - `SERVING_PORT=8002`
  - `MARKETPLACE_PORT=8001`
  - `AUTO_REGISTER_WITH_SERVING=true`
  - `MARKETPLACE_NAME="ClaudeVN Marketplace"`
  - `COMPUTE_PORT=8003`
  - `LOG_LEVEL=INFO`

### Script Updates
- **start_all.sh**
  - Loads `.env` file if present
  - Builds both marketplace and serving frontends
  - Correct `PYTHONPATH` for each component
  - Displays serving endpoints in summary

## Documentation Organization

### Files Moved to `docs/development/serving/`:
- `MARKETPLACE_REGISTRATION_COMPLETE.md` (from root)
- `MARKETPLACE_UI_UPDATE.md` (from root)
- `SERVING_INTEGRATION_COMPLETE.md` (from root)
- `MARKETPLACE_REGISTRATION_PROGRESS.md` (from serving/)
- `PHASE1_COMPLETE.md` (from serving/)
- `STARTUP_FIXES.md` (from serving/)
- `UI_COMPLETE.md` (from serving/)
- `UI_IMPROVEMENTS.md` (from serving/)

### Files Moved to `docs/guides/`:
- `QUICK_REFERENCE.md` (from root)
- `QUICK_START_INTEGRATIONS.md` (from root)
- `QUICK_TEST_GUIDE.md` (from root)
- `START_HERE.md` (from root)
- `TESTING_GUIDE.md` (from root)

### New Documentation:
- `docs/releases/0.1.5/RELEASE_NOTES.md` - Comprehensive release documentation
- `docs/releases/0.1.5/CHANGELOG.md` - This file

## Bug Fixes

1. **Serving UI Layout**
   - Issue: 2/3 of screen was white, content scrunched to left
   - Cause: Vite template CSS applying `display: flex` to body
   - Fix: Removed conflicting styles from `index.css`

2. **Marketplace Auto-Registration**
   - Issue: Registration not persisting across restarts
   - Cause: Environment variables not configured
   - Fix: Created `.env` file with persistent configuration

3. **Health Monitor Integration**
   - Issue: Marketplace instances not being monitored
   - Cause: HealthMonitor only checking compute registry
   - Fix: Updated to monitor both compute and marketplace registries

## Breaking Changes

None. This release is fully backward compatible with 0.1.4.

## Deprecations

None.

## Security

No security-related changes in this release. Authentication and authorization will be added in a future release (planned for after functional completion of all core features).

## Performance

- Minimal impact: Additional API calls for marketplace registration
- Frontend auto-refresh interval: 10 seconds (configurable)
- Heartbeat interval: 30 seconds (configurable)

## Known Issues

None.

## Upgrade Path from 0.1.4

1. Pull latest code
2. Run `npm install` in both `marketplace/frontend` and `serving/frontend`
3. Create `.env` file in root (see Configuration section)
4. Run `./start_all.sh`
5. Verify marketplace appears in serving dashboard

## Dependencies

No new external dependencies. All changes use existing packages:
- `httpx` (already in marketplace requirements)
- `fastapi` and `pydantic` (already in serving requirements)

## Testing

Manual testing performed:
- ✅ End-to-end registration flow
- ✅ Heartbeat mechanism
- ✅ Status tracking and health monitoring
- ✅ UI navigation and layout
- ✅ Configuration persistence
- ✅ Graceful shutdown and deregistration

## Contributors

- Implementation: AI Assistant (Claude Sonnet 4.5)
- Design & Testing: mlyons

