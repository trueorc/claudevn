# Serving UI Guide

An overview of each tab in the ClaudeVN Serving monitoring interface.

The UI is organized into six tabs accessible from the left sidebar. Each tab serves a distinct purpose in the workflow — from infrastructure health to goal setting and work execution.

---

## Network & Health

**Route:** `/network`

The system health dashboard. Shows the operational status of all infrastructure components and compute instances.

**What you see:**

- **System health bar** — Overall status indicator (healthy, degraded, offline) with individual service checks for Redis, Serving, and Marketplace
- **Compute instances** — List of all registered compute workers with their current status (online, degraded, offline) and instance count
- **Marketplace status** — Health of the skill marketplace service
- **Connection indicator** — Shows whether the UI has a live or polling connection to the backend

**View modes:**

- **List view** — Two-column layout with compute instances on the left and marketplace services on the right
- **Map view** — Network topology visualization showing relationships between components

Click any compute instance or marketplace service to open a detail modal with extended information.

---

## Projects

**Route:** `/projects`

Manage the GitHub projects integrated with ClaudeVN.

**What you see:**

- **Project list** — All projects with status filtering
- **Project details** — Metadata fields, description, labels, and associated repositories
- **Activity sidebar** — Recent events for the selected project

**Actions:**

- Create, edit, and delete projects
- Add and remove repositories associated with a project
- Filter projects by status

---

## Marketplace

**Route:** `/marketplace`

Browse and manage the skill registry. Skills are the atomic capability units that get composed into agents for compute instances.

**What you see:**

- **Skill catalog** — All available skills with filtering by author/contributor
- **Skill details** — Definition, capabilities, constraints, and composition metadata

**Actions:**

- Browse existing skills
- Create new skill definitions
- Edit skill details
- View which skills are available for agent composition

---

## Directives

**Route:** `/directives`

The primary interface for setting strategic direction. Submit natural language goals and review system interpretations.

**What you see:**

- **Conversation timeline** — A chronological view of your directives, system responses, proposed backlog items, and status updates
- **Goal history panel** (right sidebar) — All active and archived goals with comment counts and progress indicators

**How it works:**

1. Type a directive in the input area (e.g., "Add rate limiting to all API endpoints")
2. The Goal Decomposer interprets your intent and proposes backlog items
3. Each proposed item appears in the conversation timeline with Apply/Reject controls
4. Applied items flow into the Backlog and Execution Plan

**Modes:**

- **New directive** — Empty conversation area with example prompts to get started
- **Goal detail** — Select a goal from the history panel to view its conversation thread and add follow-up comments

**Goal management:**

- Archive/unarchive completed goals
- Delete goals
- Toggle archived goal visibility
- Track progress via progress bars on active goals

---

## Plan

**Route:** `/plan`

The execution visibility layer. Shows what the system is doing right now and why.

**What you see:**

- **Summary bar** — High-level counts: total items, pending, in progress, blocked, done
- **Active work** — Items currently executing with their assigned compute instance
- **Ready queue** — Items that are unblocked and next in line for execution
- **Blocked items** — Items waiting on dependencies, with blockers listed
- **Why This Order** — Decision traces explaining the system's reasoning for work sequencing

**Interaction:**

Click any item to open a detail modal with full information. The Plan tab is read-only — the system manages execution order based on goals, priorities, and dependencies. To influence ordering, adjust goals in Directives or priorities in Backlog.

---

## Backlog

**Route:** `/backlog`

The full work inventory. View, create, filter, and organize all work items.

**What you see:**

- **Stats bar** — Total count, pending, in progress, blocked, done
- **Work items** — Each item shows title, description, priority, type, area, status, characterization status, ontology tags, required skills, assignment info, and dependency count

**View modes:**

- **List view** — Detailed rows
- **Grid view** — Card layout

**Filtering and grouping:**

- **Filter by:** Status, Priority (P0–P3), Area, Goal association
- **Group by:** Status, Priority, Area, Type, Goal, or None — supports two-level grouping
- **Sort by:** Created date, Priority, Title (ascending or descending)
- Filters persist in the URL for sharing

**Item details:**

Each item displays a characterization badge showing its analysis status (Pending, Analyzing, Characterized, Failed). Characterized items show ontology tags from the AI analysis pipeline — work type, lifecycle stage, technical domain, and project-specific domain clusters.

**Actions:**

- Create new issues with title, description, priority, type, and area
- Edit existing issues
- View full details including characterization results and dependencies
