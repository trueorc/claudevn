"""Compute instance registry service."""

import asyncio
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from collections import defaultdict

from models.compute import (
    ComputeInstance,
    ComputeAuthStatus,
    InstanceStatus,
    InstanceCapabilities,
    InstanceResources,
    AggregatedCapabilities,
)
from storage.registry_storage import RegistryStorage

logger = logging.getLogger(__name__)


class ComputeRegistry:
    """Registry for managing compute instances.

    This service maintains the registry of all compute instances,
    tracks their status, provides discovery capabilities, and manages
    SSE event queues for connected instances.
    """

    def __init__(self, storage_backend: Optional[RegistryStorage] = None):
        """Initialize the registry.

        Args:
            storage_backend: Optional storage backend for persistence
        """
        self._instances: Dict[str, ComputeInstance] = {}
        self._storage = storage_backend
        self._capability_index: Dict[str, List[str]] = defaultdict(list)
        self._project_index: Dict[str, List[str]] = defaultdict(list)  # project_id -> [instance_ids]
        # SSE event queues for each connected instance
        self._event_queues: Dict[str, asyncio.Queue] = {}

        logger.info("Initialized ComputeRegistry")
    
    async def initialize(self):
        """Initialize registry and load from storage if available."""
        if self._storage:
            await self._load_from_storage()
    
    async def _load_from_storage(self):
        """Load instances from storage backend."""
        try:
            if not self._storage:
                return
            
            instances_data = await self._storage.load_all_instances()
            
            for instance_id, instance_data in instances_data.items():
                try:
                    # Create ComputeInstance from stored data
                    instance = ComputeInstance(**instance_data)
                    self._instances[instance_id] = instance

                    # Update indexes
                    self._update_capability_index(instance)
                    self._update_project_index(instance)
                    
                except Exception as e:
                    logger.error(f"Failed to load instance {instance_id}: {e}")
                    continue
            
            logger.info(f"Loaded {len(self._instances)} instances from storage")
            
        except Exception as e:
            logger.error(f"Failed to load from storage: {e}")
    
    async def _save_to_storage(self, instance: ComputeInstance):
        """Save instance to storage backend.
        
        Args:
            instance: Instance to save
        """
        try:
            if self._storage:
                instance_dict = instance.model_dump()
                await self._storage.save_compute_instance(instance.instance_id, instance_dict)
                logger.debug(f"Saved instance {instance.instance_id} to storage")
        except Exception as e:
            logger.error(f"Failed to save to storage: {e}")
    
    def _update_project_index(self, instance: ComputeInstance):
        """Update the project index for fast lookups.

        Args:
            instance: Instance whose project tags to index
        """
        instance_id = instance.instance_id
        for project_id in instance.project_ids:
            if instance_id not in self._project_index.get(project_id, []):
                self._project_index[project_id].append(instance_id)

    def _remove_from_project_index(self, instance_id: str):
        """Remove instance from project index.

        Args:
            instance_id: Instance ID to remove
        """
        for key in list(self._project_index.keys()):
            if instance_id in self._project_index[key]:
                self._project_index[key].remove(instance_id)
                if not self._project_index[key]:
                    del self._project_index[key]

    def _update_capability_index(self, instance: ComputeInstance):
        """Update the capability index for fast lookups.

        Args:
            instance: Instance whose capabilities to index
        """
        instance_id = instance.instance_id

        # Index agents
        for agent_id in instance.capabilities.agents:
            if instance_id not in self._capability_index.get(f"agent:{agent_id}", []):
                self._capability_index[f"agent:{agent_id}"].append(instance_id)

        # Index tools
        for tool_id in instance.capabilities.tools:
            if instance_id not in self._capability_index.get(f"tool:{tool_id}", []):
                self._capability_index[f"tool:{tool_id}"].append(instance_id)

        # Index labels (for work routing)
        for label in instance.capabilities.labels:
            if instance_id not in self._capability_index.get(f"label:{label}", []):
                self._capability_index[f"label:{label}"].append(instance_id)

        # Index tools_available (specialized tools for routing)
        for tool in instance.capabilities.tools_available:
            if instance_id not in self._capability_index.get(f"tool_available:{tool}", []):
                self._capability_index[f"tool_available:{tool}"].append(instance_id)

        logger.debug(f"Updated capability index for {instance_id}")
    
    def _remove_from_capability_index(self, instance_id: str):
        """Remove instance from capability index.
        
        Args:
            instance_id: Instance ID to remove
        """
        # Remove from all capability lists
        for key in list(self._capability_index.keys()):
            if instance_id in self._capability_index[key]:
                self._capability_index[key].remove(instance_id)
                if not self._capability_index[key]:
                    del self._capability_index[key]
        
        logger.debug(f"Removed {instance_id} from capability index")
    
    async def add_instance(
        self,
        instance: ComputeInstance
    ) -> ComputeInstance:
        """Register a new compute instance.
        
        Args:
            instance: Instance to register
            
        Returns:
            Registered instance
            
        Raises:
            ValueError: If instance_id already exists
        """
        if instance.instance_id in self._instances:
            raise ValueError(f"Instance {instance.instance_id} already registered")
        
        # Set initial timestamps (preserve passed status - model defaults to ONLINE)
        now = datetime.now(timezone.utc)
        instance.registered_at = now
        instance.last_heartbeat = now
        instance.failed_health_checks = 0
        
        # Add to registry
        self._instances[instance.instance_id] = instance

        # Update indexes
        self._update_capability_index(instance)
        self._update_project_index(instance)

        # Save to storage
        await self._save_to_storage(instance)

        logger.info(
            f"Registered instance {instance.instance_id} "
            f"({instance.name}) with {len(instance.capabilities.agents)} agents"
        )
        
        return instance
    
    async def remove_instance(self, instance_id: str) -> bool:
        """Deregister a compute instance.

        Args:
            instance_id: Instance ID to remove

        Returns:
            True if removed, False if not found
        """
        if instance_id not in self._instances:
            return False

        # Remove from indexes
        self._remove_from_capability_index(instance_id)
        self._remove_from_project_index(instance_id)

        # Remove SSE event queue if present
        self._remove_event_queue(instance_id)

        # Remove from registry
        del self._instances[instance_id]

        # Remove from storage
        if self._storage:
            await self._storage.delete_compute_instance(instance_id)

        logger.info(f"Deregistered instance {instance_id}")

        return True
    
    async def get_instance(self, instance_id: str) -> Optional[ComputeInstance]:
        """Get instance by ID.
        
        Args:
            instance_id: Instance ID
            
        Returns:
            Instance or None if not found
        """
        return self._instances.get(instance_id)
    
    async def list_instances(
        self,
        status: Optional[InstanceStatus] = None,
        limit: int = 100
    ) -> List[ComputeInstance]:
        """List registered instances.
        
        Args:
            status: Optional status filter
            limit: Maximum number of instances
            
        Returns:
            List of instances
        """
        instances = list(self._instances.values())
        
        # Filter by status
        if status:
            instances = [i for i in instances if i.status == status]
        
        # Sort by registration time (newest first)
        instances.sort(key=lambda i: i.registered_at, reverse=True)
        
        return instances[:limit]
    
    async def get_by_capability(
        self,
        agent_id: Optional[str] = None,
        tool_id: Optional[str] = None,
        online_only: bool = True
    ) -> List[ComputeInstance]:
        """Find instances with specific capability.
        
        Args:
            agent_id: Agent ID to search for
            tool_id: Tool ID to search for
            online_only: Only return online instances
            
        Returns:
            List of instances with the capability
        """
        instance_ids = set()
        
        # Find by agent
        if agent_id:
            instance_ids.update(self._capability_index.get(f"agent:{agent_id}", []))
        
        # Find by tool
        if tool_id:
            instance_ids.update(self._capability_index.get(f"tool:{tool_id}", []))
        
        # Get instances
        instances = [
            self._instances[iid]
            for iid in instance_ids
            if iid in self._instances
        ]
        
        # Filter by online status
        if online_only:
            instances = [i for i in instances if i.status == InstanceStatus.ONLINE]
        
        return instances
    
    def find_instances_with_agent(
        self,
        agent_id: str,
        online_only: bool = True
    ) -> List[ComputeInstance]:
        """Find instances that have a specific agent (synchronous version).

        Args:
            agent_id: Agent ID to search for
            online_only: Only return online instances

        Returns:
            List of instances with the agent
        """
        instance_ids = self._capability_index.get(f"agent:{agent_id}", [])

        # Get instances
        instances = [
            self._instances[iid]
            for iid in instance_ids
            if iid in self._instances
        ]

        # Filter by online status
        if online_only:
            instances = [i for i in instances if i.status == InstanceStatus.ONLINE]

        return instances

    async def get_by_label(
        self,
        label: str,
        online_only: bool = True
    ) -> List[ComputeInstance]:
        """Find instances with a specific routing label.

        Args:
            label: Label to search for (e.g., "production-access")
            online_only: Only return online instances

        Returns:
            List of instances with the label
        """
        instance_ids = self._capability_index.get(f"label:{label}", [])

        # Get instances
        instances = [
            self._instances[iid]
            for iid in instance_ids
            if iid in self._instances
        ]

        # Filter by online status
        if online_only:
            instances = [i for i in instances if i.status == InstanceStatus.ONLINE]

        return instances

    async def get_by_tool_available(
        self,
        tool: str,
        online_only: bool = True
    ) -> List[ComputeInstance]:
        """Find instances with a specific available tool.

        Args:
            tool: Tool to search for (e.g., "deploy_prod")
            online_only: Only return online instances

        Returns:
            List of instances with the tool available
        """
        instance_ids = self._capability_index.get(f"tool_available:{tool}", [])

        # Get instances
        instances = [
            self._instances[iid]
            for iid in instance_ids
            if iid in self._instances
        ]

        # Filter by online status
        if online_only:
            instances = [i for i in instances if i.status == InstanceStatus.ONLINE]

        return instances

    async def update_project_tags(
        self,
        instance_id: str,
        project_ids: List[str]
    ) -> Optional[ComputeInstance]:
        """Update project tags for a compute instance.

        Args:
            instance_id: Instance ID
            project_ids: New list of project IDs (empty = benched, ['*'] = all)

        Returns:
            Updated instance or None if not found
        """
        instance = self._instances.get(instance_id)
        if not instance:
            return None

        # Remove old project index entries
        self._remove_from_project_index(instance_id)

        # Update project tags
        instance.project_ids = project_ids

        # If instance was OFFLINE (e.g. post-drain) and has an active SSE
        # connection, transition back to ONLINE when projects are assigned
        if (
            instance.status == InstanceStatus.OFFLINE
            and project_ids
            and instance.metadata.get("sse_connected")
        ):
            instance.status = InstanceStatus.ONLINE
            logger.info(f"Instance {instance_id} transitioned OFFLINE -> ONLINE (projects assigned with active SSE)")

        # Re-index
        self._update_project_index(instance)

        # Save to storage
        await self._save_to_storage(instance)

        logger.info(f"Updated project tags for {instance_id}: {project_ids}")
        return instance

    async def drain_instance(
        self,
        instance_id: str,
        auto_deregister: bool = False,
    ) -> Optional[ComputeInstance]:
        """Start graceful drain of a compute instance.

        Removes all project tags (stops new work) and sets status to DRAINING.

        Args:
            instance_id: Instance ID
            auto_deregister: Whether to auto-deregister when drain completes

        Returns:
            Updated instance or None if not found
        """
        instance = self._instances.get(instance_id)
        if not instance:
            return None

        if instance.status == InstanceStatus.DRAINING:
            logger.info(f"Instance {instance_id} is already draining")
            return instance

        # Remove all project tags to stop new work assignment
        self._remove_from_project_index(instance_id)
        instance.project_ids = []

        # Set draining status
        instance.status = InstanceStatus.DRAINING
        instance.drain_started_at = datetime.now(timezone.utc)

        # Store auto_deregister preference in metadata
        if auto_deregister:
            instance.metadata["auto_deregister_on_drain"] = True

        # Save to storage
        await self._save_to_storage(instance)

        logger.info(f"Started draining instance {instance_id}")
        return instance

    async def cancel_drain(
        self,
        instance_id: str,
    ) -> Optional[ComputeInstance]:
        """Cancel an in-progress drain operation.

        Restores the instance to ONLINE status but keeps project_ids empty.
        Operator must re-assign projects manually.

        Args:
            instance_id: Instance ID

        Returns:
            Updated instance or None if not found
        """
        instance = self._instances.get(instance_id)
        if not instance:
            return None

        if instance.status != InstanceStatus.DRAINING:
            return instance

        instance.status = InstanceStatus.ONLINE
        instance.drain_started_at = None
        instance.metadata.pop("auto_deregister_on_drain", None)

        await self._save_to_storage(instance)

        logger.info(f"Cancelled drain for instance {instance_id}")
        return instance

    async def get_pending_instances(self) -> List[ComputeInstance]:
        """Get all instances in PENDING status.

        Returns:
            List of instances in PENDING status (unordered).
            Use list_pending_instances() for sorted results.
        """
        return [
            inst for inst in self._instances.values()
            if inst.status == InstanceStatus.PENDING
        ]

    def get_instance_count(self) -> int:
        """Get the total number of registered instances (all statuses)."""
        return len(self._instances)

    async def get_by_project(
        self,
        project_id: str,
        online_only: bool = True
    ) -> List[ComputeInstance]:
        """Find instances tagged for a specific project.

        Includes instances with the exact project_id and those with '*' wildcard.

        Args:
            project_id: Project ID to search for
            online_only: Only return online instances

        Returns:
            List of instances tagged for the project
        """
        instance_ids = set()

        # Instances explicitly tagged for this project
        instance_ids.update(self._project_index.get(project_id, []))

        # Instances with wildcard '*' (all projects)
        instance_ids.update(self._project_index.get("*", []))

        # Get instances
        instances = [
            self._instances[iid]
            for iid in instance_ids
            if iid in self._instances
        ]

        # Filter by online status
        if online_only:
            instances = [i for i in instances if i.status == InstanceStatus.ONLINE]

        return instances

    async def find_matching_compute(
        self,
        required_labels: Optional[List[str]] = None,
        required_tools: Optional[List[str]] = None,
        required_capabilities: Optional[List[str]] = None,
        online_only: bool = True
    ) -> Optional[ComputeInstance]:
        """Find a compute instance that matches all requirements.

        This is the main routing method that matches work requirements to compute
        instances based on labels, tools_available, and capabilities.

        Args:
            required_labels: Labels the compute must have
            required_tools: Specialized tools the compute must have available
            required_capabilities: Capability tags the compute must have (agents)
            online_only: Only return online instances

        Returns:
            A matching ComputeInstance or None if no match found
        """
        # Start with all instances
        candidates = list(self._instances.values())

        # Filter by online status
        if online_only:
            candidates = [i for i in candidates if i.status == InstanceStatus.ONLINE]

        # Filter by auth status - only authorized instances can receive work
        candidates = [i for i in candidates if i.auth_status == ComputeAuthStatus.AUTHORIZED]

        # Filter by required labels
        if required_labels:
            candidates = [
                i for i in candidates
                if all(label in i.capabilities.labels for label in required_labels)
            ]

        # Filter by required tools
        if required_tools:
            candidates = [
                i for i in candidates
                if all(tool in i.capabilities.tools_available for tool in required_tools)
            ]

        # Filter by required capabilities (agents)
        if required_capabilities:
            candidates = [
                i for i in candidates
                if all(cap in i.capabilities.agents for cap in required_capabilities)
            ]

        # Return first matching instance (could be enhanced with load balancing)
        return candidates[0] if candidates else None

    async def approve_instance(
        self,
        instance_id: str,
        project_ids: Optional[List[str]] = None,
    ) -> Optional[ComputeInstance]:
        """Approve a PENDING instance, transitioning it to ONLINE.

        Args:
            instance_id: Instance ID to approve
            project_ids: Project IDs to assign (defaults to [] if None — approved but benched)

        Returns:
            Updated instance or None if not found

        Raises:
            ValueError: If instance is not in PENDING status
        """
        instance = self._instances.get(instance_id)
        if not instance:
            return None

        if instance.status != InstanceStatus.PENDING:
            raise ValueError(
                f"Instance {instance_id} is not pending (status={instance.status.value})"
            )

        # Transition to ONLINE
        instance.status = InstanceStatus.ONLINE
        instance.pending_since = None

        # Assign projects
        self._remove_from_project_index(instance_id)
        instance.project_ids = project_ids if project_ids is not None else []
        self._update_project_index(instance)

        await self._save_to_storage(instance)

        logger.info(
            f"Approved instance {instance_id}, "
            f"project_ids={instance.project_ids}"
        )
        return instance

    async def reject_instance(
        self,
        instance_id: str,
        reason: str = "",
    ) -> bool:
        """Reject a PENDING instance and remove it from the registry.

        Args:
            instance_id: Instance ID to reject
            reason: Optional rejection reason

        Returns:
            True if rejected and removed, False if not found

        Raises:
            ValueError: If instance is not in PENDING status
        """
        instance = self._instances.get(instance_id)
        if not instance:
            return False

        if instance.status != InstanceStatus.PENDING:
            raise ValueError(
                f"Instance {instance_id} is not pending (status={instance.status.value})"
            )

        logger.info(
            f"Rejected instance {instance_id}"
            + (f": {reason}" if reason else "")
        )

        return await self.remove_instance(instance_id)

    async def list_pending_instances(self) -> List[ComputeInstance]:
        """List all instances in PENDING status.

        Returns:
            List of pending instances sorted by pending_since (oldest first)
        """
        pending = [
            i for i in self._instances.values()
            if i.status == InstanceStatus.PENDING
        ]
        pending.sort(
            key=lambda i: i.pending_since or i.registered_at,
        )
        return pending

    async def update_status(
        self,
        instance_id: str,
        status: InstanceStatus,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update instance status.
        
        Args:
            instance_id: Instance ID
            status: New status
            metadata: Optional metadata update
            
        Returns:
            True if updated, False if not found
        """
        instance = self._instances.get(instance_id)
        if not instance:
            return False
        
        old_status = instance.status
        instance.status = status
        
        if metadata:
            instance.metadata.update(metadata)
        
        # Save to storage
        await self._save_to_storage(instance)
        
        if old_status != status:
            logger.info(f"Instance {instance_id} status: {old_status} -> {status}")
        
        return True
    
    async def update_heartbeat(
        self,
        instance_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update instance heartbeat.
        
        Args:
            instance_id: Instance ID
            metadata: Optional metadata from heartbeat
            
        Returns:
            True if updated, False if not found
        """
        instance = self._instances.get(instance_id)
        if not instance:
            return False
        
        # Update heartbeat
        instance.update_heartbeat()
        
        # Update metadata if provided
        if metadata:
            instance.metadata.update(metadata)
        
        # Save to storage
        await self._save_to_storage(instance)
        
        logger.debug(f"Updated heartbeat for {instance_id}")
        
        return True
    
    async def update_instance(
        self,
        instance_id: str,
        name: Optional[str] = None,
        capabilities: Optional[InstanceCapabilities] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[ComputeInstance]:
        """Update instance information.
        
        Args:
            instance_id: Instance ID
            name: New name
            capabilities: New capabilities
            metadata: New metadata
            
        Returns:
            Updated instance or None if not found
        """
        instance = self._instances.get(instance_id)
        if not instance:
            return None
        
        # Update fields
        if name:
            instance.name = name
        
        if capabilities:
            # Remove old capability index entries
            self._remove_from_capability_index(instance_id)
            
            # Update capabilities
            instance.capabilities = capabilities
            
            # Re-index
            self._update_capability_index(instance)
        
        if metadata:
            instance.metadata.update(metadata)
        
        # Save to storage
        await self._save_to_storage(instance)
        
        logger.info(f"Updated instance {instance_id}")

        return instance

    async def claim_instance(
        self,
        instance_id: str,
        owner_id: str,
    ) -> Optional[ComputeInstance]:
        """Claim ownership of an unclaimed compute instance.

        Args:
            instance_id: Instance to claim
            owner_id: User ID of the claiming user

        Returns:
            Updated instance or None if not found

        Raises:
            ValueError: If already claimed by another user
        """
        instance = self._instances.get(instance_id)
        if not instance:
            return None

        if instance.owner_id and instance.owner_id != owner_id:
            raise ValueError(
                f"Instance {instance_id} is already claimed by user {instance.owner_id}"
            )

        instance.owner_id = owner_id
        instance.claimed_at = datetime.now(timezone.utc)

        await self._save_to_storage(instance)

        logger.info(f"Instance {instance_id} claimed by user {owner_id}")
        return instance

    async def get_instances_by_owner(
        self,
        owner_id: str,
    ) -> List[ComputeInstance]:
        """Get all instances owned by a user.

        Args:
            owner_id: User ID

        Returns:
            List of owned instances
        """
        return [
            instance for instance in self._instances.values()
            if instance.owner_id == owner_id
        ]

    async def get_unclaimed_instances(self) -> List[ComputeInstance]:
        """Get all instances with no owner."""
        return [
            instance for instance in self._instances.values()
            if instance.owner_id is None
        ]

    async def update_auth_status(
        self,
        instance_id: str,
        auth_status: ComputeAuthStatus,
        auth_expires_at: Optional[datetime] = None,
    ) -> Optional[ComputeInstance]:
        """Update auth status for a compute instance.

        Args:
            instance_id: Instance ID
            auth_status: New auth status
            auth_expires_at: Token expiry time (for authorized status)

        Returns:
            Updated instance or None if not found
        """
        instance = self._instances.get(instance_id)
        if not instance:
            return None

        old_status = instance.auth_status
        instance.auth_status = auth_status

        if auth_status == ComputeAuthStatus.AUTHORIZED:
            instance.auth_authorized_at = datetime.now(timezone.utc)
            instance.auth_expires_at = auth_expires_at
        elif auth_status == ComputeAuthStatus.UNAUTHORIZED:
            instance.auth_expires_at = None
            instance.auth_authorized_at = None

        await self._save_to_storage(instance)

        if old_status != auth_status:
            logger.info(f"Instance {instance_id} auth: {old_status.value} -> {auth_status.value}")

        return instance

    async def check_auth_expiry(self) -> List[str]:
        """Check all instances for auth token expiry.

        Returns:
            List of instance IDs whose auth expired
        """
        now = datetime.now(timezone.utc)
        expired_ids = []

        for instance_id, instance in self._instances.items():
            if (
                instance.auth_status == ComputeAuthStatus.AUTHORIZED
                and instance.auth_expires_at
                and now >= instance.auth_expires_at
            ):
                instance.auth_status = ComputeAuthStatus.EXPIRED
                await self._save_to_storage(instance)
                expired_ids.append(instance_id)
                logger.warning(f"Auth expired for instance {instance_id}")

        return expired_ids

    async def get_aggregated_capabilities(self) -> AggregatedCapabilities:
        """Get aggregated capabilities across all instances.

        Returns:
            Aggregated capabilities
        """
        total = len(self._instances)
        online = sum(1 for i in self._instances.values() if i.status == InstanceStatus.ONLINE)

        # Build capability maps
        agent_map: Dict[str, List[str]] = {}
        tool_map: Dict[str, List[str]] = {}
        label_map: Dict[str, List[str]] = {}
        tools_available_map: Dict[str, List[str]] = {}

        for key, instance_ids in self._capability_index.items():
            if key.startswith("agent:"):
                agent_id = key[6:]  # Remove "agent:" prefix
                agent_map[agent_id] = instance_ids
            elif key.startswith("tool:"):
                tool_id = key[5:]  # Remove "tool:" prefix
                tool_map[tool_id] = instance_ids
            elif key.startswith("label:"):
                label = key[6:]  # Remove "label:" prefix
                label_map[label] = instance_ids
            elif key.startswith("tool_available:"):
                tool = key[15:]  # Remove "tool_available:" prefix
                tools_available_map[tool] = instance_ids

        # Sum resources
        total_cpu = 0
        total_memory = 0.0
        total_gpu = 0
        total_storage = 0.0

        for instance in self._instances.values():
            if instance.status == InstanceStatus.ONLINE and instance.capabilities.resources:
                res = instance.capabilities.resources
                if res.cpu_count:
                    total_cpu += res.cpu_count
                if res.memory_gb:
                    total_memory += res.memory_gb
                if res.gpu_count:
                    total_gpu += res.gpu_count
                if res.storage_gb:
                    total_storage += res.storage_gb

        return AggregatedCapabilities(
            total_instances=total,
            online_instances=online,
            agents=agent_map,
            tools=tool_map,
            labels=label_map,
            tools_available=tools_available_map,
            total_resources=InstanceResources(
                cpu_count=total_cpu if total_cpu > 0 else None,
                memory_gb=total_memory if total_memory > 0 else None,
                gpu_count=total_gpu if total_gpu > 0 else None,
                storage_gb=total_storage if total_storage > 0 else None,
            )
        )
    
    async def check_health(
        self,
        max_heartbeat_age: int = 90,
        degraded_threshold: int = 60
    ) -> Dict[str, Any]:
        """Check health of all instances based on heartbeat age.
        
        Args:
            max_heartbeat_age: Max seconds before marking offline
            degraded_threshold: Seconds before marking degraded
            
        Returns:
            Dict with health check results
        """
        now = datetime.now(timezone.utc)
        results = {
            "checked_at": now.isoformat(),
            "total_instances": len(self._instances),
            "status_changes": []
        }
        
        for instance_id, instance in self._instances.items():
            # Skip instances that are draining — drain completion is handled separately
            if instance.status == InstanceStatus.DRAINING:
                continue

            age = (now - instance.last_heartbeat).total_seconds()
            old_status = instance.status

            if age > max_heartbeat_age:
                # Mark as offline
                instance.failed_health_checks += 1
                instance.status = InstanceStatus.OFFLINE
                
                logger.warning(
                    f"Instance {instance_id} is offline "
                    f"(no heartbeat for {age:.0f}s, {instance.failed_health_checks} failed checks)"
                )
            elif age > degraded_threshold:
                # Mark as degraded
                if instance.status == InstanceStatus.ONLINE:
                    instance.status = InstanceStatus.DEGRADED
                    logger.warning(
                        f"Instance {instance_id} is degraded "
                        f"(no heartbeat for {age:.0f}s)"
                    )
            
            if old_status != instance.status:
                results["status_changes"].append({
                    "instance_id": instance_id,
                    "old_status": old_status.value,
                    "new_status": instance.status.value,
                    "heartbeat_age": age
                })
                
                # Save updated status
                await self._save_to_storage(instance)
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics.

        Returns:
            Dict with statistics
        """
        status_counts = defaultdict(int)
        auth_counts = defaultdict(int)
        for instance in self._instances.values():
            status_counts[instance.status.value] += 1
            auth_counts[instance.auth_status.value] += 1

        return {
            "total_instances": len(self._instances),
            "by_status": dict(status_counts),
            "by_auth_status": dict(auth_counts),
            "total_agents": len([k for k in self._capability_index.keys() if k.startswith("agent:")]),
            "total_tools": len([k for k in self._capability_index.keys() if k.startswith("tool:")]),
            "total_labels": len([k for k in self._capability_index.keys() if k.startswith("label:")]),
            "total_tools_available": len([k for k in self._capability_index.keys() if k.startswith("tool_available:")]),
            "sse_connections": len(self._event_queues),
        }

    # =========================================================================
    # SSE Event Queue Methods
    # =========================================================================

    def _create_event_queue(self, instance_id: str) -> asyncio.Queue:
        """Create an event queue for an SSE-connected instance.

        Args:
            instance_id: The compute instance ID

        Returns:
            The created asyncio.Queue
        """
        if instance_id not in self._event_queues:
            self._event_queues[instance_id] = asyncio.Queue()
            logger.debug(f"Created SSE event queue for {instance_id}")
        return self._event_queues[instance_id]

    def _remove_event_queue(self, instance_id: str) -> None:
        """Remove the event queue for an instance.

        Args:
            instance_id: The compute instance ID
        """
        if instance_id in self._event_queues:
            del self._event_queues[instance_id]
            logger.debug(f"Removed SSE event queue for {instance_id}")

    async def queue_event(
        self,
        instance_id: str,
        event_type: str,
        data: Dict[str, Any],
    ) -> bool:
        """Queue an event to be sent to an SSE-connected instance.

        Args:
            instance_id: The compute instance ID
            event_type: The SSE event type (e.g., "work_assigned")
            data: The event data

        Returns:
            True if event was queued, False if instance not connected
        """
        queue = self._event_queues.get(instance_id)
        if queue is None:
            logger.warning(f"Cannot queue event for {instance_id}: not SSE-connected")
            return False

        event = {
            "event_type": event_type,
            "data": data,
        }
        await queue.put(event)
        logger.debug(f"Queued {event_type} event for {instance_id}")
        return True

    async def get_pending_event(
        self,
        instance_id: str,
        timeout: float = 0.1,
    ) -> Optional[Dict[str, Any]]:
        """Get the next pending event for an SSE-connected instance.

        This method is called by the SSE event generator to check for
        events to send to the connected compute.

        Args:
            instance_id: The compute instance ID
            timeout: How long to wait for an event (seconds)

        Returns:
            The event dict or None if no event is pending
        """
        queue = self._event_queues.get(instance_id)
        if queue is None:
            # Create queue on first call (lazy initialization)
            queue = self._create_event_queue(instance_id)

        try:
            return await asyncio.wait_for(queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def has_sse_connection(self, instance_id: str) -> bool:
        """Check if an instance has an active SSE connection.

        Args:
            instance_id: The compute instance ID

        Returns:
            True if SSE-connected, False otherwise
        """
        return instance_id in self._event_queues


# Global registry instance
_registry: Optional[ComputeRegistry] = None


def get_compute_registry() -> ComputeRegistry:
    """Get the global compute registry instance.
    
    Returns:
        ComputeRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = ComputeRegistry()
    return _registry


def set_compute_registry(registry: ComputeRegistry):
    """Set the global compute registry instance.
    
    Args:
        registry: ComputeRegistry instance
    """
    global _registry
    _registry = registry

