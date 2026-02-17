# Audit Feature Workflow

Review a feature area for gaps, inconsistencies, and improvement opportunities with deep analysis and documentation.

## Arguments
- `$ARGUMENTS` - Feature area to audit (e.g., `work-map`, `authentication`, `frontend`, `mcp-tools`)

## Workflow

### 1. Define Audit Scope

Map the argument to relevant directories and components:

| Area | Directories | Focus |
|------|-------------|-------|
| `serving` | `serving/` | API routes, services, models |
| `frontend` | `serving/frontend/src/` | Components, hooks, state |
| `marketplace` | `marketplace/` | Skills, personas, registry |
| `compute` | `compute/` | Runtime, MCP client |
| `git` | `serving/git/` | SSH, hooks, PR management |
| `mcp` | `serving/mcp/` | Tools, server, models |
| `work-map` | `serving/services/work_map*`, `serving/api/work_map*` | Coordination logic |
| `{custom}` | Search codebase | User-specified feature |

### 2. Inventory Existing Code

**Discover all related files:**
```bash
# Find Python files
find {directories} -name "*.py" -type f

# Find JS/JSX files
find {directories} -name "*.js" -o -name "*.jsx" -type f

# Find test files
find {directories} -name "test_*.py" -o -name "*.test.js" -type f
```

**Document the inventory:**
- Source files with line counts
- Test files with coverage areas
- Config files
- Documentation files

### 3. Analyze Code Quality

**For Python code, check:**
- [ ] Pydantic v2 patterns (`model_config` not `class Config`)
- [ ] Timezone-aware datetimes (`datetime.now(timezone.utc)`)
- [ ] Type hints on function signatures
- [ ] Docstrings on modules, classes, public methods
- [ ] Service layer pattern (business logic not in routes)
- [ ] Singleton pattern for services (`get_service()`, `set_service()`)
- [ ] Async/await consistency

**For React/JS code, check:**
- [ ] Functional components with hooks
- [ ] CSS co-located with components
- [ ] Custom hooks for data fetching
- [ ] Proper error handling
- [ ] Loading states
- [ ] API client abstraction

### 4. Analyze Test Coverage

**Identify gaps:**
```bash
# Python coverage
pytest {directories}/tests/ --cov={module} --cov-report=term-missing

# JS coverage
cd serving/frontend && npm test -- --coverage --collectCoverageFrom="{pattern}"
```

**Check for:**
- [ ] Unit tests exist for each service/component
- [ ] Edge cases covered
- [ ] Error paths tested
- [ ] Async operations tested
- [ ] Mocking done correctly

### 5. Check Documentation

**Review existing docs:**
- API endpoints documented?
- Architecture decisions recorded?
- Setup/usage guides current?
- Code comments where needed?

**Cross-reference with:**
- `docs/design/architecture/`
- `docs/design/specifications/`
- `docs/guides/`
- Component-level READMEs

### 6. Identify Gaps

Create a structured gap analysis:

```markdown
## Gap Analysis: {Feature Area}

### Missing Functionality
1. {Description of missing feature}
   - Impact: {High/Medium/Low}
   - Suggested fix: {Brief approach}

### Code Quality Issues
1. {Issue description}
   - Location: {file:line}
   - Pattern violation: {Which pattern}

### Test Gaps
1. {Untested scenario}
   - Risk: {What could break}
   - Suggested test: {Test description}

### Documentation Gaps
1. {Missing documentation}
   - Type: {API/Architecture/Guide}
   - Suggested content: {Brief outline}
```

### 7. Prioritize Findings

Categorize by severity:

**P0 - Critical:**
- Security vulnerabilities
- Data loss risks
- Breaking functionality

**P1 - High:**
- Missing core tests
- Significant pattern violations
- Incomplete features

**P2 - Medium:**
- Code quality issues
- Minor test gaps
- Documentation updates

**P3 - Low:**
- Style inconsistencies
- Nice-to-have improvements
- Refactoring opportunities

### 8. Generate Report

Create audit report at `docs/audits/{feature-area}-audit-{date}.md`:

```markdown
# {Feature Area} Audit Report

**Date:** {YYYY-MM-DD}
**Auditor:** Claude Code
**Scope:** {Directories audited}

## Executive Summary
{2-3 sentence overview of findings}

## Inventory
{List of files reviewed}

## Findings

### Critical (P0)
{List or "None found"}

### High Priority (P1)
{List with details}

### Medium Priority (P2)
{List with details}

### Low Priority (P3)
{List with details}

## Recommendations
1. {Actionable recommendation}
2. {Actionable recommendation}

## Suggested Issues
{Draft issue titles for significant findings}
```

### 9. Create Follow-up Issues (Optional)

For significant findings, create GitHub issues:

```bash
gh issue create \
  --title "[P{X}] {Finding from audit}" \
  --label "{type},{priority},{area}" \
  --body "{Details from audit}"
```

## Checklist

- [ ] Audit scope defined
- [ ] All relevant files inventoried
- [ ] Code quality analyzed against patterns
- [ ] Test coverage gaps identified
- [ ] Documentation reviewed
- [ ] Gaps categorized by priority
- [ ] Audit report generated
- [ ] Follow-up issues created (if needed)
