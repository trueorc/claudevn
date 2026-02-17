# Process Map Observability - UI Mockups Guide

**Version**: 1.0  
**Date**: November 25, 2025  
**Purpose**: Visual reference for UI implementation

---

## Overview

This document provides ASCII-art mockups and detailed UI specifications for the observability system. These mockups are intended as implementation guides for frontend developers.

---

## 1. Multi-Session Dashboard (System Overview)

### Desktop Layout (1400px+)

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ ClaudeVN - Process Observability Dashboard                    👤 User ▼   ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

┌─────────────────────────────────────────────────────────────────────────────┐
│ 📊 System Statistics                                    🔄 Auto-refresh: ON │
├────────────────┬────────────────┬────────────────┬─────────────────────────┤
│                │                │                │                         │
│   12 Active    │   45 Total     │   8 Compute    │    24 Active            │
│   Sessions     │   Activities   │   Resources    │    Agents               │
│   🔵●●●●       │   ━━━━━━━░░░   │   🟢🟢🟢🟢      │    🤖🤖🤖              │
│                │   Progress 68% │   All Online   │    Working Now          │
│                │                │                │                         │
└────────────────┴────────────────┴────────────────┴─────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ 🔍 Filter & Sort                                                            │
│ [ Status: All ▼ ] [ Time: Last 24h ▼ ] [ Compute: All ▼ ] [🔍 Search...] │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ 🔄 Active Sessions (12)                                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  │
│  ┃ Session: improve-retention-abc123                   🔵 In Progress  ┃  │
│  ┃ Goal: Increase customer retention by 20%                            ┃  │
│  ┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫  │
│  ┃ Progress: ━━━━━━━━━━━━━━━━━━━━━━━━░░░░░░░░░░░░░░░░░░░ 45% (5/12)   ┃  │
│  ┃                                                                      ┃  │
│  ┃ 📋 Activities: 5 🟢  3 🔵  3 🟡  1 🔴    ⏱️  Duration: 2h 34m      ┃  │
│  ┃ 💻 Compute: 3 instances in use         🔄 Map Version: 3           ┃  │
│  ┃ 🤖 Agents: 5 actively working          ⚠️  1 Blocker                ┃  │
│  ┃                                                                      ┃  │
│  ┃ Last Update: 5 seconds ago              Created: Today at 2:15 PM  ┃  │
│  ┃                                                                      ┃  │
│  ┃ [ View Details ] [ View Timeline ] [ Resource Usage ]               ┃  │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛  │
│                                                                              │
│  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  │
│  ┃ Session: analyze-sales-xyz789                       🔵 In Progress  ┃  │
│  ┃ Goal: Analyze Q4 sales performance across all regions               ┃  │
│  ┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫  │
│  ┃ Progress: ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━░░░░░░░ 78% (6/8)      ┃  │
│  ┃                                                                      ┃  │
│  ┃ 📋 Activities: 6 🟢  1 🔵  1 🟡  0 🔴    ⏱️  Duration: 1h 12m      ┃  │
│  ┃ 💻 Compute: 2 instances in use         🔄 Map Version: 1           ┃  │
│  ┃ 🤖 Agents: 2 actively working          ⚠️  0 Blockers              ┃  │
│  ┃                                                                      ┃  │
│  ┃ Last Update: 3 seconds ago              Created: Today at 3:05 PM  ┃  │
│  ┃                                                                      ┃  │
│  ┃ [ View Details ] [ View Timeline ] [ Resource Usage ]               ┃  │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛  │
│                                                                              │
│  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  │
│  ┃ Session: customer-segmentation-def456               🔴 Blocked      ┃  │
│  ┃ Goal: Develop customer segmentation strategy                        ┃  │
│  ┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫  │
│  ┃ Progress: ━━━━━━━━━━━━░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 23% (3/10)     ┃  │
│  ┃                                                                      ┃  │
│  ┃ 📋 Activities: 3 🟢  0 🔵  5 🟡  2 🔴    ⏱️  Duration: 45m         ┃  │
│  ┃ 💻 Compute: 1 instance in use          🔄 Map Version: 2           ┃  │
│  ┃ 🤖 Agents: 0 actively working          ⚠️  2 Blockers              ┃  │
│  ┃                                                                      ┃  │
│  ┃ ⚠️  BLOCKER: Waiting for customer database access                   ┃  │
│  ┃                                                                      ┃  │
│  ┃ Last Update: 2 seconds ago              Created: Today at 3:32 PM  ┃  │
│  ┃                                                                      ┃  │
│  ┃ [ View Details ] [ View Timeline ] [ Resource Usage ]               ┃  │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛  │
│                                                                              │
│  ... (9 more sessions)                               [ Load More... ]       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### UI Elements

**Session Card Components**:
- Session ID (truncated, full on hover)
- Business goal (2 lines max, ellipsis)
- Status badge (colored: green/blue/red/yellow)
- Progress bar (visual + percentage + fraction)
- Activity breakdown (emoji + count for each status)
- Compute resource count
- Active agent count
- Blocker count (if any)
- Duration elapsed
- Map version
- Last update timestamp
- Action buttons (View Details, Timeline, Resources)

**Card States**:
- Normal: White background, gray border
- In Progress: Light blue left border (4px)
- Blocked: Red left border (4px) + warning icon
- Hover: Slight shadow, cursor pointer

---

## 2. Session Detail View - Overview Tab

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ ← Back to Dashboard     Session: improve-retention-abc123                  ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

┌─────────────────────────────────────────────────────────────────────────────┐
│ 🎯 Business Goal: Increase customer retention by 20%                       │
│ Status: 🔵 In Progress   │  Created: Today at 2:15 PM   │  🔄 Auto-refresh │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ [ Overview ] [ Workflow ] [ Timeline ] [ Resources ] [ Events ]            │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ 📊 Progress Summary                                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Overall Progress:  ━━━━━━━━━━━━━━━━━━━━━━━━░░░░░░░░░░░░░  45% (5/12)     │
│                                                                              │
│  ┌──────────────┬──────────────┬──────────────┬─────────────────────────┐  │
│  │ ⏱️  Duration  │ 🔄 Version   │ ⚠️  Blockers  │ 📝 Reevaluations      │  │
│  │ 2h 34m       │ Map v3       │ 1 Active     │ 2 times               │  │
│  └──────────────┴──────────────┴──────────────┴─────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ 🎯 Activity Status                                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────┬─────────────────┬──────────────────┬─────────────────┐ │
│  │ 🟢 Completed   │ 🔵 In Progress  │ 🟡 Proposed      │ 🔴 Blocked      │ │
│  │                │                 │                  │                 │ │
│  │      5         │       3         │        3         │       1         │ │
│  │  activities    │   activities    │   activities     │   activity      │ │
│  │                │                 │                  │                 │ │
│  └────────────────┴─────────────────┴──────────────────┴─────────────────┘ │
│                                                                              │
│  [ View All ] [ Filter by Status ▼ ] [ Jump to Blocked ]                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ 🤖 Active Agents (5)                                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  │
│  ┃ 🔵 data-analyst-v1                                                   ┃  │
│  ┃ Activity: Activity 2a - Analyze high-value segment retention        ┃  │
│  ┃ Compute: compute-001 (Data Processing Node)                         ┃  │
│  ┃ Status: Active - 18 exchanges, 23m elapsed                          ┃  │
│  ┃ [ View Activity Details ]                                            ┃  │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛  │
│                                                                              │
│  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  │
│  ┃ 🔵 customer-insights-v2                                              ┃  │
│  ┃ Activity: Activity 2b - Analyze SMB segment retention               ┃  │
│  ┃ Compute: compute-003 (ML/AI Node)                                   ┃  │
│  ┃ Status: Active - 12 exchanges, 15m elapsed                          ┃  │
│  ┃ [ View Activity Details ]                                            ┃  │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛  │
│                                                                              │
│  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  │
│  ┃ 👁️  consistency-manager-v1                                           ┃  │
│  ┃ Role: Monitoring all activities for contradictions                  ┃  │
│  ┃ Compute: compute-004 (Coordination Node)                            ┃  │
│  ┃ Status: Monitoring - Last check: 5s ago, No issues detected         ┃  │
│  ┃ [ View Events ]                                                      ┃  │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛  │
│                                                                              │
│  ... (2 more agents)                                [ Expand All ]           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ 💻 Compute Resources (3 instances)                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  │
│  ┃ 🟢 compute-001 - Data Processing Node                               ┃  │
│  ┃ Active: 2 activities  │  Agents: 2  │  Heartbeat: 5s ago            ┃  │
│  ┃ Resources: CPU 45% ██████░░░░  │  Memory 12GB/32GB ████░░░░         ┃  │
│  ┃ [ View Details ] [ View Logs ]                                       ┃  │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛  │
│                                                                              │
│  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  │
│  ┃ 🟢 compute-003 - ML/AI Node                                         ┃  │
│  ┃ Active: 1 activity    │  Agents: 1  │  Heartbeat: 3s ago            ┃  │
│  ┃ Resources: CPU 67% █████████░  │  Memory 18GB/64GB ███░░░░░         ┃  │
│  ┃ [ View Details ] [ View Logs ]                                       ┃  │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛  │
│                                                                              │
│  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  │
│  ┃ 🟢 compute-004 - Coordination Node                                  ┃  │
│  ┃ Active: 2 coordinating agents  │  Heartbeat: 8s ago                 ┃  │
│  ┃ Resources: CPU 12% ██░░░░░░░░  │  Memory 4GB/16GB ██░░░░░░         ┃  │
│  ┃ [ View Details ] [ View Logs ]                                       ┃  │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ ⚠️  Active Blockers (1)                                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  │
│  ┃ 🔴 Activity 2b-1: Obtain Historical Pricing Data                    ┃  │
│  ┃ Issue: Database access credentials not available                    ┃  │
│  ┃ Identified: 15 minutes ago by activity-facilitator-v1               ┃  │
│  ┃ Impact: Blocking Activity 2b (SMB segment analysis)                 ┃  │
│  ┃ [ View Activity ] [ View Resolution Plan ]                           ┃  │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Session Detail View - Workflow Tab

### Small Process Map (10-30 activities)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ [ Overview ] [ Workflow ] [ Timeline ] [ Resources ] [ Events ]            │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ 🔧 Workflow Controls                                                        │
│ [ Show: All ▼ ] [ Group By: None ▼ ] [ Layout: Auto ▼ ] [ 🔍 Search ]    │
│ [ ⚙️ Settings ] [ 📷 Export Image ] [ 🔄 Refresh ]                         │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ Workflow Visualization                                [ + ] [ - ] [ ↺ ]   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│                      ┌─────────────────────────────┐                        │
│                      │ Activity 0:                 │                        │
│                      │ Obtain Database Access      │                        │
│                      │ 🟢 Completed (12m ago)      │                        │
│                      │ Agent: IT-Access-Agent      │                        │
│                      │ Compute: compute-004        │                        │
│                      └──────────┬──────────────────┘                        │
│                                 │                                            │
│                                 ↓                                            │
│                      ┌─────────────────────────────┐                        │
│                      │ Activity 1:                 │                        │
│                      │ Understand Current          │                        │
│                      │ Retention                   │                        │
│                      │ 🟢 Completed (8m ago)       │                        │
│                      │ Agent: DataAnalyst          │                        │
│                      │ Compute: compute-001        │                        │
│                      │ Duration: 23m | 18 exchanges│                        │
│                      └──────────┬──────────────────┘                        │
│                                 │                                            │
│                        ┌────────┴────────┐                                  │
│                        ↓                 ↓                                   │
│          ┌─────────────────────┐  ┌─────────────────────┐                  │
│          │ Activity 2a:        │  │ Activity 2b:        │                  │
│          │ Analyze High-Value  │  │ Analyze SMB Segment │                  │
│          │ Segment             │  │                     │                  │
│          │ 🔵 Active (45% done)│  │ 🔴 Blocked          │                  │
│          │ Agent: DataAnalyst  │  │ Agent: Insights-v2  │                  │
│          │ Compute: compute-001│  │ Compute: compute-003│                  │
│          │ 8 exchanges, 15m    │  │ ⚠️  Needs data access│                 │
│          └──────────┬──────────┘  └──────────┬──────────┘                  │
│                     │                         │                             │
│                     │       ┌─────────────────┘                             │
│                     │       │                                               │
│                     │       ↓                                               │
│                     │  ┌─────────────────────┐                             │
│                     │  │ Activity 2b-1:      │                             │
│                     │  │ Obtain Pricing Data │                             │
│                     │  │ 🔵 Active (just     │                             │
│                     │  │       started)      │                             │
│                     │  │ Agent: data-accessor│                             │
│                     │  └─────────────────────┘                             │
│                     │                                                        │
│                     └────────────┬───────────────────┐                      │
│                                  ↓                   ↓                      │
│                     ┌─────────────────────┐ ┌─────────────────────┐       │
│                     │ Activity 3a:        │ │ Activity 3b:        │       │
│                     │ Develop High-Value  │ │ Develop SMB         │       │
│                     │ Strategy            │ │ Strategy            │       │
│                     │ 🟡 Proposed         │ │ 🟡 Proposed         │       │
│                     │ (waiting)           │ │ (waiting)           │       │
│                     └─────────────────────┘ └─────────────────────┘       │
│                                                                              │
│  Legend: 🟢 Completed  🔵 Active  🟡 Proposed  🔴 Blocked                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Large Process Map (30-100+ activities) - Collapsed View

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Workflow Visualization (Collapsed)                   [ + ] [ - ] [ ↺ ]    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ▼ Phase 1: Data Collection & Access                                       │
│     ┌────────────────────────────────────────────────────────────────────┐ │
│     │ 5 activities  │  🟢 100% Complete  │  Duration: 1h 15m              │ │
│     │ Activities: 0, 1, 1a, 1b, 1c                                        │ │
│     │ [ Collapse ] [ View Timeline ] [ View Activities ]                  │ │
│     └────────────────────────────────────────────────────────────────────┘ │
│                 │                                                            │
│                 ↓                                                            │
│  ▼ Phase 2: Retention Analysis                                             │
│     ┌────────────────────────────────────────────────────────────────────┐ │
│     │ 12 activities  │  🔵 67% Complete  │  Duration: 1h 45m (ongoing)   │ │
│     │ 8 Completed 🟢  │  3 Active 🔵  │  1 Proposed 🟡                   │ │
│     ├────────────────────────────────────────────────────────────────────┤ │
│     │                                                                      │ │
│     │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐ │ │
│     │  │ Activity 2  🟢   │  │ Activity 3  🟢   │  │ Activity 4  🟢   │ │ │
│     │  └──────────────────┘  └──────────────────┘  └──────────────────┘ │ │
│     │  ... (5 more completed)                                            │ │
│     │                                                                      │ │
│     │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐ │ │
│     │  │ Activity 10 🔵   │  │ Activity 11 🔵   │  │ Activity 12 🔵   │ │ │
│     │  │ 45% complete     │  │ 30% complete     │  │ 10% complete     │ │ │
│     │  └──────────────────┘  └──────────────────┘  └──────────────────┘ │ │
│     │                                                                      │ │
│     │  ┌──────────────────┐                                              │ │
│     │  │ Activity 13 🟡   │  (Waiting for dependencies)                 │ │
│     │  └──────────────────┘                                              │ │
│     │                                                                      │ │
│     │ [ Collapse ] [ View Timeline ] [ View All Activities ]             │ │
│     └────────────────────────────────────────────────────────────────────┘ │
│                 │                                                            │
│                 ↓                                                            │
│  ▶ Phase 3: Strategy Development                                           │
│     ┌────────────────────────────────────────────────────────────────────┐ │
│     │ 8 activities  │  🟡 0% Complete  │  Not yet started                │ │
│     │ All activities pending (dependencies not met)                       │ │
│     │ [ Expand ] [ View Planned Activities ]                              │ │
│     └────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ▶ Phase 4: Implementation & Validation                                    │
│     ┌────────────────────────────────────────────────────────────────────┐ │
│     │ 6 activities  │  🟡 0% Complete  │  Not yet started                │ │
│     │ [ Expand ]                                                           │ │
│     └────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Activity Detail Modal

```
╔═════════════════════════════════════════════════════════════════════════════╗
║ Activity Detail: Understand Current Retention Metrics         [✕ Close]   ║
║ Session: improve-retention-abc123                                          ║
╠═════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║ [ Overview ] [ Conversation ] [ Outputs ] [ Metadata ]                     ║
║                                                                              ║
║ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ║
║                                                                              ║
║ 📋 Activity Overview                                                        ║
║ ┌──────────────────────────────────────────────────────────────────────┐  ║
║ │ Activity ID: activity-1-abc                                           │  ║
║ │ Goal: Analyze historical customer retention data to establish        │  ║
║ │       baseline metrics and identify trends                            │  ║
║ │                                                                        │  ║
║ │ Status: 🟢 Completed                                                  │  ║
║ │ Started: Today at 2:15 PM  │  Completed: Today at 2:38 PM            │  ║
║ │ Duration: 23 minutes                                                   │  ║
║ │                                                                        │  ║
║ │ 👤 Participants:                                                      │  ║
║ │   • data-analyst-v1 (Primary) - compute-001                           │  ║
║ │     Reason: Complete capability match, has database access            │  ║
║ │   • customer-insights-v2 (Backup) - compute-003                       │  ║
║ │     Not used in this activity                                         │  ║
║ │                                                                        │  ║
║ │ 🔗 Dependencies:                                                      │  ║
║ │   ✓ Activity 0: Obtain Database Access (completed)                   │  ║
║ │                                                                        │  ║
║ │ 🎯 Enables:                                                           │  ║
║ │   → Activity 2a: Analyze High-Value Segment                           │  ║
║ │   → Activity 2b: Analyze SMB Segment                                  │  ║
║ │                                                                        │  ║
║ │ ⚠️  Blockers: None                                                     │  ║
║ │                                                                        │  ║
║ └──────────────────────────────────────────────────────────────────────┘  ║
║                                                                              ║
║ 💬 Conversation Timeline (18 exchanges)                                    ║
║ ┌──────────────────────────────────────────────────────────────────────┐  ║
║ │ ┌──────────────────────────────────────────────────────────────────┐ │  ║
║ │ │ [2:15:30 PM] 🎯 FRAME - activity-facilitator-v1                 │ │  ║
║ │ │ We need to understand current retention metrics to establish a   │ │  ║
║ │ │ baseline. What data sources and timeframe do you need?          │ │  ║
║ │ └──────────────────────────────────────────────────────────────────┘ │  ║
║ │                                                                        │  ║
║ │ ┌──────────────────────────────────────────────────────────────────┐ │  ║
║ │ │ [2:16:15 PM] 💬 ANSWER - data-analyst-v1                        │ │  ║
║ │ │ I need access to the customer database for the last 12 months.   │ │  ║
║ │ │ Specifically, I need these fields:                                │ │  ║
║ │ │   - user_id                                                       │ │  ║
║ │ │   - signup_date                                                   │ │  ║
║ │ │   - last_activity_date                                            │ │  ║
║ │ │   - subscription_status                                           │ │  ║
║ │ │   - customer_type (if available)                                  │ │  ║
║ │ └──────────────────────────────────────────────────────────────────┘ │  ║
║ │                                                                        │  ║
║ │ ┌──────────────────────────────────────────────────────────────────┐ │  ║
║ │ │ [2:17:02 PM] ❓ QUESTION - activity-facilitator-v1              │ │  ║
║ │ │ Do you have the necessary database credentials?                  │ │  ║
║ │ └──────────────────────────────────────────────────────────────────┘ │  ║
║ │                                                                        │  ║
║ │ ┌──────────────────────────────────────────────────────────────────┐ │  ║
║ │ │ [2:17:20 PM] 💬 ANSWER - data-analyst-v1                        │ │  ║
║ │ │ Yes, credentials were provided in Activity 0. I can proceed.     │ │  ║
║ │ └──────────────────────────────────────────────────────────────────┘ │  ║
║ │                                                                        │  ║
║ │ ┌──────────────────────────────────────────────────────────────────┐ │  ║
║ │ │ [2:19:45 PM] 🔍 CLARIFY - activity-facilitator-v1               │ │  ║
║ │ │ Should we segment the analysis by customer type or analyze as a  │ │  ║
║ │ │ whole initially?                                                  │ │  ║
║ │ └──────────────────────────────────────────────────────────────────┘ │  ║
║ │                                                                        │  ║
║ │ ┌──────────────────────────────────────────────────────────────────┐ │  ║
║ │ │ [2:20:30 PM] 💬 ANSWER - data-analyst-v1                        │ │  ║
║ │ │ Let me query the data first to see the distribution... │ │
║ │ │ [Analysis running...]                                             │ │  ║
║ │ └──────────────────────────────────────────────────────────────────┘ │  ║
║ │                                                                        │  ║
║ │ ┌──────────────────────────────────────────────────────────────────┐ │  ║
║ │ │ [2:25:10 PM] 📊 ASSESS - data-analyst-v1                        │ │  ║
║ │ │ Initial analysis reveals significant variance by segment:        │ │  ║
║ │ │   • High-value customers: 78% retention                           │ │  ║
║ │ │   • SMB customers: 55% retention                                  │ │  ║
║ │ │   • Overall blended: 67% retention                                │ │  ║
║ │ │                                                                    │ │  ║
║ │ │ Recommendation: We should analyze segments separately for more   │ │  ║
║ │ │ actionable insights.                                              │ │  ║
║ │ │                                                                    │ │  ║
║ │ │ 📊 [View Full Analysis Data]                                      │ │  ║
║ │ └──────────────────────────────────────────────────────────────────┘ │  ║
║ │                                                                        │  ║
║ │ ... [12 more exchanges - scroll or click "Load More"]                 │  ║
║ │                                                                        │  ║
║ │ ┌──────────────────────────────────────────────────────────────────┐ │  ║
║ │ │ [2:38:15 PM] ✅ CONCLUDE - activity-facilitator-v1              │ │  ║
║ │ │ Activity goal has been achieved. We have established baseline    │ │  ║
║ │ │ retention metrics and identified the critical need for segment-  │ │  ║
║ │ │ based analysis.                                                   │ │  ║
║ │ │                                                                    │ │  ║
║ │ │ Outcome: Goal Met                                                 │ │  ║
║ │ │ New Understanding: Segmentation is critical - variance is high   │ │  ║
║ │ │ Decision: Recommend restructuring next activities by segment     │ │  ║
║ │ └──────────────────────────────────────────────────────────────────┘ │  ║
║ │                                                                        │  ║
║ │ [ Load More (6 exchanges) ] [ Export Conversation ] [ View Raw JSON ]  │  ║
║ └──────────────────────────────────────────────────────────────────────┘  ║
║                                                                              ║
║ [ Close ] [ ← Previous Activity ] [ Next Activity → ]                      ║
║                                                                              ║
╚═════════════════════════════════════════════════════════════════════════════╝
```

---

## 5. Timeline View

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ [ Overview ] [ Workflow ] [ Timeline ] [ Resources ] [ Events ]            │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ 🔍 Timeline Filters                                                         │
│ [ Show: All Events ▼ ] [ Time: All Time ▼ ] [ Jump to: Now ▼ ]           │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ Timeline - Session: improve-retention-abc123                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ 2:00 PM ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│         │                                                                    │
│         │ 📋 Session Created                                                │
│         │ Goal: Increase customer retention by 20%                          │
│         │ Created by: Process Mapper                                        │
│         │                                                                    │
│ 2:02 PM │ 🗺️  Process Map v1 Created                                       │
│         │ Initial structure: 3 activities proposed                          │
│         │ Activities: 0 (Data Access), 1 (Analysis), 2 (Strategy)          │
│         │ [ View Process Map v1 ]                                           │
│         │                                                                    │
│ 2:03 PM │ 🎯 Activity 0: Obtain Database Access                            │
│         │ Status: Proposed → In Progress                                    │
│         │ Agent: IT-Access-Agent assigned (compute-004)                     │
│         │                                                                    │
│ 2:15 PM │ ✅ Activity 0: Completed                                         │
│         │ Duration: 12 minutes                                              │
│         │ Output: Database credentials provided                             │
│         │ [ View Activity Details ]                                         │
│         │                                                                    │
│ 2:15 PM │ 🎯 Activity 1: Understand Current Retention                      │
│         │ Status: Proposed → In Progress                                    │
│         │ Agent: data-analyst-v1 assigned (compute-001)                     │
│         │ Dependencies satisfied: Activity 0 completed                      │
│         │                                                                    │
│ 2:25 PM │ 💡 Key Finding Identified - Activity 1                           │
│         │ Significant retention variance by segment detected               │
│         │ High-value: 78%  │  SMB: 55%  │  Blended: 67%                    │
│         │ Recommendation: Segment-based analysis needed                     │
│         │                                                                    │
│ 2:30 PM │ 🔄 Process Map v2 (Reevaluation Event)                           │
│         │ Triggered by: Segmentation discovered in Activity 1               │
│         │ Changes: Activity 2 split → Activity 2a, 2b                       │
│         │ Reasoning: Separate analysis paths for different segments         │
│         │ [ View Reevaluation Details ] [ Compare v1 vs v2 ]               │
│         │                                                                    │
│ 2:38 PM │ ✅ Activity 1: Completed                                         │
│         │ Duration: 23 minutes  │  Exchanges: 18                            │
│         │ Key Finding: Segmentation is critical for retention strategy      │
│         │ [ View Conversation ] [ View Outputs ]                            │
│         │                                                                    │
│ 2:40 PM │ 🎯 Activity 2a: Analyze High-Value Segment                       │
│         │ Status: Proposed → In Progress                                    │
│         │ Agent: data-analyst-v1 assigned (compute-001)                     │
│         │                                                                    │
│ 2:41 PM │ 🎯 Activity 2b: Analyze SMB Segment                              │
│         │ Status: Proposed → In Progress                                    │
│         │ Agent: customer-insights-v2 assigned (compute-003)                │
│         │                                                                    │
│ 2:55 PM │ 📊 Progress Report Generated                                     │
│         │ By: progress-reporter-v1                                          │
│         │ Status: On Track  │  Progress: 42%  │  No critical issues        │
│         │ [ View Full Report ]                                              │
│         │                                                                    │
│ 3:05 PM │ ⚠️  Blocker Identified - Activity 2b                             │
│         │ Issue: Need historical pricing data for SMB analysis              │
│         │ Identified by: activity-facilitator-v1                            │
│         │ Severity: Moderate (blocks 1 activity)                            │
│         │ Action: Creating Activity 2b-1 to resolve                         │
│         │ [ View Blocker Details ]                                          │
│         │                                                                    │
│ 3:07 PM │ 🔄 Process Map v3 (Reevaluation Event)                           │
│         │ Triggered by: Blocker in Activity 2b                              │
│         │ Changes: Added Activity 2b-1 as dependency for 2b                │
│         │ Reasoning: Must obtain pricing data before SMB analysis continues │
│         │ [ View Reevaluation Details ]                                     │
│         │                                                                    │
│ 3:08 PM │ 🔴 Activity 2b: Status Changed                                   │
│         │ Status: In Progress → Blocked                                     │
│         │ Waiting for: Activity 2b-1 completion                             │
│         │                                                                    │
│ 3:10 PM │ 🎯 Activity 2b-1: Obtain Historical Pricing Data                 │
│         │ Status: Proposed → In Progress                                    │
│         │ Agent: data-accessor-v1 assigned (compute-001)                    │
│         │ Created to resolve blocker in Activity 2b                         │
│         │                                                                    │
│ 3:25 PM │ 🔍 Consistency Check Completed                                   │
│         │ By: consistency-manager-v1                                        │
│         │ Activities Checked: Activity 2a outputs vs Activity 1 baseline    │
│         │ Result: No contradictions detected                                │
│         │ [ View Check Details ]                                            │
│         │                                                                    │
│         │ └─ Now ──────────────────────────────────────────────────────────│
│                                                                              │
│ [ Scroll to Top ] [ Jump to Event... ] [ Export Timeline ]                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## UI Component Specifications

### Color Palette

**Primary Colors**:
- Primary Blue: `#3b82f6`
- Success Green: `#10b981`
- Warning Yellow: `#f59e0b`
- Danger Red: `#ef4444`
- Secondary Purple: `#8b5cf6`

**Status Colors**:
- Completed: Green `#10b981`
- In Progress: Blue `#3b82f6`
- Proposed: Yellow `#f59e0b`
- Blocked: Red `#ef4444`
- Revisit: Purple `#8b5cf6`

**Neutral Colors**:
- Background: `#ffffff`
- Secondary Background: `#f9fafb`
- Border: `#e5e7eb`
- Text Primary: `#1f2937`
- Text Secondary: `#6b7280`
- Text Muted: `#9ca3af`

### Typography

**Headings**:
- H1: 28px, Bold, Primary Text
- H2: 24px, Semi-bold, Primary Text
- H3: 20px, Semi-bold, Primary Text
- H4: 18px, Medium, Primary Text

**Body**:
- Body Large: 16px, Regular, Primary Text
- Body: 14px, Regular, Primary Text
- Body Small: 12px, Regular, Secondary Text

**Code/Data**:
- Monospace: `'Monaco', 'Menlo', monospace`
- Font Size: 13px

### Spacing

- **xs**: 4px
- **sm**: 8px
- **md**: 16px
- **lg**: 24px
- **xl**: 32px
- **2xl**: 48px

### Cards

**Session Card**:
- Padding: 24px
- Border Radius: 8px
- Border: 1px solid `#e5e7eb`
- Shadow (hover): `0 4px 12px rgba(0,0,0,0.1)`
- Status Indicator: 4px left border in status color

**Activity Card**:
- Padding: 16px
- Border Radius: 6px
- Border: 1px solid `#e5e7eb`
- Background: Status-dependent (light tint)
  - Completed: `#f0fdf4` (light green)
  - In Progress: `#eff6ff` (light blue)
  - Proposed: `#fffbeb` (light yellow)
  - Blocked: `#fef2f2` (light red)

### Badges

**Status Badge**:
- Height: 24px
- Padding: 4px 12px
- Border Radius: 12px (pill shape)
- Font Size: 12px
- Font Weight: 600
- Background: Status color with 20% opacity
- Text: Status color at 100% opacity

### Buttons

**Primary Button**:
- Background: Primary Blue
- Text: White
- Padding: 8px 16px
- Border Radius: 6px
- Font Weight: 600
- Hover: Darken 10%

**Secondary Button**:
- Background: White
- Text: Primary Blue
- Border: 1px solid Primary Blue
- Padding: 8px 16px
- Border Radius: 6px
- Font Weight: 600
- Hover: Light blue background

### Progress Bars

**Bar Style**:
- Height: 8px
- Border Radius: 4px
- Background: `#e5e7eb`
- Fill: Gradient from Primary Blue to Success Green
- Animated (indeterminate): Shimmer effect

### Icons

**Size Standards**:
- Small: 16px
- Medium: 20px
- Large: 24px
- X-Large: 32px

**Icon Library**: Use consistent icon set (e.g., Heroicons, Feather Icons)

---

## Responsive Breakpoints

**Desktop** (1400px+):
- Full dashboard layout
- Side-by-side panels
- Expanded workflow visualizations

**Tablet** (768px - 1399px):
- Stacked panels
- Collapsible sidebar
- Simplified workflow graphs

**Mobile** (< 768px):
- Single column layout
- Bottom navigation
- Accordion-style sections
- List view only (no workflow graph)

---

## Accessibility Requirements

- **WCAG 2.1 Level AA** compliance
- **Keyboard Navigation**: All interactive elements accessible via keyboard
- **Screen Reader Support**: Proper ARIA labels and roles
- **Color Contrast**: Minimum 4.5:1 for text, 3:1 for UI components
- **Focus Indicators**: Visible focus states for all interactive elements
- **Alternative Text**: All icons and images have descriptive alt text

---

## Animation Guidelines

**Transitions**:
- Default: 200ms ease-in-out
- Hover effects: 150ms ease
- Modal open/close: 300ms ease-in-out

**Loading States**:
- Skeleton screens for initial loads
- Spinners for actions (< 3 seconds expected)
- Progress bars for long operations (> 3 seconds)

**Micro-interactions**:
- Button press: Slight scale down (0.95)
- Card hover: Lift with shadow
- Status change: Fade + scale animation

---

## Implementation Notes

### Technology Recommendations

**Frontend**:
- React 18+
- CSS Modules or Tailwind CSS
- D3.js or Vis.js for workflow graphs
- React Query for data fetching
- Zustand or Redux for state management

**Real-time Updates**:
- Polling with `setInterval` (Phase 1-6)
- WebSocket with Socket.io (Phase 7+)

**Performance**:
- Virtual scrolling for long lists (react-window)
- Lazy loading for modals and heavy components
- Memoization for expensive computations
- Debounced search inputs

---

**Version**: 1.0  
**Date**: November 25, 2025  
**Status**: Reference for Implementation  
**Related**: [Full Observability Design](PROCESS_MAP_OBSERVABILITY.md)

