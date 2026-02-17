# Phase 1 Test Guide - Process Map Foundation

## What We Built

✅ **Phase 1 Complete!**

- ProcessMap and Activity data models
- ProcessMapService for storage and versioning
- Process Maps API endpoints
- ProcessMapViewer UI component
- Integration into Serving UI

---

## Testing Phase 1

### Prerequisites

1. **Rebuild frontend:**
```bash
cd serving/frontend
npm install  # If new dependencies needed
npm run build
cd ../..
```

2. **Start all services:**
```bash
./start_all.sh
```

3. **Verify services running:**
```bash
./status.sh

# Should show:
# ✅ Serving running on port 8002
# ✅ Compute running on port 8003
# ✅ Marketplace running on port 8001
```

---

## Test Scenarios

### Scenario 1: Create Process Map via API

```bash
# 1. Create a test session first (if you don't have one)
curl -X POST http://localhost:8002/api/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"goal": "Test facilitated process"}' \
  | python3 -m json.tool

# Note the session_id from response (e.g., "sess-123")

# 2. Create process map for that session
curl -X POST http://localhost:8002/api/v1/process-maps/sessions/sess-123/map \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess-123",
    "business_goal": "Increase customer retention by 20%"
  }' \
  | python3 -m json.tool

# 3. Get the process map
curl http://localhost:8002/api/v1/process-maps/sessions/sess-123/map \
  | python3 -m json.tool
```

### Scenario 2: Add Activities via API

```bash
# Add Activity 1
curl -X POST http://localhost:8002/api/v1/process-maps/sessions/sess-123/map/activities \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Understand current customer retention metrics",
    "description": "Analyze existing data to establish baseline",
    "depends_on": []
  }' \
  | python3 -m json.tool

# Add Activity 2
curl -X POST http://localhost:8002/api/v1/process-maps/sessions/sess-123/map/activities \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Identify key retention drivers",
    "description": "Determine what influences customer retention",
    "depends_on": ["act-1"]
  }' \
  | python3 -m json.tool

# Add Activity 3
curl -X POST http://localhost:8002/api/v1/process-maps/sessions/sess-123/map/activities \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Develop improvement strategies",
    "description": "Create actionable retention improvement plan",
    "depends_on": ["act-1", "act-2"]
  }' \
  | python3 -m json.tool

# Get updated process map
curl http://localhost:8002/api/v1/process-maps/sessions/sess-123/map \
  | python3 -m json.tool
```

### Scenario 3: Test via UI

**Steps:**

1. **Open UI:**
   ```
   http://localhost:8002
   ```

2. **Navigate to Process Maps:**
   - Click "Process Maps" tab in navigation

3. **Enter Session ID:**
   - Type: `sess-123` (or your session ID)
   - Click "Load Process Map"

4. **Verify Display:**
   - ✅ Business goal shown: "Increase customer retention by 20%"
   - ✅ Map version: v1
   - ✅ Progress bar showing 0% (no activities completed yet)
   - ✅ 3 activities displayed as cards:
     - act-1: Blue (proposed)
     - act-2: Blue (proposed)
     - act-3: Blue (proposed)

5. **View Activity Details:**
   - Click on act-1 card
   - Verify:
     - Goal displayed
     - Description shown
     - Dependencies: none
     - Status dropdown appears

6. **Change Activity Status:**
   - With act-1 selected, change status to "In Progress"
   - Click away and reload page
   - Verify:
     - act-1 now shows Orange (in_progress)
     - Progress bar updates

7. **Add Activity via UI:**
   - Click "+ Add Activity" button
   - Fill in:
     - Goal: "Test new activity"
     - Description: "Testing UI add functionality"
     - Dependencies: (leave empty)
   - Click "Add Activity"
   - Verify new activity appears

8. **View Progress:**
   - Check progress bar updates as you change statuses
   - Statistics update (Completed, In Progress, etc.)

### Scenario 4: Test Status Changes

```bash
# Change activity to in_progress
curl -X PUT http://localhost:8002/api/v1/process-maps/sessions/sess-123/activities/act-1/status \
  -H "Content-Type: application/json" \
  -d '{"status": "in_progress"}' \
  | python3 -m json.tool

# Change activity to goal_met
curl -X PUT http://localhost:8002/api/v1/process-maps/sessions/sess-123/activities/act-1/status \
  -H "Content-Type: application/json" \
  -d '{"status": "goal_met"}' \
  | python3 -m json.tool

# Check progress
curl http://localhost:8002/api/v1/process-maps/sessions/sess-123/map/progress \
  | python3 -m json.tool
```

### Scenario 5: Test Activity Colors

In the UI, verify status colors:

| Status | Color | Hex |
|--------|-------|-----|
| proposed | Blue | #3b82f6 |
| in_progress | Orange/Yellow | #f59e0b |
| goal_met | Green | #10b981 |
| blocked | Red | #ef4444 |
| revisit | Purple | #8b5cf6 |

**Test:**
1. Change act-1 to each status
2. Verify card border color changes
3. Verify status badge color changes

---

## Expected Results

### ✅ Success Criteria

- [ ] Can create process map via API
- [ ] Can add activities via API
- [ ] Can view process map in UI
- [ ] Activities display with correct status colors
- [ ] Can change activity status via UI
- [ ] Progress bar updates correctly
- [ ] Can add activities via UI form
- [ ] Dependencies show correctly
- [ ] Process map data persists (survives restart)

### API Endpoints Working

- [ ] `POST /api/v1/process-maps/sessions/{id}/map` - Create map
- [ ] `GET /api/v1/process-maps/sessions/{id}/map` - Get map
- [ ] `GET /api/v1/process-maps/sessions/{id}/map/progress` - Get progress
- [ ] `POST /api/v1/process-maps/sessions/{id}/map/activities` - Add activity
- [ ] `GET /api/v1/process-maps/sessions/{id}/activities/{id}` - Get activity
- [ ] `PUT /api/v1/process-maps/sessions/{id}/activities/{id}/status` - Update status

### UI Features Working

- [ ] Session ID input and load button
- [ ] Process map info display (goal, version, status)
- [ ] Progress bar with percentage
- [ ] Activity cards with status colors
- [ ] Click activity to see details
- [ ] Status dropdown for changing status
- [ ] Add activity form (show/hide)
- [ ] Form submission and map reload

---

## Troubleshooting

### Issue: Frontend not building

```bash
cd serving/frontend
npm install
npm run build
cd ../..
./stop_all.sh
./start_all.sh
```

### Issue: API endpoints not found

Check serving logs:
```bash
tail -f logs/serving.log
```

Verify process_maps router is loaded:
```bash
curl http://localhost:8002/docs
# Look for /process-maps endpoints
```

### Issue: Process map not found

Check storage directory:
```bash
ls -la data/serving/process_maps/
```

Verify process map was created:
```bash
cat data/serving/process_maps/sess-123_map.json
```

### Issue: UI shows error

1. Check browser console (F12)
2. Check network tab for failed requests
3. Verify API base URL in frontend:
   ```bash
   # Should be http://localhost:8002/api/v1
   grep API_BASE_URL serving/frontend/src/api.js
   ```

---

## What's Next

**Phase 2 Preview:**

Next we'll create the **Process Mapper** coordinating agent that:
- Takes a business goal
- Analyzes it using LLM
- Generates initial 3-5 activities automatically
- Populates the process map

Instead of manually adding activities via API, we'll:
1. Enter business goal in UI
2. Click "Create Facilitated Session"
3. Process Mapper agent generates activities
4. Process map appears with proposed activities

**Stay tuned for Phase 2!** 🚀

---

## Files Created in Phase 1

```
serving/
├── models/
│   └── process_map.py                          ✅ NEW
├── services/
│   └── process_map_service.py                  ✅ NEW
├── api/
│   └── process_maps.py                         ✅ NEW
├── app.py                                      ✏️ MODIFIED
└── frontend/src/
    ├── api.js                                  ✏️ MODIFIED
    ├── App.jsx                                 ✏️ MODIFIED
    └── components/
        ├── ProcessMapViewer.jsx                ✅ NEW
        └── ProcessMapViewer.css                ✅ NEW
```

**Summary:**
- 3 new backend files
- 1 new frontend component (2 files)
- 3 files modified for integration

---

**Phase 1 Status: ✅ COMPLETE**

Ready to move to Phase 2 when you are!

