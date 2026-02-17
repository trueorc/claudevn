# ClaudeVN Core Use Cases

How the platform is used in practice — from defining goals to shipping code.

---

## How ClaudeVN Works

ClaudeVN is an AI agent orchestration platform. You define high-level goals in natural language, and the system decomposes them into work items, plans execution order, and assigns work to Claude Code compute instances that execute autonomously on Git branches. You steer the system through directives and backlog management while monitoring progress in real time.

The core loop:

```
Define Goals → System Decomposes → Backlog Populated → Plan Built → Compute Executes → Code Merged
     ↑                                                                                      |
     └──────────────────── Observe, Adjust, Add New Goals ─────────────────────────────────┘
```

---

## Use Case 1: Goal-Driven Development

**Scenario:** You have a high-level objective and want the system to figure out the details.

**Workflow:**

1. Open the **Directives** tab
2. Type a natural language goal:
   - "Build a user authentication system with OAuth support"
   - "Add comprehensive test coverage to the API layer"
   - "Refactor the database access layer for connection pooling"
3. The system's Goal Decomposer interprets your intent and proposes backlog items
4. Review the proposed items — apply or reject each suggestion
5. Accepted items flow into the **Backlog** with appropriate priority, type, and area tags
6. The **Characterization Pipeline** enriches each item with ontology tags, technical domain classification, and dependency analysis
7. Items enter the **Execution Plan** where the system determines optimal ordering
8. Available compute instances pick up work and execute on feature branches

**When to use:** Starting a new feature area, setting strategic direction, or when you want the AI to handle task breakdown.

---

## Use Case 2: Direct Backlog Management

**Scenario:** You know exactly what needs to be done and want to define the work items yourself.

**Workflow:**

1. Open the **Backlog** tab
2. Create issues directly with:
   - Title and description
   - Priority (P0–P3)
   - Type (Feature, Bug, Refactor, Docs, Test)
   - Area (API, Database, Frontend, Infrastructure, Other)
3. The system characterizes each item automatically (ontology tags, dependencies)
4. Items appear in the **Execution Plan** based on priority and dependencies
5. Compute instances execute the work

**When to use:** Bug fixes, well-defined tasks, or when you want direct control over what gets built.

---

## Use Case 3: Monitoring and Steering Execution

**Scenario:** Work is in progress and you want to understand what's happening and adjust course.

**Workflow:**

1. Check the **Plan** tab to see:
   - What's currently executing and on which compute instance
   - What's in the ready queue (next up)
   - What's blocked and by what
   - **Why This Order** — decision traces explaining the system's reasoning
2. Check the **Backlog** tab with grouping/filtering to understand work distribution:
   - Group by Status to see pipeline health
   - Group by Priority to see what's getting attention
   - Filter by Area to focus on specific domains
3. If the system's direction needs adjustment:
   - Add a new directive in the **Directives** tab (e.g., "Pause new features, focus on testing")
   - Reprioritize items directly in the Backlog
   - Add comments to existing goals for additional context

**When to use:** Ongoing development sessions, daily check-ins, or when priorities shift.

---

## Use Case 4: Skill and Capability Management

**Scenario:** You want to customize what your compute instances can do.

**Workflow:**

1. Open the **Marketplace** tab to browse available skills
2. Review existing skill definitions and their capabilities
3. Create new skills that define specific behaviors for compute instances
4. Skills are atomic CLAUDE.md fragments that get composed into agents:
   - Code implementation, testing, documentation, debugging, etc.
   - When Serving assigns work, it selects relevant skills and merges them into a complete agent definition

**When to use:** Setting up a new project, adding specialized capabilities, or tuning agent behavior.

---

## Use Case 5: Infrastructure Monitoring

**Scenario:** You need to verify the system is healthy and compute instances are operational.

**Workflow:**

1. Open the **Network & Health** tab
2. Check overall system status (healthy/degraded/offline)
3. Verify service health: Redis, Serving, Marketplace
4. Review compute instance status — see which instances are online, degraded, or offline
5. Use the Map view for a topology visualization of the network
6. Click individual instances for detailed information

**When to use:** Before starting a work session, troubleshooting execution issues, or verifying infrastructure after changes.

---

## Use Case 6: Project Setup and Configuration

**Scenario:** You're setting up a new project or managing existing ones.

**Workflow:**

1. Open the **Projects** tab
2. Create a new project with metadata and description
3. Associate GitHub repositories with the project
4. View project activity and status
5. Manage project lifecycle (edit, archive, delete)

**When to use:** Onboarding a new codebase, managing multi-repo projects, or organizing work across repositories.

---

## Typical Session Flow

A typical development session follows this pattern:

1. **Check health** — Network & Health tab, verify infrastructure
2. **Review state** — Plan tab for current execution, Backlog for overall work status
3. **Set direction** — Directives tab to add or adjust goals
4. **Manage specifics** — Backlog tab to create, prioritize, or edit individual items
5. **Monitor progress** — Plan tab to watch execution and understand system decisions
6. **Iterate** — Add new directives or adjust backlog as work completes and new needs emerge

---

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Directives/Goals** | Natural language objectives that drive system behavior. Not task assignments — statements of strategic intent. |
| **Backlog Items** | Concrete work units with priority, type, area, and dependencies. Your direct influence point. |
| **Execution Plan** | System-managed work queue showing active, ready, blocked, and completed items with ordering rationale. |
| **Characterization** | AI analysis that enriches work items with ontology tags, semantic context, and dependency mapping. |
| **Skills** | Atomic capability definitions (CLAUDE.md fragments) composed into agents for compute instances. |
| **Compute Instances** | Claude Code workers that execute tasks autonomously on Git feature branches. |
| **Decision Traces** | Structured explanations of why the system ordered work the way it did. |
