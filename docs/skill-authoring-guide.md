# Skill Authoring Guide

Skills are atomic capability units in ClaudeVN that define what an agent can do. They are YAML files stored in the marketplace service and composed together to create specialized agents for compute instances.

## Quick Start

Skills live in `marketplace/skills/`:
- `system/` - Built-in skills (19 total)
- `user/` - Custom user-created skills (Git-backed with version history)

When a task arrives at the serving layer, it selects appropriate skills based on task requirements, merges their instructions into a single CLAUDE.md file, and sends the composed agent to a compute instance via MCP.

## YAML Format Reference

Every skill is a YAML file with the following structure:

```yaml
id: skill-identifier
name: Human-Readable Name
description: One-line description of what this skill does
version: "1.0.0"
author: system

instructions: |
  # Skill Name

  ## Role
  What this agent does (core purpose)

  ## Working Style
  - How it approaches problems
  - Key principles and preferences

  ## Approach
  1. Step-by-step workflow
  2. Process to follow

  ## Before Submission
  Checklist before completing work

specialized_tools: []

tags:
  - primary-domain
  - specific-capability

conflicts_with: []

constraints:
  - Rule or limitation the agent must follow

dependencies: []
```

### Field Reference

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `id` | yes | string | Unique identifier (lowercase, hyphens only) |
| `name` | yes | string | Display name for UI |
| `description` | yes | string | One-line summary of skill purpose |
| `version` | yes | string | Semver version (e.g., "1.0.0") |
| `author` | yes | string | "system" or "user:username" |
| `instructions` | yes | string | CLAUDE.md fragment (markdown instructions) |
| `specialized_tools` | no | array | Tool IDs this skill grants access to |
| `tags` | yes | array | Discovery tags for matching skills to tasks |
| `conflicts_with` | no | array | Skill IDs incompatible with this one |
| `constraints` | no | array | Rules the agent must follow |
| `dependencies` | no | array | Skill IDs required for this skill to work |

## Writing Effective Instructions

The `instructions` field is markdown that becomes part of the composed agent's system instructions. Structure it for clarity:

### 1. Role Section
Define what the agent does:

```markdown
## Role
You implement features and write production-quality code. Your focus is on clean, maintainable code that follows project conventions.
```

### 2. Working Style Section
Describe approach and principles:

```markdown
## Working Style
- Read and understand existing code patterns before writing new code
- Follow established project conventions strictly
- Write clean, readable code with meaningful names
- Keep changes focused and minimal
```

### 3. Approach Section
Step-by-step workflow:

```markdown
## Approach
1. Understand the requirement fully before coding
2. Explore related code to understand patterns
3. Make minimal, focused changes
4. Verify changes work as expected
5. Clean up any debug code before finishing
```

### 4. Before Submission Section
Checklist before task completion:

```markdown
## Before Submission
Before pushing your branch and completing the task:

1. **Run tests**: Execute the test suite and ensure all tests pass
2. **Check code quality**: Run linters and formatters
3. **Request code review**: Use `claudevn_request_review()` to signal your branch is ready
4. **Address review feedback**: Make requested changes and push updates

Only after passing code review should you call `claudevn_complete_task()`.
```

## Skill Discovery via Tags

Tags determine when a skill gets selected for a task. The skill registry performs multi-tier matching:

1. **Exact match** (10 points): Tag exactly matches capability
2. **Partial match** (5 points): Tag is substring of capability or vice versa
3. **Token match** (2 points per word): Word overlap between tag and capability

### Tag Best Practices

- Use lowercase with hyphens: `api-integration`, `bug-fix`
- Include primary domain: `coding`, `testing`, `documentation`, `deployment`
- Include specific capabilities: `unit-tests`, `security-audit`, `database-migration`
- Skills can have multiple tags for broader matching

Example from `code-writer.yaml`:

```yaml
tags:
  - coding
  - implementation
  - feature-development
  - bug-fix
```

## Specialized Tools

Some skills require tools beyond the global set (read, write, edit, bash, glob, grep). Specialized tools use two-tier authorization:

1. **Skill grants intent**: Agent has permission to use the tool
2. **Compute provides capability**: Compute instance has the tool installed

### Available Specialized Tools

Defined in `marketplace/tools/specialized.yaml`:

| Tool ID | Purpose | Required Labels | Security Level |
|---------|---------|-----------------|----------------|
| `db_migration_tool` | Database schema migrations | `database-admin` | elevated |
| `deploy_prod` | Production deployment | `production-access` | admin |
| `run_security_scan` | Security vulnerability scans | `security-tools` | elevated |
| `test_api_endpoint` | HTTP API endpoint testing | `api-testing` | standard |

### Granting Tool Access

Add tool IDs to `specialized_tools` array:

```yaml
specialized_tools:
  - test_api_endpoint
```

The compute instance must have matching labels for the tool to be available:

```yaml
# Compute instance configuration
labels:
  - api-testing  # Matches test_api_endpoint required_labels
```

## Skill Composition

Multiple skills can be composed together to create specialized agents. The system merges their instructions in order.

### Conflicts

Use `conflicts_with` to prevent incompatible skills from being composed:

```yaml
conflicts_with:
  - manual-deployment  # Cannot coexist with auto-deployment skill
```

### Dependencies

Use `dependencies` to require other skills:

```yaml
dependencies:
  - test-creation  # Requires test-creation skill for full functionality
```

## Tutorial: Create a Custom Skill

Let's create a "react-component-builder" skill step-by-step.

### Step 1: Choose a Unique ID

IDs must be:
- Lowercase letters
- Hyphens for word separation
- Descriptive of the capability

```yaml
id: react-component-builder
```

### Step 2: Add Metadata

```yaml
name: React Component Builder
description: Creates React components following best practices for composition, hooks, and TypeScript.
version: "1.0.0"
author: user:myteam
```

### Step 3: Write Instructions

Focus on one atomic capability. Structure with Role, Working Style, Approach, and Before Submission:

```yaml
instructions: |
  # React Component Builder

  ## Role
  You create React components following modern best practices. Focus on functional components, hooks, TypeScript types, and composition patterns.

  ## Working Style
  - Prefer functional components over class components
  - Use TypeScript for all component props and state
  - Follow React hooks rules strictly
  - Keep components small and composable
  - Separate logic into custom hooks when appropriate

  ## Component Structure
  1. **Props Interface**: Define TypeScript interface at top
  2. **Component Function**: Functional component with destructured props
  3. **Hooks**: useState, useEffect, custom hooks in order
  4. **Handlers**: Event handlers and callbacks
  5. **Render**: JSX return statement

  ## Best Practices
  - Name components with PascalCase
  - Destructure props in function signature
  - Use meaningful prop and state names
  - Extract complex logic into custom hooks
  - Memoize expensive computations with useMemo
  - Optimize re-renders with useCallback for callbacks

  ## Example Pattern
  ```typescript
  interface ButtonProps {
    label: string;
    onClick: () => void;
    variant?: 'primary' | 'secondary';
    disabled?: boolean;
  }

  export function Button({
    label,
    onClick,
    variant = 'primary',
    disabled = false
  }: ButtonProps) {
    const className = `btn btn-${variant}`;

    return (
      <button
        className={className}
        onClick={onClick}
        disabled={disabled}
      >
        {label}
      </button>
    );
  }
  ```

  ## Before Submission
  Before pushing your branch:

  1. **Verify TypeScript**: Ensure no type errors
  2. **Check component tests**: Write or update tests for the component
  3. **Review accessibility**: Add ARIA labels where needed
  4. **Request code review**: Use `claudevn_request_review()`

  Only after passing review should you call `claudevn_complete_task()`.
```

### Step 4: Add Tags for Discovery

Think about when this skill should be selected:

```yaml
tags:
  - react
  - frontend
  - component
  - typescript
  - ui
```

Now tasks requiring "react component" or "frontend ui" will match this skill.

### Step 5: Set Constraints

Add guardrails:

```yaml
constraints:
  - Use functional components only (no class components)
  - All components must have TypeScript types
  - Follow project naming conventions
  - Do not add external dependencies without approval
```

### Step 6: Declare Dependencies (Optional)

If this skill requires others:

```yaml
dependencies:
  - test-creation  # Needs test-creation for component testing
```

### Step 7: Complete File

Here's the full skill:

```yaml
id: react-component-builder
name: React Component Builder
description: Creates React components following best practices for composition, hooks, and TypeScript.
version: "1.0.0"
author: user:myteam

instructions: |
  # React Component Builder

  ## Role
  You create React components following modern best practices. Focus on functional components, hooks, TypeScript types, and composition patterns.

  ## Working Style
  - Prefer functional components over class components
  - Use TypeScript for all component props and state
  - Follow React hooks rules strictly
  - Keep components small and composable
  - Separate logic into custom hooks when appropriate

  ## Component Structure
  1. **Props Interface**: Define TypeScript interface at top
  2. **Component Function**: Functional component with destructured props
  3. **Hooks**: useState, useEffect, custom hooks in order
  4. **Handlers**: Event handlers and callbacks
  5. **Render**: JSX return statement

  ## Best Practices
  - Name components with PascalCase
  - Destructure props in function signature
  - Use meaningful prop and state names
  - Extract complex logic into custom hooks
  - Memoize expensive computations with useMemo
  - Optimize re-renders with useCallback for callbacks

  ## Before Submission
  Before pushing your branch:

  1. **Verify TypeScript**: Ensure no type errors
  2. **Check component tests**: Write or update tests for the component
  3. **Review accessibility**: Add ARIA labels where needed
  4. **Request code review**: Use `claudevn_request_review()`

  Only after passing review should you call `claudevn_complete_task()`.

specialized_tools: []

tags:
  - react
  - frontend
  - component
  - typescript
  - ui

conflicts_with: []

dependencies:
  - test-creation

constraints:
  - Use functional components only (no class components)
  - All components must have TypeScript types
  - Follow project naming conventions
  - Do not add external dependencies without approval
```

### Step 8: Save to Marketplace

Save as `marketplace/skills/user/react-component-builder.yaml`. The marketplace service will:

1. Detect the new file on next load
2. Parse and validate the YAML
3. Register it in the skill catalog
4. Make it available for task matching

User skills are Git-backed, so the file is automatically committed with version history.

## Creating Skills via API

You can also create skills programmatically using the marketplace API:

```bash
curl -X POST http://localhost:8003/api/skills \
  -H "Content-Type: application/json" \
  -d '{
    "id": "react-component-builder",
    "name": "React Component Builder",
    "description": "Creates React components following best practices",
    "version": "1.0.0",
    "instructions": "# React Component Builder\n...",
    "tags": ["react", "frontend", "component"],
    "specialized_tools": [],
    "conflicts_with": [],
    "dependencies": ["test-creation"],
    "constraints": [
      "Use functional components only",
      "All components must have TypeScript types"
    ]
  }'
```

The API will:
- Validate the request
- Create the YAML file
- Commit to Git with message: "create: react-component-builder v1.0.0 - Initial version"
- Return the created skill

## Updating Skills

To update a skill, modify the YAML file or use the API:

```bash
curl -X PATCH http://localhost:8003/api/skills/react-component-builder \
  -H "Content-Type: application/json" \
  -d '{
    "version": "1.1.0",
    "instructions": "# Updated instructions...",
    "changelog": "Added support for React 19 features"
  }'
```

When a skill is updated:
- Version is bumped in the YAML file
- Git commit created with changelog message
- Any personas using this skill are marked stale
- Stale personas regenerate merged_instructions on next use

## Version History

User skills maintain full version history via Git:

```bash
# List all versions
curl http://localhost:8003/api/skills/react-component-builder/versions

# Get specific version
curl http://localhost:8003/api/skills/react-component-builder/versions/1.0.0
```

Each commit includes:
- Skill content at that version
- Commit timestamp
- Changelog message
- Author information

## System Skills vs User Skills

| Aspect | System Skills | User Skills |
|--------|---------------|-------------|
| Location | `marketplace/skills/system/` | `marketplace/skills/user/` |
| Author | `system` | `user:username` |
| Storage | Local filesystem (read-only) | Git repository (versioned) |
| Editing | Via code changes | Via API or file edits |
| Deletion | Not allowed | Allowed via API |
| Version History | No Git history | Full Git history |
| Marketplace Tier | ROOT | USER (or inherited) |

## Skill Selection Process

When a task arrives:

1. **Parse task requirements**: Extract required capabilities from task description
2. **Search skills by capabilities**: Find skills with matching tags
3. **Score and rank**: Calculate match scores (exact > partial > token match)
4. **Resolve conflicts**: Remove conflicting skill pairs
5. **Include dependencies**: Add required dependency skills
6. **Compose instructions**: Merge skill instructions into single CLAUDE.md
7. **Assign to compute**: Send composed agent to compute instance via MCP

## Best Practices

### Keep Skills Atomic

Each skill should do one thing well. Instead of:

```yaml
id: full-stack-developer  # Too broad!
```

Create separate skills:

```yaml
id: api-endpoint-builder  # Focused on backend APIs
id: react-component-builder  # Focused on React UI
```

### Write Clear Instructions

- Use concrete examples in instructions
- Provide step-by-step workflows
- Include "Before Submission" checklists
- Keep language clear and action-oriented

### Tag Thoughtfully

- Primary domain: `coding`, `testing`, `documentation`
- Technology: `react`, `python`, `docker`
- Capability: `bug-fix`, `refactoring`, `migration`
- Level: `beginner-friendly`, `advanced`

### Version Semantically

Follow semver:
- **1.0.0 → 1.0.1**: Bug fix in instructions
- **1.0.0 → 1.1.0**: Add new capability or section
- **1.0.0 → 2.0.0**: Breaking change (incompatible with previous version)

### Test Before Publishing

1. Create the skill YAML
2. Test composition with other skills
3. Verify no conflicts with common skills
4. Test tag matching with sample task requirements
5. Validate specialized tools work on compute instances

## Troubleshooting

### Skill Not Being Selected

Check:
- Are tags too specific? Add more general tags
- Is skill marked in conflicts_with? Review conflict list
- Are dependencies missing? Ensure dependent skills exist
- Tag spelling matches task requirements

### Composition Conflicts

If skills conflict when composed:
- Add to `conflicts_with` array in both skills
- Or redesign skills to be more focused/atomic

### Tool Not Available

If specialized tool fails:
- Verify skill grants tool in `specialized_tools`
- Check compute instance has required labels
- Confirm tool exists in `marketplace/tools/specialized.yaml`

### Git History Issues

User skills use Git storage:
- Check Git repository is initialized
- Verify permissions on Git storage path
- Review commit messages for changelog tracking

## Examples from System Skills

Study existing system skills for patterns:

- **code-writer.yaml**: General-purpose coding with quality checklist
- **test-automator.yaml**: Testing workflow and best practices
- **api-integration.yaml**: API client patterns and error handling
- **security-audit.yaml**: Structured audit process with risk classification
- **doc-writer.yaml**: Documentation types and quality standards

All system skills follow the same structure and can serve as templates for custom skills.

## Next Steps

1. **Browse system skills**: Read `marketplace/skills/system/*.yaml` for examples
2. **Create your first skill**: Follow the tutorial above
3. **Test composition**: Use marketplace API to compose skills and see merged output
4. **Iterate**: Update based on how well agents perform with your skill
5. **Share**: User skills are stored in Git for team collaboration

For more information:
- Architecture: `docs/design/specifications/skill-marketplace.md`
- API Reference: `docs/api/marketplace-api.md`
- Persona Composition: `docs/design/specifications/persona-composition.md`
