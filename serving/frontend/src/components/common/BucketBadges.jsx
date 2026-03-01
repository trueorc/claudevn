function BucketBadges({ entries }) {
  if (!entries || entries.length === 0) return null
  const visible = entries.slice(0, 2).sort((a, b) => a.rank - b.rank)
  const overflow = entries.length - 2

  return (
    <div className="bucket-badges">
      {visible.map(b => (
        <span
          key={b.bucket_id}
          className={`bucket-badge bucket-badge-rank-${Math.min(b.rank, 3)}`}
          title={b.description || b.name}
        >
          {b.name}
        </span>
      ))}
      {overflow > 0 && (
        <span className="bucket-badge-more">+{overflow}</span>
      )}
    </div>
  )
}

export default BucketBadges
