# Marketplace Scripts Summary

This document summarizes the startup, teardown, and seed data scripts added to the marketplace service.

---

## Scripts Created

### 1. start.sh - Resilient Startup Script ✅

**Location:** `/marketplace/start.sh`

**Features:**
- ✅ **Port Conflict Resolution:** Automatically detects and kills processes on target port
- ✅ **Resilient for Development:** Uses `kill -9` to force-stop conflicting processes
- ✅ **Dependency Checking:** Verifies Python and required packages
- ✅ **Directory Setup:** Creates necessary data and log directories
- ✅ **Environment Loading:** Loads `.env` if present
- ✅ **Service Health Check:** Tests health endpoint after startup
- ✅ **Automatic Seed Loading:** Loads seed data on first run
- ✅ **Background Execution:** Runs service as daemon with PID tracking
- ✅ **Colored Output:** User-friendly status messages
- ✅ **Logging:** Captures output to `logs/marketplace.log`

**Usage:**
```bash
cd marketplace
./start.sh
```

**Startup Flow:**
1. Check and free port 8001 (or configured port)
2. Load environment variables
3. Create data directories
4. Verify dependencies
5. Start service in background
6. Wait for initialization
7. Test health endpoint
8. Load seed data if first run
9. Display access information

**Safety Features:**
- Kills existing processes on port before starting
- Validates service actually started
- Saves PID for later shutdown
- Comprehensive error messages

---

### 2. stop.sh - Graceful Teardown Script ✅

**Location:** `/marketplace/stop.sh`

**Features:**
- ✅ **Graceful Shutdown:** Tries SIGTERM before SIGKILL
- ✅ **PID File Tracking:** Uses saved PID file
- ✅ **Port Cleanup:** Ensures port is freed
- ✅ **Multiple Attempts:** Tries graceful shutdown with 10s timeout
- ✅ **Force Kill Fallback:** Force stops if graceful fails
- ✅ **Verification:** Confirms service stopped and port free
- ✅ **Cleanup:** Removes stale PID files

**Usage:**
```bash
cd marketplace
./stop.sh
```

**Shutdown Flow:**
1. Find service PID from file
2. Send SIGTERM (graceful)
3. Wait up to 10 seconds
4. Send SIGKILL if still running (force)
5. Check for processes on port
6. Kill any remaining processes
7. Verify port is free
8. Remove PID file

---

### 3. load_seed_data.sh - Initial Data Loader ✅

**Location:** `/marketplace/scripts/load_seed_data.sh`

**Features:**
- ✅ **Idempotent:** Safe to run multiple times (checks `.seeded` flag)
- ✅ **JSON Validation:** Validates seed data before loading
- ✅ **Timestamp Addition:** Adds `created_at` and `updated_at` if missing
- ✅ **Default Values:** Sets performance metrics to defaults
- ✅ **Metadata Generation:** Creates collection metadata
- ✅ **Python Integration:** Uses Python for JSON parsing
- ✅ **Error Handling:** Validates and reports errors

**Usage:**
```bash
cd marketplace
./scripts/load_seed_data.sh
```

**What It Loads:**
- 5 Coordinating Agents
- 2 Specialized Agents (Content Writer, Research)
- 0 Tools (Phase 1)
- Collection metadata

**Behavior:**
- Skips if `.seeded` flag exists
- Parses `seed_data/agents.json` and `seed_data/tools.json`
- Creates one file per agent/tool in data directory
- Marks as seeded to prevent reloading

---

### 4. refresh_seed_data.sh - Data Reset Script ✅

**Location:** `/marketplace/scripts/refresh_seed_data.sh`

**Features:**
- ✅ **Confirmation Prompt:** Requires explicit "yes" to proceed
- ✅ **Complete Cleanup:** Removes all existing data
- ✅ **Reload:** Calls `load_seed_data.sh` after cleanup
- ✅ **Statistics:** Shows count of loaded items
- ✅ **Service Detection:** Checks if service is running
- ✅ **User Guidance:** Prompts to restart service

**Usage:**
```bash
cd marketplace
./scripts/refresh_seed_data.sh
```

**⚠️ Warning:** Deletes ALL custom agents, tools, and access rules!

**Confirmation Required:**
```
This will DELETE all existing marketplace data and reload seed data.
Are you sure you want to continue? (yes/no): yes
```

**Use Cases:**
- Reset to initial state
- Test with fresh data
- Apply updated seed data
- Recover from corruption

---

## Seed Data Files Created

### 1. agents.json ✅

**Location:** `/marketplace/seed_data/agents.json`

**Contents:**
- 5 Coordinating Agents (Goal Decomposer, Team Assembler, Execution Coordinator, Progress Tracker, Result Synthesizer)
- 2 Specialized Agents (Content Writer, Research Agent)

**Format:** JSON array of complete agent documents

---

### 2. tools.json ✅

**Location:** `/marketplace/seed_data/tools.json`

**Contents:** Empty array `[]` (no tools in Phase 1)

---

### 3. Seed Data README ✅

**Location:** `/marketplace/seed_data/README.md`

**Contents:**
- Description of seed files
- Document structure examples
- Loading instructions
- Modification guide
- Troubleshooting

---

## Configuration Files Created

### 1. ENV_TEMPLATE.md ✅

**Location:** `/marketplace/ENV_TEMPLATE.md`

**Contents:**
- Complete environment variable template
- Configuration guide
- Backend-specific settings
- Security notes
- Setup instructions

**Variables Defined:**
- Service config (port, host, log level)
- Storage backend selection
- Filesystem backend settings
- Future DynamoDB settings
- Future S3 settings
- API configuration (CORS, version, page size)
- Future authentication settings

---

### 2. .gitignore ✅

**Location:** `/marketplace/.gitignore`

**Ignores:**
- `.env` files
- `data/` directory
- `logs/` directory
- PID files
- Python cache
- Virtual environments
- IDE files
- OS files

---

## Documentation Created

### 1. Scripts README ✅

**Location:** `/marketplace/scripts/README.md`

**Contents:**
- Script descriptions
- Usage instructions
- Requirements
- Execution flow diagrams
- Troubleshooting guide
- Exit codes
- Safety features
- Future scripts planned

---

## Key Features

### Port Conflict Resolution (start.sh)

**As Requested:** Resilient startup that kills existing services on port

```bash
# Automatically detects processes on port 8001
if lsof -Pi :8001 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "Port 8001 is already in use"
    PIDS=$(lsof -Pi :8001 -sTCP:LISTEN -t)
    
    # Kill all processes on the port
    for PID in $PIDS; do
        kill -9 $PID
    done
    
    # Verify port is free
    sleep 2
fi
```

**Development-Friendly:**
- No manual port cleanup needed
- Fast iteration during development
- Clear messages about what's being killed
- Automatic retry after cleanup

**Future Enhancement:**
- Add `--force` flag to control this behavior
- Add `--preserve` flag to fail if port in use
- Currently always kills (development mode)

---

### Graceful Shutdown (stop.sh)

**Shutdown Strategy:**
1. Try SIGTERM (allows cleanup)
2. Wait up to 10 seconds
3. Force with SIGKILL if needed
4. Clean up port and files

**Verification:**
- Confirms process stopped
- Confirms port freed
- Removes stale PID files
- Reports any issues

---

### Idempotent Seed Loading

**Smart Loading:**
- Checks for `.seeded` flag file
- Skips if already loaded
- Won't duplicate data
- Safe for startup scripts

**Flag Location:** `data/marketplace/agents/.seeded`

**Reset Required:** Use `refresh_seed_data.sh` to reload

---

## Usage Examples

### First Time Setup

```bash
cd marketplace

# Service starts and loads seed data automatically
./start.sh

# Service running with 7 agents loaded
```

---

### Development Iteration

```bash
# Make changes to code

# Restart service (handles port conflicts)
./stop.sh
./start.sh

# Service restarts cleanly
```

---

### Reset to Initial State

```bash
cd marketplace

# Clear and reload seed data
./scripts/refresh_seed_data.sh
# Confirms: Are you sure? (yes/no): yes

# Restart service
./stop.sh && ./start.sh
```

---

### Update Seed Data

```bash
# Edit seed data
vim seed_data/agents.json

# Reload
./scripts/refresh_seed_data.sh

# Restart
./stop.sh && ./start.sh
```

---

## Testing the Scripts

### Test Startup

```bash
cd marketplace
./start.sh

# Should see:
# ✓ Port 8001 is available
# ✓ Dependencies are installed
# ✓ Service started successfully
# ✓ Health check passed
# → Loading seed data...
# ✓ Seed Data Loaded
# Agents: 7
```

---

### Test Port Conflict

```bash
# Start service
./start.sh

# Try starting again (without stopping)
./start.sh

# Should see:
# ✗ Port 8001 is already in use
# → Killing existing processes: [PID]
# ✓ Port 8001 is now free
# ✓ Service started successfully
```

---

### Test Graceful Shutdown

```bash
./stop.sh

# Should see:
# → Found PID file: [PID]
# → Stopping process [PID]...
# ✓ Process [PID] stopped
# ✓ Port 8001 is free
```

---

### Test Seed Refresh

```bash
./scripts/refresh_seed_data.sh

# Should see:
# ⚠ This will DELETE all existing marketplace data
# Are you sure? (yes/no): yes
# → Clearing existing data...
# ✓ Existing data cleared
# → Loading seed data...
# ✓ Seed Data Refreshed
# Agents: 7
```

---

## File Permissions

All scripts are executable:
```bash
chmod +x start.sh stop.sh scripts/*.sh
```

This was done automatically during creation.

---

## Environment Variables

Scripts respect these variables:
- `MARKETPLACE_PORT`: Service port (default 8001)
- `MARKETPLACE_HOST`: Bind address (default 0.0.0.0)
- `LOG_LEVEL`: Logging verbosity (default INFO)
- `STORAGE_BACKEND`: Backend type (default filesystem)
- `STORAGE_PATH`: Data directory (default ./data/marketplace)

Load from `.env`:
```bash
# Scripts automatically source .env if present
cp ENV_TEMPLATE.md .env
# Edit .env
./start.sh  # Uses settings from .env
```

---

## Logging

**Log Location:** `logs/marketplace.log`

**View Logs:**
```bash
tail -f logs/marketplace.log
```

**Log Contents:**
- Service startup messages
- API requests and responses
- Errors and warnings
- Seed data loading progress

---

## PID Management

**PID File:** `.marketplace.pid`

**Contents:** Process ID of running service

**Usage:**
- Created by `start.sh`
- Used by `stop.sh` to find process
- Automatically cleaned up on stop
- Removed if stale

**Manual Stop:**
```bash
kill $(cat .marketplace.pid)
```

---

## Directory Structure After Setup

```
marketplace/
├── start.sh              ✅ Executable
├── stop.sh               ✅ Executable
├── ENV_TEMPLATE.md       ✅ Configuration guide
├── .gitignore           ✅ Ignore patterns
├── .marketplace.pid      (created at runtime)
├── scripts/
│   ├── load_seed_data.sh        ✅ Executable
│   ├── refresh_seed_data.sh     ✅ Executable
│   └── README.md                ✅ Documentation
├── seed_data/
│   ├── agents.json      ✅ 7 agents
│   ├── tools.json       ✅ Empty array
│   └── README.md        ✅ Documentation
├── data/                (created at runtime)
│   └── marketplace/
│       ├── agents/      (7 .json files after seeding)
│       ├── tools/       (empty after seeding)
│       ├── access_control/
│       └── _metadata/
└── logs/                (created at runtime)
    └── marketplace.log
```

---

## Summary

✅ **All Requirements Met:**
- Startup script that kills existing services on port ✅
- Teardown/stop script for graceful shutdown ✅
- Seed data loading script (idempotent) ✅
- Seed data refresh script (full reset) ✅
- Actual seed data files (7 agents) ✅
- Environment configuration template ✅
- Comprehensive documentation ✅

✅ **Development-Friendly:**
- No manual port cleanup needed
- Fast iteration with automatic restart
- Clear, colored status messages
- Comprehensive error handling

✅ **Production-Ready Design:**
- Graceful shutdown before force kill
- PID file tracking
- Log file management
- Environment variable support

✅ **Safe and Robust:**
- Confirmation prompts for destructive operations
- Idempotent operations
- Comprehensive validation
- Clear error messages

**Ready for use in development!**

