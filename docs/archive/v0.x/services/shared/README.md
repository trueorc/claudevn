# ClaudeVN Shared Library

Common utilities, models, and types used across all ClaudeVN components (Marketplace, Serving, Compute).

## Installation

For development (editable install):

```bash
cd shared
pip install -e .
```

For production:

```bash
pip install claudevn-shared
```

## Usage

```python
from claudevn_shared.llm_types import LLMConfig, LLMProvider, LLMResponse
from claudevn_shared.models import AgentCard, Task, ExecutionPlan
from claudevn_shared.a2a_types import TaskStatus, TaskInput
```

## Contents

- `llm_types.py` - LLM provider types and configurations
- `models.py` - Common data models (AgentCard, Task, etc.)
- `a2a_types.py` - A2A protocol types
- `config.py` - Configuration helpers
- `utils.py` - Utility functions

