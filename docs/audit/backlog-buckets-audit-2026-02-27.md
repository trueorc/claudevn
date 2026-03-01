# Backlog Bucket Views - Functional Audit

**Date:** 2026-02-27
**Type:** Standard Functional Audit
**Feature:** Backlog screen bucket-based filtered views
**Result:** Gaps identified - partial backend support, no frontend integration

## Executive Summary

The backlog screen (`/backlog`) currently supports grouping and filtering by status, priority, area, type, and goal. The user wants the ability to view issues grouped by their classification "buckets" - strategic groupings that cut across the ontology. An issue should be able to belong to multiple buckets.

Significant backend infrastructure already exists (bucket tree model, Redis store, reorganization service, API endpoints), and frontend API functions are defined but **never consumed by any UI component**. The gap is primarily in frontend integration and a data model adjustment for multi-bucket membership.

## Current State

### What Works

| Capability | Status | Location |
|-----------|--------|----------|
| Bucket tree data model | Implemented | `serving/models/priority_bucket.py` |
| Bucket tree Redis persistence | Implemented | `serving/services/bucket_tree_store.py` |
| Bucket reorganization service | Implemented | `serving/services/bucket_reorganization_service.py` |
| API: GET `/workmap/bucket-tree` | Implemented | `serving/api/work_map.py:1882` |
| API: GET `/workmap/bucket-tree/{bucket_id}` | Implemented | `serving/api/work_map.py:1927` |
| Frontend API: `getBucketTree()` | Implemented | `serving/frontend/src/api/workmap.js:247` |
| Frontend API: `getBucketDetail()` | Implemented | `serving/frontend/src/api/workmap.js:251` |
| BacklogPage grouping (status/priority/area/type/goal) | Implemented | `serving/frontend/src/pages/BacklogPage.jsx` |
| BacklogPage filtering (status/priority/area) | Implemented | `serving/frontend/src/pages/BacklogPage.jsx` |
| Characterization / ontology tags | Implemented | `serving/services/characterization_service.py` |

### What's Missing

| Gap | Severity | Description |
|-----|----------|-------------|
| No bucket view in BacklogPage | High | `groupByOptions` has no "By Bucket" option; no bucket tab/view exists |
| No `useBucketTree` hook | High | No React hook to fetch and poll bucket tree data |
| Frontend API functions unused | High | `getBucketTree` and `getBucketDetail` are defined but never called |
| Single-bucket membership model | Medium | `BucketTree.find_item()` returns one bucket; items live in exactly one bucket. User wants multi-bucket |
| No bucket filter in filter panel | Medium | Cannot filter backlog by specific bucket(s) |
| No bucket metadata on issue cards | Low | BacklogItem does not display which bucket(s) an issue belongs to |
| No bucket stats in stats bar | Low | Stats bar shows status counts but not bucket distribution |

## Detailed Findings

### 1. Backend Bucket Infrastructure (Functional - Well Built)

The `PriorityBucket` model (`serving/models/priority_bucket.py`) is comprehensive:
- `BucketDefinition` with criteria (work_type, lifecycle_stage, technical_domain, weight, completion, blocking, dependency readiness)
- `BucketCriterion` supports AND/OR logic via `MATCH_ANY` with nested criteria
- `BucketItem` with readiness state, priority score, blocking count
- `PriorityBucket` with rank, ready/blocked item accessors
- `BucketTree` with validation, assignment queue, item lookup
- Full reorganization event tracking

### 2. Frontend API Bridge (Exists but Disconnected)

`serving/frontend/src/api/workmap.js` defines:
- `getBucketTree(projectId)` → `GET /workmap/bucket-tree?project_id=...`
- `getBucketDetail(bucketId, projectId)` → `GET /workmap/bucket-tree/{bucketId}?project_id=...`

These are dead code - no component or hook imports them.

### 3. BacklogPage Grouping Gap

`BacklogPage.jsx` lines 72-88 define grouping options:
```javascript
const groupByOptions = [
  { value: 'none', label: 'No Grouping' },
  { value: 'status', label: 'By Status' },
  { value: 'priority', label: 'By Priority' },
  { value: 'area', label: 'By Area' },
  { value: 'type', label: 'By Type' },
  { value: 'goal', label: 'By Goal' }
]
```

No "By Bucket" option exists. The `getGroupKey()` function has no bucket case.

### 4. Multi-Bucket Membership Model Gap

The current `BucketTree` model assigns each item to exactly one bucket:
- `BucketTree.find_item()` returns a single `(PriorityBucket, BucketItem)` tuple
- Items are placed via bucket membership criteria during tree creation
- The `is_default` catch-all bucket captures unmatched items

For the user's requirement (issues in multiple buckets), the model needs adjustment - either items can appear in multiple buckets, or a separate "bucket tags" concept is needed that maps items to multiple classifications.

## Recommendations

1. **Create `useBucketTree` hook** - Fetch bucket tree data with polling, expose buckets and loading state
2. **Add "By Bucket" grouping option** to BacklogPage - Use bucket tree data to group issues
3. **Add bucket filter** to filter panel - Allow selecting one or more buckets
4. **Show bucket badges on issue cards** - Display which bucket(s) an issue belongs to
5. **Support multi-bucket membership** - Adjust backend model or add separate tagging layer
6. **Add bucket stats** to the stats bar or as a separate summary section

## Issues to Create

1. [P1] Add `useBucketTree` hook and "By Bucket" grouping to BacklogPage
2. [P1] Add bucket filter to BacklogPage filter panel
3. [P2] Support multi-bucket membership for issues
4. [P2] Display bucket badges on backlog issue cards
5. [P2] Add bucket distribution stats to BacklogPage
