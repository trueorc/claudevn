# Component Registration Architecture

**Version:** 0.2.0  
**Last Updated:** November 23, 2025

---

## Overview

The ClaudeVN platform uses a **"phone home"** registration pattern where components (Marketplace, Compute) initiate connections to the Serving component.

---

## Architecture Pattern

### Why "Phone Home" Pattern?

**Key Constraint:** Serving component is publicly accessible (cloud), but Marketplace and Compute can be local/private.

```
┌─────────────────────────────────────────────────────────┐
│                    CLOUD (Public)                       │
│  ┌─────────────────────────────────────────────────┐   │
│  │         SERVING COMPONENT (8002)                │   │
│  │         Public IP / Domain Name                 │   │
│  │                                                  │   │
│  │  • Accepts registrations                        │   │
│  │  • Tracks component health                      │   │
│  │  • Routes requests                              │   │
│  └─────────────────────────────────────────────────┘   │
│                         ▲                               │
└─────────────────────────┼───────────────────────────────┘
                          │
                    Registration
                   & Heartbeats
                          │
      ┌───────────────────┴───────────────────┐
      │                                       │
┌─────┴─────────────────────┐    ┌──────────┴──────────────────┐
│   LOCAL (Private)         │    │   LOCAL (Private)           │
│  ┌──────────────────┐     │    │  ┌──────────────────┐       │
│  │   MARKETPLACE    │     │    │  │    COMPUTE       │       │
│  │     (8001)       │     │    │  │     (8003+)      │       │
│  │                  │     │    │  │                  │       │
│  │  • Registers on  │     │    │  │  • Registers on  │       │
│  │    startup       │     │    │  │    startup       │       │
│  │  • Sends updates │     │    │  │  • Sends         │       │
│  │    periodically  │     │    │  │    heartbeats    │       │
│  └──────────────────┘     │    │  └──────────────────┘       │
│                           │    │                             │
│  Behind NAT/Firewall      │    │  Behind NAT/Firewall        │
└───────────────────────────┘    └─────────────────────────────┘
```

### Key Points:
- ✅ **Serving is passive**: Listens for registrations, doesn't initiate connections
- ✅ **Components are active**: Initiate registration and maintain connectivity
- ✅ **Works through firewalls**: No need for port forwarding on local machines
- ✅ **Scalable**: Any number of components can register from anywhere

---

## Component Registration Details

### 1. Marketplace Registration

**When:** On marketplace startup  
**Who Initiates:** Marketplace  
**Frequency:** Once on startup, with periodic health updates

#### Registration Flow:
```
Marketplace Startup
    │
    ├─ 1. Load config (SERVING_URL from env)
    │
    ├─ 2. POST /api/v1/marketplaces/register
    │      {
    │        "marketplace_id": "marketplace-001",
    │        "name": "ClaudeVN Central Marketplace",
    │        "endpoint": "http://localhost:8001",
    │        "public_endpoint": "https://marketplace.example.com",
    │        "capabilities": {
    │          "agent_count": 10,
    │          "tool_count": 5,
    │          "supports_search": true,
    │          "supports_categories": true
    │        },
    │        "metadata": {
    │          "version": "0.1.4",
    │          "region": "us-west-2"
    │        }
    │      }
    │
    ├─ 3. Receive registration confirmation
    │      {
    │        "status": "registered",
    │        "marketplace_id": "marketplace-001",
    │        "heartbeat_interval": 60,
    │        "heartbeat_endpoint": "/api/v1/marketplaces/{id}/heartbeat"
    │      }
    │
    └─ 4. Start heartbeat loop (every 60s)
           │
           └─ POST /api/v1/marketplaces/{id}/heartbeat
              {
                "agent_count": 10,
                "tool_count": 5,
                "status": "healthy"
              }
```

#### Marketplace Registration Data:
```python
{
    "marketplace_id": str,        # Unique ID (generated or config)
    "name": str,                  # Human-readable name
    "endpoint": str,              # Internal endpoint (for dev)
    "public_endpoint": str | None,# Public endpoint (for prod)
    "capabilities": {
        "agent_count": int,
        "tool_count": int,
        "supports_search": bool,
        "supports_categories": bool,
        "supports_access_control": bool
    },
    "metadata": dict,             # Version, region, etc.
    "version": str                # Marketplace version
}
```

---

### 2. Compute Registration

**When:** On compute engine startup  
**Who Initiates:** Compute  
**Frequency:** Once on startup, with frequent heartbeats

#### Registration Flow:
```
Compute Startup
    │
    ├─ 1. Load config (SERVING_URL from env)
    │
    ├─ 2. Discover local agents/capabilities
    │
    ├─ 3. POST /api/v1/compute/register
    │      {
    │        "instance_id": "compute-001",
    │        "name": "Data Processing Node",
    │        "endpoint": "http://localhost:8003",
    │        "capabilities": {
    │          "agents": ["data-analyzer", "csv-processor"],
    │          "tools": ["pandas", "numpy"],
    │          "resources": {
    │            "memory_gb": 32,
    │            "cpu_cores": 8
    │          }
    │        }
    │      }
    │
    ├─ 3. Receive registration confirmation
    │      {
    │        "status": "registered",
    │        "instance_id": "compute-001",
    │        "heartbeat_interval": 30,
    │        "heartbeat_endpoint": "/api/v1/compute/{id}/heartbeat"
    │      }
    │
    └─ 4. Start heartbeat loop (every 30s)
           │
           └─ POST /api/v1/compute/{id}/heartbeat
              {
                "status": "online",
                "active_tasks": 3
              }
```

---

## Configuration

### Marketplace (Environment Variables)
```bash
# Where is the serving component?
SERVING_URL=http://localhost:8002  # Dev
# SERVING_URL=https://serving.example.com  # Prod

# Should we auto-register on startup?
AUTO_REGISTER_WITH_SERVING=true

# Marketplace identification
MARKETPLACE_ID=marketplace-001  # Optional, auto-generated if not provided
MARKETPLACE_NAME="ClaudeVN Central Marketplace"

# Endpoints
MARKETPLACE_PUBLIC_ENDPOINT=  # Optional, for public access
```

### Compute (Environment Variables)
```bash
# Where is the serving component?
SERVING_URL=http://localhost:8002  # Dev
# SERVING_URL=https://serving.example.com  # Prod

# Should we auto-register on startup?
AUTO_REGISTER_WITH_SERVING=true

# Compute identification
COMPUTE_INSTANCE_ID=compute-001  # Optional, auto-generated if not provided
COMPUTE_NAME="Data Processing Node"
```

### Serving (Environment Variables)
```bash
# Health monitoring configuration
HEALTH_CHECK_INTERVAL=30  # How often to check (seconds)
DEGRADED_THRESHOLD=60     # Mark degraded after no heartbeat (seconds)
OFFLINE_THRESHOLD=90      # Mark offline after no heartbeat (seconds)
MAX_FAILED_CHECKS=3       # Auto-deregister after this many failures
AUTO_DEREGISTER=false     # Auto-remove offline instances
```

---

## Health Monitoring

### Marketplace Health
- **Interval:** 60 seconds (less frequent than compute)
- **Metrics:**
  - Agent count
  - Tool count
  - API response time
  - Storage health
- **States:**
  - `healthy`: Normal operation
  - `degraded`: High load or slow responses
  - `offline`: No heartbeat for 90+ seconds

### Compute Health
- **Interval:** 30 seconds (more frequent, critical for execution)
- **Metrics:**
  - Active task count
  - Resource utilization
  - Agent availability
  - Error rate
- **States:**
  - `online`: Ready to accept tasks
  - `degraded`: Overloaded but functional
  - `offline`: No heartbeat for 90+ seconds

---

## API Endpoints

### Serving Component Provides:

#### Marketplace Registration
```
POST   /api/v1/marketplaces/register     # Register marketplace
GET    /api/v1/marketplaces               # List registered marketplaces
GET    /api/v1/marketplaces/{id}          # Get marketplace details
POST   /api/v1/marketplaces/{id}/heartbeat # Send heartbeat
DELETE /api/v1/marketplaces/{id}          # Deregister
GET    /api/v1/marketplaces/stats         # Registration stats
```

#### Compute Registration (Already Implemented ✅)
```
POST   /api/v1/compute/register           # Register compute instance
GET    /api/v1/compute                    # List registered instances
GET    /api/v1/compute/{id}               # Get instance details
POST   /api/v1/compute/{id}/health        # Send heartbeat
DELETE /api/v1/compute/{id}               # Deregister
GET    /api/v1/compute/stats              # Registration stats
```

---

## Implementation Order

### Phase 1: Marketplace Registration (NOW)
1. ✅ **Serving Side:**
   - Create marketplace models (similar to compute models)
   - Implement marketplace registry service
   - Create marketplace API endpoints
   - Add marketplace health monitoring

2. ✅ **Marketplace Side:**
   - Add serving client module
   - Implement registration on startup
   - Implement heartbeat loop
   - Add graceful deregistration on shutdown

### Phase 2: Compute Registration (LATER)
1. **Compute Side:**
   - Add serving client module
   - Implement registration on startup
   - Implement heartbeat loop
   - Add agent discovery and capability reporting

---

## Testing

### Development Environment
```bash
# Start serving
cd serving
./start.sh

# Start marketplace (auto-registers with serving)
cd marketplace
./start.sh

# Check registration
curl http://localhost:8002/api/v1/marketplaces

# View in UI
open http://localhost:8002  # See marketplace in dashboard
```

### Production Environment
```bash
# Serving (cloud, public IP)
SERVING_HOST=0.0.0.0 SERVING_PORT=8002 ./serving/start.sh

# Marketplace (local, private network)
SERVING_URL=https://serving.example.com AUTO_REGISTER_WITH_SERVING=true ./marketplace/start.sh
```

---

## Security Considerations (Future)

Currently no authentication. When we add auth:
- Components will need API keys/tokens
- Registration will require authentication
- Heartbeats will include token validation
- HTTPS required for production

---

## Benefits of This Architecture

1. **Firewall Friendly:** Local components can reach cloud serving
2. **NAT Traversal:** No need for port forwarding
3. **Dynamic Discovery:** Components can come and go
4. **Health Monitoring:** Automatic detection of failed components
5. **Scalability:** Any number of components can register
6. **Flexibility:** Development (localhost) and production (cloud) same code

---

## Next Steps

1. ✅ Implement marketplace registration (serving side)
2. ✅ Implement marketplace registration (marketplace side)
3. ✅ Test registration flow
4. ✅ Update UIs to show marketplace registrations
5. ⏭️  Implement compute registration (compute side)
6. ⏭️  Add authentication layer

