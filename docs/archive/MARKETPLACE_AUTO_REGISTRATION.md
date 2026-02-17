# Marketplace Auto-Registration with Serving

## Overview

The marketplace now auto-registers with the serving component on startup, similar to how compute instances work. This eliminates the need for manual UI-based registration.

## Configuration

### Environment Variables

The marketplace uses these environment variables for auto-registration:

```bash
# Required: URL of the serving component
SERVING_URL=http://localhost:8002

# Optional: Enable/disable auto-registration (default: true)
AUTO_REGISTER_WITH_SERVING=true

# Optional: Custom marketplace ID (auto-generated if not provided)
MARKETPLACE_ID=marketplace-custom

# Optional: Custom marketplace name (default: "ClaudeVN Marketplace")
MARKETPLACE_NAME=My Custom Marketplace

# Optional: Marketplace priority - lower values have higher priority (default: 1)
MARKETPLACE_PRIORITY=1

# Optional: Public-facing endpoint (if different from internal)
MARKETPLACE_PUBLIC_ENDPOINT=https://marketplace.example.com
```

### How It Works

1. **On Startup**: Marketplace reads `SERVING_URL` from environment
2. **Auto-Registration**: If `SERVING_URL` is set and `AUTO_REGISTER_WITH_SERVING=true`, marketplace automatically registers with serving
3. **Retry Logic**: If serving is not available, marketplace retries 3 times with exponential backoff (2s, 4s, 8s)
4. **Heartbeats**: After successful registration, marketplace sends periodic heartbeats (default: 60s)
5. **On Shutdown**: Marketplace automatically deregisters from serving

## Setup

### Local Development (.env file)

Add to your `.env` file:

```bash
SERVING_URL=http://localhost:8002
AUTO_REGISTER_WITH_SERVING=true
```

### Docker Compose

Already configured in `docker-compose.yml`:

```yaml
marketplace:
  environment:
    - SERVING_URL=http://serving:8002
```

### Manual Registration (Fallback)

If you need to disable auto-registration and register manually:

```bash
# Disable auto-registration
AUTO_REGISTER_WITH_SERVING=false

# Then use the UI or API:
curl -X POST http://localhost:8001/api/v1/integrations/serving/register \
  -H "Content-Type: application/json" \
  -d '{"serving_url": "http://localhost:8002"}'
```

## Verification

Check if marketplace is registered:

```bash
# Check serving's registered marketplaces
curl http://localhost:8002/api/v1/marketplaces | jq

# Check marketplace registration status
curl http://localhost:8001/api/v1/integrations/status | jq
```

## Comparison with Compute Registration

Both marketplace and compute now work the same way:

| Feature | Compute | Marketplace |
|---------|---------|-------------|
| Config Variable | `SERVING_URL` | `SERVING_URL` |
| Auto-Register | Default: true | Default: true |
| Retry Logic | ✅ Yes | ✅ Yes |
| Heartbeats | ✅ Yes | ✅ Yes |
| UI Registration | ❌ No | ✅ Optional fallback |

## Troubleshooting

### Marketplace not registering

1. Check if `SERVING_URL` is set: `echo $SERVING_URL`
2. Check marketplace logs: `tail -f marketplace/logs/marketplace.log | grep -i serv`
3. Verify serving is running: `curl http://localhost:8002/api/v1/health`

### Registration expires

If marketplace was registered but expired:
- Check if marketplace process is still running
- Check if heartbeats are being sent (logs)
- Manually re-register if needed (see Manual Registration above)

### Serving starts after marketplace

The retry logic handles this automatically. Marketplace will retry registration for up to 3 attempts with increasing delays.

## Benefits

1. **Consistency**: Same pattern as compute instances
2. **No Manual Steps**: No need to use UI for registration
3. **Resilient**: Automatic retry with exponential backoff
4. **Infrastructure-as-Code**: Fully configurable via environment variables
5. **Docker-Friendly**: Works seamlessly in containerized environments
