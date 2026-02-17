# Agent Marketplace & Orchestration Platform

## Overview

A platform for discovering, assembling, and executing AI agent teams to solve business processes. The system combines a marketplace for agent/tool discovery with a distributed orchestration engine that enables agents to self-organize around goals without predefined workflows.

---

## Agent-to-Agent (A2A) Protocol Integration

This platform leverages the A2A protocol standard for inter-instance agent communication. The Serving Component acts as an A2A broker, enabling agents to communicate across distributed orchestration engine instances without requiring direct peer-to-peer connections.

**Key A2A Features Used:**
- **Agent Cards:** Agents publish standardized JSON metadata describing capabilities, endpoints, and authentication requirements
- **Asynchronous Communication:** Push notifications and task status updates enable coordination across disconnected instances
- **Task Management:** A2A task states (submitted, working, input-required, completed, failed, canceled) map to execution plan tracking
- **Broker-Mediated Routing:** The Serving Component translates between internal orchestration messages and A2A protocol for cross-instance communication

**Architecture Benefits:**
- Enables interoperability with external A2A-compatible agents
- Supports distributed execution without requiring persistent connections
- Provides standardized discovery mechanism via Agent Cards
- Allows hybrid deployment across cloud and edge devices

---

## Core Components

### Marketplace

A registry of agent and tool metadata that enables discovery and selection.

**Contents:**
- Agent skill descriptions and capabilities
- Tool definitions (MCP tools for external integration, ecosystem functions for internal use)
- Data requirements and resource dependencies
- Agent groupings suggested by publishers
- Performance metrics and usage data (future)
- Monetization hooks (future)

**Access Model:**
- Orchestration engine owners control which marketplaces their instances can access
- Businesses can whitelist/blacklist specific agents or tools
- Exclusive agents/tools can be scoped to specific organizations

**Publishing:**
- End users publish agents initially
- Agents may generate other agents in the future, with overlap prevention gates

---

### Orchestration Engine

A two-part system for executing agent workloads.

**Compute Engine (Local):**
- Runs agent processes within local scope
- Manages agent lifecycle for a session
- Handles tool invocations
- Maintains session state

**Serving Component (A2A Broker):**
- Manages compute engine instance registrations
- Brokers connections between engine instances (A↔B) using A2A protocol
- Maintains marketplace connections
- Distributes relevant information to registered instances
- Translates between internal orchestration protocol and A2A messages for inter-instance communication
- Handles A2A Agent Card discovery and capability routing

**Deployment Model:**
- Hybrid: runs in cloud and on personal devices
- Instances register with the Serving component, which facilitates communication between instances using A2A protocol
- No direct peer-to-peer communication between compute engines
- A2A-compatible for inter-instance agent invocation and external agent integration
- No leader election or complex failover (initial version)

---

### Agents

**Coordinating Agents:**
- Marketplace-aware
- Decompose business processes into executable plans
- Assemble and manage teams of specialized agents
- Specializations include: project management, industry expertise, business analysis, current team awareness, subject matter expertise

**Specialized Agents:**
- Not marketplace-aware
- Focused on specific skills
- Receive work from coordinating agents, return results
- Can hold limited ephemeral state

**Characteristics:**
- Non-deterministic (LLM-backed)
- Invoke tools as needed
- Do not negotiate or vote on task assignment

---

### Tools

- Deterministic utilities (mostly)
- Two types: MCP tools (external proxies), ecosystem functions (internal)
- Available to agents based on marketplace/access rules
- Can hold limited state

---

## Execution Model

### Session Lifecycle

1. User submits goal (text, documents, structured definitions like Git issues or test cases)
2. Coordinating agent group receives goal
3. Coordinators decompose goal and select agents from marketplace
4. Execution pipeline is created and managed
5. Specialized agents execute tasks, invoke tools, return results
6. Coordinating agents track progress, handle gaps, assemble final output
7. Session completes; state is discarded (external systems persist business data)

### Session Boundaries

- One session = one business process instance
- State is ephemeral within the agent system
- Business data persists in external applications/databases, queried as needed

### User-Designated Agents

- Users can mandate specific agents participate in a session
- These agents receive high priority or guaranteed placement
- Useful for testing new agents or enforcing organizational standards
- Coordinators place them in best-fit roles; system can report on their contribution level

---

## Key Design Challenges & Proposed Solutions

### 1. Pipeline/Workflow Representation

**Problem:** Coordinating agents create execution plans, but there's no defined structure for what that plan looks like or how it's tracked across distributed agents.

**Proposed Solution:**

Define a lightweight execution plan schema that coordinating agents produce:

- **Plan structure:** Directed graph of tasks with dependencies, assigned agents, expected inputs/outputs, and status
- **Plan ownership:** The coordinating agent group holds and updates the plan as execution progresses
- **Plan visibility:** The plan is the source of truth for what's been done, what's pending, and what's blocked
- **Execution tracking:** Each task node has states (pending, running, completed, failed, blocked) updated by the responsible agent or engine

This keeps workflows dynamic (agents generate the plan) while providing enough structure for tracking and inter-instance coordination.

---

### 2. Boundary Between Coordinating Agents and Orchestration Engine

**Problem:** Unclear division of responsibility — who instantiates agents, routes messages, tracks completion?

**Proposed Solution:**

Establish a clear contract:

**Coordinating agents are responsible for:**
- Deciding which agents to involve
- Producing the execution plan
- Interpreting results and deciding next steps
- Handling incomplete solutions or gaps

**Orchestration engine is responsible for:**
- Instantiating agent processes based on coordinator requests
- Routing inputs/outputs between agents (using A2A protocol for inter-instance communication)
- Reporting task status back to coordinators
- Managing compute resources and tool access
- Publishing and maintaining Agent Cards for discoverable agents

The engine is infrastructure; it doesn't make decisions about *what* to run, only *how* to run it. Coordinators request agent invocations through a defined API, and the engine handles the mechanics. When agents need to communicate across instances, the Serving Component translates these requests into A2A protocol messages.

---

### 3. Inter-Instance State Sharing

**Problem:** Sessions may span multiple engine instances when resources are distributed, but state is ephemeral with no shared persistence layer.

**Proposed Solution:**

Introduce a session state service (or protocol):

- **Session state store:** A lightweight, shared state layer accessible to all engine instances participating in a session
- **State contents:** Execution plan, task statuses, intermediate results, context summaries
- **Write responsibility:** The coordinating agents (or their host engine) are authoritative; other instances read and report back
- **Implementation options:** Could be a dedicated service, a designated "primary" instance for the session, or a replicated state protocol between instances
- **A2A Integration:** While A2A handles message passing between agents, session state remains internal to the orchestration system. Cross-instance agents communicate via A2A task messages, but execution plan state is maintained by the session host and accessed through internal APIs.

For the initial version, keep it simple: designate one instance as the session host, and have other instances push results back to it via A2A task completion messages. Avoid full distributed consensus until it's proven necessary.

---

### 4. Marketplace Overlap Prevention

**Problem:** If multiple agents have similar skills, coordinators can't differentiate, and selection becomes arbitrary. Need a gate to prevent excessive overlap.

**Proposed Solution:**

Multi-layer overlap detection:

- **Capability tagging:** Require agents to declare capabilities using a controlled vocabulary (not just free-text descriptions)
- **Semantic similarity check:** On publish, compare new agent's description and tags against existing agents; flag if similarity exceeds threshold
- **Differentiation requirements:** If flagged, require publisher to clarify distinguishing factors (different tool access, domain specialization, performance characteristics)
- **Human review (optional):** For contested cases or high-value marketplace segments

Additionally, expose differentiation data to coordinating agents so they can make informed selections (e.g., "Agent A is faster but less accurate than Agent B for this task type").

---

## A2A Protocol Integration Architecture

### Communication Layers

The orchestration system uses a hybrid communication model:

**Internal Communication (Within Instance):**
- Direct function calls between agents and tools
- Shared memory access for session state
- Synchronous execution where appropriate

**Inter-Instance Communication (Across Instances):**
- A2A protocol messages routed through Serving Component
- Asynchronous task-based communication
- Agent Card discovery for capability matching

### Agent Card Management

**Coordinating Agents:**
- Published as A2A-compatible agents with Agent Cards
- Exposed for cross-instance invocation
- Agent Cards include: capabilities, supported business process types, authentication requirements

**Specialized Agents:**
- Not directly exposed via A2A (internal to orchestration engine)
- Invoked by coordinating agents within the same instance
- May be exposed via A2A in future versions for direct external access

**Tools:**
- Remain internal to the orchestration system
- Not exposed as A2A agents (initial version)
- Accessed only by agents within the same instance

### A2A Message Flow

1. **Cross-Instance Agent Invocation:**
   - Coordinating agent on Instance A requests specialized work
   - If target agent is on Instance B, request goes to local Serving Component
   - Serving Component translates to A2A task message
   - Message routed to Instance B's Serving Component
   - Instance B instantiates agent and executes task
   - Results returned via A2A task completion message

2. **Task State Synchronization:**
   - A2A task states map to internal execution plan states
   - Serving Component updates session state based on A2A messages
   - Coordinating agents query local state, unaware of A2A translation

3. **Agent Discovery:**
   - Marketplace publishes Agent Cards for all registered agents
   - Coordinating agents query marketplace for capabilities
   - Serving Component fetches Agent Cards and caches locally
   - Selection happens at orchestration layer, invocation uses A2A

### Security and Authentication

- **Inter-Instance:** OAuth 2.0 and mutual TLS for A2A messages
- **Intra-Instance:** Trust boundary within compute engine
- **Marketplace Access:** API keys and access control lists
- **Agent Cards:** Include authentication requirements for invocation

### Observability

- **A2A Message Tracing:** All cross-instance messages logged with correlation IDs
- **Task State Tracking:** A2A task states recorded in session history
- **Performance Metrics:** Latency and success rates for inter-instance invocations
- **Debugging:** A2A message payloads available for session replay

---

## State Management Approach

State is managed at three levels:

| Level | Scope | Persistence | Contents |
|-------|-------|-------------|----------|
| Tool | Single invocation | Ephemeral | Execution context, intermediate data |
| Agent | Single session | Ephemeral | Task context, local decisions |
| Session | One business process | Ephemeral (external systems persist business data) | Execution plan, results, context summaries |

**Intelligent state management includes:**
- Context summarization to reduce token usage
- Prompt caching for repeated patterns
- Relevance filtering to route right information to right agents
- Resource mapping to match tasks to available/optimal agents

---

## Out of Scope (Initial Version)

- Automatic failover and session recovery
- Leader election between engine instances
- Monetization and billing
- Agent-generated agents
- Complex negotiation or voting between agents

These are acknowledged as future concerns but intentionally deferred to keep the initial system simple and functional.

---

## Open Questions for Future Work

1. **Queuing:** How are sessions queued when demand exceeds capacity?
2. **Billing in multi-instance scenarios:** If execution spans instances owned by different parties, who pays? How are A2A invocations metered?
3. **Agent versioning:** How are agent updates handled without breaking existing sessions? How do Agent Cards communicate version compatibility?
4. **Trust and verification:** How do users know an agent does what it claims? How are Agent Cards verified for authenticity?
5. **Debugging and observability:** How do users inspect what went wrong in a failed session? How are A2A message traces presented to users?
6. **A2A Tool Integration:** Should tools be exposed as A2A agents for external access? What are the security implications?
7. **External Agent Integration:** How do third-party A2A-compatible agents integrate with the marketplace? What validation is required?

---

## Summary

This platform bets on a few key ideas:

- Agents should organize themselves around goals, not be shoehorned into predefined workflows
- Coordination is a specialized skill that dedicated agents handle, freeing specialized agents to focus
- Distribution across devices and cloud should be transparent to the user
- Simplicity now, resilience later — avoid overengineering before the core model is proven

The main risks are in the underspecified areas: pipeline representation, engine/agent boundaries, and inter-instance state. The proposed solutions above are starting points, not final answers. They'll need validation through prototyping.
