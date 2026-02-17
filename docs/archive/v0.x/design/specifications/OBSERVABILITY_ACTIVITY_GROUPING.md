# Dynamic Activity Grouping for Observability

**Version**: 1.0  
**Date**: November 25, 2025  
**Status**: Design Proposal

## Overview

This document describes the **dynamic activity grouping system** that allows the Process Mapper to semantically group related activities as the facilitated process evolves, enabling better visualization and reducing UI overwhelm.

---

## Core Concept

As a facilitated process unfolds, activities naturally cluster into **semantic phases** or **work groups**:

- **"Decomposition & Planning"** - Early activities that break down the problem
- **"Data Collection"** - Activities that gather necessary information
- **"Analysis"** - Activities that process and understand data
- **"Strategy Development"** - Activities that create solutions
- **"Implementation"** - Activities that execute the plan

These groupings:
1. **Emerge naturally** during facilitation (not predetermined)
2. **Provide context** for understanding the process structure
3. **Enable collapsing** completed groups to reduce visual clutter
4. **Are created by Process Mapper** based on activity patterns and outcomes

---

## When Groups Are Created

### Scenario 1: Initial Process Map Creation

When Process Mapper creates the initial process map, it can propose initial groups:

```python
# Process Mapper creates initial map
business_goal = "Increase customer retention by 20%"

# Initial activities proposed
activities = [
    Activity(id="act-1", goal="Understand current retention metrics"),
    Activity(id="act-2", goal="Identify retention drivers"),
    Activity(id="act-3", goal="Develop improvement strategies")
]

# Process Mapper creates initial group
group = ActivityGroup(
    group_id="group-planning",
    group_name="Problem Understanding",
    activity_ids=["act-1", "act-2"],
    status="proposed"
)
```

### Scenario 2: After Reevaluation

When Process Mapper reevaluates the map (e.g., splits Activity 2 into 2a and 2b):

```python
# Reevaluation triggered: segmentation discovered
# Activity 2 splits into 2a (high-value) and 2b (SMB)

# Process Mapper creates new group for segment analysis
group = ActivityGroup(
    group_id="group-segment-analysis",
    group_name="Segment-Based Retention Analysis",
    activity_ids=["act-2a", "act-2b"],
    status="in_progress",
    parent_group="group-planning"  # Optional: nested grouping
)
```

### Scenario 3: When Activities Complete

When all activities in a potential group complete:

```python
# Activities 0, 1, 1a, 1b have all completed
# Process Mapper recognizes these form a logical group

group = ActivityGroup(
    group_id="group-data-collection",
    group_name="Data Collection & Access",
    activity_ids=["act-0", "act-1", "act-1a", "act-1b"],
    status="completed",
    collapsible=True  # Can be collapsed in UI
)
```

### Scenario 4: When Blocker Spawns Sub-Activities

When a blocker creates resolution activities:

```python
# Activity 2b is blocked, spawns resolution activity 2b-1

group = ActivityGroup(
    group_id="group-blocker-resolution-1",
    group_name="Resolve Data Access Blocker",
    activity_ids=["act-2b-1"],
    status="in_progress",
    parent_activity="act-2b"  # Linked to blocked activity
)
```

---

## Data Model

### ActivityGroup

```python
class ActivityGroup(BaseModel):
    """A semantic grouping of related activities."""
    group_id: str = Field(..., description="Unique group identifier")
    group_name: str = Field(..., description="Human-readable group name")
    group_description: Optional[str] = Field(None, description="What this group represents")
    
    # Activities in this group
    activity_ids: List[str] = Field(default_factory=list, description="Activity IDs in group")
    
    # Status (derived from activities)
    status: str = Field(..., description="proposed, in_progress, completed, blocked")
    
    # Progress (derived)
    total_activities: int = Field(0, description="Total activities in group")
    completed_activities: int = Field(0, description="Completed activities in group")
    progress_percent: float = Field(0.0, description="Percentage complete")
    
    # Hierarchy (optional)
    parent_group: Optional[str] = Field(None, description="Parent group ID if nested")
    sub_groups: List[str] = Field(default_factory=list, description="Sub-group IDs")
    
    # UI behavior
    collapsible: bool = Field(True, description="Can this group be collapsed in UI?")
    collapsed_by_default: bool = Field(False, description="Should UI collapse this by default?")
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = Field(default="process-mapper-v1")
    
    # Visual styling (optional)
    color: Optional[str] = Field(None, description="UI color hint (e.g., '#3b82f6')")
    icon: Optional[str] = Field(None, description="UI icon hint (e.g., '📊')")
```

### ProcessMap Enhancement

Add grouping support to ProcessMap:

```python
class ProcessMap(BaseModel):
    # ... existing fields ...
    
    # NEW: Activity grouping
    activity_groups: Dict[str, ActivityGroup] = Field(
        default_factory=dict,
        description="Activity groups by group_id"
    )
    group_order: List[str] = Field(
        default_factory=list,
        description="Ordered list of group IDs for display"
    )
```

---

## Process Mapper Logic

### When to Create Groups

The Process Mapper uses **heuristics** to decide when to create groups:

```python
class ProcessMapper:
    def should_create_group(
        self,
        activities: List[Activity],
        trigger: str
    ) -> bool:
        """Determine if activities should be grouped."""
        
        # Heuristic 1: Related goals (semantic similarity)
        if self.have_similar_goals(activities):
            return True
        
        # Heuristic 2: Common dependencies (all depend on same parent)
        if self.share_dependencies(activities):
            return True
        
        # Heuristic 3: Temporal clustering (all completed around same time)
        if self.completed_together(activities):
            return True
        
        # Heuristic 4: All spawn from same blocker resolution
        if trigger == "blocker_resolution":
            return True
        
        # Heuristic 5: User/system specified grouping
        if trigger == "explicit_grouping":
            return True
        
        return False
    
    def suggest_group_name(
        self,
        activities: List[Activity],
        context: str
    ) -> str:
        """Use LLM to suggest semantic group name."""
        
        prompt = f"""
        Given these activities:
        {[a.goal for a in activities]}
        
        Context: {context}
        
        Suggest a concise, semantic group name (3-5 words) that captures
        what these activities collectively accomplish.
        """
        
        group_name = await self.llm_client.generate(prompt)
        return group_name
```

### Automatic Grouping Example

```python
async def auto_group_completed_activities(
    self,
    session_id: str,
    process_map: ProcessMap
) -> Optional[ActivityGroup]:
    """
    After activities complete, check if they should be grouped.
    Called by Process Mapper periodically or on reevaluation.
    """
    
    # Find recently completed activities not in a group
    ungrouped_completed = []
    for activity_id in process_map.completed_activities:
        if not self.is_in_group(activity_id, process_map):
            ungrouped_completed.append(process_map.get_activity(activity_id))
    
    if len(ungrouped_completed) < 2:
        return None  # Need at least 2 activities to group
    
    # Check if they should be grouped
    if self.should_create_group(ungrouped_completed, "auto_completion"):
        # Generate group name
        group_name = await self.suggest_group_name(
            ungrouped_completed,
            context=f"These activities were completed in sequence for: {process_map.business_goal}"
        )
        
        # Create group
        group = ActivityGroup(
            group_id=f"group-{uuid.uuid4()}",
            group_name=group_name,
            activity_ids=[a.activity_id for a in ungrouped_completed],
            status="completed",
            total_activities=len(ungrouped_completed),
            completed_activities=len(ungrouped_completed),
            progress_percent=100.0,
            collapsible=True,
            collapsed_by_default=True  # Collapse completed groups by default
        )
        
        # Add to process map
        process_map.activity_groups[group.group_id] = group
        process_map.group_order.append(group.group_id)
        
        # Emit event
        await self.event_client.emit_activity_grouping(
            session_id=session_id,
            group_id=group.group_id,
            group_name=group.group_name,
            activity_ids=group.activity_ids,
            created_by="process-mapper-v1"
        )
        
        return group
    
    return None
```

---

## UI Rendering

### Collapsed Group View

```
┌─────────────────────────────────────────────────────────────────┐
│ ▶ Data Collection & Access (4 activities - 100% complete) 🟢   │
│   Completed 15 minutes ago                                      │
│   [ Expand ] [ View Timeline ]                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Expanded Group View

```
┌─────────────────────────────────────────────────────────────────┐
│ ▼ Data Collection & Access (4 activities - 100% complete) 🟢   │
│   ┌───────────────────────────────────────────────────────────┐ │
│   │ 🟢 Activity 0: Obtain Database Access (12m)              │ │
│   │ Agent: IT-Access-Agent  │  Compute: compute-004          │ │
│   │ [ View Details ]                                          │ │
│   └───────────────────────────────────────────────────────────┘ │
│   ┌───────────────────────────────────────────────────────────┐ │
│   │ 🟢 Activity 1: Understand Current Retention (23m)        │ │
│   │ Agent: DataAnalyst  │  Compute: compute-001              │ │
│   │ [ View Details ]                                          │ │
│   └───────────────────────────────────────────────────────────┘ │
│   ┌───────────────────────────────────────────────────────────┐ │
│   │ 🟢 Activity 1a: Verify Baseline Metrics (8m)             │ │
│   │ Agent: MetricReporter  │  Compute: compute-001           │ │
│   │ [ View Details ]                                          │ │
│   └───────────────────────────────────────────────────────────┘ │
│   ┌───────────────────────────────────────────────────────────┐ │
│   │ 🟢 Activity 1b: Document Assumptions (5m)                │ │
│   │ Agent: DocumentationAgent  │  Compute: compute-002       │ │
│   │ [ View Details ]                                          │ │
│   └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│   [ Collapse ] [ View as Timeline ] [ Export Group ]           │
└─────────────────────────────────────────────────────────────────┘
```

### Mixed View (Some Groups, Some Individual Activities)

```
┌─────────────────────────────────────────────────────────────────┐
│ Workflow View                                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ▶ Group: Data Collection & Access                             │
│     4 activities - 100% complete 🟢                            │
│                                                                 │
│              ↓                                                  │
│                                                                 │
│  ▼ Group: Segment-Based Analysis                               │
│     3 activities - 67% in progress 🔵                          │
│     ┌───────────────────────┐  ┌───────────────────────┐      │
│     │ Activity 2a:          │  │ Activity 2b:          │      │
│     │ High-Value Segment    │  │ SMB Segment           │      │
│     │ 🔵 Active (45%)       │  │ 🔴 Blocked            │      │
│     └───────────────────────┘  └───────────────────────┘      │
│                                        ↓                        │
│                                 ┌───────────────────────┐      │
│                                 │ Activity 2b-1:        │      │
│                                 │ Obtain Pricing Data   │      │
│                                 │ 🔵 Active             │      │
│                                 └───────────────────────┘      │
│                                                                 │
│              ↓                                                  │
│                                                                 │
│  Activity 3: Synthesize Findings                               │
│  🟡 Proposed (waiting for dependencies)                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## React Component Implementation

```javascript
// serving/frontend/src/components/ActivityGroupCard.jsx

function ActivityGroupCard({ group, processMap, expanded, onToggle }) {
  const activities = group.activity_ids.map(id => processMap.activities[id]);
  
  const statusIcon = group.status === 'completed' ? '🟢' :
                     group.status === 'in_progress' ? '🔵' :
                     group.status === 'blocked' ? '🔴' : '🟡';
  
  if (!expanded) {
    return (
      <div className="activity-group-collapsed" onClick={onToggle}>
        <div className="group-header">
          <span className="expand-icon">▶</span>
          <span className="group-name">{group.group_name}</span>
          <span className="group-status">{statusIcon}</span>
        </div>
        <div className="group-summary">
          {group.total_activities} activities - {group.progress_percent}% complete
        </div>
        <div className="group-actions">
          <button onClick={(e) => { e.stopPropagation(); onExpand(); }}>
            Expand
          </button>
          <button onClick={(e) => { e.stopPropagation(); onViewTimeline(); }}>
            View Timeline
          </button>
        </div>
      </div>
    );
  }
  
  return (
    <div className="activity-group-expanded">
      <div className="group-header">
        <span className="expand-icon">▼</span>
        <span className="group-name">{group.group_name}</span>
        <span className="group-status">{statusIcon}</span>
      </div>
      <div className="group-description">
        {group.group_description}
      </div>
      <div className="group-activities">
        {activities.map(activity => (
          <ActivityCard
            key={activity.activity_id}
            activity={activity}
            onClick={() => onActivityClick(activity)}
          />
        ))}
      </div>
      <div className="group-actions">
        <button onClick={onToggle}>Collapse</button>
        <button onClick={onViewTimeline}>View as Timeline</button>
        <button onClick={onExport}>Export Group</button>
      </div>
    </div>
  );
}
```

---

## Grouping Strategies

### Strategy 1: Temporal Grouping

Group activities that complete around the same time:

```python
def temporal_grouping(completed_activities: List[Activity]) -> List[List[Activity]]:
    """Group activities completed within 5 minutes of each other."""
    
    groups = []
    current_group = []
    
    sorted_activities = sorted(completed_activities, key=lambda a: a.completed_at)
    
    for activity in sorted_activities:
        if not current_group:
            current_group.append(activity)
        else:
            last_activity = current_group[-1]
            time_diff = (activity.completed_at - last_activity.completed_at).total_seconds()
            
            if time_diff <= 300:  # 5 minutes
                current_group.append(activity)
            else:
                if len(current_group) >= 2:
                    groups.append(current_group)
                current_group = [activity]
    
    if len(current_group) >= 2:
        groups.append(current_group)
    
    return groups
```

### Strategy 2: Dependency Grouping

Group activities that share the same parent/dependency:

```python
def dependency_grouping(activities: List[Activity]) -> Dict[str, List[Activity]]:
    """Group activities by shared dependencies."""
    
    groups = {}
    
    for activity in activities:
        if not activity.depends_on:
            continue
        
        # Group by first dependency
        parent_id = activity.depends_on[0]
        
        if parent_id not in groups:
            groups[parent_id] = []
        
        groups[parent_id].append(activity)
    
    # Only keep groups with 2+ activities
    return {k: v for k, v in groups.items() if len(v) >= 2}
```

### Strategy 3: Semantic Grouping (LLM-Based)

Use LLM to determine if activities are semantically related:

```python
async def semantic_grouping(
    activities: List[Activity],
    business_goal: str
) -> Optional[str]:
    """Use LLM to determine if activities should be grouped."""
    
    prompt = f"""
    Business Goal: {business_goal}
    
    Activities:
    {chr(10).join([f"- {a.activity_id}: {a.goal}" for a in activities])}
    
    Question: Do these activities form a coherent group that accomplishes
    a specific phase or sub-goal of the overall business goal?
    
    If yes, respond with: YES | <group_name> | <brief_description>
    If no, respond with: NO
    
    Example: YES | Data Collection & Validation | These activities gather and verify all necessary data sources
    """
    
    response = await llm_client.generate(prompt)
    
    if response.startswith("YES"):
        parts = response.split("|")
        group_name = parts[1].strip()
        description = parts[2].strip()
        return (group_name, description)
    
    return None
```

---

## Grouping Rules

### Rule 1: Completed Groups Collapse by Default

When all activities in a group complete, automatically collapse the group to reduce visual clutter:

```python
async def check_group_completion(group: ActivityGroup, process_map: ProcessMap):
    """Check if group is complete and update UI state."""
    
    all_complete = all(
        activity_id in process_map.completed_activities
        for activity_id in group.activity_ids
    )
    
    if all_complete:
        group.status = "completed"
        group.collapsed_by_default = True
        group.progress_percent = 100.0
```

### Rule 2: Active Groups Expand by Default

Groups with in-progress or blocked activities should be expanded by default:

```python
if group.status in ["in_progress", "blocked"]:
    group.collapsed_by_default = False
```

### Rule 3: Hierarchical Grouping

Groups can contain sub-groups for complex processes:

```python
# Parent group
parent_group = ActivityGroup(
    group_id="group-analysis",
    group_name="Comprehensive Retention Analysis",
    activity_ids=[],  # No direct activities
    sub_groups=["group-high-value", "group-smb"]
)

# Sub-groups
sub_group_1 = ActivityGroup(
    group_id="group-high-value",
    group_name="High-Value Customer Analysis",
    activity_ids=["act-2a", "act-3a"],
    parent_group="group-analysis"
)

sub_group_2 = ActivityGroup(
    group_id="group-smb",
    group_name="SMB Customer Analysis",
    activity_ids=["act-2b", "act-3b"],
    parent_group="group-analysis"
)
```

### Rule 4: Dynamic Regrouping

If process map reevaluates and activities move, update groups:

```python
async def handle_reevaluation(
    process_map: ProcessMap,
    reevaluation_event: ReevaluationEvent
):
    """Update groups after reevaluation."""
    
    # Check if any activities were moved or split
    for group in process_map.activity_groups.values():
        # Remove activities that no longer exist
        group.activity_ids = [
            aid for aid in group.activity_ids
            if aid in process_map.activities
        ]
        
        # Recalculate status and progress
        group.status = derive_group_status(group, process_map)
        group.progress_percent = calculate_group_progress(group, process_map)
    
    # Remove empty groups
    process_map.activity_groups = {
        gid: group for gid, group in process_map.activity_groups.items()
        if len(group.activity_ids) > 0
    }
```

---

## Benefits of Dynamic Grouping

### 1. Visual Clarity

- Reduce 100 activities to 5-10 groups
- Completed work collapses out of the way
- Focus on active/blocked work

### 2. Semantic Understanding

- Groups provide context ("Oh, this is the data collection phase")
- Easier to explain the process to stakeholders
- Natural narrative structure

### 3. Progressive Disclosure

- High-level view: See groups
- Medium view: Expand active groups
- Detailed view: Click individual activities

### 4. Flexible Organization

- Groups emerge organically (not forced upfront)
- Can re-group as understanding evolves
- Supports both flat and hierarchical structures

---

## Example: Full Process with Grouping

```
Session: Increase customer retention by 20%

Group 1: Problem Decomposition (Collapsed - 100% complete) ▶
  - Process mapping
  - Initial planning
  - 3 activities, completed 2 hours ago

Group 2: Data Collection & Access (Collapsed - 100% complete) ▶
  - Database access
  - Historical data extraction
  - 4 activities, completed 1 hour ago

Group 3: Segment-Based Analysis (Expanded - 67% in progress) ▼
  Activity 2a: High-Value Customer Analysis 🔵 Active
  Activity 2b: SMB Customer Analysis 🔴 Blocked
    ↳ Sub-activity 2b-1: Obtain Pricing Data 🔵 Active
  Activity 2c: Mid-Market Analysis 🟡 Proposed

Group 4: Strategy Development (Collapsed - Not started) ▶
  - Planned: 6 activities
  - Waiting for Group 3 completion

Group 5: Implementation Planning (Collapsed - Not started) ▶
  - Planned: 5 activities
  - Waiting for Group 4 completion
```

---

## Summary

✅ **Dynamic**: Groups created as process evolves, not predetermined  
✅ **Semantic**: Groups named based on what they accomplish  
✅ **Collapsible**: Completed groups collapse to reduce clutter  
✅ **Hierarchical**: Supports nested groups for complex processes  
✅ **Automatic**: Process Mapper suggests groups, minimal user intervention  
✅ **Flexible**: Can re-group as understanding changes  

**Result**: Process maps with 100+ activities become manageable and understandable.

---

**Version**: 1.0  
**Date**: November 25, 2025  
**Status**: Design Proposal  
**Related**: [Event-Driven Architecture](OBSERVABILITY_EVENT_DRIVEN.md)





