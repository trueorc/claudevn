# Changelog - Version 0.1.8

## Added

### Execution Pipeline System
- Added `ExecutionPipeline` and `PipelineStep` models for structured execution plans
- Added `PipelineService` for coordinating team logic and pipeline execution
- Added pipeline API endpoints for executing business goals
- Added pipeline builder agent for automated plan creation
- Added dependency management between pipeline steps
- Added distributed execution across compute instances
- Added result aggregation and storage

### Mock LLM Provider
- Added `MockLLMProvider` for zero-cost testing
- Added context-aware response generation
- Added support for: data analysis, content generation, code review, task planning, pipeline building
- Added token estimation and usage tracking
- Added MOCK provider to LLMProvider enum

### Agent Execution
- Added `AgentExecutor` service for managing agent lifecycle
- Added agent execution API endpoints
- Added task status tracking
- Added result storage with metadata
- Added LLM integration with fallback support

### Sample Agents
- Added `data-analyst-v1` agent
- Added `task-coordinator-v1` agent
- Added `content-writer-v1` agent
- Added `pipeline-builder-v1` agent (orchestration specialist)

### Task Routing
- Added task submission API in serving
- Added automatic compute instance selection
- Added task routing with result handling
- Added demo business process endpoint

### Testing
- Added `test_mock_e2e.sh` for mock LLM testing
- Added `test_pipeline_e2e.sh` for pipeline testing
- Added comprehensive test coverage

### Utilities
- Added `cleanup_registrations.sh` for cleaning old compute registrations

### Documentation
- Added 12 comprehensive documentation files
- Added architecture specifications
- Added implementation guides
- Added quick start guides
- Organized documentation into proper structure

## Changed

- Enhanced `compute/api/agents.py` with execution endpoints
- Enhanced `compute/app.py` with agent executor initialization
- Enhanced `serving/app.py` with pipeline and task routers
- Updated `shared/claudevn_shared/llm_types.py` with additional fields
- Updated `README.md` with pipeline and mock testing sections
- Reorganized documentation from root to `docs/` folders

## Fixed

- Fixed provider registry to use decorator pattern
- Fixed compute registration cleanup

## Version

- Updated VERSION from 0.1.7 to 0.1.8

## Documentation Structure

### Root Level (Quick Reference)
- `README.md` - Main entry point
- `MOCK_TESTING_QUICKSTART.md` - Quick mock testing guide
- `README_PIPELINE.md` - Quick pipeline guide
- `WHATS_NEW.md` - What's new summary

### docs/design/architecture/
- `EXECUTION_PIPELINE_ARCHITECTURE.md` - Complete pipeline architecture
- `EXECUTION_FLOW.md` - Execution flow details

### docs/development/
- `MOCK_E2E_IMPLEMENTATION.md` - Mock implementation details
- `MOCK_E2E_SUMMARY.md` - Implementation summary
- `PIPELINE_COMPLETE.md` - Pipeline implementation complete
- `PIPELINE_PLAN.md` - Pipeline build plan

### docs/guides/
- `MOCK_E2E_GUIDE.md` - Comprehensive mock testing guide
- `EXECUTION_FLOW.md` - User-facing execution flow

## API Endpoints Added

### Pipeline Endpoints
```
POST /api/v1/pipelines/execute-from-goal
GET  /api/v1/pipelines/demo/business-process
GET  /api/v1/pipelines/health
```

### Agent Execution Endpoints
```
POST /agents/execute
GET  /agents/tasks/{task_id}
GET  /agents/tasks
```

### Task Routing Endpoints
```
POST /api/v1/tasks/submit
GET  /api/v1/tasks/{task_id}
POST /api/v1/tasks/demo/business-process
```

## Performance

- Mock LLM response time: ~0.5 seconds
- Zero API costs with mock provider
- Pipeline execution: ~2 seconds for 2-step workflow

## Testing

All tests passing:
```bash
./test_mock_e2e.sh      # Mock LLM testing
./test_pipeline_e2e.sh  # Pipeline execution testing
```

## Breaking Changes

None - all changes are backwards compatible.

## Contributors

ClaudeVN Team

