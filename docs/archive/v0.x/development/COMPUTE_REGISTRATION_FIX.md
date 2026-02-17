# Compute Registration Fix

## Issue Summary

When using `start_all.sh` to start services locally, the compute module would fail to register with the serving module, even though it worked correctly in Docker deployments.

### Root Cause

The issue occurred when restarting services:

1. **Persistent State**: The serving component persists registered compute instances to disk
2. **Duplicate Registration**: On restart, the compute instance attempts to register with the same `instance_id`
3. **Registration Rejection**: The serving component rejects the registration with HTTP 400 "Instance already registered"
4. **Standalone Mode**: The compute instance falls back to standalone mode and never sends heartbeats
5. **Offline Status**: The serving component marks the instance as offline due to lack of heartbeats

### Why Docker Worked

In Docker deployments:
- Services have clean starts with proper dependency ordering (`depends_on: serving`)
- The startup timing ensures serving is ready before compute tries to register
- Or the instance IDs might differ due to containerized hostnames

## Solution

### Fix 1: Graceful Re-registration in Compute Client

Modified `/compute/services/registration_client.py` to:

1. **Detect "Already Registered" Errors**: When registration fails with HTTP 400 and the error message contains "already registered"
2. **Force Deregister**: Call `deregister(force=True)` to remove the stale registration
3. **Re-register**: Attempt registration again after successful deregistration

Key changes:
- Added `force` parameter to `deregister()` method to bypass local registration check
- Handle HTTP 404 responses in deregister (instance already removed)
- Detect and handle "already registered" errors with automatic retry logic

### Fix 2: Cleanup Script

Created `/scripts/cleanup_compute_registrations.sh` to manually remove stale registrations when needed.

Usage:
```bash
./scripts/cleanup_compute_registrations.sh
```

This script:
- Lists all registered compute instances
- Shows their current status (online/offline)
- Allows manual cleanup of all registrations

## Verification

After the fix, the compute module successfully:

1. Detects existing registration: `Instance already registered`
2. Deregisters: `Successfully deregistered from serving component`
3. Re-registers: `Successfully re-registered with serving component`
4. Starts heartbeats: `Starting heartbeat task (interval: 30s)`
5. Maintains online status: `Status: online`

Example log output:
```
2025-11-24 12:05:25,850 - services.registration_client - WARNING - Instance compute-Matthews-MacBook-Air.local-8003 already registered. Attempting to deregister and re-register...
2025-11-24 12:05:25,858 - services.registration_client - INFO - Successfully deregistered from serving component
2025-11-24 12:05:26,862 - services.registration_client - INFO - Successfully re-registered with serving component at http://localhost:8002
2025-11-24 12:05:26,863 - services.registration_client - INFO - Starting heartbeat task (interval: 30s)
```

## Testing

To verify the fix works:

1. Start all services:
   ```bash
   ./start_all.sh
   ```

2. Check compute registration status:
   ```bash
   curl http://localhost:8002/api/v1/compute
   ```

3. Stop and restart compute:
   ```bash
   pkill -f "python3 main.py"
   cd compute && python3 main.py
   ```

4. Verify it re-registers automatically and maintains online status

## Future Improvements

Potential enhancements:
1. Add configurable retry logic with exponential backoff
2. Implement registration tokens/authentication
3. Add instance version checking to handle upgrades
4. Improve serving component to allow controlled re-registration (update instead of replace)

## Related Files

- `/compute/services/registration_client.py` - Client-side registration logic
- `/serving/services/registry_service.py` - Server-side registry management
- `/serving/api/compute.py` - Registration API endpoints
- `/scripts/cleanup_compute_registrations.sh` - Manual cleanup utility

