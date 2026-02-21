"""Compute instance definitions for demo data.

Shared across all phases — computes are infrastructure, not phase-specific.
"""

DEMO_COMPUTE_INSTANCES = [
    {
        "instance_id": "compute-alpha-1",
        "name": "Alpha Primary",
        "endpoint": "http://compute-alpha-1.internal:8100",
        "health_endpoint": "http://compute-alpha-1.internal:8100/health",
        "status": "online",
        "capabilities": {
            "agents": ["code-writer", "test-automator", "debugger", "code-reviewer"],
            "tools": ["python-executor", "git", "docker", "pytest"],
            "labels": ["production-access", "database-admin"],
            "tools_available": ["deploy_prod", "db_migrate"],
            "resources": {
                "cpu_count": 16,
                "memory_gb": 64.0,
                "gpu_count": 1,
                "gpu_type": "NVIDIA A100",
                "storage_gb": 1000.0,
            },
        },
        "metadata": {
            "location": "us-east-1",
            "owner": "platform-team",
            "environment": "production",
            "demo": True,
        },
    },
    {
        "instance_id": "compute-alpha-2",
        "name": "Alpha Secondary",
        "endpoint": "http://compute-alpha-2.internal:8100",
        "health_endpoint": "http://compute-alpha-2.internal:8100/health",
        "status": "online",
        "capabilities": {
            "agents": ["code-writer", "test-automator", "doc-writer"],
            "tools": ["python-executor", "git", "npm"],
            "labels": ["production-access"],
            "tools_available": [],
            "resources": {
                "cpu_count": 8,
                "memory_gb": 32.0,
                "storage_gb": 500.0,
            },
        },
        "metadata": {
            "location": "us-east-1",
            "owner": "platform-team",
            "environment": "production",
            "demo": True,
        },
    },
    {
        "instance_id": "compute-beta-1",
        "name": "Beta Staging",
        "endpoint": "http://compute-beta-1.internal:8100",
        "health_endpoint": "http://compute-beta-1.internal:8100/health",
        "status": "online",
        "capabilities": {
            "agents": ["code-writer", "debugger", "security-reviewer"],
            "tools": ["python-executor", "git", "bandit", "safety"],
            "labels": ["staging-only"],
            "tools_available": [],
            "resources": {
                "cpu_count": 8,
                "memory_gb": 32.0,
                "storage_gb": 500.0,
            },
        },
        "metadata": {
            "location": "us-west-2",
            "owner": "security-team",
            "environment": "staging",
            "demo": True,
        },
    },
    {
        "instance_id": "compute-beta-2",
        "name": "Beta Test Runner",
        "endpoint": "http://compute-beta-2.internal:8100",
        "health_endpoint": "http://compute-beta-2.internal:8100/health",
        "status": "degraded",
        "capabilities": {
            "agents": ["test-automator", "code-writer"],
            "tools": ["python-executor", "git", "pytest", "coverage"],
            "labels": ["staging-only", "test-runner"],
            "tools_available": [],
            "resources": {
                "cpu_count": 4,
                "memory_gb": 16.0,
                "storage_gb": 250.0,
            },
        },
        "metadata": {
            "location": "us-west-2",
            "owner": "qa-team",
            "environment": "staging",
            "demo": True,
            "degraded_reason": "High memory usage — investigation in progress",
        },
    },
    {
        "instance_id": "compute-gamma-1",
        "name": "Gamma Maintenance",
        "endpoint": "http://compute-gamma-1.internal:8100",
        "health_endpoint": "http://compute-gamma-1.internal:8100/health",
        "status": "draining",
        "capabilities": {
            "agents": ["code-writer", "deploy-engineer"],
            "tools": ["python-executor", "git", "docker", "kubectl"],
            "labels": ["production-access", "infrastructure"],
            "tools_available": ["deploy_prod", "rollback_prod"],
            "resources": {
                "cpu_count": 8,
                "memory_gb": 32.0,
                "storage_gb": 500.0,
            },
        },
        "metadata": {
            "location": "eu-west-1",
            "owner": "infra-team",
            "environment": "production",
            "demo": True,
            "drain_reason": "Scheduled maintenance window",
        },
    },
    {
        "instance_id": "compute-delta-1",
        "name": "Delta Offline",
        "endpoint": "http://compute-delta-1.internal:8100",
        "status": "offline",
        "capabilities": {
            "agents": ["code-writer"],
            "tools": ["git"],
            "labels": [],
            "tools_available": [],
        },
        "metadata": {
            "location": "ap-southeast-1",
            "owner": "apac-team",
            "demo": True,
            "offline_since": "2025-02-19T14:30:00Z",
        },
    },
]
