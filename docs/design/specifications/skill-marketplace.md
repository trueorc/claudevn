# Skill Marketplace Specification

**Version**: 1.0.0
**Last Updated**: January 2026
**Status**: Design Specification

---

## Overview

The Skill Marketplace is a reimagined architecture for managing capabilities in ClaudeVN v1.0. Instead of monolithic personas, the marketplace provides **atomic skills** that Serving composes into **Agent bundles** deployed to Claude Code compute instances.

This approach enables:
- Fine-grained capability selection
- Dynamic agent composition based on task requirements
- Reusable, modular skill definitions
- Two-tier tool authorization (global vs specialized)

---

## Core Concepts

### Skills (Atomic Capability Units)

A skill is a **single, focused capability** that can be combined with other skills. Unlike personas (which define complete roles), skills are building blocks.

#### Skill Components

Each skill contains:

| Component | Description |
|-----------|-------------|
| **Identity** | ID, name, description, version, author (system or user:{id}) |
| **Instructions** | CLAUDE.md content fragment defining behavior |
| **Specialized Tools** | Tools this skill grants access to (beyond global tools) |
| **Tags/Categories** | For discovery (coding, testing, finance, security, etc.) |
| **Conflict Hints** | Known tensions with other skills (advisory, not blocking) |
| **Constraints** | Boundaries - what this skill should NOT do |

#### Skill vs Persona

| Aspect | Skill (v1.0) | Persona (Legacy) |
|--------|--------------|------------------|
| **Scope** | Atomic capability | Complete role definition |
| **Composition** | Combined with other skills | Used standalone |
| **Instructions** | Fragment (partial CLAUDE.md) | Complete CLAUDE.md |
| **Tools** | Declares specialized needs | All tools bundled |
| **Reusability** | Highly reusable | Role-specific |

### Agent (Composed Bundle)

An Agent is the **runtime configuration** deployed to a Claude Code compute instance. It consists of:

- **Selected Skills**: Collection of skills chosen for the task
- **Merged Instructions**: Intelligent composition of skill instruction fragments
- **All Tools**: Global tools + specialized tools from all selected skills
- **Project Context**: Repo conventions, tech stack, domain knowledge
- **Task Assignment**: Specific work to be done

### Personas (Pre-Combined Skill Bundles)

Personas are **pre-configured skill combinations** for common scenarios. Stored alongside skills in Marketplace.

```yaml
id: fullstack-developer
name: Full-Stack Developer
description: Complete development capability
skills: [code-writer, test-automator, db-engineer]
# Merged instructions pre-generated for efficiency
```

Personas simplify assignment for common work patterns while skills provide flexibility for novel combinations.

### Tool Authorization (Two-Part Check)

Tool access requires **both** skill permission AND compute capability:

| Check | Question | Example |
|-------|----------|---------|
| **Skill grants** | Is agent allowed to use this tool? | `deployer` skill grants `deploy_prod` |
| **Compute has** | Is tool available on this instance? | `compute-prod-001` has `deploy_prod` installed |

Both must align. Skill grants intent, Compute provides capability.

#### Global Tools (Tier 1)

All agents receive these foundational tools (available on all Compute instances):

| Tool | Purpose |
|------|---------|
| **Read** | Read files from the workspace |
| **Write** | Create new files |
| **Edit** | Modify existing files |
| **Bash** | Execute shell commands |
| **Glob** | Find files by pattern |
| **Grep** | Search file contents |

#### Specialized Tools (Tier 2)

Skills declare specialized tool requirements. Tool must also be available on assigned Compute:

| Tool | Required Skill | Compute Label | Purpose |
|------|----------------|---------------|---------|
| `deploy_prod` | `deploy-engineer` | `production-access` | Deploy to production |
| `db_migrate` | `db-engineer` | `database-admin` | Run database migrations |
| `run_security_scan` | `security-auditor` | `security-tools` | Execute security scans |

### Compute Labels (Routing)

Compute instances declare labels at registration for work routing:

```yaml
# Compute registration
compute_id: compute-001
labels: [production-access, database-admin]
tools_available: [deploy_prod, db_migrate]
capabilities: [coding, testing]

compute_id: compute-002
labels: [standard]
tools_available: []  # Global tools only
capabilities: [coding, testing, documentation]
```

Serving matches issues to Computes where:
- Skill permissions align with required tools
- Compute has those tools available (via labels)

---

## Functional Areas

### 1. Skill Catalog

**Purpose**: Repository of atomic skill definitions.

#### Features

- CRUD operations for skills
- Versioning support (semver)
- System skills (bundled with ClaudeVN) vs User skills (custom)
- Tag-based organization
- Search by tags, capabilities, and descriptions

#### System Skills (Bundled)

| Skill ID | Name | Capabilities | Tools |
|----------|------|--------------|-------|
| `code-implementation` | Code Implementation | Write/modify code | (global only) |
| `test-creation` | Test Creation | Write automated tests | (global only) |
| `code-analysis` | Code Analysis | Review code quality | (global only) |
| `bug-investigation` | Bug Investigation | Debug issues, root cause analysis | (global only) |
| `documentation` | Documentation | Write docs, comments | (global only) |
| `git-operations` | Git Operations | Branch management, PRs | (global only) |
| `database-migration` | Database Migration | Schema changes | `db_migration_tool` |
| `prod-deployment` | Production Deployment | Deploy to production | `deploy_prod` |
| `security-audit` | Security Audit | Vulnerability scanning | `run_security_scan` |
| `api-integration` | API Integration | External API work | `test_api_endpoint` |

#### Operations

```python
# List all skills
skills = catalog.list(tags=["coding"], author="system")

# Get skill details
skill = catalog.get("code-implementation")

# Create new skill
skill = Skill(
    id="custom-validator",
    name="Custom Validator",
    description="Validates custom business rules",
    instructions="...",
    specialized_tools=["validate_business_rule"],
    tags=["validation", "business-logic"],
    conflicts_with=["security-audit"],  # Advisory
    constraints=["Do not modify validation logic"]
)
catalog.create(skill)

# Update skill
catalog.update("custom-validator", version="1.1.0", instructions="...")

# Delete skill
catalog.delete("custom-validator")
```

---

### 2. Tool Authorization Registry

**Purpose**: Centralized registry of tool definitions and permissions.

#### Tool Definition Schema

```yaml
ToolDefinition:
  id: string                  # Unique tool identifier
  name: string                # Display name
  description: string         # What the tool does
  tier: "global" | "specialized"
  parameters:                 # JSON schema for parameters
    type: object
    properties: {}
  granted_by: []              # Skill IDs (for specialized tools)
  security_level: string      # "read-only" | "read-write" | "admin"
```

#### Example Tool Definitions

```yaml
# Global tool
- id: read_file
  name: Read
  description: Read files from the workspace
  tier: global
  security_level: read-only
  granted_by: []

# Specialized tool
- id: deploy_prod
  name: Deploy to Production
  description: Deploy application to production environment
  tier: specialized
  security_level: admin
  granted_by:
    - prod-deployment
    - emergency-hotfix
```

#### Authorization Check

```python
def check_tool_authorization(agent: Agent, tool_id: str) -> bool:
    """Check if agent is authorized to use a tool."""

    tool = tool_registry.get(tool_id)

    # Global tools always allowed
    if tool.tier == "global":
        return True

    # Check if any agent skill grants this tool
    agent_skills = {skill.id for skill in agent.skills}
    granting_skills = set(tool.granted_by)

    return bool(agent_skills & granting_skills)
```

---

### 3. Skill Selection (Planner-Driven)

**Purpose**: Planner Compute determines skills needed for each issue.

#### How It Works

Planner queries Marketplace catalog to discover available skills, then assigns skills to each issue during planning:

```
Planner : GET /api/v1/skills : Marketplace
Marketplace : returns skill catalog (id, name, description, tags) : Planner
Planner : analyzes goal, selects skills per issue : claudevn_add_issues()
```

#### Planner Selection Process

```python
# Planner queries catalog
skills_catalog = marketplace.list_skills()

# Planner (Claude Code) decides skills for each issue based on:
# - Issue description/requirements
# - Available skills and their tags
# - Skill descriptions and capabilities

# Planner submits issues with required_skills
claudevn_add_issues({
    "goal_id": "goal-001",
    "issues": [
        {
            "title": "Design database schema",
            "required_skills": ["code-writer", "db-engineer"],  # Planner selected
            ...
        },
        {
            "title": "Write API tests",
            "required_skills": ["test-automator"],  # Planner selected
            ...
        }
    ]
})
```

#### Fallback: Tag-Based Matching

If issue has no `required_skills`, Serving can fall back to tag matching:

```python
def select_skills_by_tags(issue: Issue) -> List[Skill]:
    """Fallback: select skills matching issue tags."""

    matched = []
    for skill in catalog.list():
        if set(skill.tags) & set(issue.tags):
            matched.append(skill)

    return matched[:3]  # Limit to top matches
```

**3. Dependency Resolution**

Some skills imply others:

```python
skill_dependencies = {
    "prod-deployment": ["code-analysis"],  # Must review before deploying
    "database-migration": ["code-implementation"],  # Need to write migration
    "api-integration": ["test-creation"],  # Must test integrations
}

def resolve_dependencies(selected_skills: List[Skill]) -> List[Skill]:
    """Add implied skills based on dependencies."""

    result = set(selected_skills)

    for skill in selected_skills:
        if skill.id in skill_dependencies:
            for dep_id in skill_dependencies[skill.id]:
                dep_skill = catalog.get(dep_id)
                result.add(dep_skill)

    return list(result)
```

**4. Semantic Similarity (Future)**

```python
# Future enhancement: use embeddings for semantic matching
def select_skills_semantic(task: Task) -> List[Skill]:
    """Select skills using semantic similarity."""

    task_embedding = embed(task.description)

    similarities = []
    for skill in catalog.list():
        skill_embedding = embed(skill.description + " " + skill.instructions)
        similarity = cosine_similarity(task_embedding, skill_embedding)
        similarities.append((skill, similarity))

    similarities.sort(key=lambda x: x[1], reverse=True)
    return [s[0] for s in similarities[:5]]
```

---

### 4. Composition Engine

**Purpose**: Combines selected skills into a deployable Agent bundle.

#### Composition Process

```
Input: [skill1, skill2, skill3], ProjectContext, Task

1. Concatenate Instructions
   └─> Append skill instruction fragments in order

2. Aggregate Tools
   └─> Global + specialized from all skills

3. Inject Context
   └─> Add project conventions, tech stack, domain rules

4. Generate CLAUDE.md
   └─> Output deployable Agent configuration

Output: Agent (ready for Claude Code compute)
```

**Note:** Composition is simple concatenation. May evolve to pre-combined Personas for common scenarios to improve efficiency.

#### Instruction Concatenation

Skills are concatenated with section headers:

```markdown
# Example Input: Two Skills

## Skill: code-implementation
### Instructions Fragment
- Read and understand existing code patterns
- Write clean, readable code
- Follow established project conventions
- Keep changes minimal and focused

## Skill: test-creation
### Instructions Fragment
- Understand code behavior before writing tests
- Test behavior, not implementation
- Cover edge cases and error conditions
- Keep tests fast and independent

# Composed Output (by Serving Claude Code)

## Your Role
You are implementing code and creating tests for this project.

## Working Approach
1. Read and understand existing code patterns and behavior
2. Write clean, readable code following established conventions
3. Create tests that verify behavior (not implementation details)
4. Keep both code changes and tests minimal, fast, and focused
5. Cover edge cases and error conditions in your tests

## Quality Standards
- Code is clean and follows project conventions
- Changes are minimal and focused on requirements
- Tests verify behavior and cover edge cases
- Tests are fast and independent
```

#### Overlap Resolution

When skills have contradictory guidance:

```python
# Example: code-implementation says "keep changes minimal"
# vs rapid-prototyping says "prioritize speed over perfection"

# Serving Claude Code makes judgment call based on:
# 1. Task context (is this a prototype or production feature?)
# 2. Skill priority (which skill is more central to the task?)
# 3. Project context (what are the project's standards?)

# Output might be:
"Prioritize rapid implementation for this prototype, but maintain
 readability and basic code quality standards."
```

#### Tool Aggregation

```python
def aggregate_tools(skills: List[Skill]) -> List[str]:
    """Combine global and specialized tools."""

    # Start with global tools
    tools = [
        "Read", "Write", "Edit", "Bash", "Glob", "Grep"
    ]

    # Add specialized tools from each skill
    for skill in skills:
        for tool_id in skill.specialized_tools:
            if tool_id not in tools:
                tools.append(tool_id)

    return tools
```

---

### 5. Conflict Audit

**Purpose**: Pre-composition analysis to flag potential issues (advisory only).

#### Conflict Types

| Conflict Type | Example |
|---------------|---------|
| **Contradictory Instructions** | "move fast" vs "thorough review" |
| **Tool Permission Overlap** | Multiple skills requesting same admin tool |
| **Scope Confusion** | "fix bugs only" + "add new features" |
| **Priority Mismatch** | "security first" vs "ship fast" |

#### Audit Process

```python
def audit_skill_combination(skills: List[Skill]) -> ConflictReport:
    """Analyze skill combination for potential conflicts."""

    warnings = []

    # Check declared conflicts
    for skill in skills:
        for other_skill in skills:
            if other_skill.id in skill.conflicts_with:
                warnings.append({
                    "type": "declared_conflict",
                    "severity": "medium",
                    "message": f"{skill.name} conflicts with {other_skill.name}",
                    "skills": [skill.id, other_skill.id]
                })

    # Check tool permission overlaps
    tool_counts = {}
    for skill in skills:
        for tool in skill.specialized_tools:
            tool_def = tool_registry.get(tool)
            if tool_def.security_level == "admin":
                if tool not in tool_counts:
                    tool_counts[tool] = []
                tool_counts[tool].append(skill.id)

    for tool, skill_ids in tool_counts.items():
        if len(skill_ids) > 1:
            warnings.append({
                "type": "tool_overlap",
                "severity": "low",
                "message": f"Multiple skills request admin tool '{tool}'",
                "skills": skill_ids
            })

    # Check for scope confusion (AI-based analysis)
    # This would use Serving Claude Code to analyze instruction overlap

    return ConflictReport(warnings=warnings)
```

#### Decision Point, Not Rejection

Conflicts are detected when adding a new skill to a composition. This is a **decision point**:

- Conflict detected → user/system notified
- Can proceed with both skills if intentional (e.g., writer + reviewer for thorough work)
- Can remove conflicting skill if desired
- Not automatic rejection

```python
# Example: Adding a skill that conflicts
result = composition.add_skill("code-reviewer")

if result.has_conflicts:
    # Decision point - conflicts with existing code-writer
    print(f"Conflict: {result.conflicts}")
    # Options:
    # 1. Keep both (intentional)
    # 2. Remove conflicting skill
    # 3. Cancel addition
```

---

### 6. User Skill Studio

**Purpose**: Interface for creating and managing custom skills.

#### Create Custom Skill

```python
# API endpoint
POST /api/v1/skills
Content-Type: application/json

{
  "id": "custom-email-validator",
  "name": "Email Validator",
  "description": "Validates email addresses using custom business rules",
  "version": "1.0.0",
  "author": "user:alice",
  "instructions": """
## Email Validation Skill

When validating email addresses:
- Check format using RFC 5322 regex
- Verify domain has valid MX records
- Apply company-specific rules:
  - Block disposable email domains
  - Require corporate domains for enterprise accounts
  - Flag suspicious patterns

## Constraints
- Do not modify existing validation logic
- Do not store email addresses
- Report validation results clearly
  """,
  "specialized_tools": ["validate_email_format", "check_mx_records"],
  "tags": ["validation", "email", "security"],
  "conflicts_with": [],
  "constraints": [
    "Do not modify existing validation logic",
    "Do not store email addresses"
  ]
}

Response:
{
  "id": "custom-email-validator",
  "status": "created",
  "version": "1.0.0"
}
```

#### Version Management

Skills don't have explicit version fields. Git backend provides implicit versioning:

```python
# Update skill (Git tracks history)
PUT /api/v1/skills/custom-email-validator

{
  "instructions": "... updated instructions ..."
}

# Git commit created automatically with change history
# Can reference skill state at any Git commit if needed
```

**Note:** Git-backed storage means full history is available via Git operations, not via explicit version API endpoints.

#### Declare Tool Requirements

```yaml
# Custom skill declares need for new specialized tool
specialized_tools:
  - id: validate_email_format
    description: Validate email address format using regex
    parameters:
      email:
        type: string
        description: Email address to validate
    returns:
      valid: boolean
      reason: string  # If invalid, why
```

---

### 7. Context Layer

**Purpose**: Inject project and domain context alongside skills.

#### Project Context Components

```yaml
ProjectContext:
  project_id: string

  # Code conventions
  conventions:
    code_style: |
      - Use 4 spaces for indentation
      - Max line length: 100 characters
      - Follow PEP 8 for Python code
    naming_patterns:
      - Classes: PascalCase
      - Functions: snake_case
      - Constants: UPPER_SNAKE_CASE
    patterns:
      - Use dependency injection
      - Prefer composition over inheritance
      - Write docstrings for all public functions

  # Tech stack
  tech_stack:
    - Python 3.10+
    - FastAPI
    - PostgreSQL
    - Redis
    - React (frontend)

  # Domain context
  domain_context: |
    ClaudeVN is an AI agent orchestration platform. Key concepts:
    - Serving: Central coordination hub
    - Compute: Claude Code worker instances
    - Skills: Atomic capability units
    - Agents: Composed bundles of skills

  # Custom rules
  custom_rules:
    - All code changes require tests
    - Security changes require review by security-audit skill
    - Database migrations must be reversible
    - API changes must update OpenAPI spec
```

#### Context Injection

```python
def compose_agent(
    skills: List[Skill],
    context: ProjectContext,
    task: Task
) -> Agent:
    """Compose agent with skills and context."""

    # Generate merged instructions using Serving Claude Code
    merged_instructions = intelligent_merge(
        skill_instructions=[s.instructions for s in skills],
        project_context=context,
        task_description=task.description
    )

    # Aggregate tools
    tools = aggregate_tools(skills)

    # Build agent
    agent = Agent(
        id=f"agent-{uuid4()}",
        skills=skills,
        merged_instructions=merged_instructions,
        tools=tools,
        context=context,
        task=task,
        created_at=datetime.utcnow()
    )

    return agent
```

---

## Data Models

### Skill

```yaml
Skill:
  id: string                  # unique identifier (e.g., "code-implementation")
  name: string                # display name (e.g., "Code Implementation")
  description: string         # what this skill does
  version: string             # semver (e.g., "1.2.0")
  author: string              # "system" or "user:{id}"

  instructions: string        # CLAUDE.md fragment (partial instructions)
  specialized_tools: []       # tool IDs this skill requires
  tags: []                    # for discovery ["coding", "python", "backend"]
  conflicts_with: []          # skill IDs with known tensions (advisory)
  constraints: []             # what NOT to do

  metadata:
    created_at: datetime
    updated_at: datetime
    usage_count: integer      # how many times used
    avg_rating: float         # user ratings (if applicable)
```

### Agent

```yaml
Agent:
  id: string                  # unique identifier (e.g., "agent-abc123")

  # Composition
  skills: Skill[]             # selected skills
  merged_instructions: string # composed CLAUDE.md content
  tools: string[]             # global + all specialized tools

  # Context
  context: ProjectContext     # project-specific context
  task: TaskAssignment        # assigned work

  # Metadata
  created_at: datetime
  deployed_to: string         # compute instance ID
  status: string              # "composing" | "ready" | "deployed" | "complete"
```

### ProjectContext

```yaml
ProjectContext:
  project_id: string

  conventions: string         # code style, patterns, naming
  tech_stack: []              # languages, frameworks, tools
  domain_context: string      # domain-specific knowledge
  custom_rules: []            # project-specific constraints

  updated_at: datetime
```

### TaskAssignment

```yaml
TaskAssignment:
  task_id: string
  title: string
  description: string
  required_capabilities: []   # capabilities needed for this task
  tags: []                    # for skill matching
  priority: string            # "low" | "medium" | "high" | "critical"
  deadline: datetime          # optional

  dependencies: []            # task IDs this depends on
  blocking: []                # task IDs blocked by this
```

### ToolDefinition

```yaml
ToolDefinition:
  id: string                  # unique identifier (e.g., "deploy_prod")
  name: string                # display name (e.g., "Deploy to Production")
  description: string         # what the tool does

  tier: string                # "global" | "specialized"
  granted_by: []              # skill IDs (for specialized tools)
  security_level: string      # "read-only" | "read-write" | "admin"

  # JSON schema for tool parameters
  parameters:
    type: object
    properties: {}
    required: []

  # JSON schema for tool return value
  returns:
    type: object
    properties: {}
```

---

## API Endpoints

### Skills

```
# List all skills
GET /api/v1/skills?tags=coding,testing&author=system
Response: { "skills": [...] }

# Get skill details
GET /api/v1/skills/{skill_id}
Response: { "id": "...", "name": "...", "instructions": "...", ... }

# Search by tags/capabilities
GET /api/v1/skills/search?q=authentication&tags=security
Response: { "skills": [...], "total": N }

# Create new skill
POST /api/v1/skills
Body: { "id": "...", "name": "...", "instructions": "...", ... }
Response: { "id": "...", "status": "created" }

# Update skill
PUT /api/v1/skills/{skill_id}
Body: { "version": "1.1.0", "instructions": "...", "changelog": "..." }
Response: { "id": "...", "status": "updated", "version": "1.1.0" }

# Delete skill
DELETE /api/v1/skills/{skill_id}
Response: { "id": "...", "status": "deleted" }

# List skill versions
GET /api/v1/skills/{skill_id}/versions
Response: { "versions": [...] }

# Get specific version
GET /api/v1/skills/{skill_id}?version=1.0.0
Response: { "id": "...", "version": "1.0.0", ... }
```

### Composition

```
# Compose agent from skills
POST /api/v1/agents/compose
Body: {
  "task_id": "task-123",
  "skill_overrides": ["code-implementation", "test-creation"],  # Optional
  "context_overrides": { ... }  # Optional
}
Response: {
  "agent": {
    "id": "agent-abc123",
    "skills": [...],
    "merged_instructions": "...",
    "tools": [...],
    "status": "ready"
  },
  "conflict_warnings": [...]  # Advisory conflicts
}

# Get agent details
GET /api/v1/agents/{agent_id}
Response: { "id": "...", "skills": [...], ... }

# List active agents
GET /api/v1/agents?status=deployed
Response: { "agents": [...] }
```

### Tools

```
# List all tool definitions
GET /api/v1/tools?tier=specialized
Response: { "tools": [...] }

# Get tool definition
GET /api/v1/tools/{tool_id}
Response: { "id": "...", "name": "...", "tier": "...", ... }

# Check authorization
POST /api/v1/tools/check-authorization
Body: { "agent_id": "agent-abc123", "tool_id": "deploy_prod" }
Response: { "authorized": true, "granted_by": ["prod-deployment"] }
```

### Conflict Analysis

```
# Analyze skill combination for conflicts
POST /api/v1/skills/analyze-conflicts
Body: {
  "skill_ids": ["code-implementation", "rapid-prototyping", "security-audit"]
}
Response: {
  "conflicts": [
    {
      "type": "contradictory_instructions",
      "severity": "medium",
      "message": "rapid-prototyping prioritizes speed, security-audit prioritizes thoroughness",
      "skills": ["rapid-prototyping", "security-audit"],
      "recommendation": "Consider task context when merging instructions"
    }
  ]
}
```

---

## Storage

### File System Structure

```
marketplace/                      # Separate service (port 8003)
├── skills/
│   ├── system/                   # System skills (bundled)
│   │   ├── code-implementation.yaml
│   │   ├── test-creation.yaml
│   │   ├── code-analysis.yaml
│   │   ├── bug-investigation.yaml
│   │   ├── documentation.yaml
│   │   ├── git-operations.yaml
│   │   ├── database-migration.yaml
│   │   ├── prod-deployment.yaml
│   │   ├── security-audit.yaml
│   │   └── api-integration.yaml
│   │
│   └── user/                     # User-created skills
│       ├── alice/
│       │   └── custom-email-validator.yaml
│       └── bob/
│           └── special-reporting.yaml
│
├── tools/
│   ├── global.yaml               # Global tool definitions
│   └── specialized.yaml          # Specialized tool definitions
│
├── api.py                        # FastAPI router
├── skill_registry.py             # Skill catalog service
└── composition_engine.py         # Agent composition logic

serving/
├── clients/
│   └── marketplace_client.py     # HTTP client to Marketplace
└── frontend/
    └── src/
        └── pages/
            └── SkillMarketplace.tsx  # UI sourced from Marketplace API
```

### Database Schema (PostgreSQL)

```sql
-- Skills table
CREATE TABLE skills (
    id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    version VARCHAR(20) NOT NULL,
    author VARCHAR(100) NOT NULL,  -- 'system' or 'user:{id}'

    instructions TEXT NOT NULL,    -- CLAUDE.md fragment
    specialized_tools JSONB,       -- ["tool1", "tool2"]
    tags JSONB,                    -- ["coding", "testing"]
    conflicts_with JSONB,          -- ["skill-id-1"]
    constraints JSONB,             -- ["constraint1", "constraint2"]

    metadata JSONB,                -- { usage_count: 0, avg_rating: 0.0 }

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_skills_tags ON skills USING GIN (tags);
CREATE INDEX idx_skills_author ON skills (author);
CREATE INDEX idx_skills_version ON skills (id, version);

-- Skill versions (for version history)
CREATE TABLE skill_versions (
    skill_id VARCHAR(100) REFERENCES skills(id),
    version VARCHAR(20) NOT NULL,
    instructions TEXT NOT NULL,
    specialized_tools JSONB,
    changelog TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (skill_id, version)
);

-- Tool definitions
CREATE TABLE tools (
    id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    tier VARCHAR(20) NOT NULL,     -- 'global' or 'specialized'
    granted_by JSONB,              -- ["skill-id-1", "skill-id-2"]
    security_level VARCHAR(20),    -- 'read-only', 'read-write', 'admin'

    parameters JSONB,              -- JSON schema
    returns JSONB,                 -- JSON schema

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tools_tier ON tools (tier);

-- Agents (composed)
CREATE TABLE agents (
    id VARCHAR(100) PRIMARY KEY,
    skill_ids JSONB NOT NULL,      -- ["skill1", "skill2"]
    merged_instructions TEXT NOT NULL,
    tools JSONB NOT NULL,          -- ["Read", "Write", "deploy_prod"]

    project_id VARCHAR(100),
    task_id VARCHAR(100),

    context JSONB,                 -- ProjectContext
    status VARCHAR(20),            -- 'composing', 'ready', 'deployed', 'complete'
    deployed_to VARCHAR(100),      -- compute instance ID

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_agents_status ON agents (status);
CREATE INDEX idx_agents_deployed_to ON agents (deployed_to);
CREATE INDEX idx_agents_task ON agents (task_id);
```

---

## Integration with Serving

### Marketplace as Separate Service

The Marketplace is a **separate service** (port 8003) that owns skill definitions, registry, and composition logic. Serving integrates with Marketplace via HTTP:

```python
# serving/main.py
from serving.clients.marketplace_client import MarketplaceClient

app = FastAPI()

# Serving connects to Marketplace service
marketplace_client = MarketplaceClient(
    base_url=config.marketplace_url,  # http://marketplace:8003
)

# Serving's Skill Marketplace UI sources data from Marketplace service
# but is hosted within Serving's frontend
```

### Serving Startup

```python
@app.on_event("startup")
async def initialize_serving():
    """Connect to Marketplace service on startup."""

    # Verify Marketplace service is available
    await marketplace_client.health_check()

    # Cache skill catalog for quick lookups
    await marketplace_client.refresh_skill_cache()

    logger.info("Connected to Marketplace service")
```

### Work Assignment Flow

```
1. Task arrives at Serving
   ↓
2. Serving requests skill selection from Marketplace
   ↓
3. Marketplace: Selection Engine picks relevant skills
   ↓
4. Marketplace: Conflict Audit analyzes skill combination (advisory)
   ↓
5. Marketplace: Composition Engine merges skills into Agent
   ↓
6. Marketplace returns Agent bundle to Serving:
   - Merged CLAUDE.md instructions
   - Aggregated tool permissions
   ↓
7. Serving adds project context and task assignment
   ↓
8. Agent deployed to Claude Code compute instance via SSE
   ↓
9. Compute executes work using composed Agent configuration
```

### Agent Deployment

```python
async def assign_work_to_compute(task: Task, compute_id: str):
    """Request agent from Marketplace and deploy to compute."""

    # 1. Request composed agent from Marketplace
    agent = await marketplace_client.compose_agent(
        skill_ids=task.required_skills,
        task_context=task.description
    )

    # 2. Push work assignment via SSE (see compute-registration.md)
    await sse_manager.send_event(
        compute_id=compute_id,
        event="work_assigned",
        data={
            "task_id": task.id,
            "title": task.title,
            "description": task.description,
            "branch_name": f"f/{task.id}/{compute_id}",
            "skills": {
                "ids": [s.id for s in agent.skills],
                "merged_instructions": agent.merged_instructions
            },
            "context": {
                "repository": f"git@serving:{task.project}.git",
                "base_branch": "main",
            },
            "mcp_config": {
                "server_url": config.mcp_server_url,
                "api_key": generate_task_scoped_key(task.id)
            }
        }
    )
```

---

## Example Workflows

### Workflow 1: Bug Fix Task

```python
# Task arrives
task = Task(
    id="task-456",
    title="Fix authentication timeout bug",
    description="Users are getting logged out after 5 minutes instead of 30",
    required_capabilities=["bug-investigation", "code-implementation", "test-creation"],
    tags=["bug", "authentication", "backend"]
)

# Selection Engine picks skills
selected_skills = selection_engine.select(task)
# Returns: [bug-investigation, code-implementation, test-creation]

# Conflict audit (no conflicts expected)
audit = conflict_auditor.analyze(selected_skills)
# Returns: ConflictReport(warnings=[])

# Composition Engine merges
agent = composition_engine.compose(
    skills=selected_skills,
    context=project_context,
    task=task
)

# Agent.merged_instructions contains:
"""
# Your Role
You are investigating and fixing an authentication timeout bug.

## Working Approach
1. Reproduce the bug (users logged out after 5 min instead of 30 min)
2. Investigate the authentication timeout logic
3. Identify the root cause
4. Implement a targeted fix
5. Create a regression test to prevent recurrence

## Quality Standards
- Bug must be reproducible before fix
- Fix is minimal and targeted
- Regression test fails without fix
- All existing tests still pass

## Constraints
- Do not refactor unrelated authentication code
- Do not modify session handling beyond the timeout issue
...
"""

# Agent deployed to compute
await deploy_agent_to_compute(agent, compute_id="compute-007")
```

### Workflow 2: New Feature with Multiple Skills

```python
# Task: Add email notification system
task = Task(
    id="task-789",
    title="Implement email notification system",
    description="Send email alerts for important events",
    required_capabilities=[
        "code-implementation",
        "api-integration",
        "test-creation",
        "documentation"
    ],
    tags=["feature", "email", "notifications"]
)

# Selection includes all required skills
selected_skills = [
    skill_catalog.get("code-implementation"),
    skill_catalog.get("api-integration"),
    skill_catalog.get("test-creation"),
    skill_catalog.get("documentation")
]

# Composition creates comprehensive agent
agent = composition_engine.compose(
    skills=selected_skills,
    context=project_context,
    task=task
)

# Agent.tools includes specialized tools
# ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "test_api_endpoint"]
```

---

## Migration from Persona Marketplace

### Key Changes

| Aspect | Persona Marketplace (Legacy) | Skill Marketplace (v1.0) |
|--------|------------------------------|--------------------------|
| **Unit of Capability** | Complete role (persona) | Atomic skill |
| **Composition** | Single persona per agent | Multiple skills combined |
| **Instructions** | Complete CLAUDE.md | Fragments merged by AI |
| **Tools** | All tools to all personas | Two-tier authorization |
| **Reusability** | Limited (role-specific) | High (skill building blocks) |

### Migration Path

```python
# Convert existing personas to skills
def migrate_persona_to_skills(persona: Persona) -> List[Skill]:
    """Break persona into atomic skills."""

    # Example: code-writer persona becomes:
    skills = [
        Skill(
            id="code-implementation",
            name="Code Implementation",
            instructions=extract_code_impl_section(persona.claude_md),
            ...
        ),
        Skill(
            id="test-creation",
            name="Test Creation",
            instructions=extract_test_section(persona.claude_md),
            ...
        ),
        Skill(
            id="documentation",
            name="Documentation",
            instructions=extract_docs_section(persona.claude_md),
            ...
        )
    ]

    return skills
```

---

## Related Documents

- [v1.0 Architecture](../architecture/v1.0-architecture.md)
- [MCP Tools Specification](./mcp-tools.md)
- [Git Infrastructure Design](./git-infrastructure.md)
- [Persona Marketplace Specification](./persona-marketplace.md) *(legacy - being replaced)*
