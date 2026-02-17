# Execution Pipeline Architecture

## Overview

This document defines the **Execution Pipeline** - the orchestration layer that manages how business requests are decomposed into activities and executed through facilitated collaboration.

## Evolution: From Pipeline to Facilitated Process

### Version 0.1.8 - Traditional Pipeline (Current Implementation)
- Predetermined steps with fixed dependencies
- Upfront decomposition and planning
- Sequential/parallel execution model
- Good for well-defined workflows

### Version 0.2.x - Facilitated Process (This Document)
- Dynamic activities that emerge through conversation
- Dependencies discovered naturally
- Hierarchies form as complexity is revealed
- Reevaluation is normal and expected
- Focus on quality and goal achievement over efficiency

**This document describes the 0.2.x vision - a fundamental paradigm shift.**

## Core Concept: Distributed Coordination

Unlike traditional pipelines, this system uses a **coordinating team** where each member has a specific role:

1. **Process Mapper** - Builds and evolves the process map
2. **Agent Selector** - Determines who needs to be involved
3. **Activity Facilitator** - Guides individual activity conversations
4. **Consistency Manager** - Detects contradictions and inconsistencies
5. **Progress Reporter** - Tracks and reports overall status
6. **Result Synthesizer** - Assembles final deliverables

**Key Principle**: No single agent is all-knowing. Intelligence is distributed.

## The Coordinating Team (Distributed Intelligence)

The coordinating team consists of **specialized coordinating agents**, each with a focused responsibility. No single agent is omniscient.

### 1. Process Mapper Agent

**Role**: Builds and evolves the process map structure

**Responsibilities**:
- Create initial process map from business goal
- Propose initial activities (high-level)
- Evolve the map as understanding deepens
- Handle map restructuring (split/merge activities, create hierarchies)
- Track map versions and changes
- Manage sub-process creation

**NOT Responsible For**:
- Selecting agents (Agent Selector does this)
- Facilitating activities (Activity Facilitator does this)
- Detecting inconsistencies (Consistency Manager does this)
- Knowing all domain details (learns from activity outcomes)

**Example Interaction**:
```
Input: Business goal "Increase customer retention by 20%"

Process Mapper:
"I propose we start with three activities:
1. Understand current retention metrics
2. Identify retention drivers
3. Develop improvement strategies

These may evolve as we learn more."
```

### 2. Agent Selector Agent

**Role**: Determines who needs to be involved in each activity

**Responsibilities**:
- Analyze activity goals and identify needed expertise
- Query marketplace for agents with relevant capabilities
- Match agent capabilities to activity needs
- Consider agent availability and workload
- Suggest primary and backup participants
- Adapt participant selection based on activity evolution

**Decision Factors**:
- Activity goal and complexity
- Required capabilities/expertise
- Domain knowledge needed
- Previous activity context
- Agent specialization depth
- Cross-functional needs

**NOT Responsible For**:
- Executing the activity (Activity Facilitator does this)
- Building the overall process (Process Mapper does this)

**Example Interaction**:
```
Input: Activity "Understand current retention metrics"

Agent Selector queries marketplace:
- Searches for: ["data_analysis", "customer_metrics", "reporting"]
- Finds: DataAnalystAgent, CustomerInsightsAgent, MetricsReporterAgent

Agent Selector recommends:
"Primary: DataAnalystAgent (has data access + analysis)
 Backup: CustomerInsightsAgent (specialized in retention)
 Optional: MetricsReporterAgent (if visualization needed)"

Reasoning: "DataAnalystAgent covers core need. CustomerInsights
provides domain depth if we need interpretation."
```

### 3. Activity Facilitator Agent

**Role**: Guides one activity conversation to goal completion

**Responsibilities**:
- Frame the activity for participants
- Ask clarifying questions
- Guide the conversation forward
- Determine if activity goal is met (for THIS activity only)
- Identify blockers or missing information
- Document activity outcomes and decisions
- Identify dependencies that emerge during the conversation

**NOT Responsible For**:
- Overall process consistency (Consistency Manager does this)
- Process map changes (Process Mapper does this)
- Selecting participants (Agent Selector does this)
- Knowing if this contradicts earlier activities (stays focused on this activity)

**Key Principle**: The facilitator is **activity-focused**, not omniscient. They guide THIS conversation to completion.

**Example Interaction**:
```
Facilitator → DataAnalystAgent:
"We need to understand current retention metrics. What data do you need?"

DataAnalystAgent:
"I need customer database access and timeframe."

Facilitator:
"Timeframe is last 12 months. Do you have database access?"

DataAnalystAgent:
"No, I need credentials or a data export."

Facilitator (identifying blocker):
"We're blocked on data access. This activity cannot proceed without it."

[Reports blocker - Process Mapper creates new activity: "Obtain data access"]
```

### 4. Consistency Manager Agent

**Role**: Detects contradictions and inconsistencies across activities

**Responsibilities**:
- Monitor activity outputs for contradictions
- Compare new findings against earlier decisions
- Identify logical inconsistencies
- Flag assumption violations
- Recommend reconciliation activities
- Track resolution of inconsistencies

**Monitoring Patterns**:
- Conflicting data (Activity A says X, Activity B says not-X)
- Violated assumptions (Activity C assumed Y, Activity D proves Y false)
- Scope creep (Activity E expands beyond original goal)
- Circular dependencies (Activity F needs G which needs F)

**NOT Responsible For**:
- Resolving inconsistencies (recommends reconciliation activities)
- Building the process map (Process Mapper does this)
- Facilitating activities (Activity Facilitator does this)

**Example Interaction**:
```
Consistency Manager observes:

Activity 3 output: "Current retention rate is 65%"
Activity 7 output: "Based on 70% retention rate..."

Consistency Manager flags:
"⚠️ INCONSISTENCY DETECTED
Activity 3 and Activity 7 use different retention rates (65% vs 70%).

Recommendation: Create reconciliation activity to:
1. Verify which rate is correct
2. Update dependent activities
3. Document which timeframe/segment each rate applies to"
```

### 5. Progress Reporter Agent

**Role**: Tracks and reports overall session status

**Responsibilities**:
- Monitor activity statuses across process map
- Calculate overall completion percentage
- Identify bottlenecks and critical path
- Generate progress summaries
- Alert on stalled activities
- Provide time estimates (if possible)
- Report to stakeholders

**Reporting Dimensions**:
- Activities: proposed, in-progress, goal-met, blocked, revisited
- Dependencies: satisfied, pending, discovered
- Blockers: data access, expertise gaps, external dependencies
- Reevaluations: how many times map has been restructured

**NOT Responsible For**:
- Determining if activities are complete (Activity Facilitator does this)
- Restructuring the process (Process Mapper does this)
- Fixing blockers (identifies them only)

**Example Report**:
```
Progress Reporter generates:

📊 SESSION PROGRESS REPORT
Business Goal: "Increase customer retention by 20%"
Session Duration: 2 hours 15 minutes

Activity Status:
✅ Completed: 5 activities
🔄 In Progress: 2 activities  
⏸️  Blocked: 1 activity (data access needed)
📋 Proposed: 3 activities

Process Map Evolution:
- Map Version: 4 (3 reevaluations)
- Activities Added: 4 (emerged during facilitation)
- Dependencies Discovered: 7

Current Focus:
- Activity 8: "Analyze high-value customer segment" (in progress)
- Activity 9: "Identify at-risk indicators" (in progress)

Next Up:
- Activity 10: "Develop retention strategies" (waiting on Activities 8, 9)

Blockers:
- Activity 6 blocked on CRM data access (escalated)
```

### 6. Result Synthesizer Agent

**Role**: Assembles final deliverables from all activity outputs

**Responsibilities**:
- Collect outputs from completed activities
- Identify key findings and insights
- Create coherent narrative connecting results
- Generate executive summary
- Package supporting artifacts
- Validate completeness against original goal
- Add metadata (execution time, agents involved, etc.)

**NOT Responsible For**:
- Individual activity execution
- Process structure
- Determining if activities are complete

**Example Output**:
```
Result Synthesizer creates:

📦 FINAL DELIVERABLE

Executive Summary:
"Analysis of customer retention data reveals..."

Key Findings:
1. Current retention rate: 65% (Activity 3)
2. Primary driver: Customer support response time (Activity 5)
3. High-value segment retention: 78% (Activity 8)
4. At-risk indicators: Payment delays, reduced usage (Activity 9)

Recommendations:
[Based on Activity 10 outputs]

Supporting Data:
- 12 data visualizations
- 3 statistical analyses  
- Customer segment profiles

Metadata:
- Session Duration: 3 hours 42 minutes
- Activities Completed: 12
- Agents Involved: 8
- Process Reevaluations: 3
```

## Coordinating Team Collaboration Flow

```
Business Goal
    ↓
[Process Mapper] → Creates initial process map with proposed activities
    ↓
[Agent Selector] → Recommends participants for Activity 1
    ↓
[Activity Facilitator] → Guides Activity 1 conversation
    ↓                           ↓
[Consistency Manager] ←────────┤ (monitors for contradictions)
[Progress Reporter] ←────────────┘ (tracks status)
    ↓
Activity 1 completes → New understanding emerges
    ↓
[Process Mapper] → Updates process map (new activities, dependencies)
    ↓
[Agent Selector] → Recommends participants for Activity 2
    ↓
Continue until all activities goal-met...
    ↓
[Result Synthesizer] → Assembles final deliverable
```

## Conceptual Architecture

### The Full Stack (Refined)

```
┌─────────────────────────────────────────────────────┐
│  BUSINESS REQUEST                                   │
│  "Increase customer retention by 20%"               │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  1. SESSION (Owning Entity)                         │
│     • session_id: "sess-001"                        │
│     • business_goal: "Increase retention by 20%"    │
│     • status: "in_progress"                         │
│     • created_by: "user-123"                        │
│     • owns: ProcessMap                              │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  2. PROCESS MAP (Living Document)                   │
│     • map_id: "map-001"                            │
│     • session_id: "sess-001"                        │
│     • map_version: 1 (evolves)                      │
│     • activities: {} (emerge over time)             │
│     • activity_graph: Graph (dependencies)          │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  3. COORDINATING TEAM (Distributed)                 │
│     • Process Mapper - Builds/evolves map           │
│     • Agent Selector - Chooses who joins      │
│     • Activity Facilitator - Guides conversations   │
│     • Consistency Manager - Detects contradictions │
│     • Progress Reporter - Tracks overall status     │
│     • Result Synthesizer - Assembles deliverables   │
│     • Has access to:                                │
│       - Marketplace agent catalog                   │
│       - Available compute instances                 │
│       - Session context and history                 │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  4. PROBLEM DECOMPOSITION                           │
│     Business Analyst Agent analyzes:                │
│     • What data is needed?                          │
│     • What analysis is required?                    │
│     • What output format?                           │
│     • What's the success criteria?                  │
│                                                     │
│     Output: Requirements breakdown                  │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  5. AGENT SELECTION                                 │
│     Resource Agent queries:                         │
│     • Marketplace for capable agents                │
│     • Compute registry for availability             │
│     • Returns list of suitable agents               │
│                                                     │
│     Output: Available agents with capabilities      │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  6. PIPELINE BUILDING                               │
│     Pipeline Agent creates structured plan:         │
│     • Step 1: data-analyst-v1                       │
│       - Input: Q4 sales CSV                         │
│       - Output: Analysis results                    │
│       - Dependencies: none                          │
│       - Target: compute-001                         │
│     • Step 2: content-writer-v1                     │
│       - Input: Analysis from Step 1                 │
│       - Output: Executive report                    │
│       - Dependencies: [Step 1]                      │
│       - Target: compute-002                         │
│                                                     │
│     Output: Complete ExecutionPipeline              │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  7. PIPELINE SUBMISSION TO SERVING                  │
│     Pipeline Agent submits:                         │
│     POST /api/v1/sessions/{session_id}/pipeline     │
│     {                                               │
│       "steps": [...],                               │
│       "dependencies": {...},                        │
│       "metadata": {...}                             │
│     }                                               │
│                                                     │
│     Serving validates and accepts pipeline          │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  8. PIPELINE EXECUTION (Serving)                    │
│     For each step in pipeline:                      │
│     • Check dependencies satisfied                  │
│     • Route to target compute instance              │
│     • Execute agent with context                    │
│     • Store result in session                       │
│     • Mark step complete                            │
│     • Proceed to next step                          │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  9. SESSION COMPLETION                              │
│     • All pipeline steps executed                   │
│     • Results aggregated                            │
│     • Session marked "completed"                    │
│     • Final output returned to user                 │
└─────────────────────────────────────────────────────┘
```

## Participant Selection Process (Detailed)

### How Agent Selector Works

The **Agent Selector** is a specialized coordinating agent responsible for determining who should participate in each activity.

#### Step 1: Activity Analysis

```python
def analyze_activity(self, activity: Activity) -> ActivityRequirements:
    """Analyze what the activity needs"""
    
    # Parse activity goal to identify:
    - Core objective (what needs to be accomplished)
    - Domain area (customer analytics, financial modeling, etc.)
    - Required capabilities (data_analysis, visualization, writing, etc.)
    - Technical needs (database access, API calls, computation)
    - Context from previous activities (what's already known)
    - Complexity level (simple, moderate, complex)
    
    return ActivityRequirements(
        core_capabilities=["data_analysis", "customer_metrics"],
        domain_expertise=["customer_retention"],
        technical_requirements=["database_read"],
        context_needs=["prior_activity_outputs"],
        complexity="moderate"
    )
```

#### Step 2: Marketplace Query

```python
async def query_marketplace(self, requirements: ActivityRequirements) -> List[CandidateAgent]:
    """Find agents that could fulfill the requirements"""
    
    # Query marketplace with filters
    marketplace_query = {
        "capabilities": requirements.core_capabilities,
        "domain": requirements.domain_expertise,
        "tools_access": requirements.technical_requirements,
        "status": "active",
        "available": True  # If tracking availability
    }
    
    # Query all connected marketplaces
    candidates = []
    for marketplace_url in self.config.marketplace_urls:
        results = await self.marketplace_client.search(
            marketplace_url, 
            marketplace_query
        )
        candidates.extend(results)
    
    return candidates
```

#### Step 3: Candidate Evaluation

```python
def evaluate_candidates(self, candidates: List[CandidateAgent], 
                       requirements: ActivityRequirements,
                       context: ProcessMap) -> List[ScoredCandidate]:
    """Score and rank candidates"""
    
    scored = []
    for candidate in candidates:
        score = 0
        
        # Capability match (0-40 points)
        matched_caps = set(candidate.capabilities) & set(requirements.core_capabilities)
        score += len(matched_caps) * 10
        
        # Domain expertise (0-30 points)
        if requirements.domain_expertise:
            if candidate.has_domain(requirements.domain_expertise):
                score += 30
        
        # Specialization depth (0-15 points)
        # More specialized agents score higher
        if len(candidate.capabilities) <= 3:
            score += 15
        elif len(candidate.capabilities) <= 5:
            score += 10
        else:
            score += 5
        
        # Previous success in session (0-10 points)
        if candidate.id in context.successful_agents:
            score += 10
        
        # Availability / workload (0-5 points)
        if candidate.current_workload < 0.7:
            score += 5
        
        scored.append(ScoredCandidate(
            agent=candidate,
            score=score,
            match_reasons=[...],  # Why this agent fits
            gaps=[...]  # What this agent doesn't cover
        ))
    
    # Sort by score descending
    scored.sort(key=lambda x: x.score, reverse=True)
    return scored
```

#### Step 4: Participant Recommendation

```python
def recommend_participants(self, scored_candidates: List[ScoredCandidate],
                          requirements: ActivityRequirements) -> ParticipantRecommendation:
    """Create final recommendation"""
    
    # Primary participant (highest score)
    primary = scored_candidates[0]
    
    # Backup participant (second highest, or different specialization)
    backup = scored_candidates[1] if len(scored_candidates) > 1 else None
    
    # Optional participants (if activity is complex or multi-faceted)
    optional = []
    if requirements.complexity == "complex":
        # Look for complementary skills
        for candidate in scored_candidates[2:]:
            if has_complementary_skills(candidate, primary):
                optional.append(candidate)
    
    return ParticipantRecommendation(
        primary=primary,
        backup=backup,
        optional=optional,
        reasoning=self.explain_selection(primary, requirements),
        alternatives=scored_candidates[1:4]  # Show alternatives
    )
```

#### Step 5: Adaptive Re-selection

```python
def adapt_participants(self, activity: Activity, 
                      facilitation_progress: FacilitationProgress) -> Optional[ParticipantChange]:
    """Adapt participants if activity evolves"""
    
    # Monitor facilitation progress
    if facilitation_progress.new_expertise_needed:
        # Activity revealed need for additional expertise
        new_requirements = self.extract_new_requirements(facilitation_progress)
        additional_agent = self.find_agent_for_gap(new_requirements)
        
        return ParticipantChange(
            action="add",
            agent=additional_agent,
            reason="Activity revealed need for additional expertise"
        )
    
    elif facilitation_progress.participant_ineffective:
        # Current participant isn't working out
        original_requirements = activity.requirements
        replacement = self.find_alternative(original_requirements, 
                                           exclude=[facilitation_progress.ineffective_agent])
        
        return ParticipantChange(
            action="replace",
            remove=facilitation_progress.ineffective_agent,
            add=replacement,
            reason="Participant unable to fulfill activity needs"
        )
    
    return None  # No changes needed
```

### Example: Complete Participant Selection Flow

```
Activity: "Understand current customer retention metrics"

1. ACTIVITY ANALYSIS
   Agent Selector analyzes:
   - Core objective: Extract and analyze retention data
   - Required capabilities: [data_analysis, customer_metrics, database_read]
   - Domain: customer_retention
   - Complexity: moderate

2. MARKETPLACE QUERY
   Searches 2 connected marketplaces:
   - Found 8 candidates with data_analysis capability
   - 5 also have customer_metrics
   - 3 have database_read tool access

3. CANDIDATE EVALUATION
   Scored candidates:
   
   Rank 1: DataAnalystAgent (score: 85)
     ✅ Has all required capabilities
     ✅ Database access
     ✅ Previously successful in this session
     ✅ Specialized (only 3 capabilities, all relevant)
     ✅ Low workload (30%)
   
   Rank 2: CustomerInsightsAgent (score: 75)
     ✅ Has data_analysis + customer_metrics
     ✅ Domain expert in retention
     ❌ No database_read (would need data export)
     ✅ Specialized
   
   Rank 3: GeneralAnalyticsAgent (score: 55)
     ✅ Has data_analysis
     ✅ Database access
     ❌ No customer domain expertise
     ❌ Less specialized (8 capabilities)

4. RECOMMENDATION
   Agent Selector recommends:
   
   "PRIMARY: DataAnalystAgent
    - Best overall match (85/100)
    - Has all required capabilities
    - Database access means no blockers
    - Proven track record in this session
   
    BACKUP: CustomerInsightsAgent  
    - Strong domain expertise (retention specialist)
    - Use if DataAnalyst unavailable or if domain depth needed
    - Note: Would require data export (no direct DB access)
   
    OPTIONAL: None
    - Activity is moderate complexity
    - Primary agent should be sufficient
   
    REASONING:
    DataAnalystAgent is the clear choice - has complete capability 
    coverage, direct database access eliminates potential blocker, 
    and has already proven effective in Activity 3. CustomerInsights 
    is strong backup with deeper retention expertise if needed."

5. FACILITATION BEGINS
   Activity Facilitator engages DataAnalystAgent...
   
   [During facilitation, DataAnalyst asks about customer segmentation]
   
6. ADAPTIVE RE-SELECTION
   Agent Selector monitors:
   - Facilitation reveals need for "customer_segmentation" expertise
   - DataAnalystAgent can do basic segmentation but not advanced
   
   Agent Selector recommends:
   "ADD OPTIONAL: SegmentationSpecialistAgent
    - Has advanced customer_segmentation capability
    - Can provide segmentation framework to DataAnalyst
    - Keep DataAnalyst as primary (doing the actual analysis)"
   
   Activity Facilitator brings in SegmentationSpecialist for 
   consultation, then continues with DataAnalyst...
```

## Data Models (Refined for Facilitated Process)

### Session

```python
class Session(BaseModel):
    """Owning entity for business request"""
    session_id: str
    user_id: Optional[str]
    business_goal: str  # High-level business objective
    status: SessionStatus  # initiated, in_progress, goal_achieved, failed
    process_map_id: str  # Link to process map
    context: Dict[str, Any]  # Session-level context
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any]

class SessionStatus(str, Enum):
    INITIATED = "initiated"  # Just started
    IN_PROGRESS = "in_progress"  # Activities being facilitated
    GOAL_ACHIEVED = "goal_achieved"  # Business goal met
    FAILED = "failed"  # Cannot complete
```

### Process Map

```python
class ProcessMap(BaseModel):
    """Evolving understanding of the process"""
    map_id: str
    session_id: str
    business_goal: str
    
    # Map evolution
    map_version: int  # Increments with restructuring
    activities: Dict[str, Activity]  # All activities by ID
    activity_graph: Graph  # Dependency relationships
    
    # Current state
    proposed_activities: List[str]  # Not started
    in_progress_activities: List[str]  # Currently being facilitated
    completed_activities: List[str]  # Goal met
    blocked_activities: List[str]  # Cannot proceed
    
    # Evolution tracking
    reevaluations: List[ReevaluationEvent]
    discovered_dependencies: List[Dependency]
    identified_gaps: List[Gap]
    
    # Metadata
    created_at: datetime
    updated_at: datetime
    created_by: str  # "process-mapper-v1"

class Activity(BaseModel):
    """A goal-oriented work conversation"""
    activity_id: str
    goal: str  # What this activity aims to accomplish
    description: Optional[str]  # Additional context
    status: ActivityStatus
    
    # Participants (evolves)
    assigned_agents: List[ParticipantAssignment]
    participant_history: List[ParticipantChange]  # Track changes
    
    # Relationships (discovered dynamically)
    depends_on: List[str]  # Activity IDs
    enables: List[str]  # What this unblocks
    parent_activity: Optional[str]  # If this is a sub-activity
    sub_activities: List[str]  # Hierarchies emerge
    
    # Facilitation
    facilitation_history: List[Exchange]  # Conversation record
    decisions_made: List[Decision]
    blockers: List[Blocker]
    
    # Outputs
    outputs: Dict[str, Any]  # What was produced
    key_findings: List[str]
    
    # Tracking
    proposed_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    revisit_count: int  # Times reevaluated
    
class ActivityStatus(str, Enum):
    PROPOSED = "proposed"  # Identified but not started
    IN_PROGRESS = "in_progress"  # Currently being facilitated
    GOAL_MET = "goal_met"  # Objective achieved
    BLOCKED = "blocked"  # Cannot proceed
    REVISIT = "revisit"  # Needs reevaluation

class ParticipantAssignment(BaseModel):
    """Who is assigned to an activity"""
    agent_id: str
    agent_name: str
    role: ParticipantRole  # primary, backup, optional
    capabilities: List[str]
    added_at: datetime
    added_by: str  # "participant-selector-v1"
    reason: str  # Why this agent was selected

class ParticipantRole(str, Enum):
    PRIMARY = "primary"  # Main participant
    BACKUP = "backup"  # Alternative if primary unavailable
    OPTIONAL = "optional"  # Additional expertise if needed
    CONSULTANT = "consultant"  # Brought in for specific question
```

### Facilitation Records

```python
class Exchange(BaseModel):
    """One interaction in activity facilitation"""
    exchange_id: str
    activity_id: str
    timestamp: datetime
    speaker: str  # Agent ID or "facilitator"
    message: str
    intent: ExchangeIntent
    
    # Outcomes
    outcome: Optional[ExchangeOutcome]
    new_understanding: Optional[str]
    decision_made: Optional[str]

class ExchangeIntent(str, Enum):
    FRAME = "frame"  # Set context for activity
    QUESTION = "question"  # Ask for information
    ANSWER = "answer"  # Provide information
    CLARIFY = "clarify"  # Seek clarification
    ASSESS = "assess"  # Check goal completion
    REDIRECT = "redirect"  # Change direction
    CONCLUDE = "conclude"  # Mark activity complete
    IDENTIFY_BLOCKER = "identify_blocker"  # Flag obstacle

class FacilitationResult(BaseModel):
    """Outcome of facilitating one activity"""
    activity_id: str
    status: ActivityStatus  # goal_met, blocked, revisit
    
    # What emerged
    outputs: Dict[str, Any]
    decisions: List[Decision]
    new_activities_discovered: List[Activity]
    dependencies_discovered: List[Dependency]
    inconsistencies_detected: List[Inconsistency]
    
    # If blocked
    blocker: Optional[Blocker]
    blocker_resolution_activity: Optional[Activity]
    
    # Metadata
    duration: timedelta
    exchange_count: int
    participants_involved: List[str]
```

### Coordinating Team Models

```python
class CoordinatingTeam(BaseModel):
    """The distributed coordinating team"""
    team_id: str
    session_id: str
    
    members: Dict[str, CoordinatingMember]  # By role
    
    # Team state
    current_focus: Optional[str]  # Current activity_id
    decisions_log: List[TeamDecision]
    
class CoordinatingMember(BaseModel):
    """One member of coordinating team"""
    role: CoordinatingRole
    agent_id: str
    agent_name: str
    active: bool

class CoordinatingRole(str, Enum):
    PROCESS_MAPPER = "process_mapper"
    AGENT_SELECTOR = "agent_selector"  
    ACTIVITY_FACILITATOR = "activity_facilitator"
    CONSISTENCY_MANAGER = "consistency_manager"
    PROGRESS_REPORTER = "progress_reporter"
    RESULT_SYNTHESIZER = "result_synthesizer"

class Inconsistency(BaseModel):
    """Detected contradiction"""
    inconsistency_id: str
    type: InconsistencyType
    description: str
    
    # What conflicts
    activity_1: str
    activity_1_claim: str
    activity_2: str  
    activity_2_claim: str
    
    # Detection
    detected_at: datetime
    detected_by: str  # "consistency-guardian-v1"
    severity: InconsistencySeverity
    
    # Resolution
    status: InconsistencyStatus
    resolution_activity: Optional[str]
    resolution: Optional[str]

class InconsistencyType(str, Enum):
    CONFLICTING_DATA = "conflicting_data"  # Different values
    VIOLATED_ASSUMPTION = "violated_assumption"  # Assumption proven false
    LOGICAL_CONTRADICTION = "logical_contradiction"  # Can't both be true
    SCOPE_DRIFT = "scope_drift"  # Wandered from goal
```

## Platform Component Responsibilities (Refined)

### Serving Component
**Role**: Lightweight routing and coordination broker

**Responsibilities:**
- Session lifecycle management
- Process map storage and versioning
- Activity state tracking
- Message routing between components
- Event bus for coordinating agent communication
- Marketplace integration (proxying queries)
- Compute instance registry and routing
- API endpoint hosting
- SSE/WebSocket support for real-time updates

**NOT Responsible For:**
- Executing ANY agents (ALL agents run in Compute)
- Heavy computation or LLM calls
- Deciding process structure (Process Mapper does this)
- Selecting participants (Agent Selector does this)
- Domain logic or business decisions

**Key Principle**: Serving is a lightweight broker. ALL agent execution (coordinating and specialized) happens in Compute components.

### Compute Component(s)
**Role**: Agent execution environment (ALL agents)

**Responsibilities:**
- Execute ALL agents (both coordinating and specialized)
- LLM integration (OpenAI, Anthropic, Mock)
- Tool invocation
- Resource management (CPU, memory, GPU)
- Local agent storage (coordinating + specialized)
- Registration with Serving
- Heartbeat maintenance
- Heavy computation and memory-intensive operations

**Agent Types Executed:**
- **Coordinating Agents**: Process Mapper, Agent Selector, Activity Facilitator, Consistency Manager, Progress Reporter, Result Synthesizer
- **Specialized Agents**: DataAnalyst, ContentWriter, CodeReviewer, etc.

**NOT Responsible For:**
- Routing messages between components (Serving does this)
- Storing process maps (Serving does this)
- Session management (Serving does this)

### Marketplace Component
**Role**: Agent discovery and capability catalog

**Responsibilities:**
- Agent metadata storage
- Capability-based search
- Agent versioning
- Access control
- Agent Card (A2A) publishing
- Performance metrics (future)

**NOT Responsible For:**
- Agent execution (Compute does this)
- Agent selection for activities (Agent Selector does this)
- Process orchestration (Serving does this)

### Process Mapper (Coordinating Agent - Runs in Compute)
**Role**: Process structure architect

**Execution Location**: Compute instance (heavy LLM use for planning)

**Owns:**
- Process map structure
- Activity definitions
- Map evolution and reevaluation

**Collaborates With:**
- Activity Facilitator (receives facilitation results)
- Consistency Manager (receives inconsistency flags)
- Progress Reporter (provides structure for reporting)

**Communication**: Via Serving's event bus (messages routed through Serving)

### Agent Selector (Coordinating Agent - Runs in Compute)
**Role**: Expertise matcher

**Execution Location**: Compute instance (LLM use for scoring/reasoning)

**Owns:**
- Participant recommendations
- Agent-activity matching logic
- Marketplace query strategy

**Collaborates With:**
- Process Mapper (receives new activities)
- Activity Facilitator (provides participants)
- Marketplace (queries via Serving proxy)

**Communication**: Via Serving's event bus (messages routed through Serving)

### Activity Facilitator (Coordinating Agent - Runs in Compute)
**Role**: Conversation guide

**Execution Location**: Compute instance (heavy LLM use for facilitation)

**Owns:**
- Individual activity facilitation
- Exchange management
- Goal assessment (for specific activity only)
- Blocker identification

**Collaborates With:**
- Agent Selector (receives participants)
- Process Mapper (reports outcomes and blockers)
- Consistency Manager (provides outputs for monitoring)
- Specialized Agents (engages them in conversation via Serving routing)

**Communication**: Via Serving's message routing

### Consistency Manager (Coordinating Agent - Runs in Compute)
**Role**: Quality assurance

**Execution Location**: Compute instance (LLM use for detecting contradictions)

**Owns:**
- Inconsistency detection
- Cross-activity validation
- Assumption tracking

**Collaborates With:**
- Activity Facilitator (monitors outputs)
- Process Mapper (recommends reconciliation activities)
- Progress Reporter (flags issues in reports)

**Communication**: Via Serving's event bus

### Progress Reporter (Coordinating Agent - Runs in Compute)
**Role**: Status communicator

**Execution Location**: Compute instance (lightweight, but may use LLM for summaries)

**Owns:**
- Progress calculation
- Status reporting
- Bottleneck identification
- Stakeholder communication

**Collaborates With:**
- All team members (monitors all events via Serving)
- External systems (publishes reports)

**Communication**: Via Serving's event bus

### Result Synthesizer (Coordinating Agent - Runs in Compute)
**Role**: Deliverable assembler

**Execution Location**: Compute instance (heavy LLM use for synthesis)

**Owns:**
- Output collection
- Synthesis logic
- Final deliverable packaging
- Quality validation

**Collaborates With:**
- Activity Facilitator (collects outputs)
- Process Mapper (understands structure)
- Progress Reporter (adds metadata)

**Communication**: Via Serving's message routing

## Execution Flow (Distributed Facilitated Process)

### Complete Example: Customer Retention Analysis

```
┌─────────────────────────────────────────────────────┐
│  USER SUBMITS BUSINESS GOAL                         │
│  "Increase customer retention by 20%"               │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  SERVING: CREATE SESSION                            │
│  • session_id: "sess-42"                           │
│  • business_goal: "Increase retention by 20%"       │
│  • Instantiate coordinating team                    │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  PROCESS MAPPER: Create Initial Map                 │
│                                                     │
│  Analyzes business goal and proposes:               │
│                                                     │
│  Activity 1: "Understand current retention"         │
│    Goal: Determine baseline retention metrics       │
│    Status: proposed                                 │
│                                                     │
│  Activity 2: "Identify retention drivers"           │
│    Goal: Find what influences retention             │
│    Status: proposed                                 │
│                                                     │
│  Activity 3: "Develop improvement strategies"       │
│    Goal: Create actionable improvement plan         │
│    Status: proposed                                 │
│    Depends on: Activities 1, 2                      │
│                                                     │
│  Process Map created (version 1)                    │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  PARTICIPANT SELECTOR: Activity 1 Participants      │
│                                                     │
│  Analyzes Activity 1:                               │
│  • Needs: data_analysis, customer_metrics           │
│  • Domain: customer_retention                       │
│  • Complexity: moderate                             │
│                                                     │
│  Queries marketplace → 8 candidates found           │
│                                                     │
│  Recommends:                                        │
│  • Primary: DataAnalystAgent (score: 85)            │
│  • Backup: CustomerInsightsAgent (score: 75)        │
│                                                     │
│  Reasoning: "DataAnalystAgent has full capability   │
│   coverage plus database access. No blockers."      │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  ACTIVITY FACILITATOR: Facilitate Activity 1        │
│  Participants: Facilitator + DataAnalystAgent       │
│                                                     │
│  Exchange 1:                                        │
│  Facilitator: "We need to understand current        │
│   retention. What data do you need?"                │
│                                                     │
│  DataAnalyst: "I need customer database access      │
│   and timeframe."                                   │
│                                                     │
│  Exchange 2:                                        │
│  Facilitator: "Timeframe is last 12 months. Do      │
│   you have database access?"                        │
│                                                     │
│  DataAnalyst: "No, I need credentials or export."   │
│                                                     │
│  Exchange 3:                                        │
│  Facilitator (identifies blocker): "We're blocked   │
│   on data access."                                  │
│                                                     │
│  Returns: FacilitationResult(                       │
│    status=blocked,                                  │
│    blocker="Database access needed",                │
│    resolution_activity="Obtain customer DB access"  │
│  )                                                  │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  PROCESS MAPPER: Update Map (Emergent Activity)    │
│                                                     │
│  Creates NEW Activity 0:                            │
│  "Obtain customer database access"                  │
│    Goal: Get DataAnalyst access to customer DB      │
│    Status: proposed                                 │
│                                                     │
│  Updates Activity 1:                                │
│    Status: blocked                                  │
│    Depends on: Activity 0 (NEW)                     │
│                                                     │
│  Process Map updated (version 2)                    │
│  • Activity 0 emerged from blocker                  │
│  • Dependency discovered: Activity 1 needs 0        │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  PROGRESS REPORTER: Generate Status Update          │
│                                                     │
│  📊 Status Report:                                  │
│  Activities: 4 total (1 emergent)                   │
│    Proposed: 3 (Activities 0, 2, 3)                 │
│    Blocked: 1 (Activity 1)                          │
│  Process Map: Version 2 (1 evolution)               │
│  Blocker: Database access needed for Activity 1     │
│  Next: Facilitate Activity 0 (data access)          │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  PARTICIPANT SELECTOR: Activity 0 Participants      │
│                                                     │
│  Recommends: ITAccessAgent (database credentials)   │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  ACTIVITY FACILITATOR: Facilitate Activity 0        │
│                                                     │
│  Facilitator → ITAccessAgent:                       │
│  "DataAnalyst needs customer DB read access."       │
│                                                     │
│  ITAccessAgent → Facilitator:                       │
│  "Access granted. Credentials: [provided]"          │
│                                                     │
│  Facilitator: "Activity goal met. Credentials       │
│   provided to DataAnalyst."                         │
│                                                     │
│  Returns: FacilitationResult(                       │
│    status=goal_met,                                 │
│    outputs={"credentials": "[...]"},                │
│    enables=[Activity 1]                             │
│  )                                                  │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  PROCESS MAPPER: Update Map                         │
│  • Activity 0: status = goal_met                    │
│  • Activity 1: status = proposed (unblocked)        │
│  • Process Map version 3                            │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  ACTIVITY FACILITATOR: Return to Activity 1         │
│  (Now has credentials from Activity 0)              │
│                                                     │
│  Facilitator → DataAnalyst:                         │
│  "You now have DB access. Please analyze retention."│
│                                                     │
│  DataAnalyst executes analysis...                   │
│                                                     │
│  DataAnalyst → Facilitator:                         │
│  "Current retention rate: 65%. Trending down 3%     │
│   per year. Segmentation shows high-value at 78%,   │
│   SMB at 55%."                                      │
│                                                     │
│  Facilitator: "Does this answer our goal of         │
│   understanding current retention?"                 │
│                                                     │
│  Facilitator assesses: YES, goal met               │
│                                                     │
│  BUT: New understanding emerges...                  │
│  "Segmentation reveals significant variance.        │
│   We should analyze segments separately."           │
│                                                     │
│  Returns: FacilitationResult(                       │
│    status=goal_met,                                 │
│    outputs={"retention_rate": "65%", ...},          │
│    new_activities_discovered=[                      │
│      "Analyze high-value segment retention",        │
│      "Analyze SMB segment retention"                │
│    ]                                                │
│  )                                                  │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  CONSISTENCY GUARDIAN: Monitor                      │
│  (Listening to all activity outputs)                │
│                                                     │
│  No inconsistencies detected yet.                   │
│  Baseline established: 65% retention                │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  PROCESS MAPPER: Reevaluate Process Map            │
│                                                     │
│  "Activity 1 revealed significant segmentation.     │
│   Should we analyze segments separately?"           │
│                                                     │
│  Decision: YES - Split approach                     │
│                                                     │
│  Restructures:                                      │
│  • Activity 2 splits into:                          │
│    - Activity 2a: "Drivers for high-value segment"  │
│    - Activity 2b: "Drivers for SMB segment"         │
│                                                     │
│  • Activity 3 becomes:                              │
│    - Activity 3a: "Strategies for high-value"       │
│    - Activity 3b: "Strategies for SMB"              │
│    - Activity 3c: "Synthesize overall strategy"     │
│      (depends on 3a, 3b)                            │
│                                                     │
│  Process Map updated (version 4)                    │
│  • 2 activities split into 5                        │
│  • Reevaluation event recorded                      │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  PROGRESS REPORTER: Updated Status                  │
│                                                     │
│  📊 Status Report:                                  │
│  Activities: 7 total                                │
│    Completed: 2 (Activities 0, 1)                   │
│    Proposed: 5 (Activities 2a, 2b, 3a, 3b, 3c)      │
│  Process Map: Version 4 (1 reevaluation)            │
│  Progress: ~28% (2 of 7 completed)                  │
│  Next: Activities 2a and 2b (can run in parallel)   │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
       Continue facilitating Activities 2a, 2b...
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  CONSISTENCY GUARDIAN: Detects Issue                │
│                                                     │
│  Activity 2a output: "High-value retention driven   │
│   by personal account management."                  │
│                                                     │
│  Activity 2b output: "SMB retention correlates with │
│   product features and pricing."                    │
│                                                     │
│  Earlier (Activity 1): "Overall rate 65%"           │
│                                                     │
│  ⚠️ POTENTIAL INCONSISTENCY DETECTED:               │
│  Weighted average of segments (78% high-value,      │
│  55% SMB) doesn't match 65% overall. Need to verify │
│  segment distribution.                              │
│                                                     │
│  Flags: Inconsistency(                              │
│    type=CONFLICTING_DATA,                           │
│    description="Segment rates don't average to      │
│      overall rate",                                 │
│    severity=MEDIUM,                                 │
│    recommendation="Verify segment distribution"     │
│  )                                                  │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  PROCESS MAPPER: Create Reconciliation Activity     │
│                                                     │
│  Creates Activity 1b:                               │
│  "Verify customer segment distribution"             │
│    Goal: Confirm segment sizes to validate rates    │
│    Status: proposed                                 │
│    Priority: high (blocking synthesis)              │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
       Facilitate Activity 1b...
       (Discovers 70% high-value, 30% SMB)
       (Math now checks: 0.7×78% + 0.3×55% = 71%, not 65%)
       (Reveals Activity 1 data was outdated)
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  CONSISTENCY GUARDIAN: Inconsistency Resolved       │
│                                                     │
│  Activity 1b revealed: Original 65% was last year.  │
│  Current rate: 71% (recent improvement).            │
│                                                     │
│  Updates: All downstream activities notified of     │
│    corrected baseline.                              │
│                                                     │
│  Inconsistency marked: RESOLVED                     │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
       Continue through Activities 3a, 3b, 3c...
       All activities reach goal_met...
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  RESULT SYNTHESIZER: Assemble Final Deliverable     │
│                                                     │
│  Collects outputs from all 8 completed activities   │
│                                                     │
│  Creates:                                           │
│  • Executive Summary                                │
│    "Current retention: 71% (not 65% as initially    │
│     thought). High-value segment at 78%, SMB at     │
│     55%..."                                         │
│                                                     │
│  • Key Findings (from Activities 2a, 2b)            │
│  • Strategies (from Activities 3a, 3b, 3c)          │
│  • Supporting Data                                  │
│  • Metadata:                                        │
│    - 8 activities completed                         │
│    - 1 reevaluation                                 │
│    - 1 inconsistency detected and resolved          │
│    - 2 emergent activities (Activity 0, 1b)         │
│    - Session duration: 4h 23m                       │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  SESSION COMPLETE                                   │
│  • Status: goal_achieved                            │
│  • Process Map: Final version 7                     │
│  • Deliverable returned to user                     │
└─────────────────────────────────────────────────────┘
```

### Key Observations from This Flow

1. **Emergence**: Activities 0 and 1b weren't in the original plan - they emerged from facilitation

2. **Dependencies Discovered**: Activity 1's dependency on Activity 0 wasn't predetermined - the facilitator discovered it

3. **Reevaluation**: Process Map restructured from 3 activities to 7 when segmentation was revealed

4. **Distributed Intelligence**: 
   - Process Mapper handled structure
   - Agent Selector chose agents
   - Activity Facilitator guided conversations
   - Consistency Manager caught the data mismatch
   - Progress Reporter tracked status
   - Result Synthesizer assembled deliverable

5. **Inconsistency Detection**: Guardian caught that segment rates didn't match overall, leading to discovery of outdated baseline

6. **Quality Focus**: Process took time to get it right (4h 23m), prioritized correctness over speed

## API Design (Refined for Facilitated Process)

### Session Management

```python
# Create facilitated session
POST   /api/v1/sessions/create-facilitated
Request:
{
  "business_goal": "Increase customer retention by 20%",
  "user_id": "user-123",
  "context": {
    "timeframe": "Q4 2024",
    "additional_context": "..."
  }
}
Response:
{
  "session_id": "sess-42",
  "process_map_id": "map-42",
  "status": "initiated",
  "coordinating_team": {
    "process_mapper": "process-mapper-v1",
    "agent_selector": "participant-selector-v1",
    "activity_facilitator": "activity-facilitator-v1",
    "consistency_manager": "consistency-guardian-v1",
    "progress_reporter": "progress-reporter-v1",
    "result_synthesizer": "result-synthesizer-v1"
  }
}

# Get session status
GET    /api/v1/sessions/{session_id}
Response:
{
  "session_id": "sess-42",
  "business_goal": "Increase retention by 20%",
  "status": "in_progress",
  "process_map": {
    "map_version": 4,
    "total_activities": 7,
    "completed": 3,
    "in_progress": 1,
    "proposed": 3
  },
  "current_activity": "activity-2a",
  "progress_percentage": 43,
  "duration": "2h 15m"
}

# Get session results
GET    /api/v1/sessions/{session_id}/results
  → Returns final deliverable (when status = goal_achieved)
```

### Process Map Management

```python
# Get process map
GET    /api/v1/sessions/{session_id}/process-map
Response:
{
  "map_id": "map-42",
  "map_version": 4,
  "activities": [...],
  "activity_graph": {...},
  "reevaluations": [...]
}

# Get process map history (evolution over time)
GET    /api/v1/sessions/{session_id}/process-map/history
  → Returns all map versions showing evolution

# Get specific activity
GET    /api/v1/sessions/{session_id}/activities/{activity_id}
Response:
{
  "activity_id": "act-1",
  "goal": "Understand current retention",
  "status": "goal_met",
  "assigned_agents": [...],
  "facilitation_history": [...],
  "outputs": {...}
}
```

### Facilitation Monitoring

```python
# Monitor active facilitation (SSE stream)
GET    /api/v1/sessions/{session_id}/facilitation/stream
  → Server-Sent Events stream of facilitation exchanges
  → Real-time updates as facilitator and agents converse

# Get facilitation history for activity
GET    /api/v1/sessions/{session_id}/activities/{activity_id}/exchanges
Response:
{
  "activity_id": "act-1",
  "exchanges": [
    {
      "exchange_id": "ex-1",
      "speaker": "facilitator",
      "message": "We need to understand current retention...",
      "timestamp": "2024-11-24T10:15:00Z"
    },
    {
      "exchange_id": "ex-2",
      "speaker": "data-analyst-v1",
      "message": "I need database access...",
      "timestamp": "2024-11-24T10:15:30Z"
    }
  ]
}
```

### Progress Reporting

```python
# Get current progress report
GET    /api/v1/sessions/{session_id}/progress
Response:
{
  "session_id": "sess-42",
  "progress_percentage": 43,
  "activities_completed": 3,
  "activities_total": 7,
  "current_activities": ["act-2a"],
  "blockers": [],
  "reevaluations": 1,
  "estimated_completion": "2024-11-24T14:00:00Z"
}

# Get progress history
GET    /api/v1/sessions/{session_id}/progress/history
  → Time series of progress reports
```

### Consistency Management

```python
# Get detected inconsistencies
GET    /api/v1/sessions/{session_id}/inconsistencies
Response:
{
  "inconsistencies": [
    {
      "inconsistency_id": "inc-1",
      "type": "conflicting_data",
      "description": "Activity 2a says X, Activity 2b says Y",
      "severity": "medium",
      "status": "detected",
      "resolution_activity": "act-1b"
    }
  ]
}
```

### Coordinating Team Interaction (Internal)

These endpoints are used by coordinating team members to coordinate with each other:

```python
# Process Mapper updates map
POST   /api/v1/internal/process-map/{map_id}/update
  → Used by Process Mapper to evolve the map

# Agent Selector recommends participants
POST   /api/v1/internal/activities/{activity_id}/recommend-participants
  → Returns participant recommendations

# Activity Facilitator submits facilitation result
POST   /api/v1/internal/activities/{activity_id}/facilitation-result
  → Records outcome of facilitation

# Consistency Manager flags inconsistency
POST   /api/v1/internal/sessions/{session_id}/flag-inconsistency
  → Alerts team to detected inconsistency
```

## Coordinating Team Communication Patterns

### How Team Members Collaborate

The coordinating team operates through **event-driven collaboration** where each member reacts to events from others:

#### Event Types

```python
class CoordinatingEvent(BaseModel):
    """Event passed between coordinating team members"""
    event_id: str
    event_type: CoordinatingEventType
    source_role: CoordinatingRole  # Who generated this
    target_role: Optional[CoordinatingRole]  # Specific target, or None for broadcast
    session_id: str
    activity_id: Optional[str]
    data: Dict[str, Any]
    timestamp: datetime

class CoordinatingEventType(str, Enum):
    # Process Mapper events
    MAP_INITIALIZED = "map_initialized"
    MAP_UPDATED = "map_updated"
    ACTIVITY_PROPOSED = "activity_proposed"
    MAP_REEVALUATED = "map_reevaluated"
    
    # Agent Selector events
    PARTICIPANTS_RECOMMENDED = "participants_recommended"
    PARTICIPANTS_CHANGED = "participants_changed"
    
    # Activity Facilitator events
    FACILITATION_STARTED = "facilitation_started"
    FACILITATION_COMPLETED = "facilitation_completed"
    BLOCKER_IDENTIFIED = "blocker_identified"
    DEPENDENCY_DISCOVERED = "dependency_discovered"
    
    # Consistency Manager events
    INCONSISTENCY_DETECTED = "inconsistency_detected"
    INCONSISTENCY_RESOLVED = "inconsistency_resolved"
    
    # Progress Reporter events
    PROGRESS_UPDATE = "progress_update"
    BLOCKER_ALERT = "blocker_alert"
    
    # Result Synthesizer events
    SYNTHESIS_STARTED = "synthesis_started"
    SYNTHESIS_COMPLETED = "synthesis_completed"
```

#### Collaboration Flow Example

```
┌─────────────────────────────────────────────────────┐
│  PROCESS MAPPER                                     │
│  • Proposes Activity 1                              │
│  • Emits: ACTIVITY_PROPOSED                         │
└────────────────┬────────────────────────────────────┘
                 │
                 ├──────────────────────┐
                 ▼                      ▼
┌─────────────────────────┐  ┌──────────────────────┐
│  PARTICIPANT SELECTOR   │  │  PROGRESS REPORTER   │
│  Receives: ACTIVITY_PROPOSED │  Receives: ACTIVITY_PROPOSED │
│  • Analyzes activity    │  │  • Updates activity  │
│  • Queries marketplace  │  │    count             │
│  • Recommends agents    │  │  • Generates report  │
│  • Emits: PARTICIPANTS_ │  └──────────────────────┘
│    RECOMMENDED          │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────┐
│  ACTIVITY FACILITATOR                               │
│  Receives: PARTICIPANTS_RECOMMENDED                 │
│  • Engages recommended agents                       │
│  • Guides conversation                              │
│  • Discovers blocker                                │
│  • Emits: BLOCKER_IDENTIFIED                        │
└────────────┬────────────────────────────────────────┘
             │
             ├──────────────────────┐
             ▼                      ▼
┌─────────────────────┐  ┌──────────────────────────┐
│  PROCESS MAPPER     │  │  PROGRESS REPORTER       │
│  Receives: BLOCKER_ │  │  Receives: BLOCKER_      │
│    IDENTIFIED       │  │    IDENTIFIED            │
│  • Creates new      │  │  • Flags blocker in      │
│    activity to      │  │    report                │
│    resolve blocker  │  │  • Emits: BLOCKER_ALERT  │
│  • Adds dependency  │  └──────────────────────────┘
│  • Emits: MAP_      │
│    UPDATED          │
└─────────────────────┘
```

#### Team Coordination Service

```python
class CoordinatingTeamService:
    """Manages coordination between team members"""
    
    def __init__(self):
        self.event_bus = EventBus()
        self.members = {}  # Role → Agent instance
        
    def subscribe_member(self, role: CoordinatingRole, agent: Agent):
        """Register a coordinating team member"""
        self.members[role] = agent
        
        # Subscribe to relevant events
        if role == CoordinatingRole.PROCESS_MAPPER:
            self.event_bus.subscribe(agent, [
                CoordinatingEventType.FACILITATION_COMPLETED,
                CoordinatingEventType.BLOCKER_IDENTIFIED,
                CoordinatingEventType.INCONSISTENCY_DETECTED
            ])
        
        elif role == CoordinatingRole.AGENT_SELECTOR:
            self.event_bus.subscribe(agent, [
                CoordinatingEventType.ACTIVITY_PROPOSED,
                CoordinatingEventType.MAP_UPDATED
            ])
        
        elif role == CoordinatingRole.ACTIVITY_FACILITATOR:
            self.event_bus.subscribe(agent, [
                CoordinatingEventType.PARTICIPANTS_RECOMMENDED,
                CoordinatingEventType.MAP_UPDATED
            ])
        
        elif role == CoordinatingRole.CONSISTENCY_MANAGER:
            self.event_bus.subscribe(agent, [
                CoordinatingEventType.FACILITATION_COMPLETED  # Monitor outputs
            ])
        
        elif role == CoordinatingRole.PROGRESS_REPORTER:
            self.event_bus.subscribe(agent, [
                "*"  # Monitor all events
            ])
    
    async def emit_event(self, event: CoordinatingEvent):
        """Emit event to relevant subscribers"""
        await self.event_bus.publish(event)
    
    async def handle_event(self, role: CoordinatingRole, event: CoordinatingEvent):
        """Route event to appropriate handler"""
        agent = self.members[role]
        await agent.handle_coordinating_event(event)
```

### Example: Complete Collaboration Sequence

```
Event 1: Process Mapper → ACTIVITY_PROPOSED
  Data: {activity_id: "act-1", goal: "Understand retention"}
  
  ├─> Agent Selector receives
  │     • Analyzes activity requirements
  │     • Queries marketplace
  │     • Scores candidates
  │
  └─> Progress Reporter receives
        • Updates activity count
        • Generates status update

Event 2: Agent Selector → PARTICIPANTS_RECOMMENDED
  Data: {activity_id: "act-1", primary: "data-analyst-v1", ...}
  
  └─> Activity Facilitator receives
        • Validates participants available
        • Begins facilitation

Event 3: Activity Facilitator → FACILITATION_STARTED
  Data: {activity_id: "act-1", participants: [...]}
  
  ├─> Progress Reporter receives
  │     • Updates activity status: in_progress
  │
  └─> Consistency Manager receives
        • Begins monitoring this activity

Event 4: Activity Facilitator → BLOCKER_IDENTIFIED
  Data: {activity_id: "act-1", blocker: "Database access needed"}
  
  ├─> Process Mapper receives
  │     • Creates new activity: "Obtain DB access"
  │     • Updates dependencies
  │     • Emits: MAP_UPDATED
  │
  └─> Progress Reporter receives
        • Records blocker
        • Emits: BLOCKER_ALERT

Event 5: Process Mapper → MAP_UPDATED
  Data: {map_version: 2, changes: [...]}
  
  ├─> Agent Selector receives
  │     • Analyzes new activity
  │     • Emits: PARTICIPANTS_RECOMMENDED
  │
  ├─> Activity Facilitator receives
  │     • Pauses current activity
  │     • Prepares to facilitate new activity
  │
  └─> Progress Reporter receives
        • Updates activity counts
        • Notes map evolution

... continues until session complete ...

Event N: Activity Facilitator → All activities completed
  
  └─> Result Synthesizer receives
        • Collects all outputs
        • Synthesizes deliverable
        • Emits: SYNTHESIS_COMPLETED
```

## Implementation Roadmap

### Version 0.1.8 (Current - Traditional Pipeline)
**Status**: ✅ Implemented
- Fixed pipeline with predetermined steps
- Sequential/parallel execution
- Basic coordination
- Good foundation for evolution

### Version 0.2.0 - Foundational Facilitated Process
**Priority**: High - Core Architecture
**Timeline**: 4-6 weeks

#### Phase 1: Core Models & Storage (Week 1-2)
1. ✅ Define refined data models
   - Activity model (replaces PipelineStep)
   - ProcessMap model (replaces ExecutionPipeline)
   - Exchange, FacilitationResult models
   - Inconsistency, CoordinatingEvent models

2. ✅ Create storage layer
   - ProcessMap storage
   - Activity storage with facilitation history
   - Event store for coordinating team events

3. ✅ Session enhancement
   - Link session to process map
   - Support map versioning

#### Phase 2: Process Mapper (Week 2)
1. ✅ Implement Process Mapper agent
   - Initial map creation from business goal
   - Activity proposal logic
   - Map evolution/restructuring
   - Reevaluation triggers

2. ✅ Create Process Map Service
   - Map CRUD operations
   - Version management
   - Graph operations (dependencies)

#### Phase 3: Agent Selector (Week 2-3)
1. ✅ Implement Agent Selector agent
   - Activity requirement analysis
   - Marketplace query integration
   - Candidate evaluation and scoring
   - Recommendation generation

2. ✅ Marketplace integration refinements
   - Enhanced capability search
   - Agent availability tracking
   - Performance metrics (future)

#### Phase 4: Activity Facilitator (Week 3-4)
1. ✅ Implement Activity Facilitator agent
   - Activity framing
   - Conversational facilitation
   - Goal assessment
   - Blocker identification

2. ✅ Facilitation engine
   - Exchange management
   - Agent engagement
   - Result capture

#### Phase 5: Consistency Manager (Week 4)
1. ✅ Implement Consistency Manager agent
   - Output monitoring
   - Contradiction detection
   - Inconsistency flagging
   - Reconciliation recommendations

#### Phase 6: Support Components (Week 5)
1. ✅ Progress Reporter agent
   - Status tracking
   - Report generation
   - Alert system

2. ✅ Result Synthesizer agent
   - Output collection
   - Synthesis logic
   - Deliverable assembly

#### Phase 7: Integration & Testing (Week 5-6)
1. ✅ Coordinating team event bus
2. ✅ End-to-end facilitation flow
3. ✅ API endpoints
4. ✅ Comprehensive testing
5. ✅ Documentation

### Version 0.2.1 - Enhanced Facilitation
**Priority**: Medium
**Timeline**: 2-3 weeks

- Advanced participant adaptation
- Parallel activity facilitation
- Smart reevaluation triggers
- Facilitation pattern learning
- Improved inconsistency detection

### Version 0.3.0 - Sophisticated Process Understanding
**Priority**: Medium-Low
**Timeline**: 4-6 weeks

- Multi-level process hierarchies
- Complex dependency management
- Process templates and patterns
- Learning from past sessions
- Process optimization suggestions

### Version 0.4.0 - Advanced Features
**Priority**: Low
**Timeline**: TBD

- Collaborative human-AI facilitation
- External stakeholder integration
- Advanced analytics and insights
- Cross-session learning
- Predictive process mapping

## Key Design Principles (Summary)

### 1. **Emergence Over Predetermination**
Activities, dependencies, and hierarchies emerge from facilitated conversations rather than being predetermined through upfront planning.

**Example**: Activity 0 (database access) wasn't in the original plan—it emerged when the facilitator discovered a blocker.

### 2. **Distributed Intelligence**
No single agent is omniscient. Each coordinating agent has a focused responsibility and collaborates through events.

**Example**: Facilitator guides conversations, Process Mapper structures the map, Consistency Manager watches for contradictions—each stays in their lane.

### 3. **Goal-Oriented Activities**
Activities are defined by their goals, not their implementations. Success is measured by goal achievement, not task completion.

**Example**: "Understand current retention" is the goal. How it's achieved (which data, which analysis) emerges during facilitation.

### 4. **Conversation as Execution**
Execution happens through facilitated conversations, not predetermined step execution.

**Example**: The facilitator doesn't just run the DataAnalyst—they engage in a back-and-forth to clarify needs, identify blockers, and assess goal completion.

### 5. **Reevaluation is Normal**
The process map evolves as understanding deepens. Restructuring is expected, not a deviation.

**Example**: When segmentation was discovered, the map restructured from 3 activities to 7—this is healthy evolution, not plan failure.

### 6. **Quality Over Efficiency**
Take time to get it right. Allow exploration, discovery, and course correction.

**Example**: Session took 4h 23m and involved 3 reevaluations—this depth produced accurate, high-quality results.

### 7. **Dynamic Participant Selection**
Participants are chosen based on emerging needs, not fixed assignments.

**Example**: SegmentationSpecialist was brought in mid-activity when need emerged, then DataAnalyst continued as primary.

### 8. **Consistency Through Monitoring**
A dedicated agent watches for contradictions rather than assuming all outputs are consistent.

**Example**: Consistency Manager caught the retention rate mismatch, leading to discovery of outdated baseline data.

## Architectural Advantages

### Compared to Traditional Pipelines

| Aspect | Traditional Pipeline | Facilitated Process |
|--------|---------------------|-------------------|
| **Planning** | Upfront, complete | Emergent, evolving |
| **Structure** | Fixed steps | Dynamic activities |
| **Dependencies** | Predetermined | Discovered |
| **Changes** | Plan deviation | Natural evolution |
| **Participant Selection** | Fixed assignments | Context-aware matching |
| **Quality Assurance** | Testing after execution | Continuous monitoring |
| **Complexity Handling** | Must be planned for | Emerges and adapts |
| **Human Intuition** | Requires upfront human design | Emerges from AI facilitation |

### Compared to Ad-Hoc Agent Invocation

| Aspect | Ad-Hoc Invocation | Facilitated Process |
|--------|------------------|-------------------|
| **Coordination** | None | Structured facilitation |
| **State Management** | Unclear | Process map tracks everything |
| **Dependencies** | Implicit | Explicit and tracked |
| **Consistency** | Unmonitored | Actively guarded |
| **Progress Visibility** | Opaque | Real-time reporting |
| **Reproducibility** | Difficult | Process map provides record |

## Design Challenges & Solutions

### Challenge 1: When to Reevaluate?

**Problem**: Process Mapper can't reevaluate after every activity—too expensive. But waiting too long means working with outdated structure.

**Solution**: Reevaluation triggers:
- Significant new understanding emerges (facilitator flags)
- Multiple activities blocked
- Inconsistency detected by guardian
- X% of proposed activities completed
- User requests reevaluation
- Time threshold (every N hours)

### Challenge 2: Facilitator Knows When Goal is Met?

**Problem**: Facilitator must assess if activity goal is achieved, but isn't domain expert.

**Solution**: 
- Facilitator asks the participants: "Does this achieve the goal?"
- Compares outputs to activity goal statement
- Uses LLM reasoning to assess alignment
- Can flag for human review if uncertain
- If goal not met, continues facilitation

### Challenge 3: Participant Selection Quality?

**Problem**: Agent Selector might recommend wrong agent.

**Solution**:
- Facilitator can request alternative if participant ineffective
- Backup participants identified upfront
- Selection reasoning is recorded (auditable)
- Learn from successful/failed selections over time
- Allow human override of recommendations

### Challenge 4: Consistency Manager Misses Issues?

**Problem**: Guardian might not catch all contradictions.

**Solution**:
- Don't rely solely on Guardian—it's a safety net
- Result Synthesizer also validates consistency
- Human reviewers see inconsistency log
- False negatives better than false positives (flag only high confidence)
- Learn patterns of common inconsistencies

### Challenge 5: Infinite Reevaluation Loop?

**Problem**: Process could keep restructuring forever.

**Solution**:
- Track reevaluation count (flag if excessive)
- Each reevaluation must have clear reasoning
- Progress Reporter alerts if map oscillating
- Max reevaluations per session (configurable)
- Human intervention if loop detected

## Migration Path from v0.1.8

### Option 1: Parallel Implementation (Recommended)
- Keep current pipeline system as "simple mode"
- Implement facilitated process as "advanced mode"
- Let users choose based on use case
- Both share underlying infrastructure (Serving, Compute)

### Option 2: Gradual Evolution
- Start with facilitated process for new sessions
- Maintain backward compatibility for existing pipeline API
- Deprecate pipeline approach over 2-3 releases

### Option 3: Hybrid Mode
- Use pipeline for well-defined workflows
- Fall back to facilitated process when blockers/unknowns encountered
- Best of both worlds

## Conclusion

This architecture represents a **fundamental shift** in how AI agent orchestration works:

**From**: "Tell me the plan and I'll execute it"  
**To**: "Tell me the goal and I'll figure it out"

### What Makes This Different

1. **No Predetermined Workflows** - Structure emerges from the problem, not imposed on it

2. **Distributed Coordination** - Multiple specialist agents coordinate without a single orchestrator brain

3. **Conversation as Execution** - Work happens through facilitated dialogue, not function calls

4. **Quality-Focused** - Take time to understand, explore, and get it right

5. **Naturally Hierarchical** - Complexity reveals itself through facilitation, creating sub-processes as needed

6. **Self-Correcting** - Consistency monitoring and reevaluation catch and fix issues

### This Is Hard, But Worth It

Traditional pipelines are easier to implement and reason about. This architecture is more complex:
- More agents to coordinate
- More state to track  
- More uncertainty in execution time
- More emergent behavior to handle

But it enables a **qualitatively different** capability:
- Tackle truly open-ended problems
- Adapt to unexpected complexity
- Produce higher-quality results
- Handle ambiguity gracefully

### Next Steps

1. **Review and refine** this document with team
2. **Start with Phase 1** (Core Models & Storage)
3. **Build Process Mapper first** - Foundation for everything else
4. **Iterate rapidly** - This is new territory, expect learning
5. **Document patterns** - Capture what works as we discover it

---

**Document Version**: 2.0  
**Date**: November 24, 2024  
**Status**: Conceptual Design - Ready for Implementation  
**Target Release**: ClaudeVN v0.2.0

