"""
Activity Grouping Service

Provides dynamic, semantic grouping of activities for visualization.
Groups are created by analyzing activity relationships, goals, and phases.
"""

import logging
from typing import List, Dict, Optional, Set
from models.process_map import ProcessMap, Activity, ActivityGroup, ActivityStatus

logger = logging.getLogger(__name__)


class ActivityGroupingService:
    """
    Analyzes activities and creates semantic groupings for better visualization.
    
    Grouping strategies:
    1. Phase-based: Discovery, Analysis, Implementation, Validation
    2. Dependency-based: Independent groups based on dependency chains
    3. Goal-based: Activities with similar goals or topics
    """
    
    def __init__(self):
        self.common_phases = [
            "Discovery",
            "Analysis",
            "Planning",
            "Implementation",
            "Validation",
            "Refinement",
            "Documentation"
        ]
    
    def analyze_and_group(self, process_map: ProcessMap) -> List[ActivityGroup]:
        """
        Analyze activities in a process map and create semantic groups.
        Returns a list of newly created groups.
        """
        if not process_map.activities:
            return []
        
        logger.info(f"Analyzing {len(process_map.activities)} activities for grouping")
        
        groups = []
        
        # Strategy 1: Phase-based grouping using goal keywords
        phase_groups = self._create_phase_groups(process_map)
        groups.extend(phase_groups)
        
        # Strategy 2: Dependency chain grouping for ungrouped activities
        dependency_groups = self._create_dependency_groups(process_map)
        groups.extend(dependency_groups)
        
        # Update process map with groups
        for group in groups:
            process_map.add_activity_group(
                group_id=group.group_id,
                name=group.name,
                activity_ids=group.activity_ids,
                description=group.description,
                parent_group_id=group.parent_group_id,
                created_by=group.created_by
            )
            
            # Update group status
            process_map.update_group_status(group.group_id)
        
        logger.info(f"Created {len(groups)} activity groups")
        return groups
    
    def _create_phase_groups(self, process_map: ProcessMap) -> List[ActivityGroup]:
        """Create groups based on common phases identified in activity goals."""
        phase_keywords = {
            "Discovery": ["understand", "discover", "explore", "identify", "investigate"],
            "Analysis": ["analyze", "examine", "evaluate", "assess", "review"],
            "Planning": ["plan", "design", "architect", "structure", "organize"],
            "Implementation": ["implement", "build", "create", "develop", "execute"],
            "Validation": ["validate", "test", "verify", "confirm", "check"],
            "Refinement": ["refine", "optimize", "improve", "enhance", "polish"],
            "Documentation": ["document", "record", "log", "report", "summarize"]
        }
        
        phase_activities: Dict[str, List[str]] = {phase: [] for phase in phase_keywords.keys()}
        
        for activity_id, activity in process_map.activities.items():
            goal_lower = activity.goal.lower()
            
            # Check which phase this activity belongs to
            matched_phase = None
            for phase, keywords in phase_keywords.items():
                if any(keyword in goal_lower for keyword in keywords):
                    matched_phase = phase
                    break
            
            if matched_phase:
                phase_activities[matched_phase].append(activity_id)
        
        # Create groups for phases that have activities
        groups = []
        group_number = 1
        for phase, activity_ids in phase_activities.items():
            if len(activity_ids) > 0:
                group_id = f"phase-{phase.lower()}-{process_map.map_id}"
                group = ActivityGroup(
                    group_id=group_id,
                    name=f"{phase} Phase",
                    description=f"Activities related to the {phase.lower()} phase",
                    activity_ids=activity_ids,
                    parent_group_id=None,
                    status="in_progress",
                    created_by="activity-grouping-service"
                )
                groups.append(group)
                group_number += 1
        
        return groups
    
    def _create_dependency_groups(self, process_map: ProcessMap) -> List[ActivityGroup]:
        """Create groups based on dependency chains."""
        grouped_activities = set()
        
        # Collect all activities that are already in phase groups
        for group in process_map.activity_groups.values():
            grouped_activities.update(group.activity_ids)
        
        ungrouped = [
            aid for aid in process_map.activities.keys()
            if aid not in grouped_activities
        ]
        
        if not ungrouped:
            return []
        
        # Create dependency chains
        chains = []
        visited = set()
        
        for activity_id in ungrouped:
            if activity_id in visited:
                continue
            
            chain = self._build_dependency_chain(
                activity_id,
                process_map,
                ungrouped
            )
            
            if len(chain) > 1:  # Only create groups for chains with multiple activities
                chains.append(chain)
                visited.update(chain)
        
        # Create groups from chains
        groups = []
        for idx, chain in enumerate(chains):
            group_id = f"chain-{idx + 1}-{process_map.map_id}"
            
            # Create a descriptive name based on the first activity's goal
            first_activity = process_map.activities[chain[0]]
            chain_name = f"Activity Chain: {first_activity.goal[:40]}..."
            
            group = ActivityGroup(
                group_id=group_id,
                name=chain_name,
                description=f"Dependency chain of {len(chain)} related activities",
                activity_ids=chain,
                parent_group_id=None,
                status="in_progress",
                created_by="activity-grouping-service"
            )
            groups.append(group)
        
        return groups
    
    def _build_dependency_chain(
        self,
        start_id: str,
        process_map: ProcessMap,
        valid_ids: List[str]
    ) -> List[str]:
        """Build a dependency chain starting from a given activity."""
        chain = [start_id]
        visited = {start_id}
        
        # Follow dependencies forward (activities that depend on this one)
        current = start_id
        while True:
            next_activity = None
            for aid in valid_ids:
                if aid in visited:
                    continue
                activity = process_map.activities[aid]
                if current in activity.depends_on:
                    next_activity = aid
                    break
            
            if next_activity:
                chain.append(next_activity)
                visited.add(next_activity)
                current = next_activity
            else:
                break
        
        return chain
    
    def suggest_group_collapse(self, process_map: ProcessMap) -> List[str]:
        """
        Suggest which groups should be collapsed in the UI.
        Returns list of group IDs that should be collapsed.
        """
        collapsible_groups = []
        
        for group_id, group in process_map.activity_groups.items():
            # Collapse completed groups
            if group.status == "completed":
                collapsible_groups.append(group_id)
            
            # Collapse large groups that are not currently active
            elif len(group.activity_ids) > 5:
                has_active = any(
                    aid in process_map.in_progress_activities
                    for aid in group.activity_ids
                )
                if not has_active:
                    collapsible_groups.append(group_id)
        
        return collapsible_groups


# Singleton instance
_grouping_service: Optional[ActivityGroupingService] = None


def get_activity_grouping_service() -> ActivityGroupingService:
    """Get the singleton activity grouping service."""
    global _grouping_service
    if _grouping_service is None:
        _grouping_service = ActivityGroupingService()
    return _grouping_service


def set_activity_grouping_service(service: ActivityGroupingService):
    """Set the activity grouping service (mainly for testing)."""
    global _grouping_service
    _grouping_service = service


