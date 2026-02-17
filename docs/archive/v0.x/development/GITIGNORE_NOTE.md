# Git Ignore Note

## Files Not Committed (Due to .gitignore)

The following essential files were created but are excluded by `.gitignore` rules:

### Coordinating Agent Definitions (compute/data/)
These JSON files define the 6 coordinating agents:
```
compute/data/compute/agents/coordinating/
├── process-mapper-agent.json
├── agent-selector-agent.json
├── activity-facilitator-agent.json
├── consistency-manager-agent.json
├── progress-reporter-agent.json
└── result-synthesizer-agent.json
```

### Data Models (serving/models/)
The process map data model:
```
serving/models/process_map.py
```

## Why They're Ignored

The `.gitignore` has:
- `data/` - Catches `compute/data/`
- `serving/models` is also ignored (likely to exclude DB models or generated code)

## Recommendation

These files are **application code**, not runtime data or config. Consider either:

1. **Update .gitignore** to allow these specific paths:
   ```
   # In .gitignore, add exceptions:
   !compute/data/compute/agents/**/*.json
   !serving/models/process_map.py
   ```

2. **Move agent definitions** to a non-data directory:
   ```
   compute/agents/coordinating/  (instead of compute/data/...)
   ```

3. **Force add** if you're certain they're safe:
   ```bash
   git add -f compute/data/compute/agents/coordinating/*.json
   git add -f serving/models/process_map.py
   git commit -m "Add coordinating agent definitions and process map model"
   git push
   ```

## Current Status

✅ **Committed & Pushed:**
- All documentation
- All API endpoints
- All services
- All frontend UI

❌ **Not Committed:**
- Agent definitions (6 JSON files)
- Process map model (Python)

**Impact:** The system won't work without these files. They need to be either:
- Added to the repository (see options above)
- Deployed separately (not recommended for definitions)
- Generated at runtime (not applicable for these files)

## Next Steps

Choose one of the options above to include these essential files in version control.

