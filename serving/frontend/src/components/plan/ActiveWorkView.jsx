import { Play, Clock, AlertCircle, Layers, XCircle, CheckCircle2, GitMerge, History } from 'lucide-react'
import Badge from '../common/Badge'
import BucketBadges from '../common/BucketBadges'
import Spinner from '../common/Spinner'
import '../common/BucketBadges.css'
import './Plan.css'

const priorityColors = {
  P0: 'error',
  P1: 'warning',
  P2: 'default',
  P3: 'info'
}

function formatDuration(startIso, endIso) {
  if (!startIso) return null
  const start = new Date(startIso)
  const end = endIso ? new Date(endIso) : new Date()
  const diffMs = end - start
  if (diffMs < 0) return null
  const mins = Math.floor(diffMs / 60000)
  if (mins < 60) return `${mins}m`
  const hrs = Math.floor(mins / 60)
  const remainMins = mins % 60
  if (hrs < 24) return `${hrs}h ${remainMins}m`
  const days = Math.floor(hrs / 24)
  return `${days}d ${hrs % 24}h`
}

function ActiveWorkView({ data, loading, onItemClick, onItemTracesClick, itemBucketMap = {} }) {
  if (loading && !data) {
    return (
      <div className="plan-active-work">
        <div className="plan-loading-state">
          <Spinner />
        </div>
      </div>
    )
  }

  if (!data) return null

  const {
    running_items = [],
    queued_items = [],
    blocked_items = [],
    backlog_items = [],
    failed_items = [],
    implemented_items = [],
    done_items = [],
  } = data

  return (
    <div className="plan-active-work">
      <div className="plan-columns">
        <WorkColumn
          title="Running"
          icon={Play}
          iconClass="running"
          items={running_items}
          emptyMessage="No items running"
          onItemClick={onItemClick}
          onItemTracesClick={onItemTracesClick}
          itemBucketMap={itemBucketMap}
          showTiming
        />
        <WorkColumn
          title="Up Next"
          icon={Clock}
          iconClass="queued"
          items={queued_items}
          emptyMessage="No items queued"
          onItemClick={onItemClick}
          onItemTracesClick={onItemTracesClick}
          itemBucketMap={itemBucketMap}
        />
        <WorkColumn
          title="Backlog"
          icon={Layers}
          iconClass="backlog"
          items={backlog_items}
          emptyMessage="No backlog items"
          onItemClick={onItemClick}
          onItemTracesClick={onItemTracesClick}
          itemBucketMap={itemBucketMap}
          showBlockers
        />
        {blocked_items.length > 0 && (
          <WorkColumn
            title="Blocked"
            icon={AlertCircle}
            iconClass="blocked"
            items={blocked_items}
            emptyMessage="No blocked items"
            onItemClick={onItemClick}
            itemBucketMap={itemBucketMap}
            showBlockers
          />
        )}
        {failed_items.length > 0 && (
          <WorkColumn
            title="Failed"
            icon={XCircle}
            iconClass="failed"
            items={failed_items}
            emptyMessage=""
            onItemClick={onItemClick}
            itemBucketMap={itemBucketMap}
          />
        )}
        {implemented_items.length > 0 && (
          <WorkColumn
            title="Pending Merge"
            icon={GitMerge}
            iconClass="implemented"
            items={implemented_items}
            emptyMessage=""
            onItemClick={onItemClick}
            itemBucketMap={itemBucketMap}
          />
        )}
        {done_items.length > 0 && (
          <WorkColumn
            title="Done"
            icon={CheckCircle2}
            iconClass="done"
            items={done_items}
            emptyMessage=""
            onItemClick={onItemClick}
            itemBucketMap={itemBucketMap}
            showTiming
          />
        )}
      </div>
    </div>
  )
}

function WorkColumn({ title, icon: Icon, iconClass, items, emptyMessage, onItemClick, onItemTracesClick, itemBucketMap = {}, showBlockers, showTiming }) {
  return (
    <div className="plan-column">
      <div className="plan-column-header">
        <div className={`plan-column-icon ${iconClass}`}>
          <Icon size={14} />
        </div>
        <h3 className="plan-column-title">{title}</h3>
        <span className="plan-column-count">{items.length}</span>
      </div>
      <div className="plan-column-items">
        {items.length === 0 ? (
          <div className="plan-column-empty">{emptyMessage}</div>
        ) : (
          items.map(item => (
            <WorkItem
              key={item.issue_id}
              item={item}
              onClick={() => onItemClick?.(item)}
              onTracesClick={onItemTracesClick ? () => onItemTracesClick(item) : undefined}
              bucketEntries={itemBucketMap[item.issue_id]}
              showBlockers={showBlockers}
              showTiming={showTiming}
            />
          ))
        )}
      </div>
    </div>
  )
}

function WorkItem({ item, onClick, onTracesClick, bucketEntries, showBlockers, showTiming }) {
  const { title, priority, assigned_to, depends_on, started_at, completed_at } = item
  const displayId = item.number ? `#${item.number}` : item.issue_id
  const duration = showTiming ? formatDuration(started_at, completed_at) : null

  return (
    <div className="plan-work-item" onClick={onClick}>
      <div className="plan-work-item-header">
        <span className="plan-work-item-id">{displayId}</span>
        <span className="plan-work-item-title">{title}</span>
        {onTracesClick && (
          <button
            className="plan-work-item-traces-btn"
            onClick={(e) => { e.stopPropagation(); onTracesClick() }}
            title="View ordering history"
          >
            <History size={12} />
          </button>
        )}
      </div>
      <div className="plan-work-item-meta">
        {priority && (
          <Badge variant={priorityColors[priority] || 'default'} size="sm">
            {priority}
          </Badge>
        )}
        <BucketBadges entries={bucketEntries} />
        {assigned_to && (
          <span className="plan-work-item-assignee" title={assigned_to}>
            {assigned_to}
          </span>
        )}
        {showBlockers && depends_on?.length > 0 && (
          <span className="plan-work-item-blocker">
            needs {depends_on.length} dep{depends_on.length !== 1 ? 's' : ''}
          </span>
        )}
        {duration && (
          <span className="plan-work-item-duration">
            <Clock size={10} />
            {duration}
          </span>
        )}
      </div>
    </div>
  )
}

export default ActiveWorkView
