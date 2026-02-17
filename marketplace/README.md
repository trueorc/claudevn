# ClaudeVN Skill Marketplace

**Version:** 1.0.0
**Status:** Production Ready

The **Skill Marketplace** manages atomic skills that compose into deployable agent bundles for Claude Code instances. Skills define specialized capabilities with instructions, tool permissions, and constraints that can be mixed and matched to create custom agents.

---

## 🎯 Overview

The Skill Marketplace enables **composition-based agent creation**. Instead of monolithic agent definitions, skills are atomic capability units that combine into cohesive agent bundles tailored for specific tasks.

### Key Capabilities

- **Atomic Skills** - Composable capability units (coding, testing, debugging, documentation)
- **Agent Composition** - Combine skills dynamically based on task requirements
- **Two-Tier Tool System** - Global tools (available to all) + Specialized tools (skill-specific)
- **Conflict Detection** - Identify incompatible skill combinations
- **System + User Skills** - Built-in system skills + custom user-defined skills

---

## 🧩 Core Concepts

### Skills

**Skills** are atomic capability units that grant:
- **Instructions** - CLAUDE.md instruction fragments defining behavior and approach
- **Tools** - Specialized tool permissions beyond global tools
- **Tags** - Capability labels for discovery (e.g., "coding", "testing", "security")
- **Constraints** - Explicit boundaries on what NOT to do
- **Conflicts** - Advisory warnings about incompatible skills

Skills are composable - multiple skills combine to form complete agents.

### Agents

**Agents** are composed bundles ready for deployment to Claude Code. They contain:
- **Selected Skills** - One or more skills chosen for the task
- **Merged Instructions** - Combined CLAUDE.md content from all skills
- **Aggregated Tools** - Global tools + specialized tools from selected skills
- **Project Context** - Optional project-specific conventions and domain knowledge
- **Task Assignment** - The specific task to accomplish

### Two-Tier Tool Authorization

The tool system uses two tiers for fine-grained access control:

**Global Tools** (Tier 1) - Available to all agents by default:
- `read`, `write`, `edit` - File operations
- `bash` - Shell command execution
- `glob`, `grep` - File discovery and search

**Specialized Tools** (Tier 2) - Granted by specific skills only:

| Tool | Granted By | Required Labels | Description |
|------|------------|-----------------|-------------|
| `deploy_prod` | `prod-deployment` | `production-access` | Deploy to production |
| `db_migration_tool` | `database-migration` | `database-admin` | Run database migrations |
| `run_security_scan` | `security-audit` | `security-tools` | Execute security scans |
| `test_api_endpoint` | `api-integration` | `api-testing` | Test API endpoints |

**Two-Part Authorization Check:**

For specialized tools, both conditions must be met:
1. **Skill grants permission** - Agent must have a skill that grants the tool
2. **Compute has capability** - Compute instance must have the tool available and required labels

This model enables fine-grained security: only agents with appropriate skills deployed on properly configured compute instances can access sensitive operations.

Tool definitions are stored in `tools/specialized.yaml` with full metadata including parameter schemas.

---

## 📁 Directory Structure

```
marketplace/
├── __init__.py                  # Package initialization
├── api.py                       # FastAPI router for all endpoints
├── models.py                    # Pydantic models (Skill, Agent, etc.)
├── skill_registry.py            # Skill catalog service (load, CRUD)
├── composition_service.py       # Agent composition logic
├── README.md                    # This file
│
├── tools/                       # Tool definitions
│   └── specialized.yaml         # Specialized tool definitions with metadata
│
└── skills/                      # Skill definitions
    ├── system/                  # Built-in skills (read-only)
    │   ├── code-writer.yaml
    │   ├── database-migration.yaml  # Grants db_migration_tool
    │   ├── prod-deployment.yaml     # Grants deploy_prod
    │   ├── security-audit.yaml      # Grants run_security_scan
    │   ├── api-integration.yaml     # Grants test_api_endpoint
    │   └── ...
    │
    └── user/                    # Custom user skills (editable)
        └── (your custom skills here)
```

---

## 🔌 API Endpoints

All endpoints are available under `/api/v1/skills`.

### Skill Management

#### List Skills
```bash
GET /api/v1/skills
GET /api/v1/skills?tags=coding,testing
GET /api/v1/skills?author=system
```

**Response:**
```json
{
  "skills": [
    {
      "id": "code-writer",
      "name": "Code Writer",
      "description": "Implements features and writes production-quality code",
      "version": "1.0.0",
      "author": "system",
      "tags": ["coding", "implementation", "feature-development"],
      "specialized_tools": [],
      "constraints": ["Do not refactor unrelated code"]
    },
    {
      "id": "prod-deployment",
      "name": "Production Deployment",
      "description": "Deploys applications to production environments safely",
      "version": "1.0.0",
      "author": "system",
      "tags": ["deployment", "production", "devops"],
      "specialized_tools": ["deploy_prod"],
      "constraints": ["Never deploy without passing tests"]
    }
  ],
  "total": 2,
  "by_author": {"system": 10, "user": 0}
}
```

#### Get Skill
```bash
GET /api/v1/skills/{skill_id}
```

**Example:**
```bash
curl http://localhost:8002/api/v1/skills/code-writer
```

#### Create User Skill
```bash
POST /api/v1/skills
Content-Type: application/json

{
  "id": "python-optimizer",
  "name": "Python Performance Optimizer",
  "description": "Optimizes Python code for performance",
  "instructions": "# Python Optimizer\n\nYou optimize Python code...",
  "specialized_tools": ["profiler", "benchmark"],
  "tags": ["optimization", "performance", "python"],
  "constraints": ["Do not sacrifice readability for micro-optimizations"]
}
```

**Note:** System skills cannot be modified. Only user skills can be created/updated/deleted.

#### Update User Skill
```bash
PUT /api/v1/skills/{skill_id}
Content-Type: application/json

{
  "description": "Updated description",
  "tags": ["optimization", "performance", "python", "profiling"]
}
```

#### Delete User Skill
```bash
DELETE /api/v1/skills/{skill_id}
```

### Search & Discovery

#### Search by Capabilities
```bash
GET /api/v1/skills/search/capabilities?capabilities=coding,testing
```

**Response:**
```json
{
  "skills": [
    {"id": "code-writer", "tags": ["coding", "implementation"]},
    {"id": "test-automator", "tags": ["testing", "quality-assurance"]}
  ],
  "total": 2,
  "searched_capabilities": ["coding", "testing"]
}
```

### Tool Management

#### List Tools
```bash
GET /api/v1/tools
GET /api/v1/tools?tier=global
GET /api/v1/tools?tier=specialized
```

**Response:**
```json
{
  "tools": [
    {
      "id": "read",
      "name": "Read",
      "tier": "global",
      "granted_by": [],
      "security_level": "standard"
    },
    {
      "id": "deploy_prod",
      "name": "Deploy Prod",
      "tier": "specialized",
      "granted_by": ["deploy-engineer"],
      "security_level": "elevated"
    }
  ],
  "total": 2,
  "by_tier": {"global": 6, "specialized": 1}
}
```

#### Get Tool
```bash
GET /api/v1/skills/tools/{tool_id}
```

### Agent Composition

#### Compose Agent
```bash
POST /api/v1/skills/compose
Content-Type: application/json

{
  "task": {
    "task_id": "task-123",
    "description": "Implement user authentication",
    "required_capabilities": ["coding", "security"],
    "priority": 1
  },
  "skill_ids": ["code-writer", "security-reviewer"],
  "context": {
    "project_id": "myapp",
    "tech_stack": ["Python", "FastAPI", "PostgreSQL"],
    "conventions": "Follow PEP 8 style guide"
  }
}
```

**Response:**
```json
{
  "id": "agent-abc123",
  "skills": [
    {"id": "code-writer", "name": "Code Writer"},
    {"id": "security-reviewer", "name": "Security Reviewer"}
  ],
  "merged_instructions": "# Agent Configuration\n\n**Active Skills:** Code Writer, Security Reviewer\n\n...",
  "tools": ["read", "write", "edit", "bash", "glob", "grep"],
  "context": {...},
  "task": {...},
  "created_at": "2026-01-25T10:30:00Z"
}
```

**Auto-Selection:** If `skill_ids` is omitted, skills are automatically selected based on `task.required_capabilities`.

#### Check Conflicts
```bash
POST /api/v1/skills/conflicts/check
Content-Type: application/json

{
  "skill_ids": ["code-writer", "security-reviewer"]
}
```

**Response:**
```json
{
  "has_conflicts": false,
  "conflicts": [],
  "warnings": []
}
```

### Statistics

#### Get Marketplace Stats
```bash
GET /api/v1/skills/stats
```

**Response:**
```json
{
  "total_skills": 5,
  "total_tools": 7,
  "global_tools": 6,
  "specialized_tools": 1,
  "by_author": {"system": 5, "user": 0}
}
```

---

## 📝 Skill Definition Format

Skills are defined in YAML files with the following schema:

```yaml
# Unique identifier (lowercase, hyphens only)
id: code-writer

# Display name
name: Code Writer

# Brief description of what this skill does
description: Implements features and writes production-quality code following project conventions and best practices.

# Semantic version
version: "1.0.0"

# Author (system or user:{id})
author: system

# CLAUDE.md instruction fragment
# This gets merged into the final agent instructions
instructions: |
  # Code Writer

  ## Role
  You implement features and write production-quality code.

  ## Working Style
  - Read and understand existing code patterns
  - Follow project conventions strictly
  - Write clean, readable code
  - Keep changes focused and minimal

  ## Code Quality
  - Use descriptive names
  - Keep functions small
  - Add comments only where needed
  - Handle errors appropriately

# Specialized tools this skill grants access to
# (Global tools are automatically available)
specialized_tools:
  - profiler
  - benchmark

# Tags for capability-based search
tags:
  - coding
  - implementation
  - feature-development

# Skills that conflict with this one (advisory)
conflicts_with:
  - code-destroyer  # Example conflict

# Explicit constraints - what NOT to do
constraints:
  - Do not refactor unrelated code
  - Do not add features beyond requirements
  - Do not modify configuration without approval
```

### Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique identifier (lowercase, hyphens) |
| `name` | string | Yes | Display name |
| `description` | string | Yes | Brief description |
| `version` | string | No | Semantic version (default: "1.0.0") |
| `author` | string | No | "system" or "user:{id}" (auto-set) |
| `instructions` | string | Yes | CLAUDE.md instruction fragment |
| `specialized_tools` | list | No | Tool IDs granted by this skill |
| `tags` | list | No | Capability tags for discovery |
| `conflicts_with` | list | No | Conflicting skill IDs (advisory) |
| `constraints` | list | No | What NOT to do |

---

## 🛠️ Creating Custom Skills

### 1. Create Skill Definition

Create a new YAML file in `marketplace/skills/user/`:

```bash
cd serving/marketplace/skills/user
nano python-optimizer.yaml
```

```yaml
id: python-optimizer
name: Python Performance Optimizer
description: Optimizes Python code for performance and memory efficiency
version: "1.0.0"

instructions: |
  # Python Performance Optimizer

  ## Role
  You optimize Python code for performance while maintaining readability.

  ## Approach
  - Profile code to identify bottlenecks
  - Apply algorithmic improvements first
  - Use appropriate data structures
  - Leverage Python built-ins and libraries
  - Benchmark changes to verify improvements

  ## Tools
  - Use `profiler` to measure performance
  - Use `benchmark` to compare implementations

specialized_tools:
  - profiler
  - benchmark

tags:
  - optimization
  - performance
  - python
  - profiling

conflicts_with: []

constraints:
  - Do not sacrifice code readability for micro-optimizations
  - Always benchmark before and after changes
  - Document performance improvements with metrics
```

### 2. Register via API (Alternative)

```bash
curl -X POST http://localhost:8002/api/v1/skills \
  -H "Content-Type: application/json" \
  -d @python-optimizer.json
```

### 3. Restart Serving

```bash
cd serving
./stop.sh && ./start.sh
```

Skills are loaded on startup. Alternatively, use the API to create skills without restarting.

### 4. Verify Skill

```bash
curl http://localhost:8002/api/v1/skills/python-optimizer
```

---

## 🎨 Agent Composition

### Composition Process

When composing an agent:

1. **Select Skills** - Either explicit (`skill_ids`) or auto-selected based on `task.required_capabilities`
2. **Check Conflicts** - Validate skill compatibility (advisory warnings)
3. **Merge Instructions** - Combine CLAUDE.md fragments into coherent document
4. **Aggregate Tools** - Global tools + specialized tools from selected skills
5. **Add Context** - Inject project conventions, tech stack, domain knowledge
6. **Generate Bundle** - Return deployable agent ready for Claude Code

### Merged Instructions Structure

The final CLAUDE.md document follows this structure:

```markdown
# Agent Configuration
**Active Skills:** Code Writer, Test Writer

## Project Context
### Conventions
Follow PEP 8 style guide...

### Tech Stack
- Python
- FastAPI
- PostgreSQL

## Skill Instructions

### Code Writer
You implement features and write production-quality code...

### Test Writer
You write comprehensive tests...

## Constraints
- Do not refactor unrelated code
- Do not skip edge case testing
```

### Example: Bug Fix Agent

```bash
POST /api/v1/skills/compose

{
  "task": {
    "task_id": "bug-456",
    "description": "Fix authentication timeout",
    "required_capabilities": ["debugging", "coding", "testing"]
  }
}
```

**Auto-selects:** `debugger`, `code-writer`, `test-automator`

**Tools:** Global tools + any specialized tools from selected skills

---

## ⚙️ Configuration

### Environment Variables

```bash
# Path to skills directory
SKILLS_PATH=./marketplace/skills
```

Default: `./marketplace/skills` (relative to serving root)

### Programmatic Access

```python
from marketplace.skill_registry import get_skill_registry
from marketplace.composition_service import get_composition_service

# Get registry
registry = get_skill_registry()

# List all skills
skills = registry.list_skills()

# Get composition service
composer = get_composition_service()

# Compose agent
agent = await composer.compose(request)
```

---

## 🏗️ System Skills

ClaudeVN includes 5 built-in system skills:

| Skill ID | Name | Tags | Purpose |
|----------|------|------|---------|
| `code-writer` | Code Writer | coding, implementation | Implements features and writes production code |
| `test-automator` | Test Automator | testing, quality-assurance | Writes comprehensive tests |
| `debugger` | Debugger | debugging, troubleshooting | Investigates and fixes bugs |
| `security-reviewer` | Security Reviewer | security, code-review | Reviews code for security vulnerabilities |
| `doc-writer` | Documentation Writer | documentation, technical-writing | Creates and maintains documentation |

**System skills are read-only** and cannot be modified or deleted.

---

## 🔍 Best Practices

### Skill Design

- **Single Responsibility** - Each skill should have one clear purpose
- **Composability** - Skills should work well in combination
- **Clear Constraints** - Explicitly define what NOT to do
- **Meaningful Tags** - Use tags that describe capabilities, not implementations
- **Concise Instructions** - Keep CLAUDE.md fragments focused and actionable

### Agent Composition

- **Task-Driven** - Select skills based on task requirements
- **Minimal Set** - Use only the skills needed for the task
- **Check Conflicts** - Always validate compatibility before deployment
- **Add Context** - Provide project conventions and domain knowledge
- **Test Bundles** - Verify agent behavior before production use

### Tool Authorization

- **Principle of Least Privilege** - Grant only necessary specialized tools
- **Security Awareness** - Specialized tools should require explicit skill grants
- **Document Tools** - Clearly explain what each specialized tool does

---

## 📊 Statistics & Monitoring

### Health Check

The skill marketplace stats are included in serving health:

```bash
curl http://localhost:8002/api/v1/health
```

```json
{
  "status": "healthy",
  "skill_registry": {
    "total_skills": 5,
    "total_tools": 7,
    "global_tools": 6,
    "specialized_tools": 1,
    "by_author": {"system": 5, "user": 0}
  }
}
```

### Dedicated Stats Endpoint

```bash
curl http://localhost:8002/api/v1/skills/stats
```

---

## 🧪 Testing

### Manual Testing

```bash
# 1. List all skills
curl http://localhost:8002/api/v1/skills

# 2. Search for coding skills
curl "http://localhost:8002/api/v1/skills/search/capabilities?capabilities=coding"

# 3. Compose an agent
curl -X POST http://localhost:8002/api/v1/skills/compose \
  -H "Content-Type: application/json" \
  -d '{
    "task": {
      "task_id": "test-123",
      "description": "Test task",
      "required_capabilities": ["coding"]
    }
  }'

# 4. Check conflicts
curl -X POST http://localhost:8002/api/v1/skills/conflicts/check \
  -H "Content-Type: application/json" \
  -d '{"skill_ids": ["code-writer", "test-automator"]}'
```

---

## 🚨 Troubleshooting

### Skill Not Loading

**Symptom:** Skill doesn't appear in `/api/v1/skills`

**Solutions:**
```bash
# Check YAML syntax
yamllint marketplace/skills/user/your-skill.yaml

# Check logs
tail -f logs/serving.log | grep -i skill

# Verify file permissions
ls -la marketplace/skills/user/

# Restart serving
./stop.sh && ./start.sh
```

### Composition Fails

**Symptom:** `/api/v1/skills/compose` returns 400 error

**Solutions:**
```bash
# Check required fields in task
{
  "task": {
    "task_id": "required",
    "description": "required"
  }
}

# Verify skill IDs exist
curl http://localhost:8002/api/v1/skills/{skill_id}

# Check conflicts
curl -X POST http://localhost:8002/api/v1/skills/conflicts/check \
  -H "Content-Type: application/json" \
  -d '{"skill_ids": ["skill-1", "skill-2"]}'
```

### Tools Not Available

**Symptom:** Agent doesn't have expected specialized tools

**Solutions:**
```bash
# Verify skill grants the tool
curl http://localhost:8002/api/v1/skills/{skill_id}

# Check tool definition
curl http://localhost:8002/api/v1/skills/tools/{tool_id}

# Verify skill was included in composition
# Check agent.skills array in compose response
```

---

## 📚 Additional Documentation

- **Serving Component**: [serving/README.md](../README.md)
- **API Documentation**: http://localhost:8002/docs
- **Project Architecture**: [/docs/design/architecture/v1.0-architecture.md](../../docs/design/architecture/v1.0-architecture.md)

---

## 📝 Version History

### **1.0.0** (Current)
- ✅ Skill registry with system and user skills
- ✅ Agent composition service
- ✅ Two-tier tool authorization (global + specialized)
- ✅ Conflict detection
- ✅ Capability-based search
- ✅ 5 built-in system skills
- ✅ Full CRUD API for user skills

---

**Built with ❤️ for composable AI agents**
