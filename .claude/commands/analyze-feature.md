# Analyze Feature Workflow

Deep business and technical analysis of how a feature works, with documentation output.

## Arguments
- `$ARGUMENTS` - Feature or area to analyze (e.g., `work-map`, `skill-composition`, `compute-spawning`)

## Workflow

### 1. Define Analysis Scope

Identify what the user wants to understand:

| If analyzing... | Focus on... |
|-----------------|-------------|
| `work-map` | Goal/issue tracking, dependencies, status flow |
| `skill-composition` | How skills combine, persona bundles, marketplace |
| `compute-spawning` | How Claude Code instances are launched and managed |
| `git-workflow` | Branch management, PR queue, merge process |
| `mcp-communication` | Tool definitions, compute-serving messaging |
| `frontend-state` | React state management, API integration |
| `{custom}` | User-specified feature area |

### 2. Identify Entry Points

Find where the feature starts:

**For API features:**
```bash
# Find route handlers
grep -r "router\." serving/api/ --include="*.py"
grep -r "@app\." serving/app.py
```

**For frontend features:**
```bash
# Find page components and routes
grep -r "Route" serving/frontend/src/App.jsx
ls serving/frontend/src/pages/
```

**For services:**
```bash
# Find service entry points
grep -r "def get_service" serving/services/
```

### 3. Trace Data Flow

Document how data moves through the system:

```
[Entry Point] → [Validation] → [Business Logic] → [Storage] → [Response]
```

**For each step, identify:**
- Input data structure (Pydantic model or JS object)
- Transformations applied
- Side effects (database, Redis, events)
- Output data structure

### 4. Map Component Interactions

Create a dependency map:

```markdown
## Component Map: {Feature}

### Services Involved
- `{ServiceName}` - {responsibility}
  - Depends on: {other services}
  - Used by: {consumers}

### Models Used
- `{ModelName}` - {purpose}
  - Fields: {key fields}
  - Relationships: {to other models}

### API Endpoints
- `{METHOD} {path}` - {purpose}
  - Request: {model}
  - Response: {model}

### Frontend Components
- `{ComponentName}` - {purpose}
  - State: {what it manages}
  - API calls: {endpoints used}
```

### 5. Document State Transitions

If the feature has stateful behavior:

```markdown
## State Machine: {Feature}

### States
- `{state1}` - {description}
- `{state2}` - {description}

### Transitions
- `{state1}` → `{state2}`: {trigger/condition}

### Side Effects
- On `{transition}`: {what happens}
```

### 6. Identify Business Rules

Extract the business logic:

```markdown
## Business Rules: {Feature}

### Validation Rules
1. {Rule description}
   - Enforced in: {location}
   - Error handling: {what happens on violation}

### Processing Rules
1. {Rule description}
   - Implemented in: {location}
   - Edge cases: {known edge cases}

### Authorization Rules
1. {Who can do what}
   - Enforced in: {location}
```

### 7. Find Integration Points

Document how this feature connects to others:

```markdown
## Integration Points

### Internal
- {Feature} ↔ {Other Feature}: {how they interact}

### External
- {External system}: {integration method}

### Events/Messaging
- Publishes: {events this feature emits}
- Subscribes: {events this feature listens to}
```

### 8. Generate Analysis Document

Create documentation at `docs/analysis/{feature}-analysis.md`:

```markdown
# {Feature} Analysis

**Date:** {YYYY-MM-DD}
**Analyst:** Claude Code

## Overview
{2-3 paragraph description of what this feature does and why it exists}

## Architecture

### Component Diagram
```
{ASCII diagram of components}
```

### Data Flow
{Step-by-step data flow description}

## Key Components

### {Component 1}
- **Location:** {file path}
- **Purpose:** {what it does}
- **Key methods:**
  - `{method}()` - {description}

### {Component 2}
...

## Business Logic

### Core Rules
{List of business rules}

### State Management
{State machine if applicable}

## API Reference

### Endpoints
{Table of endpoints with methods, paths, descriptions}

### Models
{Key model definitions}

## Dependencies

### Internal
{What this feature depends on}

### External
{External dependencies}

## Usage Examples

### Example 1: {Scenario}
{Code or curl example}

## Known Limitations
{Current limitations or technical debt}

## Related Documentation
- {Link to related docs}
```

### 9. Create Visual Aids (Optional)

If helpful, create diagrams:

**Sequence diagram** for request flow:
```
User → Frontend → API → Service → Database
                    ↓
              Redis Cache
```

**Component diagram** for architecture:
```
┌─────────────┐     ┌─────────────┐
│   Frontend  │────▶│     API     │
└─────────────┘     └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   Service   │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         ┌────────┐  ┌─────────┐  ┌─────────┐
         │ Redis  │  │   Git   │  │  Events │
         └────────┘  └─────────┘  └─────────┘
```

## Checklist

- [ ] Analysis scope defined
- [ ] Entry points identified
- [ ] Data flow traced end-to-end
- [ ] Component interactions mapped
- [ ] State transitions documented (if applicable)
- [ ] Business rules extracted
- [ ] Integration points identified
- [ ] Analysis document generated
- [ ] Visual aids created (if helpful)
