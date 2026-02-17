# Emergent Workflow Implementation Plan

**Date**: December 11, 2025  
**Purpose**: Bridge the gap between predetermined pipelines and emergent coordination  
**Target**: Make ClaudeVN truly emergent and conversation-driven

---

## The Core Problem

### What We Promised
"Emergent, goal-oriented collaboration through distributed intelligence where processes evolve naturally from agent interactions"

### What We Delivered
Predetermined pipelines with static process maps that don't adapt based on execution outcomes

### The Gap
**Only 2 of 6 coordinating agents are functional.** The missing pieces prevent emergent behavior:
- 🔴 **Activity Facilitator** - Can't have conversations, can't detect blockers, can't create new activities
- 🔴 **Consistency Manager** - Can't detect contradictions that require process changes
- 🔴 **Progress Reporter** - Can't identify systemic issues requiring restructuring
- 🔴 **Result Synthesizer** - Can't determine if collective output meets goal

Without these, the system cannot adapt, restructure, or truly be emergent.

---

## What "Emergent" Actually Means

### Characteristics of Emergent Workflows

1. **Dynamic Activity Creation**
   - Activities not all defined upfront
   - New activities emerge when blockers discovered
   - Activities split when complexity revealed
   - Activities merge when redundancy detected

2. **Conversation-Driven Progress**
   - Facilitator guides, doesn't direct
   - Agents propose approaches
   - Multiple iterations until goal met
   - Blockers surface naturally through conversation

3. **Self-Correcting Behavior**
   - Contradictions detected across activities
   - Process restructures to resolve inconsistencies
   - Dependencies emerge from activity interactions
   - Map evolves based on what we learn

4. **Distributed Decision Making**
   - No central "orchestrator" with all the answers
   - Coordinating agents collaborate as peers
   - Specialized agents contribute domain expertise
   - Collective intelligence emerges

### What We Have vs What We Need

| Characteristic | Current State | Target State |
|----------------|---------------|--------------|
| **Activity Creation** | All upfront by Process Mapper | Emergent via Activity Facilitator when blockers found |
| **Progress** | Execute activities in order | Conversation loops until goal met |
| **Correction** | None | Consistency Manager triggers restructuring |
| **Decision Making** | Serving coordinates everything | Coordinating agents collaborate |

---

## Implementation Roadmap

### Phase 1: Make Activity Facilitator Truly Facilitate (2 weeks)

**Goal**: Enable conversation-driven execution with blocker detection

#### Week 1: Conversation Loop

**1.1 Design Conversation Protocol**

Create structured exchange format:
```python
# serving/models/facilitation.py

class Exchange(BaseModel):
    """Single exchange in facilitation conversation"""
    exchange_id: str
    timestamp: datetime
    speaker: str  # "facilitator" or agent_id
    intent: ExchangeIntent  # question, answer, proposal, blocker, goal_check
    content: str
    metadata: Dict[str, Any]

class FacilitationConversation(BaseModel):
    """Complete facilitation conversation for an activity"""
    activity_id: str
    session_id: str
    facilitator_id: str
    participant_id: str
    goal: str
    exchanges: List[Exchange]
    status: ConversationStatus  # active, goal_met, blocked, needs_help
    blocker: Optional[Blocker]
```

**1.2 Implement Conversation Loop**

Location: `compute/services/coordinating_team_service.py::ActivityFacilitator`

```python
async def facilitate_activity(
    self,
    session_id: str,
    activity_id: str,
    activity_goal: str,
    participant_agent_id: str
) -> FacilitationResult:
    """
    Facilitate an activity through conversation.
    
    Conversation flow:
    1. Facilitator: "Here's the goal. What do you need?"
    2. Agent: "I need X, Y, Z"
    3. Facilitator: "Do you have everything?"
    4. Agent: "I have X and Y, but not Z" [BLOCKER]
    5. Facilitator: "Let's get Z first" [CREATE NEW ACTIVITY]
    
    OR:
    
    4. Agent: "Yes, let me proceed"
    5. Agent: Executes work
    6. Facilitator: "Does this meet the goal?"
    7. Agent: "Yes, here's the output"
    8. Facilitator: "Goal met!"
    """
    
    conversation = FacilitationConversation(
        activity_id=activity_id,
        session_id=session_id,
        facilitator_id="activity-facilitator-v1",
        participant_id=participant_agent_id,
        goal=activity_goal,
        exchanges=[],
        status=ConversationStatus.ACTIVE
    )
    
    # Max iterations to prevent infinite loops
    max_iterations = 10
    iteration = 0
    
    while iteration < max_iterations and conversation.status == ConversationStatus.ACTIVE:
        iteration += 1
        
        # Facilitator asks what agent needs
        facilitator_question = self._build_facilitator_question(
            conversation, iteration
        )
        conversation.exchanges.append(facilitator_question)
        
        # Agent responds
        agent_response = await self._get_agent_response(
            participant_agent_id,
            conversation
        )
        conversation.exchanges.append(agent_response)
        
        # Analyze response for blockers
        blocker = self._detect_blocker(agent_response)
        if blocker:
            conversation.status = ConversationStatus.BLOCKED
            conversation.blocker = blocker
            break
        
        # Check if goal met
        if self._is_goal_met(agent_response, activity_goal):
            conversation.status = ConversationStatus.GOAL_MET
            break
        
        # If agent is ready to proceed, let them work
        if self._is_ready_to_work(agent_response):
            work_result = await self._execute_agent_work(
                participant_agent_id,
                activity_goal,
                conversation
            )
            conversation.exchanges.append(work_result)
            
            # Verify work meets goal
            verification = self._verify_goal_met(work_result, activity_goal)
            conversation.exchanges.append(verification)
            
            if verification.intent == ExchangeIntent.GOAL_MET:
                conversation.status = ConversationStatus.GOAL_MET
                break
    
    # Record conversation to process map
    await self._record_facilitation(session_id, activity_id, conversation)
    
    return FacilitationResult(
        activity_id=activity_id,
        status=conversation.status,
        exchanges=conversation.exchanges,
        output=self._extract_output(conversation),
        blocker=conversation.blocker
    )
```

**1.3 Implement Blocker Detection**

```python
def _detect_blocker(self, agent_response: Exchange) -> Optional[Blocker]:
    """
    Detect if agent response indicates a blocker.
    
    Blocker patterns:
    - "I need X but don't have it"
    - "Cannot proceed without Y"
    - "Missing required data/access/resource"
    - "Dependency on activity Z"
    """
    
    # Use LLM to analyze agent response for blockers
    blocker_analysis = await self.agent_executor.execute(
        agent_id="activity-facilitator-v1",
        prompt=f"""
        Analyze this agent response for blockers:
        
        Response: {agent_response.content}
        
        Is there a blocker? What is needed to proceed?
        
        Respond in JSON:
        {{
            "has_blocker": true/false,
            "blocker_type": "missing_data|missing_access|missing_dependency|other",
            "description": "what is blocking",
            "what_is_needed": "specific requirement"
        }}
        """,
        context={"action": "detect_blocker"}
    )
    
    analysis = json.loads(blocker_analysis["output"]["content"])
    
    if analysis["has_blocker"]:
        return Blocker(
            type=analysis["blocker_type"],
            description=analysis["description"],
            required_activity=analysis["what_is_needed"]
        )
    
    return None
```

#### Week 2: Dynamic Activity Creation

**2.1 Blocker Resolution Workflow**

When Activity Facilitator detects blocker, create new activity:

```python
async def handle_blocker(
    self,
    session_id: str,
    blocked_activity_id: str,
    blocker: Blocker
) -> str:
    """
    Handle blocker by creating new prerequisite activity.
    
    Returns:
        New activity ID that will resolve the blocker
    """
    
    # Create new activity to resolve blocker
    new_activity_id = f"activity-{uuid.uuid4().hex[:8]}"
    
    new_activity = Activity(
        activity_id=new_activity_id,
        goal=blocker.required_activity,
        description=f"Prerequisite for {blocked_activity_id}: {blocker.description}",
        status=ActivityStatus.PROPOSED,
        created_by="activity-facilitator-v1",
        metadata={
            "blocker_resolution": True,
            "blocks_activity": blocked_activity_id,
            "blocker_type": blocker.type
        }
    )
    
    # Add to process map
    await self.process_map_service.add_activity(
        session_id=session_id,
        activity=new_activity,
        insert_before=blocked_activity_id  # New activity must complete first
    )
    
    # Update blocked activity to show dependency
    await self.process_map_service.add_dependency(
        session_id=session_id,
        activity_id=blocked_activity_id,
        depends_on=new_activity_id
    )
    
    # Emit observability event
    await self.observability_client.emit_event({
        "type": "BLOCKER_DETECTED",
        "session_id": session_id,
        "blocked_activity": blocked_activity_id,
        "new_activity": new_activity_id,
        "blocker": blocker.dict()
    })
    
    logger.info(
        f"Created activity {new_activity_id} to resolve blocker "
        f"for {blocked_activity_id}"
    )
    
    return new_activity_id
```

**2.2 Update Process Map Service**

Add methods to `serving/services/process_map_service.py`:

```python
async def add_dependency(
    self,
    session_id: str,
    activity_id: str,
    depends_on: str
) -> None:
    """Add dependency relationship between activities."""
    
    process_map = await self.get_map(session_id)
    
    # Find activity
    activity = next(
        (a for a in process_map.activities if a.activity_id == activity_id),
        None
    )
    
    if not activity:
        raise ValueError(f"Activity {activity_id} not found")
    
    # Add dependency if not already present
    if depends_on not in activity.dependencies:
        activity.dependencies.append(depends_on)
    
    # Increment version
    process_map.version += 1
    process_map.updated_at = datetime.utcnow()
    
    # Save
    await self._save_map(session_id, process_map)

async def insert_activity_before(
    self,
    session_id: str,
    new_activity: Activity,
    before_activity_id: str
) -> None:
    """Insert new activity before specified activity in execution order."""
    
    process_map = await self.get_map(session_id)
    
    # Find the before_activity
    before_idx = next(
        (i for i, a in enumerate(process_map.activities) 
         if a.activity_id == before_activity_id),
        None
    )
    
    if before_idx is None:
        raise ValueError(f"Activity {before_activity_id} not found")
    
    # Insert before
    process_map.activities.insert(before_idx, new_activity)
    
    # Increment version and save
    process_map.version += 1
    process_map.updated_at = datetime.utcnow()
    
    await self._save_map(session_id, process_map)
```

**2.3 Test Dynamic Activity Creation**

Create test: `tests/test_emergent_activity_creation.py`

```python
async def test_blocker_creates_new_activity():
    """
    Test that Activity Facilitator creates new activity when blocker detected.
    
    Scenario:
    1. Activity: "Analyze sales data"
    2. Agent: "I need database access"
    3. Facilitator detects blocker
    4. Facilitator creates: "Obtain database access"
    5. Original activity marked depends_on new activity
    """
    
    # Setup
    session_id = "test-session"
    activity_id = "analyze-sales"
    
    # Simulate facilitation
    result = await activity_facilitator.facilitate_activity(
        session_id=session_id,
        activity_id=activity_id,
        activity_goal="Analyze Q4 sales data",
        participant_agent_id="data-analyst-v1"
    )
    
    # Verify blocker detected
    assert result.status == ConversationStatus.BLOCKED
    assert result.blocker is not None
    assert "database access" in result.blocker.description.lower()
    
    # Verify new activity created
    process_map = await process_map_service.get_map(session_id)
    
    # Should have 2 activities now
    assert len(process_map.activities) == 2
    
    # New activity should be about database access
    new_activity = [a for a in process_map.activities if a.activity_id != activity_id][0]
    assert "database" in new_activity.goal.lower()
    assert "access" in new_activity.goal.lower()
    
    # Original activity should depend on new one
    original_activity = [a for a in process_map.activities if a.activity_id == activity_id][0]
    assert new_activity.activity_id in original_activity.dependencies
```

---

### Phase 2: Consistency Manager for Self-Correction (1 week)

**Goal**: Detect contradictions and trigger process restructuring

#### Implementation

**2.1 Create Consistency Manager Agent**

File: `compute/data/compute/agents/coordinating/consistency-manager-agent.json`

```json
{
  "agent_id": "consistency-manager-v1",
  "name": "Consistency Manager",
  "type": "coordinating",
  "description": "Detects contradictions across activity outputs and triggers reconciliation",
  "capabilities": [
    "contradiction_detection",
    "output_comparison",
    "consistency_analysis",
    "reconciliation_recommendation"
  ],
  "model": {
    "provider": "openai",
    "model_name": "gpt-4",
    "temperature": 0.2,
    "fallback": {
      "provider": "mock",
      "model_name": "mock"
    }
  },
  "system_prompt": "You are a Consistency Manager. Your job is to analyze outputs from multiple activities and detect contradictions or inconsistencies.\n\nWhen reviewing outputs:\n1. Look for conflicting data (e.g., Activity A says retention is 65%, Activity B assumes 70%)\n2. Identify logical inconsistencies\n3. Spot incompatible assumptions\n4. Flag outputs that contradict each other\n\nWhen you find inconsistencies:\n1. Clearly describe the contradiction\n2. Identify which activities are involved\n3. Recommend which activity should be revisited\n4. Suggest a reconciliation approach\n\nAlways respond with structured JSON.",
  "input_format": "json",
  "output_format": "json"
}
```

**2.2 Consistency Checking Service**

File: `serving/services/consistency_service.py`

```python
class ConsistencyService:
    """Service for detecting contradictions across activities."""
    
    async def check_consistency(
        self,
        session_id: str,
        trigger_activity_id: Optional[str] = None
    ) -> ConsistencyCheckResult:
        """
        Check for contradictions across completed activities.
        
        Args:
            session_id: Session to check
            trigger_activity_id: If provided, check this activity against all others.
                               If None, check all completed activities.
        
        Returns:
            Result indicating if contradictions found
        """
        
        # Get process map
        process_map = await self.process_map_service.get_map(session_id)
        
        # Get completed activities with outputs
        completed_activities = [
            a for a in process_map.activities
            if a.status == ActivityStatus.GOAL_MET and a.output
        ]
        
        if len(completed_activities) < 2:
            return ConsistencyCheckResult(
                consistent=True,
                contradictions=[]
            )
        
        # Collect outputs
        outputs = {}
        for activity in completed_activities:
            outputs[activity.activity_id] = {
                "goal": activity.goal,
                "output": activity.output,
                "description": activity.description
            }
        
        # Invoke Consistency Manager
        result = await self.coordinating_team_service.invoke_consistency_manager(
            session_id=session_id,
            outputs=outputs,
            trigger_activity_id=trigger_activity_id
        )
        
        # Parse contradictions
        contradictions = self._parse_contradictions(result)
        
        # If contradictions found, mark activities for revisit
        if contradictions:
            for contradiction in contradictions:
                await self._handle_contradiction(
                    session_id,
                    contradiction
                )
        
        return ConsistencyCheckResult(
            consistent=len(contradictions) == 0,
            contradictions=contradictions
        )
    
    async def _handle_contradiction(
        self,
        session_id: str,
        contradiction: Contradiction
    ) -> None:
        """
        Handle detected contradiction by marking activities for revisit
        and optionally creating reconciliation activity.
        """
        
        # Mark involved activities as "revisit"
        for activity_id in contradiction.involved_activities:
            await self.process_map_service.update_activity_status(
                session_id=session_id,
                activity_id=activity_id,
                new_status=ActivityStatus.REVISIT,
                reason=f"Contradiction detected: {contradiction.description}"
            )
        
        # Create reconciliation activity
        if contradiction.requires_reconciliation:
            reconciliation_activity = Activity(
                activity_id=f"reconcile-{uuid.uuid4().hex[:8]}",
                goal=f"Reconcile: {contradiction.description}",
                description=contradiction.reconciliation_approach,
                status=ActivityStatus.PROPOSED,
                created_by="consistency-manager-v1",
                metadata={
                    "reconciliation": True,
                    "contradiction": contradiction.dict(),
                    "involved_activities": contradiction.involved_activities
                }
            )
            
            await self.process_map_service.add_activity(
                session_id=session_id,
                activity=reconciliation_activity
            )
        
        # Emit event
        await self.observability_client.emit_event({
            "type": "CONTRADICTION_DETECTED",
            "session_id": session_id,
            "contradiction": contradiction.dict()
        })
```

**2.3 Automatic Consistency Checks**

Trigger consistency check after each activity completes:

```python
# In Activity Facilitator, after activity marked goal_met:

async def _record_facilitation(
    self,
    session_id: str,
    activity_id: str,
    conversation: FacilitationConversation
) -> None:
    """Record facilitation and trigger consistency check."""
    
    # Record to process map
    await self.process_map_service.record_facilitation(
        session_id=session_id,
        activity_id=activity_id,
        exchanges=conversation.exchanges,
        output=conversation.output
    )
    
    # Trigger consistency check for this activity against others
    if conversation.status == ConversationStatus.GOAL_MET:
        await self.consistency_service.check_consistency(
            session_id=session_id,
            trigger_activity_id=activity_id
        )
```

---

### Phase 3: Process Map Evolution (1 week)

**Goal**: Enable automatic restructuring based on learnings

#### Triggers for Process Map Evolution

1. **Blocker Detected** → Insert prerequisite activity
2. **Contradiction Found** → Create reconciliation activity, mark conflicting activities for revisit
3. **Complexity Revealed** → Split activity into sub-activities
4. **Redundancy Detected** → Merge activities
5. **New Understanding** → Restructure activity hierarchy

#### Implementation

**3.1 Process Mapper Reevaluation**

Enhance `serving/services/coordinating_team_service.py`:

```python
async def reevaluate_process_map(
    self,
    session_id: str,
    trigger: str,
    trigger_data: Dict[str, Any]
) -> ProcessMapEvolution:
    """
    Invoke Process Mapper to reevaluate and potentially restructure map.
    
    Triggers:
    - "blocker_detected": New prerequisite needed
    - "contradiction_found": Inconsistency requires resolution
    - "complexity_revealed": Activity too large, needs splitting
    - "new_insights": Understanding changed, restructure needed
    """
    
    process_map = await self.process_map_service.get_map(session_id)
    
    # Build reevaluation prompt
    prompt = f"""
    Process Map Reevaluation Request
    
    Business Goal: {process_map.business_goal}
    Current Map Version: {process_map.version}
    Trigger: {trigger}
    
    Current Activities:
    {self._format_activities_for_prompt(process_map.activities)}
    
    Trigger Details:
    {json.dumps(trigger_data, indent=2)}
    
    Based on this trigger, should the process map be restructured?
    
    Consider:
    1. Should activities be split, merged, or reordered?
    2. Are new activities needed?
    3. Should dependencies change?
    4. Is the overall approach still valid?
    
    Respond with restructuring recommendations in JSON:
    {{
      "restructure_needed": true/false,
      "reasoning": "why restructuring is/isn't needed",
      "changes": [
        {{
          "type": "split_activity|merge_activities|add_activity|reorder|change_dependencies",
          "details": {{...}}
        }}
      ]
    }}
    """
    
    result = await self.invoke_process_mapper(
        session_id=session_id,
        action="reevaluate",
        data={
            "current_map": process_map.dict(),
            "trigger": trigger,
            "trigger_data": trigger_data
        }
    )
    
    # Parse and apply changes
    evolution = self._parse_evolution_recommendations(result)
    
    if evolution.restructure_needed:
        await self._apply_map_evolution(session_id, evolution)
    
    return evolution
```

**3.2 Automatic Triggers**

```python
# When blocker detected:
await coordinating_team_service.reevaluate_process_map(
    session_id=session_id,
    trigger="blocker_detected",
    trigger_data={
        "blocked_activity": blocked_activity_id,
        "blocker": blocker.dict(),
        "new_activity_created": new_activity_id
    }
)

# When contradiction found:
await coordinating_team_service.reevaluate_process_map(
    session_id=session_id,
    trigger="contradiction_found",
    trigger_data={
        "contradiction": contradiction.dict(),
        "involved_activities": contradiction.involved_activities
    }
)
```

---

### Phase 4: Result Synthesizer for Goal Achievement (1 week)

**Goal**: Determine when collective work achieves business goal

#### Implementation

**4.1 Create Result Synthesizer Agent**

File: `compute/data/compute/agents/coordinating/result-synthesizer-agent.json`

```json
{
  "agent_id": "result-synthesizer-v1",
  "name": "Result Synthesizer",
  "type": "coordinating",
  "description": "Assembles final deliverable from activity outputs and determines if business goal achieved",
  "capabilities": [
    "output_synthesis",
    "goal_achievement_assessment",
    "deliverable_generation",
    "quality_evaluation"
  ],
  "model": {
    "provider": "openai",
    "model_name": "gpt-4",
    "temperature": 0.3
  },
  "system_prompt": "You are a Result Synthesizer. Your job is to:\n1. Collect outputs from all completed activities\n2. Synthesize them into a coherent final deliverable\n3. Assess if the business goal has been achieved\n4. Identify any gaps\n\nYou focus on the OVERALL GOAL, not individual activities.",
  "input_format": "json",
  "output_format": "json"
}
```

**4.2 Synthesis Service**

```python
async def synthesize_results(
    self,
    session_id: str
) -> SynthesisResult:
    """
    Synthesize all activity outputs into final deliverable.
    
    Triggered when:
    - All activities complete (goal_met)
    - User requests synthesis
    - Process Mapper determines map is complete
    """
    
    process_map = await self.process_map_service.get_map(session_id)
    
    # Collect all outputs
    outputs = {}
    for activity in process_map.activities:
        if activity.status == ActivityStatus.GOAL_MET and activity.output:
            outputs[activity.activity_id] = {
                "goal": activity.goal,
                "output": activity.output,
                "participants": [p.agent_id for p in activity.participants]
            }
    
    # Invoke Result Synthesizer
    result = await self.coordinating_team_service.invoke_result_synthesizer(
        session_id=session_id,
        business_goal=process_map.business_goal,
        outputs=outputs
    )
    
    # Parse synthesis
    synthesis = self._parse_synthesis(result)
    
    # Determine if goal achieved
    if synthesis.goal_achieved:
        await self.session_manager.update_status(
            session_id=session_id,
            status=SessionStatus.COMPLETED
        )
    else:
        # Identify gaps and create additional activities if needed
        await self._handle_goal_gaps(session_id, synthesis.gaps)
    
    return synthesis
```

---

## Testing the Emergent System

### Test Scenario 1: Blocker Creates New Activity

```python
async def test_emergent_blocker_resolution():
    """
    Test that blockers trigger dynamic activity creation.
    
    Flow:
    1. Goal: "Analyze customer retention"
    2. Process Mapper creates: ["Get data", "Analyze data", "Create report"]
    3. "Get data" facilitation detects: "No database access"
    4. Activity Facilitator creates: "Obtain database credentials"
    5. Process map restructures with new dependency
    6. Facilitator resumes once blocker resolved
    """
    
    # Start session
    session_id = await create_facilitated_session(
        goal="Analyze customer retention by segment"
    )
    
    # Initial map should have 3 activities
    initial_map = await get_process_map(session_id)
    assert len(initial_map.activities) == 3
    
    # Start facilitating first activity
    result = await facilitate_activity(
        session_id=session_id,
        activity_id="get-data"
    )
    
    # Should detect blocker
    assert result.status == ConversationStatus.BLOCKED
    assert "database" in result.blocker.description.lower()
    
    # Map should now have 4 activities
    evolved_map = await get_process_map(session_id)
    assert len(evolved_map.activities) == 4
    
    # New activity should be prerequisite
    new_activity = [a for a in evolved_map.activities if "database" in a.goal.lower()][0]
    assert new_activity.activity_id in evolved_map.get_activity("get-data").dependencies
    
    # Process map version incremented
    assert evolved_map.version == initial_map.version + 1
```

### Test Scenario 2: Contradiction Triggers Reconciliation

```python
async def test_contradiction_triggers_reconciliation():
    """
    Test that Consistency Manager detects contradictions and creates reconciliation.
    
    Flow:
    1. Activity A completes: "Retention rate is 65%"
    2. Activity B completes: "Based on 70% retention..."
    3. Consistency Manager detects contradiction
    4. Activities A and B marked for revisit
    5. Reconciliation activity created
    """
    
    session_id = await create_session()
    
    # Complete two activities with contradictory outputs
    await complete_activity(
        session_id=session_id,
        activity_id="calculate-retention",
        output={"retention_rate": 0.65, "metric": "monthly"}
    )
    
    await complete_activity(
        session_id=session_id,
        activity_id="forecast-retention",
        output={"assumptions": {"retention_rate": 0.70}, "forecast": []}
    )
    
    # Consistency check should run automatically
    await asyncio.sleep(1)
    
    # Get updated map
    process_map = await get_process_map(session_id)
    
    # Should have reconciliation activity
    reconciliation_activities = [
        a for a in process_map.activities
        if a.metadata.get("reconciliation")
    ]
    assert len(reconciliation_activities) == 1
    
    # Original activities should be marked for revisit
    activity_a = process_map.get_activity("calculate-retention")
    activity_b = process_map.get_activity("forecast-retention")
    assert activity_a.status == ActivityStatus.REVISIT
    assert activity_b.status == ActivityStatus.REVISIT
```

### Test Scenario 3: Complete Emergent Workflow

```python
async def test_complete_emergent_workflow():
    """
    Test full emergent workflow from goal to synthesis.
    
    Flow:
    1. User provides business goal
    2. Process Mapper creates initial activities
    3. Agent Selector assigns participants
    4. Activity Facilitator detects blocker → creates new activity
    5. Blocker activity completes
    6. Original activity completes
    7. Consistency Manager detects issue → creates reconciliation
    8. Reconciliation completes
    9. Result Synthesizer determines goal achieved
    10. Session marked complete
    """
    
    # This is the "holy grail" test - proves emergent system works
    
    session_id = await create_facilitated_session(
        goal="Increase customer retention by 20%"
    )
    
    # Initial map
    v1_map = await get_process_map(session_id)
    initial_activity_count = len(v1_map.activities)
    
    # Execute facilitated process
    result = await execute_facilitated_process(session_id)
    
    # Final map should have MORE activities than initial
    # (blockers created new activities)
    final_map = await get_process_map(session_id)
    assert len(final_map.activities) > initial_activity_count
    
    # Should have multiple versions
    assert final_map.version > 1
    
    # Session should be complete
    session = await get_session(session_id)
    assert session.status == SessionStatus.COMPLETED
    
    # Should have final synthesis
    assert result.final_deliverable is not None
    assert result.goal_achieved is True
    
    # Verify emergent behaviors occurred:
    # 1. Dynamic activity creation
    emergent_activities = [
        a for a in final_map.activities
        if a.metadata.get("blocker_resolution") or a.metadata.get("reconciliation")
    ]
    assert len(emergent_activities) > 0
    
    # 2. Map evolution
    history = await get_map_history(session_id)
    assert len(history) > 1
    
    # 3. Facilitation conversations
    for activity in final_map.activities:
        if activity.status == ActivityStatus.GOAL_MET:
            assert len(activity.facilitation_history.exchanges) > 0
```

---

## Success Criteria

### The system is truly emergent when:

✅ **Dynamic Adaptation**
- [ ] Activities created during execution, not just upfront
- [ ] Process map restructures based on learnings
- [ ] Dependencies emerge from activity interactions

✅ **Conversation-Driven**
- [ ] Facilitator guides through questions, not commands
- [ ] Agents propose approaches
- [ ] Multiple exchanges until goal met

✅ **Self-Correcting**
- [ ] Contradictions automatically detected
- [ ] Reconciliation activities created
- [ ] Process restructures to resolve issues

✅ **Distributed Intelligence**
- [ ] Coordinating agents collaborate as peers
- [ ] Specialized agents contribute expertise
- [ ] No single point of control

✅ **Goal-Oriented**
- [ ] Focus on business goal, not prescribed steps
- [ ] Result Synthesizer determines achievement
- [ ] Additional work created if goal not met

---

## Timeline to Emergent System

| Phase | Duration | Deliverable | Validates |
|-------|----------|-------------|-----------|
| **Phase 1** | 2 weeks | Activity Facilitator with conversation loops | Conversation-driven progress |
| **Phase 2** | 1 week | Consistency Manager | Self-correction |
| **Phase 3** | 1 week | Process Map Evolution | Dynamic adaptation |
| **Phase 4** | 1 week | Result Synthesizer | Goal achievement assessment |
| **Testing** | 1 week | Complete E2E test | All emergent behaviors |

**Total: 6 weeks to fully emergent system**

---

## Next Immediate Steps

### This Week (Dec 11-18, 2025)

1. **Day 1-2**: Design conversation protocol and data models
2. **Day 3-5**: Implement basic conversation loop in Activity Facilitator
3. **Day 6-7**: Test conversation loop with single activity

### Next Week (Dec 18-25, 2025)

1. **Day 1-3**: Implement blocker detection
2. **Day 4-5**: Implement dynamic activity creation
3. **Day 6-7**: Test blocker → new activity flow

### Week 3 (Dec 25-Jan 1, 2026)

1. **Day 1-3**: Implement Consistency Manager agent
2. **Day 4-5**: Integrate consistency checks
3. **Day 6-7**: Test contradiction detection

---

## Measuring Success

### Metrics for Emergent Behavior

1. **Activity Emergence Rate**
   - Initial activities: N
   - Final activities: M
   - Emergence ratio: (M - N) / N
   - Target: > 0.3 (30% more activities than initial plan)

2. **Map Evolution Frequency**
   - Map versions: V
   - Triggers: Blocker, Contradiction, Insight
   - Target: V > 3 for typical session

3. **Facilitation Depth**
   - Avg exchanges per activity: E
   - Target: E > 4 (shows conversation happening)

4. **Self-Correction**
   - Contradictions detected: C
   - Reconciliations created: R
   - Target: R/C > 0.8 (80% of contradictions trigger reconciliation)

5. **Goal Achievement**
   - Sessions reaching goal: G
   - Total sessions: S
   - Target: G/S > 0.7 (70% success rate)

---

## Conclusion

The architectural inconsistency is solvable. The foundation is solid—we have:
- ✅ Process Mapper
- ✅ Agent Selector
- ✅ Process Map storage and versioning
- ✅ Observability infrastructure
- ✅ Distributed compute

We're missing the **emergent behavior layer**:
- 🔴 Conversation-driven facilitation
- 🔴 Dynamic activity creation
- 🔴 Self-correction via consistency checking
- 🔴 Goal-oriented synthesis

**6 weeks of focused work** will transform the system from "predetermined pipelines" to "emergent coordination."

The path is clear. Let's build it.
