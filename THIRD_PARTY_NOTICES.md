# Third-Party Notices

This document describes third-party services, software, and open source components that TrueOrc integrates with or depends upon.

## Third-Party Services

### Claude Code by Anthropic (Proprietary)

TrueOrc is designed to orchestrate Claude Code compute instances as specialized workers in a distributed AI agent system.

**Important Information:**
- Claude Code is proprietary software developed by Anthropic PBC
- Released under the Business Source License (BSL)
- TrueOrc does NOT bundle, redistribute, or modify Claude Code
- Users must obtain their own Anthropic API keys
- Users must agree to Anthropic's Commercial Terms of Service

**Links:**
- Commercial Terms: https://www.anthropic.com/legal/commercial-terms
- Claude Code Repository: https://github.com/anthropics/claude-code
- Anthropic API: https://www.anthropic.com/api

**Integration Method:**
TrueOrc spawns Claude Code CLI instances as compute workers and communicates with them via the Model Context Protocol (MCP) and Git. TrueOrc is complementary to Claude Code and extends its capabilities for multi-agent orchestration.

## Open Source Components

### Model Context Protocol (MCP) - MIT License

TrueOrc uses the Model Context Protocol for communication between compute instances (Claude Code) and the serving layer.

**License:** MIT License
**Project:** https://github.com/modelcontextprotocol/modelcontextprotocol
**Foundation:** MCP is an open standard donated to the Agentic AI Foundation under the Linux Foundation

**Usage in TrueOrc:**
- MCP server runs in the serving layer (port 8002)
- MCP client runs in Claude Code compute instances
- MCP tools enable work assignment, status updates, and inter-agent communication

**License Text:**
```
MIT License

Copyright (c) Model Context Protocol Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Dependency Licenses

### Python Dependencies

TrueOrc's Python dependencies are listed in the following files:
- `serving/requirements.txt` - Serving layer dependencies
- `marketplace/requirements.txt` - Marketplace service dependencies

Each dependency carries its own license. Users and contributors should review these dependencies and their licenses. Common licenses include:
- Apache License 2.0 (FastAPI, uvicorn, httpx, etc.)
- MIT License (many Python packages)
- BSD License (some scientific/data packages)

**Note:** Run `pip-licenses` in each environment to generate a complete dependency license report:
```bash
pip install pip-licenses
pip-licenses --format=markdown
```

### Frontend Dependencies (Node.js/npm)

TrueOrc's frontend dependencies are managed via npm and listed in:
- `serving/frontend/package.json`

Each dependency carries its own license. Users and contributors should review these dependencies and their licenses. Common licenses include:
- MIT License (React, Vite, TailwindCSS, and most npm packages)
- BSD License (some UI libraries)

**Note:** Run `npx license-checker` to generate a complete dependency license report:
```bash
cd serving/frontend
npx license-checker --summary
```

## Disclaimer

TrueOrc is an independent open source project and is not affiliated with, endorsed by, or sponsored by Anthropic PBC.

TrueOrc is designed to work WITH Claude Code as a complementary orchestration layer, not to compete against it. The project extends Claude Code's capabilities by enabling multi-agent coordination, distributed task execution, and emergent collaboration patterns.

Users of TrueOrc are responsible for:
- Obtaining their own Anthropic API keys
- Agreeing to Anthropic's terms of service
- Installing Claude Code separately
- Complying with all applicable licenses for dependencies
- Understanding the licensing terms of all third-party components

## Updates

This THIRD_PARTY_NOTICES.md file should be reviewed and updated whenever:
- New third-party services are integrated
- Major dependencies are added or changed
- Integration patterns with proprietary software change

Last updated: 2026-02-07
