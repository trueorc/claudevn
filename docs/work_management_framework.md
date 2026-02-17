# Automated Work Management System — Conceptual Framework

## 1. System Overview

The system receives user-defined goals as its primary input and autonomously decomposes, characterizes, plans, and distributes work to specialized AI agents. The user influences the direction of work but does not directly control execution. The planner is the central authority, maintaining a living execution model that absorbs pressure from three directions: user goals (top-down intent), worker feedback (bottom-up signals), and resource opportunities (environmental conditions).

---

## 2. Core Pipeline

```
User Goal
    ↓
Decomposition Agent → Raw tasks with parent/child structure
    ↓
Characterization Stage → Profiled work items with ontology tags,
                         semantic context, and contextual dependencies
    ↓
Planner (with dynamic profile) → Execution plan organized as
                                  a priority bucket tree
    ↓
Worker Agents (specialized, varied compute) → Execution + feedback loop
    ↑_____________________________________________________|
```

---

## 3. Goal as Intent

Goals are the user's mechanism for influencing the system. A goal is not a task assignment — it is a statement of strategic intent. Goals carry implicit signals about what matters, what's urgent, and what should be deprioritized.

**Examples of goal-level intent:**
- "Build feature X" → expansion-oriented, new capability
- "Harden current functionality" → consolidation-oriented, quality/stability focus
- "Focus on capability Y" → targeted investment in a specific domain

Goals do not replace the existing execution plan. They are absorbed into it. The planner interprets each goal to adjust its operating profile and re-organizes work accordingly. Multiple goals may coexist, with the planner managing tension between them.

---

## 4. Decomposition Agent

A dedicated agent responsible for breaking goals into accomplishable tasks. Operates independently from the planner.

**Responsibilities:**
- Receive a goal and produce a hierarchical task breakdown
- Identify obvious parent/child relationships within the decomposed work
- Pass all output to the Characterization Stage before it reaches the planner

**Boundary:** The decomposition agent defines *what work exists*. It does not determine priority, sequencing, or assignment. It may be invoked again if the planner or workers identify missing work.

---

## 5. Characterization Stage

The critical translation layer between raw tasks and plannable work. Every task (and optionally, high-level features) passes through characterization before entering the planner's backlog.

### 5.1 What Characterization Produces

For each work item, the characterization stage outputs:

**A. Universal ontology tags (fixed vocabulary, deterministic filtering)**
- Work type: feature, bug fix, refactor, test, documentation, infrastructure, integration
- Lifecycle stage: design, build, test, validate, deploy
- Technical domain: frontend, backend, data, API, security, DevOps, etc.

**B. Project-specific semantic tags (adaptive, project-scoped)**
- Domain cluster: which capability area does this belong to (e.g., payment processing, user management, reporting)
- Domain clusters are seeded from initial decomposition and grow as new work enters
- New clusters may be created when work doesn't fit existing ones

**C. Business and technical meaning assessments**
- Business meaning: what does this task contribute to the product, user experience, or business outcome — independent of other tasks
- Technical meaning: what does this task accomplish technically — what does it build, fix, validate, or enable
- Contextual meaning: given everything else in the project, what role does this task play — is it foundational, incremental, enabling, or blocking

**D. Contextual dependencies**
- Not limited to parent/child relationships
- Includes: "this task is semantically related to...", "this task is likely blocked by...", "this task enables..." based on comparison against existing characterized work
- Dependencies may be structural (hard prerequisite) or contextual (related, beneficial to sequence together, shared domain context)

### 5.2 How Characterization Works

The characterizer evaluates each task against two frames:
1. **In isolation** — what is this task on its own merits
2. **In project context** — given the existing body of characterized work, what is this task's role, and what are its relationships

This requires the characterizer to have read access to the current work topology (the full set of characterized work in the system).

---

## 6. The Two-Layer Ontology

The ontology provides the structured vocabulary that enables deterministic filtering and semantic reasoning across the system.

### Layer 1 — Universal (fixed, cross-project)

Predefined categories that apply to any software project. These never change per project. They enable the planner to make broad-stroke decisions like "prioritize all testing" or "deprioritize new feature development" without needing project-specific knowledge.

Categories include work type, lifecycle stage, and technical domain as defined above.

### Layer 2 — Project-Specific (seeded, adaptive)

Categories that describe what *this particular project* is about. Seeded when the first goal is decomposed and the initial tasks are characterized. Grows as new goals introduce new capability areas.

Examples: "payment processing," "user authentication," "reporting dashboard," "third-party integrations."

**Evolution rules:**
- New project-specific categories are created when the characterization stage encounters work that doesn't fit existing categories
- Categories may be consolidated if they converge over time
- The planner can reference either layer when constructing its operating profile

---

## 7. The Planner

The central orchestration authority. Receives characterized work and organizes it for execution based on a dynamic operating profile.

### 7.1 Planner Profile

The planner's profile is a dynamic lens constructed from the three influence sources (goals, worker feedback, resource conditions). It determines how the planner evaluates and sequences all work.

**The profile consists of three components:**

**A. Ontology weights — preferences across both layers**
- A weight (0.0 to 1.0) for each universal category indicating current priority
- A weight (0.0 to 1.0) for each project-specific category indicating current focus
- Example: testing: 0.9, bug fix: 0.85, new features: 0.15 | payment flow: 0.9, reporting: 0.1

**B. Policy rules — conditional logic that overrides weights**
- Express dependency-aware and situational reasoning
- Example: "Any task blocking a high-priority testing task inherits elevated priority regardless of its own category weight"
- Example: "Tasks that are >80% complete should be finished regardless of category deprioritization"

**C. Confidence bands — how firmly the profile holds its positions**
- Each weight or policy carries an implicit confidence level
- High confidence: the planner deviates only for strong countervailing signals
- Low confidence: the planner is willing to be opportunistic or flexible
- Influenced by the strength of the user's directive language and the consistency of other signals

### 7.2 Profile Construction and Updates

The planner profile is not static. It is rebuilt or adjusted when:
- A new goal arrives (primary trigger — reinterpret intent, adjust weights and policies)
- Worker feedback surfaces new information (secondary trigger — adjust policies, potentially shift weights if blockers or challenges change the landscape)
- Resource conditions change (tertiary trigger — introduce opportunistic policy overrides)

When multiple goals coexist, the profile must reconcile potentially competing intents. The planner resolves this by evaluating the relative strength and recency of each goal's intent signals.

### 7.3 Execution Plan — The Priority Bucket Tree

The planner organizes work into a tree of **priority buckets**. This is not a flat ranked list. It is a hierarchical grouping where:

- **Buckets represent strategic groupings** defined by the current planner profile
- **Buckets cut across the ontology** — a single bucket may contain tasks from multiple domains and work types, unified by strategic purpose
- **Buckets are ranked** against each other, determining macro-level priority
- **Tasks within each bucket are ordered** based on dependency readiness, ontology weights, and contextual priority

**Example bucket structure under a "harden current functionality" profile:**

```
Bucket 1 (highest): Validate what's built
  → Testing tasks for mature capability areas
  → Ordered by: domain maturity (most complete first), dependency readiness

Bucket 2: Remove blockers to validation
  → Bug fixes, dependency resolutions, investigation tasks
  → Ordered by: what they unblock (tasks enabling Bucket 1 items rank highest)

Bucket 3: Continue low-risk progress
  → Nearly-complete feature work that's cheap to finish
  → Ordered by: completion proximity, resource availability

Bucket 4 (lowest): Park for later
  → Early-stage new feature work
  → Ordered by: strategic value (for when focus eventually shifts back)
```

### 7.4 Bucket Reorganization Mechanics

When the planner profile shifts, the **bucket boundaries change** — not individual task scores. Tasks fall into different buckets because the definition of what each bucket represents has changed. This makes reorganization an operation on the structure itself, not a re-evaluation of every task.

**Reorganization triggers:**
- New goal changes the profile weights and policies → buckets are redefined, tasks redistribute
- Worker feedback introduces new tasks or surfaces blockers → new tasks are placed into existing buckets based on characterization; blockers may trigger policy-driven elevation
- Resource availability changes → opportunistic bucket may be temporarily created or an existing bucket's priority temporarily boosted

---

## 8. Worker Agents

Specialized AI agents with differentiated skills and varied compute capabilities (local compute through scalable cloud resources). The initial system targets **2-3 workers** to validate the planning and distribution model before addressing scale.

### 8.1 Characteristics (Initial Scope: 2-3 Workers)
- **Skill-based specialization**: each worker is configured for specific types of work based on project needs — with 2-3 workers, specialization boundaries must be deliberate and relatively broad
- **Varied compute tiers**: workers may operate on different resource levels (e.g., one local, one cloud-backed), influencing what tasks they can handle
- **Context affinity**: workers that have completed related work carry relevant context, making them more efficient for follow-on tasks in the same domain — in a small worker pool, this becomes a significant factor since each worker will accumulate substantial context over time

### 8.2 Implications of Small Worker Pool

With 2-3 workers, several dynamics simplify while others become more critical:
- **Distribution is a smaller decision space**: the planner is choosing between 2-3 options per task, not optimizing across a large pool — the emphasis shifts from matching efficiency to sequencing intelligence
- **Worker utilization matters more**: an idle worker is a larger percentage of total capacity, so the planner should minimize gaps between task completions
- **Context affinity becomes a primary factor**: with few workers, each one develops deep context in their assigned areas — the cost of breaking that affinity (assigning a worker to an unfamiliar domain) is proportionally higher
- **Specialization design is a strategic choice**: how you draw the skill boundaries across 2-3 workers significantly shapes what the planner can do — this is an early design decision with outsized impact

Scale concerns (load balancing across many agents, agent pool management, parallel execution coordination) are deferred until the core planning model is validated.

### 8.2 Feedback Loop

Workers are not passive executors. They actively influence the plan by:
- **Surfacing new dependencies**: "I can't complete this task without X being done first"
- **Issuing challenges**: "This task as defined is not achievable because..."
- **Creating new requirements**: "Completing this task revealed that Y also needs to happen"

Worker feedback enters the system as new information. New tasks go through the characterization stage. Challenges and dependency signals go to the planner for profile adjustment and bucket reorganization.

---

## 9. Influence Model — Three Pressure Sources

The planner's profile and execution plan are shaped by three distinct influence channels:

| Source | Nature | Frequency | Impact |
|---|---|---|---|
| User Goals | Strategic intent, directional | Episodic — when user issues new goals | Reconstructs or significantly adjusts the planner profile; may redefine bucket structure entirely |
| Worker Feedback | Tactical reality, ground-truth signals | Continuous — as work is executed | Adds tasks, modifies dependencies, triggers policy-driven adjustments; may gradually shift profile weights if feedback pattern indicates systemic issues |
| Resource Opportunities | Environmental conditions, transient | Variable — driven by infrastructure state | Creates opportunistic overrides; may temporarily elevate work that wouldn't otherwise be prioritized if a resource window is available |

The planner must reconcile these three channels. User goals set the strategic frame. Worker feedback keeps the plan grounded in reality. Resource opportunities enable tactical efficiency. Conflicts are resolved by the planner's profile — specifically the confidence bands, which determine how much the strategic frame bends to accommodate tactical signals.

---

## 10. Communication Substrate — Observability

The work topology (characterized work organized into ontology-tagged clusters with dependency relationships) serves as the communication substrate between the system and the user.

The user does not need to see individual tasks or the full execution plan. Instead, the system can surface:
- **Capability area status**: which project-specific domains exist, their maturity level, what's active vs. parked
- **Current planner focus**: a human-readable summary of what the planner is optimizing for
- **Blockers and risks**: what's impeding progress, surfaced at the cluster level
- **Goal alignment**: how much of the current execution plan is aligned with each active goal
- **Conflicts**: tensions the system has identified and how they are being handled (see 10.1)

This allows the user to issue new directives in the language of the topology ("accelerate payment flow validation," "unblock the API integration cluster") without needing to understand task-level details.

### 10.1 Conflict Surfacing

Conflicts are inevitable in a system absorbing multiple influence sources. Rather than resolving all conflicts silently, the system should identify, classify, and surface them so the user has awareness and can intervene when appropriate.

**Types of conflicts to surface:**

**Goal-to-goal conflicts**: Two active goals create competing demands on the same resources or push the planner profile in opposing directions. Example: "Build new reporting feature" competes with "Harden current functionality" for the same workers and the planner has deprioritized new features to serve the hardening goal.

**Goal-to-reality conflicts**: A goal's intent is undermined by ground-truth conditions. Example: "Focus on testing" is the directive, but worker feedback reveals that core modules are too unstable to test meaningfully — the system is spending most of its effort on bug fixes that weren't anticipated.

**Dependency conflicts**: Work items have circular, contradictory, or unresolvable dependency chains. Example: Task A requires Task B's output, but Task B was defined assuming Task A was already complete.

**Resource conflicts**: The current plan requires capabilities or compute that exceed what's available. Example: Two high-priority tasks both need the same specialized worker, or a task requires cloud compute that isn't currently accessible.

**How conflicts are surfaced:**

Each conflict is presented with:
- What is in tension (the specific goals, tasks, or resources involved)
- How the planner is currently handling it (which side it favored and why)
- What the user could do to resolve it (adjust a goal, provide clarification, accept the tradeoff)
- The decision trace that led to the conflict being identified (see Section 11)

The user can respond to conflicts by issuing new goals, adjusting existing goal language, or explicitly accepting the planner's resolution — all of which feed back into the planner profile.

---

## 11. Decision Traceability

The system must be able to answer "why" at any point — why is this task in this bucket, why did the profile shift, why was this conflict resolved this way. Full narration of every micro-decision would be noise. Instead, the system maintains **decision-point traceability**: a structured log of meaningful planning decisions and the reasoning behind them.

### 11.1 What Gets Traced

A trace is recorded at each **decision point** — a moment where the planner made a choice that changed the execution plan or its own profile. Decision points include:

- **Profile shifts**: the planner profile was updated due to a new goal, worker feedback, or resource change
- **Bucket reorganizations**: the priority bucket structure was redefined or buckets were re-ranked
- **Task movement**: a task was moved between buckets or significantly re-prioritized within a bucket
- **Conflict identification**: the planner identified a tension it couldn't fully resolve within its current profile
- **Conflict resolution**: the planner chose a side in a conflict or the user provided resolution
- **Worker assignment**: a task was assigned to a specific worker (particularly when the choice wasn't obvious)

### 11.2 Trace Structure

Each trace entry captures:

- **Trigger**: what initiated the decision (a new goal, a worker challenge, a dependency resolution, a resource event)
- **Context**: the relevant state at the time — which profile was active, what the bucket structure looked like, what information was available
- **Decision**: what the planner decided — what changed in the profile, the buckets, or the assignments
- **Key factors**: the 2-3 most important reasons the planner made this choice over alternatives — expressed in terms of ontology weights, policy rules, or conflict tradeoffs
- **Impact scope**: what downstream effects this decision had — which tasks were affected, which buckets shifted

### 11.3 How Traceability Is Used

**For the user (via the communication substrate):** Traces provide context when the system surfaces information. A conflict comes with the trace of how it was identified. A status update can reference why a capability area was deprioritized. The user can ask "why is this parked?" and get a traceable answer, not just the current state.

**For the planner itself:** The trace log gives the planner a form of self-awareness about its own decision history. When reconciling a new goal against existing plans, the planner can reference previous profile shifts to maintain consistency or recognize when it's oscillating. This is a lightweight form of institutional memory without requiring the planner to be a learning system.

**For system debugging and refinement:** During early development and iteration, the trace log is the primary tool for understanding whether the planner is making good decisions. If planning quality is poor, the traces show where reasoning went wrong.

---

## 12. Key Design Risks and Open Questions

**Characterization quality is the single biggest risk.** Everything downstream depends on work items being richly and accurately characterized. If characterization is shallow or inconsistent, the ontology tags are unreliable, dependencies are missed, and the planner operates on a distorted view of reality.

**Profile interpretation is high-leverage and underspecified.** The translation from a natural language goal to a structured planner profile (weights, policies, confidence bands) is where much of the system's intelligence lives. The fidelity of this interpretation directly determines planning quality.

**Bucket boundary definitions require careful design.** Buckets that cut across the ontology are more powerful but harder to define programmatically. The logic for "what makes a coherent strategic grouping" needs to be robust.

**Multi-goal reconciliation is complex.** When multiple active goals compete, the planner must balance them. The framework describes this conceptually (profile reconciliation, confidence bands) but the specific mechanics of multi-goal resolution need detailed design.

**Worker feedback volume management.** Even with 2-3 workers, feedback signals can create micro-reorganization pressure. The planner needs a mechanism to batch or prioritize feedback signals to avoid thrashing. This concern will intensify at scale but should be addressed in the initial design.

**Conflict resolution authority boundaries.** The system needs clear rules for which conflicts the planner resolves autonomously and which get surfaced to the user. Over-surfacing creates noise and decision fatigue. Under-surfacing makes the system opaque. The classification of conflict types (goal-to-goal, goal-to-reality, dependency, resource) provides a starting framework, but thresholds for surfacing vs. autonomous resolution need design.

**Traceability cost vs. value.** Decision-point tracing adds overhead. In early development with 2-3 workers, the volume is manageable and the debugging value is high. The trace structure needs to be designed lean enough that it doesn't become a scaling bottleneck later, while rich enough to be genuinely useful now.

**Resource opportunity integration (future).** The third influence channel is acknowledged but deferred. Its integration will require the planner profile to support transient overrides that don't permanently distort the strategic frame.

**Scale concerns (deferred).** Load balancing across many agents, agent pool management, parallel execution coordination, and the transition from small-pool to large-pool distribution logic are deferred until the core planning model is validated with 2-3 workers.
