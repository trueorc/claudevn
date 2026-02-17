# Release 0.1.2 - Frontend Integration

**Release Date:** November 21, 2025

## Overview

This release integrates the ClaudeVN Marketplace frontend into the backend service, providing a seamless single-port experience and correcting the platform branding throughout the codebase.

## Major Changes

### 1. Frontend Integration
- **Integrated React frontend into FastAPI backend**
  - Frontend now served at http://localhost:8001
  - Single-port deployment (frontend + API)
  - Automatic frontend building during service startup
  - SPA routing support for React Router

### 2. Branding Correction
- **Corrected spelling throughout codebase**
  - Changed "ClaudeVNh" → "ClaudeVN" (49 files updated)
  - Updated all user-facing titles and headers
  - Fixed documentation, scripts, and source code

### 3. Documentation Reorganization
- **New structured documentation system**
  - Organized docs into logical categories
  - Version-specific change docs in `releases/` folder
  - Evergreen documentation in topic-specific folders
  - Clear separation of concerns

## Features Added

### Frontend Build Automation
- `start_all.sh` now builds frontend automatically
- `marketplace/start.sh` includes frontend building
- New `marketplace/build_frontend.sh` for manual builds
- Graceful degradation when Node.js not available

### Documentation
- Created `FRONTEND_INTEGRATION.md` - Complete integration guide
- Created `BRANDING_CORRECTION.md` - Branding fix details
- Created `QUICK_REFERENCE.md` - Quick command reference
- Updated all READMEs with correct URLs and instructions

### Status Monitoring
- Updated `status.sh` to show frontend build status
- Displays integrated frontend URL
- Shows development mode option

## Technical Details

### Files Modified

**Backend Integration:**
- `marketplace/app.py` - Added static file serving and SPA routing
- `marketplace/main.py` - Updated service name

**Frontend:**
- `marketplace/frontend/index.html` - Corrected title
- `marketplace/frontend/src/App.jsx` - Updated header and footer
- All frontend files - Branding corrections

**Scripts:**
- `start_all.sh` - Added frontend build step
- `marketplace/start.sh` - Added frontend build step  
- `status.sh` - Added frontend status check
- New: `marketplace/build_frontend.sh`

**Documentation:**
- 49 files updated with correct "ClaudeVN" branding
- Documentation reorganized into structured folders

### Architecture Changes

#### Before
```
Frontend (port 3000) ←→ API (port 8001)
  ↓ CORS issues
  ↓ Two ports to manage
  ↓ Separate deployments
```

#### After
```
http://localhost:8001/
  ├── / → Frontend (React SPA)
  ├── /api/v1/ → API endpoints
  └── /docs → API documentation
```

## URLs

### Production (Integrated Mode)
| Resource | URL |
|----------|-----|
| Frontend UI | http://localhost:8001 |
| API | http://localhost:8001/api/v1 |
| API Docs | http://localhost:8001/docs |
| Health Check | http://localhost:8001/api/v1/health |

### Development Mode
| Resource | URL |
|----------|-----|
| Frontend Dev | http://localhost:3000 (with hot reload) |
| API | http://localhost:8001/api/v1 |

## Benefits

✅ **Single Port** - Everything at http://localhost:8001  
✅ **No CORS Issues** - Same origin for frontend and API  
✅ **Automatic Building** - Frontend builds on startup  
✅ **Graceful Fallback** - API-only mode if Node.js missing  
✅ **Production Ready** - Optimized minified builds  
✅ **Dev Friendly** - Hot reload mode still available  
✅ **Correct Branding** - ClaudeVN throughout  

## Upgrade Instructions

### From 0.1.1 to 0.1.2

1. **Pull latest changes:**
   ```bash
   git pull origin main
   ```

2. **Restart services:**
   ```bash
   ./stop_all.sh
   ./start_all.sh
   ```
   
   The frontend will build automatically on startup.

3. **Access the integrated UI:**
   - Open http://localhost:8001 in your browser
   - Frontend and API both available

4. **Optional - Development mode:**
   ```bash
   cd marketplace/frontend
   npm run dev
   # Access at http://localhost:3000 for hot reload
   ```

## Breaking Changes

None. This release is fully backward compatible.

## Known Issues

None.

## What's Next

Version 0.2.0 will include:
- Serving Component implementation
- Compute Engine implementation  
- End-to-end agent orchestration
- Cross-component integration

## Documentation

For detailed information, see:
- [FRONTEND_INTEGRATION.md](./FRONTEND_INTEGRATION.md) - Complete integration guide
- [BRANDING_CORRECTION.md](./BRANDING_CORRECTION.md) - Branding fix details
- [Quick Reference](../../../QUICK_REFERENCE.md) - Command reference

## Contributors

- Platform development and integration

---

**ClaudeVN Marketplace v0.1.2** - Agent Discovery with Integrated Frontend

