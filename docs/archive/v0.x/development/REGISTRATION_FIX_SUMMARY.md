# Compute Registration Fix - Summary

## Problem

When running `start_all.sh`, compute instances would fail to register with the serving component and appear as "offline", even though Docker deployments worked correctly.

## Root Cause

The serving component persists registered compute instances to disk. When services were restarted:

1. Compute tried to register with the same `instance_id`
2. Serving rejected it: `400 Bad Request - Instance already registered`
3. Compute fell back to standalone mode (no heartbeats)
4. Serving marked it as offline

## Solution Implemented

### 1. Automatic Re-registration (compute/services/registration_client.py)

The registration client now:
- Detects "already registered" errors (HTTP 400)
- Forces deregistration of the stale instance
- Re-registers successfully
- Starts heartbeat task

Key changes:
- Added `force` parameter to `deregister()` method
- Handle HTTP 404 in deregister (already removed)
- Automatic retry logic for "already registered" errors

### 2. Cleanup Script (scripts/cleanup_compute_registrations.sh)

New utility script for manual cleanup when needed:
```bash
./scripts/cleanup_compute_registrations.sh
```

Features:
- Lists all registered compute instances
- Shows status (online/offline)
- Allows bulk removal with confirmation

## Verification

### Test Log Output
```
2025-11-24 12:08:29,415 - WARNING - Instance already registered. Attempting to deregister and re-register...
2025-11-24 12:08:29,422 - INFO - Successfully deregistered from serving component
2025-11-24 12:08:30,434 - INFO - Successfully re-registered with serving component
2025-11-24 12:08:30,435 - INFO - Starting heartbeat task (interval: 30s)
```

### API Verification
```bash
$ curl -s http://localhost:8002/api/v1/compute
Total: 1, Online: 1
  - compute-Matthews-MacBook-Air.local-8003: online
```

## Testing Steps

1. Start all services:
   ```bash
   ./start_all.sh
   ```

2. Verify compute is registered and online:
   ```bash
   curl http://localhost:8002/api/v1/compute
   ```

3. Restart compute (without cleanup):
   ```bash
   pkill -f "python3 main.py"
   cd compute && python3 main.py
   ```

4. Verify automatic re-registration works:
   ```bash
   # Check logs
   tail -f logs/compute.log
   
   # Verify status
   curl http://localhost:8002/api/v1/compute
   ```

## Documentation Updates

1. **docs/development/COMPUTE_REGISTRATION_FIX.md** - Detailed technical documentation
2. **docs/guides/START_HERE.md** - Added troubleshooting note about cleanup script
3. **README.md** - Added troubleshooting section with automatic fix info

## Files Changed

### Modified
- `compute/services/registration_client.py` - Added automatic re-registration logic
- `docs/guides/START_HERE.md` - Updated troubleshooting section
- `README.md` - Added troubleshooting section

### Created
- `scripts/cleanup_compute_registrations.sh` - Manual cleanup utility
- `docs/development/COMPUTE_REGISTRATION_FIX.md` - Technical documentation
- `REGISTRATION_FIX_SUMMARY.md` - This summary

### Deleted
- `scripts/cleanup_registrations.sh` - Replaced with improved version

## Impact

- ✅ **No breaking changes** - Existing deployments unaffected
- ✅ **Automatic recovery** - No manual intervention needed
- ✅ **Backward compatible** - Works with existing serving component
- ✅ **Docker unaffected** - Still works as before
- ✅ **Development improved** - Local restarts now work smoothly

## Future Enhancements

Potential improvements:
1. Add exponential backoff for retry logic
2. Implement registration tokens/authentication
3. Add version checking for instance upgrades
4. Allow controlled re-registration on serving side (update vs replace)
5. Persist registration state locally to handle network interruptions

## Related Issues

This fix resolves the discrepancy between Docker and local deployments, making the development experience consistent across both environments.

