import { useState, useCallback } from 'react'
import { Plus } from 'lucide-react'
import SkillList from '../components/network/SkillList'
import SkillCreateModal from '../components/network/SkillCreateModal'
import InlineHint, { PageSubtitle } from '../components/common/InlineHint'

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
        <div>
          <h1 className="page-title">Skills</h1>
          <PageSubtitle>Atomic capabilities assigned to compute instances during task execution</PageSubtitle>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="btn btn-primary"
        >
          <Plus size={14} />
          Create Skill
        </button>
      </header>
      <InlineHint hintKey="skills-what-they-are">
        Skills are CLAUDE.md fragments that shape how a compute instance behaves on a specific type of task.
        They are composed at runtime — a single compute instance can hold multiple skills simultaneously.
      </InlineHint>
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
