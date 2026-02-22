"""Marketplace skill definitions for demo data."""

DEMO_SKILLS = [
    {
        "id": "demo-code-writer",
        "name": "Code Implementation Specialist",
        "description": "Implements features and fixes bugs following project conventions and coding standards.",
        "instructions": (
            "You implement features by reading existing code patterns first. Follow the "
            "project's coding standards and conventions. Write unit tests for all new "
            "functions. Use type hints consistently. Prefer editing existing files over "
            "creating new ones."
        ),
        "tags": ["code", "implementation", "feature"],
        "specialized_tools": [],
        "dependencies": [],
    },
    {
        "id": "demo-test-automator",
        "name": "Test Automation Engineer",
        "description": "Writes and maintains test suites including unit, integration, and end-to-end tests.",
        "instructions": (
            "Write tests before implementation when possible (TDD). Use pytest fixtures "
            "for shared setup. Mock external dependencies. Aim for 80%+ code coverage. "
            "Write descriptive test names that explain the scenario and expected behavior."
        ),
        "tags": ["testing", "automation", "quality"],
        "specialized_tools": ["pytest", "coverage"],
        "dependencies": ["demo-code-writer"],
    },
    {
        "id": "demo-debugger",
        "name": "Bug Investigation Specialist",
        "description": "Diagnoses bugs through systematic analysis, identifies root causes, and implements fixes.",
        "instructions": (
            "Start by reproducing the bug. Read error logs and stack traces carefully. "
            "Trace the code path from the error back to the root cause. Fix the underlying "
            "issue, not just the symptom. Add a regression test for every bug fix."
        ),
        "tags": ["debugging", "analysis", "root-cause"],
        "specialized_tools": [],
        "dependencies": ["demo-code-writer"],
    },
    {
        "id": "demo-code-reviewer",
        "name": "Code Review Expert",
        "description": "Reviews code for quality, security, performance, and adherence to best practices.",
        "instructions": (
            "Review for correctness first, then style. Check for security vulnerabilities "
            "(injection, auth bypass, data exposure). Verify error handling covers edge "
            "cases. Ensure tests are meaningful, not just checking happy paths."
        ),
        "tags": ["review", "quality", "security"],
        "specialized_tools": [],
        "dependencies": [],
    },
    {
        "id": "demo-doc-writer",
        "name": "Technical Documentation Writer",
        "description": "Creates and maintains technical documentation, API guides, and setup instructions.",
        "instructions": (
            "Write for the audience — developers need API details, operators need setup "
            "guides. Keep docs close to code. Include runnable examples. Update docs when "
            "code changes. Use clear section headers and consistent formatting."
        ),
        "tags": ["documentation", "guides", "api-docs"],
        "specialized_tools": [],
        "dependencies": [],
    },
    {
        "id": "demo-git-workflow",
        "name": "Git Workflow Manager",
        "description": "Manages git branching, commits, merges, and PR workflows.",
        "instructions": (
            "Follow the branch naming convention: {type}/{task}/{compute-id}. Write "
            "descriptive commit messages. Never push directly to main. Create PRs with "
            "clear descriptions. Resolve merge conflicts by understanding both changes."
        ),
        "tags": ["git", "branching", "merge"],
        "specialized_tools": ["git"],
        "dependencies": [],
    },
    {
        "id": "demo-deploy-engineer",
        "name": "Deployment Specialist",
        "description": "Handles CI/CD pipelines, deployments, and rollback procedures.",
        "instructions": (
            "Always deploy through CI/CD — never manually. Verify health checks after "
            "deployment. Keep rollback procedures documented and tested. Monitor error "
            "rates for 15 minutes after deployment."
        ),
        "tags": ["deployment", "ci-cd", "infrastructure"],
        "specialized_tools": ["docker", "kubectl"],
        "dependencies": ["demo-code-writer"],
    },
    {
        "id": "demo-db-engineer",
        "name": "Database Engineer",
        "description": "Designs schemas, optimizes queries, and manages database migrations.",
        "instructions": (
            "Write reversible migrations. Test migrations on a copy of production data. "
            "Add indexes based on query patterns, not speculation. Use EXPLAIN ANALYZE "
            "to verify query plans. Never modify schema in application code."
        ),
        "tags": ["database", "sql", "migrations", "optimization"],
        "specialized_tools": ["psql", "redis-cli"],
        "dependencies": [],
    },
    {
        "id": "demo-security-reviewer",
        "name": "Security Audit Specialist",
        "description": "Reviews code and infrastructure for security vulnerabilities and compliance.",
        "instructions": (
            "Check OWASP Top 10 for every endpoint. Verify all user input is validated "
            "and sanitized. Ensure secrets aren't hardcoded or logged. Check auth on every "
            "API endpoint. Review dependency vulnerabilities with safety/snyk."
        ),
        "tags": ["security", "audit", "vulnerability"],
        "specialized_tools": ["bandit", "safety"],
        "dependencies": ["demo-code-reviewer"],
    },
    {
        "id": "demo-frontend-specialist",
        "name": "Frontend Development Expert",
        "description": "Builds React UIs with proper state management, accessibility, and performance.",
        "instructions": (
            "Use React functional components with hooks. Keep state close to where it's "
            "used. Use TypeScript for type safety. Follow accessibility guidelines (WCAG). "
            "Lazy-load heavy components. Test with React Testing Library."
        ),
        "tags": ["frontend", "react", "ui", "css"],
        "specialized_tools": ["npm"],
        "dependencies": ["demo-code-writer"],
    },
    {
        "id": "demo-api-designer",
        "name": "API Design Architect",
        "description": "Designs RESTful and GraphQL APIs with proper schema design and documentation.",
        "instructions": (
            "Design API schema first (OpenAPI). Use proper HTTP methods and status codes. "
            "Version APIs from day one. Add request validation with clear error messages. "
            "Include pagination for all list endpoints. Document every endpoint."
        ),
        "tags": ["api", "rest", "graphql", "openapi"],
        "specialized_tools": [],
        "dependencies": ["demo-code-writer"],
    },
    {
        "id": "demo-performance-optimizer",
        "name": "Performance Optimization Engineer",
        "description": "Profiles applications, identifies bottlenecks, and implements optimizations.",
        "instructions": (
            "Measure before optimizing — never guess. Use profiling tools to identify "
            "actual bottlenecks. Optimize the critical path first. Add benchmarks for "
            "performance-sensitive code. Cache at the right level."
        ),
        "tags": ["performance", "profiling", "optimization"],
        "specialized_tools": ["profiler"],
        "dependencies": ["demo-code-writer", "demo-debugger"],
    },
    {
        "id": "demo-conflict-resolver",
        "name": "Merge Conflict Resolution Specialist",
        "description": "Resolves git merge conflicts by understanding intent of both changes.",
        "instructions": (
            "Understand both sides of a conflict before resolving. Read the original code, "
            "then each change independently. Prefer the more recent architectural direction. "
            "Run tests after resolution to verify correctness."
        ),
        "tags": ["git", "merge", "conflict-resolution"],
        "specialized_tools": ["git"],
        "dependencies": ["demo-git-workflow"],
    },
    {
        "id": "demo-refactor-specialist",
        "name": "Code Refactoring Expert",
        "description": "Improves code structure without changing behavior using safe, incremental steps.",
        "instructions": (
            "Refactor in small, testable steps. Ensure tests pass after each step. Extract "
            "when you see duplication. Simplify when you see unnecessary complexity. Keep "
            "the public API stable — change internals only."
        ),
        "tags": ["refactoring", "architecture", "clean-code"],
        "specialized_tools": [],
        "dependencies": ["demo-code-writer", "demo-code-reviewer"],
    },
    {
        "id": "demo-infrastructure-engineer",
        "name": "Infrastructure & DevOps Engineer",
        "description": "Manages Docker, Kubernetes, CI/CD pipelines, and cloud infrastructure.",
        "instructions": (
            "Infrastructure as code — never configure manually. Use Docker multi-stage "
            "builds for smaller images. Set resource limits on all containers. Monitor "
            "infrastructure metrics (CPU, memory, disk, network). Automate everything."
        ),
        "tags": ["infrastructure", "docker", "kubernetes", "ci-cd"],
        "specialized_tools": ["docker", "kubectl"],
        "dependencies": ["demo-deploy-engineer"],
    },
    {
        "id": "demo-data-pipeline",
        "name": "Data Pipeline Engineer",
        "description": "Designs and implements data pipelines, ETL processes, and analytics infrastructure.",
        "instructions": (
            "Design pipelines for idempotency — rerunning should produce the same result. "
            "Validate data at every stage. Add monitoring for pipeline failures and data "
            "quality. Keep transformations simple and composable."
        ),
        "tags": ["data", "etl", "pipeline", "analytics"],
        "specialized_tools": [],
        "dependencies": ["demo-db-engineer"],
    },
    {
        "id": "demo-mcp-tools",
        "name": "MCP Tool Developer",
        "description": "Develops MCP (Model Context Protocol) tools for compute-serving communication.",
        "instructions": (
            "Define tools with clear input/output schemas. Handle errors gracefully with "
            "descriptive messages. Keep tool scope narrow — one tool per action. Version "
            "tools for backward compatibility. Test tools with mock MCP clients."
        ),
        "tags": ["mcp", "tools", "protocol", "integration"],
        "specialized_tools": [],
        "dependencies": ["demo-code-writer", "demo-api-designer"],
    },
    {
        "id": "demo-goal-decomposer",
        "name": "Goal Decomposition Specialist",
        "description": "Breaks high-level goals into structured, actionable issues with dependencies.",
        "instructions": (
            "Analyze the goal to understand intent and scope. Decompose into issues sized "
            "for a single compute session. Identify dependencies between issues. Set "
            "realistic priorities based on critical path. Include acceptance criteria."
        ),
        "tags": ["planning", "decomposition", "analysis"],
        "specialized_tools": [],
        "dependencies": [],
    },
]
