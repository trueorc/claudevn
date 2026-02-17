# Data Sharing and Context Management

## Overview

ClaudeVN agents often need to share data across different compute instances that may not have direct access to a shared filesystem. This document describes the tiered storage strategy that enables flexible data sharing across various deployment topologies.

## The Challenge

Cross-instance data sharing is complex because:

- **Distributed Compute**: Instances may run on different machines or networks
- **No Shared Filesystem**: Can't assume access to common storage
- **Variable Data Sizes**: From small JSON to large files (GB+)
- **Flexible Deployment**: Must work with cloud, local, and hybrid setups
- **Temporary Nature**: Most data is ephemeral (session-scoped)

## Tiered Storage Strategy

ClaudeVN uses a three-tier approach to handle different data sizes and deployment scenarios:

```
┌─────────────────────────────────────────────────────────┐
│ Tier 1: Message-Embedded Data (< 1MB)                  │
│ - Embedded directly in A2A task messages                │
│ - Base64 encoding for binary data                       │
│ - Simple, works everywhere                              │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ Tier 2: Serving Component Storage (1MB - 100MB)        │
│ - Temporary blob storage in Serving Component           │
│ - Upload/download via HTTP                              │
│ - TTL-based cleanup                                     │
│ - Works for distributed deployments                     │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ Tier 3: External Storage URLs (> 100MB)                │
│ - Reference external URLs (S3, GCS, etc.)               │
│ - Compute instances fetch directly                      │
│ - Requires network access and credentials               │
│ - Best for production/cloud deployments                 │
└─────────────────────────────────────────────────────────┘
```

## Tier 1: Message-Embedded Data

### When to Use

- Data size < 1MB
- Simple JSON or text data
- Quick prototyping
- Single-machine deployments

### How It Works

Data is embedded directly in the A2A task context:

```json
{
  "context": {
    "session_id": "session-123",
    "task_id": "task-456",
    "data": {
      "type": "inline",
      "content": "Small text data or JSON",
      "encoding": "utf-8"
    }
  }
}
```

For binary data, use base64 encoding:

```json
{
  "context": {
    "data": {
      "type": "inline",
      "content": "SGVsbG8gV29ybGQh",
      "encoding": "base64",
      "mime_type": "image/png"
    }
  }
}
```

### Advantages

- ✅ Simple - no external storage needed
- ✅ Fast - no additional HTTP requests
- ✅ Works everywhere - no infrastructure dependencies

### Limitations

- ❌ Size limited (< 1MB recommended)
- ❌ Increases message size
- ❌ Base64 encoding adds 33% overhead for binary

## Tier 2: Serving Component Storage

### When to Use

- Data size 1MB - 100MB
- Distributed compute instances
- Need to share files between agents
- Temporary data (session-scoped)

### How It Works

The Serving Component provides a temporary blob storage API:

```
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│  Compute 1   │         │   Serving    │         │  Compute 2   │
│              │         │  Component   │         │              │
│  Agent A     │────1───>│              │         │  Agent B     │
│              │ Upload  │   Blob       │         │              │
│              │         │   Storage    │         │              │
│              │<───2────│              │<───3────│              │
│              │ Get URL │              │ Download│              │
└──────────────┘         └──────────────┘         └──────────────┘
```

**Step 1: Upload Data**

Agent A uploads data to Serving Component:

```python
# In Agent A
async def upload_data(self, data: bytes, session_id: str):
    # Upload to serving component
    response = await self.http_client.post(
        f"{self.serving_url}/api/storage/upload",
        files={"file": data},
        params={"session_id": session_id}
    )
    
    blob_info = response.json()
    return blob_info["url"]  # e.g., "/api/storage/blob-uuid"
```

**Step 2: Pass Reference in Task Context**

```json
{
  "context": {
    "session_id": "session-123",
    "data_refs": {
      "input_file": {
        "type": "blob",
        "url": "http://serving:8002/api/storage/blob-456",
        "size": 5242880,
        "mime_type": "text/csv",
        "filename": "sales_data.csv"
      }
    }
  }
}
```

**Step 3: Download Data**

Agent B downloads data from Serving Component:

```python
# In Agent B
async def download_data(self, blob_url: str):
    response = await self.http_client.get(blob_url)
    return response.content
```

### Storage Backend

The Serving Component supports multiple storage backends:

**Filesystem Backend** (default for local/development):
```bash
# serving/.env
STORAGE_BACKEND=filesystem
STORAGE_PATH=./data/blobs
STORAGE_TTL=3600  # 1 hour
STORAGE_MAX_SIZE=104857600  # 100MB
```

**S3-Compatible Backend** (Phase 3, for production):
```bash
# serving/.env
STORAGE_BACKEND=s3
S3_BUCKET=claudevn-blobs
S3_ENDPOINT=https://s3.amazonaws.com
S3_ACCESS_KEY=...
S3_SECRET_KEY=...
STORAGE_TTL=3600
```

### API Endpoints

```
POST   /api/storage/upload              Upload blob
GET    /api/storage/{blob_id}           Download blob
GET    /api/storage/{blob_id}/metadata  Get blob metadata
DELETE /api/storage/{blob_id}           Delete blob
GET    /api/storage/session/{id}/blobs  List session blobs
POST   /api/storage/cleanup              Clean up expired blobs
GET    /api/storage/stats                Get storage statistics
```

### TTL and Cleanup

Blobs have a time-to-live (TTL) and are automatically cleaned up:

- **Default TTL**: 1 hour (configurable)
- **Cleanup**: Automatic background task runs every 5 minutes
- **Manual Cleanup**: Call `/api/storage/cleanup` endpoint
- **Session Cleanup**: Delete all blobs when session completes

### Advantages

- ✅ Handles medium-sized files
- ✅ Works across distributed instances
- ✅ Automatic cleanup (TTL-based)
- ✅ No external dependencies (filesystem backend)
- ✅ Can scale to S3 for production

### Limitations

- ❌ Additional HTTP requests (latency)
- ❌ Storage space limits
- ❌ Requires Serving Component availability

## Tier 3: External Storage URLs

### When to Use

- Large files (> 100MB)
- Production deployments
- Data already in cloud storage
- Long-term data retention

### How It Works

Agents reference external URLs directly:

```json
{
  "context": {
    "session_id": "session-123",
    "data_refs": {
      "large_dataset": {
        "type": "external",
        "url": "s3://my-bucket/datasets/large_file.parquet",
        "size": 524288000,
        "mime_type": "application/octet-stream",
        "credentials": {
          "type": "aws",
          "access_key_id": "...",
          "secret_access_key": "..."
        }
      }
    }
  }
}
```

Compute instances fetch directly from the external source:

```python
# In Agent
async def download_external(self, url: str, credentials: dict):
    if url.startswith("s3://"):
        # Use boto3 or similar
        s3_client = create_s3_client(credentials)
        data = await s3_client.download(url)
    elif url.startswith("https://"):
        # Direct HTTP download
        response = await self.http_client.get(url)
        data = response.content
    
    return data
```

### Advantages

- ✅ Handles very large files
- ✅ No storage limits in ClaudeVN
- ✅ Direct access (no proxy through Serving)
- ✅ Can use existing cloud storage

### Limitations

- ❌ Requires external infrastructure
- ❌ Credentials management complexity
- ❌ Network access requirements
- ❌ Not suitable for ephemeral data

## Session Context Management

### Context Object Structure

Each session maintains a context object that flows through all tasks:

```python
{
  "session_id": "session-123",
  "execution_plan": {
    "plan_id": "plan-456",
    "goal": "Analyze sales data",
    "tasks": [...]
  },
  "task_results": {
    "task-1": {
      "status": "completed",
      "output": {...}
    },
    "task-2": {
      "status": "in_progress",
      "output": null
    }
  },
  "data_refs": {
    "uploaded_file": {
      "type": "blob",
      "url": "http://serving:8002/api/storage/blob-789",
      "size": 1048576,
      "mime_type": "text/csv"
    },
    "intermediate_results": {
      "type": "inline",
      "content": {...}
    }
  },
  "metadata": {
    "started_at": "2025-11-21T10:00:00Z",
    "user_id": "user-123",
    "total_cost": 0.0
  }
}
```

### Context Storage

The session context is stored in the Serving Component's database:

```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    context TEXT,  -- JSON
    status TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### Accessing Context

**From Coordinating Agent:**

```python
# Get full session context
context = await self.get_session_context(session_id)

# Update context
context["data_refs"]["new_data"] = {...}
await self.update_session_context(session_id, context)
```

**From Specialized Agent:**

```python
# Context is passed in task input
async def execute(self, task_input, context):
    # Access data refs
    data_url = context["data_refs"]["input_file"]["url"]
    data = await self.download_data(data_url)
    
    # Process data
    result = self.process(data)
    
    # Return result (will be added to context by coordinator)
    return {"output": result}
```

## Decision Tree: Which Tier to Use?

```
Is data < 1MB?
├─ YES → Use Tier 1 (Message-Embedded)
└─ NO  → Is data < 100MB?
         ├─ YES → Use Tier 2 (Serving Component Storage)
         └─ NO  → Is data in cloud storage?
                  ├─ YES → Use Tier 3 (External URL)
                  └─ NO  → Upload to cloud storage, then use Tier 3
                           OR split into chunks and use Tier 2
```

## Configuration Examples

### All-in-One Local Development

```bash
# serving/.env
STORAGE_BACKEND=filesystem
STORAGE_PATH=./data/blobs
STORAGE_TTL=3600
STORAGE_MAX_SIZE=104857600

# Use Tier 1 and Tier 2 only
```

### Cloud Serving + Local Compute

```bash
# serving/.env (cloud)
STORAGE_BACKEND=s3
S3_BUCKET=claudevn-blobs-prod
STORAGE_TTL=7200
STORAGE_MAX_SIZE=104857600

# compute/config.json (local)
{
  "serving_urls": ["https://serving.claudevn.io"],
  "storage_config": {
    "use_tiers": [1, 2, 3],
    "auto_upload_threshold": 1048576  // 1MB
  }
}
```

### Enterprise with Private Cloud Storage

```bash
# serving/.env
STORAGE_BACKEND=s3
S3_BUCKET=company-claudevn-blobs
S3_ENDPOINT=https://minio.company.com
STORAGE_TTL=86400  # 24 hours

# compute/.env
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

## Best Practices

### 1. Choose the Right Tier

- **Small data** (< 1MB): Always use Tier 1 for simplicity
- **Medium data** (1-100MB): Use Tier 2 for distributed setups
- **Large data** (> 100MB): Use Tier 3 with cloud storage

### 2. Clean Up After Sessions

```python
# After session completes
async def cleanup_session(self, session_id: str):
    # Delete all blobs for session
    blobs = await self.list_session_blobs(session_id)
    for blob in blobs:
        await self.delete_blob(blob["blob_id"])
```

### 3. Handle Failures Gracefully

```python
# Try download with retry
async def download_with_retry(self, url: str, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            return await self.download_data(url)
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)
```

### 4. Monitor Storage Usage

```python
# Check storage stats periodically
stats = await self.get_storage_stats()
if stats["total_size"] > threshold:
    logger.warning(f"Storage usage high: {stats['total_size']} bytes")
    await self.cleanup_expired()
```

### 5. Secure Sensitive Data

```python
# Encrypt sensitive data before upload
encrypted_data = encrypt(sensitive_data, key)
blob_url = await self.upload_data(encrypted_data, session_id)

# Decrypt after download
encrypted_data = await self.download_data(blob_url)
data = decrypt(encrypted_data, key)
```

## Security Considerations

### Access Control

- **Blob IDs**: Use UUIDs (not sequential) to prevent enumeration
- **Session Isolation**: Agents can only access blobs from their session
- **Authentication**: Require auth tokens for storage API (production)

### Data Encryption

- **At Rest**: Encrypt blobs in storage backend (Phase 4)
- **In Transit**: Use HTTPS for all storage API calls
- **Credentials**: Never embed credentials in context, use secure vault

### TTL and Retention

- **Short TTL**: Default 1 hour to minimize exposure
- **Immediate Cleanup**: Delete blobs when session completes
- **Audit Logs**: Log all storage operations for compliance

## Troubleshooting

### "Blob not found"

- Check if blob expired (TTL)
- Verify blob_id is correct
- Check storage backend is accessible

### "Storage limit exceeded"

- Increase `STORAGE_MAX_SIZE` in config
- Use Tier 3 for large files
- Clean up old blobs

### "Download timeout"

- Increase HTTP client timeout
- Check network connectivity
- Consider using streaming for large files

### "Out of disk space"

- Run cleanup: `POST /api/storage/cleanup`
- Reduce TTL to expire blobs faster
- Move to S3 backend for unlimited storage

## Future Enhancements

- [ ] Streaming uploads/downloads for large files
- [ ] Compression for blobs (gzip, zstd)
- [ ] Encryption at rest
- [ ] CDN integration for faster downloads
- [ ] Blob deduplication
- [ ] Storage quotas per session/user
- [ ] Automatic tier selection based on size

