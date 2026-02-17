# Serving Component - Storage & Cache

## Overview

The Serving component uses three storage systems:

1. **Registry Storage** - Persistent storage for compute/marketplace registrations
2. **Cache Backend** - Fast temporary storage for frequently accessed data
3. **Data Provider** - General-purpose data storage with pluggable backends

All three support swappable implementations (filesystem now, Redis/S3/cloud later).

---

## Registry Storage

**Purpose:** Persistent storage for compute instances and marketplace registrations.

**Location:** `./data/serving/registry/`

**Structure:**
```
data/serving/registry/
├── compute/
│   ├── compute-001.json
│   ├── compute-002.json
│   └── index.json
└── marketplaces/
    ├── marketplace-001.json
    └── index.json
```

**Usage:**
```python
from storage.registry_storage import RegistryStorage

storage = RegistryStorage("./data/serving")
await storage.save_instance(instance_data, subdirectory="compute")
```

---

## Cache Backend

**Purpose:** Temporary caching of frequently accessed data (agent search results, etc.)

**Location:** `./data/serving/cache/`

**TTL:** Configurable (default: 300 seconds)

**Current Implementation:** Filesystem-based with JSON files

**Future Options:** Redis, Memcached, etc.

### API Endpoints

```bash
# Get cache stats
GET /api/v1/cache/stats

# Clear all cache
DELETE /api/v1/cache/clear

# Clean up expired entries
POST /api/v1/cache/cleanup

# Delete specific entry
DELETE /api/v1/cache/{key}
```

### Usage in Code

```python
from storage.cache_backend import get_cache_backend

cache = get_cache_backend()

# Cache data (5 minute TTL)
await cache.set("my_key", {"data": "value"}, ttl=300)

# Retrieve cached data
data = await cache.get("my_key")  # Returns None if expired

# Check existence
exists = await cache.exists("my_key")

# Delete entry
await cache.delete("my_key")

# Clear all
await cache.clear()
```

### Cache Structure

Each cache entry is stored as JSON:
```json
{
  "key": "agent_search:abc123",
  "value": {
    "agents": [...],
    "total": 5
  },
  "created_at": "2025-12-11T10:00:00",
  "expires_at": "2025-12-11T10:05:00",
  "ttl": 300
}
```

### Features

- ✅ Automatic expiration based on TTL
- ✅ Cleanup of expired entries via API
- ✅ Thread-safe file operations
- ✅ Safe key handling (replaces special chars)
- ✅ JSON serializable values
- 🔄 Pluggable backend (Redis, Memcached ready)

---

## Data Provider

**Purpose:** General-purpose data storage for sessions, blobs, artifacts, etc.

**Location:** `./data/serving/datastore/`

**Current Implementation:** Filesystem-based

**Future Options:** S3, Azure Blob, Google Cloud Storage, Redis, etc.

### Supported Data Types

1. **JSON Data** - Dicts, lists, etc. (stored as `.json`)
2. **Text Data** - Strings (stored as `.txt`)
3. **Binary Data** - Bytes (stored as `.bin`)

### Usage

```python
from storage.data_provider import get_data_provider

provider = get_data_provider()

# Store JSON data
await provider.store(
    "sessions:session-123",
    {"status": "active", "data": [1, 2, 3]},
    metadata={"created_by": "user-456"}
)

# Store text data
await provider.store(
    "documents:readme",
    "This is my document content"
)

# Store binary data
await provider.store(
    "blobs:image-001",
    b'\x89PNG\r\n\x1a\n...'
)

# Retrieve data
data = await provider.retrieve("sessions:session-123")

# Check existence
exists = await provider.exists("sessions:session-123")

# List keys with prefix
keys = await provider.list_keys(prefix="sessions:")

# Get metadata
meta = await provider.get_metadata("sessions:session-123")

# Delete data
await provider.delete("sessions:session-123")
```

### Storage Structure

Data is organized by key hierarchy:
```
data/serving/datastore/
├── sessions/
│   ├── session-123.json
│   ├── session-123.meta.json
│   └── session-456.json
├── documents/
│   ├── readme.txt
│   └── readme.meta.json
└── blobs/
    ├── image-001.bin
    └── image-001.meta.json
```

Keys like `sessions:session-123` become `sessions/session-123.json`

### Metadata Example

```json
{
  "key": "sessions:session-123",
  "stored_at": "2025-12-11T10:00:00",
  "data_type": "dict"
}
```

### Features

- ✅ Automatic directory creation
- ✅ Nested key support (`:` or `/` separators)
- ✅ Multiple data type support (JSON, text, binary)
- ✅ Metadata storage for each entry
- ✅ Key prefix filtering
- 🔄 Pluggable backend (S3, Redis ready)

---

## Pluggable Backend Architecture

All storage systems use abstract base classes for easy swapping:

### Example: Switch to Redis Cache

```python
from storage.cache_backend import CacheBackend, set_cache_backend
import aioredis

class RedisCache(CacheBackend):
    def __init__(self, redis_url: str):
        self.redis = aioredis.from_url(redis_url)
    
    async def get(self, key: str):
        value = await self.redis.get(key)
        return json.loads(value) if value else None
    
    async def set(self, key: str, value: Any, ttl: int = 300):
        await self.redis.setex(key, ttl, json.dumps(value))
        return True
    
    # ... implement other methods

# Use Redis instead of filesystem
redis_cache = RedisCache("redis://localhost:6379")
set_cache_backend(redis_cache)
```

### Example: Switch to S3 Data Provider

```python
from storage.data_provider import DataProvider, set_data_provider
import boto3

class S3DataProvider(DataProvider):
    def __init__(self, bucket: str):
        self.s3 = boto3.client('s3')
        self.bucket = bucket
    
    async def store(self, key: str, data: Any, metadata: Optional[Dict] = None):
        # Upload to S3
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=json.dumps(data)
        )
        return True
    
    # ... implement other methods

# Use S3 instead of filesystem
s3_provider = S3DataProvider("my-bucket")
set_data_provider(s3_provider)
```

---

## Configuration

Environment variables:

```bash
# Storage paths
STORAGE_PATH=./data/serving              # Registry storage
CACHE_PATH=./data/serving/cache          # Cache location
DATASTORE_PATH=./data/serving/datastore  # Data provider location

# Cache settings
CACHE_DEFAULT_TTL=300                    # Default cache TTL (seconds)

# Future: Redis settings
# REDIS_URL=redis://localhost:6379
# CACHE_BACKEND=redis
# DATA_BACKEND=redis
```

---

## Usage in Serving Component

### Marketplace Agent Search (Uses Cache)

When searching for agents across marketplaces:

1. Generate cache key from search parameters
2. Check cache first
3. If miss, query all marketplaces
4. Aggregate results
5. Cache for 5 minutes
6. Return results

**Benefits:**
- Reduces marketplace load
- Faster response times
- Lower latency for repeated searches

### Session Data (Uses Data Provider)

Session data can use the data provider for persistence:

```python
# Store session
await data_provider.store(
    f"sessions:{session_id}",
    session_data,
    metadata={"created_at": datetime.utcnow()}
)

# Retrieve session
session = await data_provider.retrieve(f"sessions:{session_id}")
```

---

## Monitoring

### Cache Health

```bash
# Check cache stats
curl http://localhost:8002/api/v1/cache/stats

# Response:
{
  "backend": "filesystem",
  "total_entries": 42,
  "total_size_bytes": 153600,
  "cache_path": "/app/data/serving/cache"
}
```

### Cleanup

```bash
# Clean up expired entries
curl -X POST http://localhost:8002/api/v1/cache/cleanup

# Response:
{
  "status": "success",
  "deleted_entries": 12,
  "message": "Cleaned up 12 expired entries"
}
```

---

## Future Enhancements

### Planned Features

1. **Redis Cache Backend**
   - Distributed caching
   - Better performance
   - Built-in expiration

2. **S3 Data Provider**
   - Scalable storage
   - Lower cost for large data
   - Built-in durability

3. **Cache Warming**
   - Pre-populate frequently accessed data
   - Background refresh

4. **Cache Metrics**
   - Hit/miss ratios
   - Performance tracking
   - Usage analytics

5. **Data Versioning**
   - Track data changes
   - Rollback support

6. **Compression**
   - Reduce storage size
   - Faster transfers

---

## Best Practices

### When to Use Cache

✅ **Good Use Cases:**
- Frequently accessed data
- Expensive computations
- External API results
- Search results
- Aggregated statistics

❌ **Avoid Caching:**
- Real-time critical data
- Rapidly changing data
- Large blobs (use data provider instead)
- User-specific sensitive data

### When to Use Data Provider

✅ **Good Use Cases:**
- Session state
- User uploads
- Generated artifacts
- Documents/reports
- Blob storage
- Long-term data

### Cache TTL Guidelines

- **Search Results:** 5 minutes (300s)
- **Agent Metadata:** 15 minutes (900s)
- **Statistics:** 1 minute (60s)
- **Configuration:** 1 hour (3600s)

---

## Troubleshooting

### Cache Not Working

```bash
# Check cache directory exists
ls -la data/serving/cache/

# Check cache stats
curl http://localhost:8002/api/v1/cache/stats

# Clear cache
curl -X DELETE http://localhost:8002/api/v1/cache/clear
```

### Data Not Persisting

```bash
# Check datastore directory
ls -la data/serving/datastore/

# Check permissions
chmod -R 755 data/serving/

# Check logs
tail -f logs/serving.log | grep -i "storage\|cache\|data"
```

### High Disk Usage

```bash
# Check cache size
du -sh data/serving/cache/

# Clean up expired entries
curl -X POST http://localhost:8002/api/v1/cache/cleanup

# Clear old sessions (manual)
find data/serving/datastore/sessions -mtime +7 -delete
```

---

## Summary

- **Registry Storage** - Persistent instance/marketplace data
- **Cache Backend** - Fast temporary storage (pluggable)
- **Data Provider** - General storage (pluggable)
- All support filesystem now, Redis/S3/cloud later
- Simple API for easy backend swapping
- Built-in expiration and cleanup
