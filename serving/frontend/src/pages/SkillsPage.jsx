import { useState, useCallback } from 'react'
import { Plus } from 'lucide-react'
import SkillList from '../components/network/SkillList'
import SkillCreateModal from '../components/network/SkillCreateModal'

function SkillsPage() {
  const [skillFilter, setSkillFilter] = useState(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  const handleCreated = useCallback(() => {
    setRefreshKey(k => k + 1)
  }, [])

  return (
    <div className="page">
      <header className="page-header">
        <h1 className="page-title">Skills</h1>
        <button
          onClick={() => setShowCreateModal(true)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '6px 12px',
            background: 'var(--primary)',
            color: 'white',
            borderRadius: '6px',
            fontSize: '13px',
            fontWeight: 500
          }}
        >
          <Plus size={14} />
          Create Skill
        </button>
      </header>
      <SkillList
        key={refreshKey}
        authorFilter={skillFilter}
        onFilterChange={setSkillFilter}
      />
      <SkillCreateModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onCreated={handleCreated}
      />
    </div>
  )
}

export default SkillsPage
