# Documentation Organization Guide

## Overview

The ClaudeVN documentation is organized to separate **evergreen documentation** (always relevant) from **version-specific change documentation** (tied to releases).

## Structure

```
docs/
├── README.md                          # Documentation index (start here)
├── releases/                          # 📦 Version-specific changes
│   └── 0.1.2/                        # Current release
│       ├── CHANGELOG.md              # Release notes
│       ├── FRONTEND_INTEGRATION.md   # Feature documentation
│       └── BRANDING_CORRECTION.md    # Change details
├── design/                            # 🏗️ Architectural design
│   ├── architecture/                 # High-level architecture
│   │   ├── platform-overview.md
│   │   └── diagrams.md
│   └── specifications/               # Detailed specifications
│       ├── marketplace-spec.md
│       ├── coordinating-agents-spec.md
│       └── technical-specifications.md
├── guides/                            # 📚 User guides
│   ├── project-plan.md
│   ├── demo-scenarios.md
│   └── marketplace-scripts.md
└── development/                       # 🛠️ Developer docs
    ├── project-structure.md
    ├── marketplace-implementation-summary.md
    ├── refactoring-plan.md
    └── llm-integration.md
```

## Document Types

### 1. Release Documentation (releases/)

**Purpose:** Document changes, new features, and improvements for specific versions.

**Characteristics:**
- Version-specific
- Frozen once release is complete
- Includes changelogs and migration guides
- Lives in `releases/X.Y.Z/` folders

**Examples:**
- `releases/0.1.2/CHANGELOG.md` - What changed in 0.1.2
- `releases/0.1.2/FRONTEND_INTEGRATION.md` - How frontend integration works
- `releases/0.2.0/SERVING_IMPLEMENTATION.md` - New serving component (future)

**When to create:**
- New release with features/changes
- Major bug fixes worth documenting
- Breaking changes requiring migration

### 2. Design Documentation (design/)

**Purpose:** Describe system architecture, specifications, and design decisions.

**Characteristics:**
- Evergreen (updated in place)
- Describes current state
- Technical depth
- Reference material

**Subdirectories:**
- `architecture/` - High-level system design
- `specifications/` - Detailed component specifications

**Examples:**
- `design/architecture/platform-overview.md` - What ClaudeVN is
- `design/specifications/marketplace-spec.md` - How marketplace works
- `design/specifications/coordinating-agents-spec.md` - Agent coordination

**When to update:**
- Architecture changes
- New components added
- Design decisions made
- Specifications clarified

### 3. User Guides (guides/)

**Purpose:** Help users understand and use the system.

**Characteristics:**
- Evergreen (updated in place)
- User-focused
- Practical examples
- Step-by-step instructions

**Examples:**
- `guides/project-plan.md` - Roadmap and milestones
- `guides/demo-scenarios.md` - Example use cases
- `guides/marketplace-scripts.md` - Script usage

**When to update:**
- New features added
- Workflow changes
- User feedback incorporated
- New examples needed

### 4. Developer Documentation (development/)

**Purpose:** Help developers understand implementation and contribute.

**Characteristics:**
- Evergreen (updated in place)
- Implementation-focused
- Code organization
- Development patterns

**Examples:**
- `development/project-structure.md` - Code organization
- `development/llm-integration.md` - LLM usage patterns
- `development/refactoring-plan.md` - Refactoring strategy

**When to update:**
- Code structure changes
- New patterns established
- Development practices evolve
- Implementation details change

## Version Numbering

Following semantic versioning: `MAJOR.MINOR.PATCH`

### Version Components

**MAJOR (X.0.0)**
- Breaking changes
- Complete architectural rewrites
- API incompatibilities
- Git tag: `vX.0.0`

**MINOR (0.X.0)**
- New features
- Component implementations
- Significant enhancements
- Git tag: `v0.X.0`

**PATCH (0.0.X)**
- Bug fixes
- Small improvements
- Integrations
- Documentation updates
- Git tag: `v0.0.X`

### Current Version: 0.1.4

**History:**
- `0.1.0` - Initial marketplace implementation
- `0.1.1` - Refinements and seed data
- `0.1.2` - Frontend integration and branding correction
- `0.1.3` - User management and scope system
- `0.1.4` - Agent approval and scope system (current)

**Next:**
- `0.2.0` - Serving component implementation (planned)
- `0.3.0` - Compute engine implementation (planned)
- `1.0.0` - Complete platform with orchestration (future)

## Creating Release Documentation

### Process

1. **Create release folder:**
   ```bash
   mkdir -p docs/releases/X.Y.Z
   ```

2. **Create CHANGELOG.md:**
   ```markdown
   # Release X.Y.Z - Title
   
   ## Overview
   ## Major Changes
   ## Features Added
   ## Technical Details
   ## Upgrade Instructions
   ## Breaking Changes
   ## Known Issues
   ## What's Next
   ```

3. **Add feature documentation:**
   - Create detailed docs for major features
   - Include examples and use cases
   - Link from CHANGELOG

4. **Update VERSION file:**
   ```bash
   echo "X.Y.Z" > VERSION
   ```

5. **Create Git tag:**
   ```bash
   git tag -a vX.Y.Z -m "Release X.Y.Z: Description"
   git push origin vX.Y.Z
   ```

6. **Update main README:**
   - Update "Current Release" link
   - Add to version history if needed

## Updating Evergreen Documentation

### Process

1. **Identify document type:**
   - Design → `design/`
   - Guide → `guides/`
   - Development → `development/`

2. **Update document in place:**
   - Modify existing file
   - Keep file name consistent
   - Update last-modified date if applicable

3. **Update links:**
   - Check if other docs reference this
   - Update cross-references
   - Update docs/README.md if needed

4. **Commit changes:**
   ```bash
   git add docs/
   git commit -m "docs: update [document-name]"
   ```

## Best Practices

### Writing Release Documentation

✅ **Do:**
- Include specific version number
- List all major changes
- Provide upgrade instructions
- Document breaking changes
- Include examples and screenshots
- Link to related documents

❌ **Don't:**
- Make vague statements
- Forget migration steps
- Skip breaking changes
- Overuse technical jargon without explanation

### Writing Evergreen Documentation

✅ **Do:**
- Keep current with code
- Use clear examples
- Include diagrams where helpful
- Link to related concepts
- Update regularly

❌ **Don't:**
- Let it get out of date
- Include version-specific details
- Duplicate information
- Use outdated examples

## Document Locations Reference

### Outside docs/ Folder

Some documentation lives at the component level:

```
claudevn/
├── README.md                  # Main project overview
├── QUICK_REFERENCE.md         # Command reference
├── VERSION                    # Current version number
├── marketplace/
│   ├── README.md             # Marketplace service guide
│   ├── QUICKSTART.md         # Quick start guide
│   └── FRONTEND.md           # Frontend documentation
├── serving/
│   └── README.md             # Serving component (future)
└── compute/
    └── README.md             # Compute engine (future)
```

### Linking Between Documents

**From release docs to evergreen:**
```markdown
See [Marketplace Specification](../../design/specifications/marketplace-spec.md)
```

**From evergreen to release:**
```markdown
For latest changes, see [Release 0.1.2](../../releases/0.1.2/CHANGELOG.md)
```

**From docs/ to repo root:**
```markdown
See [Quick Reference](../QUICK_REFERENCE.md)
```

## Maintenance

### Monthly Review
- Check for outdated information
- Update examples and screenshots
- Fix broken links
- Incorporate user feedback

### Per-Release Tasks
- Create release folder and CHANGELOG
- Update VERSION file
- Create Git tag
- Update main README
- Archive old release notes (if needed)

### Annual Cleanup
- Archive very old releases (optional)
- Consolidate redundant documentation
- Refresh all examples
- Update diagrams

## Questions?

See [docs/README.md](README.md) for the complete documentation index.

---

**Documentation Organization System** - Version 0.1.4

