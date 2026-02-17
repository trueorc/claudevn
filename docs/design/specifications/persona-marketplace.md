# Persona Marketplace Specification

> **⚠️ DEPRECATED**: This specification has been superseded by the [Skill Marketplace Specification](./skill-marketplace.md).
>
> ClaudeVN v1.0 uses **Skills** (atomic capability units) instead of **Personas** (complete role definitions).
> Skills are composed by Serving's Claude Code instance into Agent bundles deployed to compute instances.
>
> See [Skill Marketplace Specification](./skill-marketplace.md) for the current design.

---

## Migration Notes

| Persona Concept | Skill Equivalent |
|-----------------|------------------|
| Persona (complete role) | Agent (composed from multiple skills) |
| Persona CLAUDE.md | Skill instructions (CLAUDE.md fragment) |
| Persona selection | Skill selection + composition |
| `/api/v1/personas` | `/api/v1/skills` |

## Related Documents

- [Skill Marketplace Specification](./skill-marketplace.md) - Current specification
- [v1.0 Architecture](../architecture/v1.0-architecture.md) - System architecture
- [MCP Tools Specification](./mcp-tools.md) - MCP tool specifications
