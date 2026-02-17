"""Instance information and capability models."""

import psutil
import platform
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class AgentDefinition(BaseModel):
    """Agent definition."""
    agent_id: str = Field(..., description="Unique agent identifier")
    name: str = Field(..., description="Agent name")
    description: str = Field(default="", description="Agent description")
    capabilities: List[str] = Field(default_factory=list, description="Agent capabilities")
    llm_providers: List[Dict[str, Any]] = Field(default_factory=list, description="LLM provider configs")
    tools: List[str] = Field(default_factory=list, description="Required tools")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ToolDefinition(BaseModel):
    """Tool definition."""
    tool_id: str = Field(..., description="Unique tool identifier")
    name: str = Field(..., description="Tool name")
    description: str = Field(default="", description="Tool description")
    function_name: str = Field(..., description="Python function name")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Tool parameters schema")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class InstanceResources(BaseModel):
    """Hardware resources of this compute instance."""
    cpu_count: Optional[int] = Field(None, description="Number of CPU cores")
    memory_gb: Optional[float] = Field(None, description="Total memory in GB")
    gpu_count: Optional[int] = Field(None, description="Number of GPUs")
    gpu_type: Optional[str] = Field(None, description="GPU type/model")
    storage_gb: Optional[float] = Field(None, description="Available storage in GB")
    
    @classmethod
    def detect_resources(cls) -> "InstanceResources":
        """Detect hardware resources of current system.
        
        Returns:
            InstanceResources with detected values
        """
        cpu_count = psutil.cpu_count(logical=False) or psutil.cpu_count(logical=True)
        memory_bytes = psutil.virtual_memory().total
        memory_gb = memory_bytes / (1024 ** 3)
        
        # Get storage info for current partition
        storage_bytes = psutil.disk_usage('/').total
        storage_gb = storage_bytes / (1024 ** 3)
        
        # GPU detection would require additional libraries (pynvml, etc.)
        # For now, we'll leave GPU info as None
        
        return cls(
            cpu_count=cpu_count,
            memory_gb=round(memory_gb, 2),
            gpu_count=None,
            gpu_type=None,
            storage_gb=round(storage_gb, 2)
        )


class InstanceCapabilities(BaseModel):
    """Capabilities of this compute instance."""
    agents: List[str] = Field(default_factory=list, description="Available agent IDs")
    tools: List[str] = Field(default_factory=list, description="Available tool IDs")
    resources: Optional[InstanceResources] = Field(None, description="Hardware resources")
    features: List[str] = Field(default_factory=list, description="Special features")
    
    @classmethod
    def from_registries(
        cls,
        agent_ids: List[str],
        tool_ids: List[str],
        features: Optional[List[str]] = None
    ) -> "InstanceCapabilities":
        """Create capabilities from agent and tool registries.
        
        Args:
            agent_ids: List of available agent IDs
            tool_ids: List of available tool IDs
            features: Optional list of special features
            
        Returns:
            InstanceCapabilities
        """
        resources = InstanceResources.detect_resources()
        
        return cls(
            agents=agent_ids,
            tools=tool_ids,
            resources=resources,
            features=features or []
        )


class InstanceInfo(BaseModel):
    """Complete instance information."""
    instance_id: str = Field(..., description="Unique instance identifier")
    name: str = Field(..., description="Human-readable name")
    endpoint: str = Field(..., description="Base URL for this instance")
    health_endpoint: str = Field(..., description="Health check endpoint")
    version: str = Field(..., description="Compute engine version")
    capabilities: InstanceCapabilities = Field(..., description="Instance capabilities")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    @classmethod
    def create(
        cls,
        instance_id: str,
        name: str,
        host: str,
        port: int,
        version: str,
        agent_ids: List[str],
        tool_ids: List[str],
        features: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        public_url: Optional[str] = None
    ) -> "InstanceInfo":
        """Create instance info with detected capabilities.

        Args:
            instance_id: Unique instance ID
            name: Instance name
            host: Host address
            port: Port number
            version: Version string
            agent_ids: Available agent IDs
            tool_ids: Available tool IDs
            features: Optional features list
            metadata: Optional metadata
            public_url: Optional public URL override (for Docker networking)

        Returns:
            InstanceInfo
        """
        # Use public URL if provided (for Docker networking)
        if public_url:
            base_url = public_url.rstrip('/')
        else:
            # Construct endpoint URLs
            base_url = f"http://{host}:{port}" if host == "0.0.0.0" else f"http://{host}:{port}"

            # Get local hostname if binding to 0.0.0.0
            if host == "0.0.0.0":
                # Use localhost instead of hostname for better compatibility
                base_url = f"http://localhost:{port}"
        
        capabilities = InstanceCapabilities.from_registries(
            agent_ids=agent_ids,
            tool_ids=tool_ids,
            features=features
        )
        
        # Add platform info to metadata
        full_metadata = metadata or {}
        full_metadata.update({
            "platform": platform.system(),
            "platform_version": platform.version(),
            "python_version": platform.python_version(),
        })
        
        return cls(
            instance_id=instance_id,
            name=name,
            endpoint=base_url,
            health_endpoint=f"{base_url}/health",
            version=version,
            capabilities=capabilities,
            metadata=full_metadata
        )

