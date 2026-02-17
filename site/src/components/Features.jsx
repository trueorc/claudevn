import { useEffect, useRef } from 'react'

const features = [
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>
      </svg>
    ),
    title: 'Distributed AI Compute',
    description: 'Claude Code is the engine. ClaudeVN is the network. Each agent is a full Claude Code instance with real reasoning and full autonomy. Scale by connecting more machines.',
  },
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 11a9 9 0 0 1 9 9"/><path d="M4 4a16 16 0 0 1 16 16"/><circle cx="5" cy="19" r="1"/>
      </svg>
    ),
    title: 'Real-Time Coordination',
    description: 'Agents don\'t just take turns — they collaborate. Shared context, progress awareness, and a common communication layer mean agents work with each other, not just alongside.',
  },
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="4"/><line x1="1.05" y1="12" x2="7" y2="12"/><line x1="17.01" y1="12" x2="22.96" y2="12"/>
      </svg>
    ),
    title: 'Git as Source of Truth',
    description: 'Every task is a branch. Every result is a pull request. You get a complete audit trail, parallel work without conflicts, and rollback built in — using tools you already know.',
  },
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
        <polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>
      </svg>
    ),
    title: 'Composable Skills',
    description: 'Define what each agent can do with simple skill definitions. Mix and match capabilities to build specialized workers for any job — no framework wrestling required.',
  },
]

export default function Features() {
  const ref = useRef(null)

  useEffect(() => {
    const observer = new IntersectionObserver(
      entries => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            entry.target.classList.add('visible')
          }
        })
      },
      { threshold: 0.15 }
    )
    const cards = ref.current?.querySelectorAll('.feature-card')
    cards?.forEach(card => observer.observe(card))
    return () => observer.disconnect()
  }, [])

  return (
    <section className="features section" id="features" ref={ref}>
      <div className="container">
        <span className="section-label">Features</span>
        <h2 className="section-title">Built for AI that works together</h2>
        <p className="section-subtitle">
          No rigid pipelines. No scripted handoffs. A networking layer for
          Claude Code that turns individual instances into a collaborative team.
        </p>

        <div className="features-grid">
          {features.map((f, i) => (
            <div
              key={f.title}
              className="feature-card fade-in"
              style={{ transitionDelay: `${i * 100}ms` }}
            >
              <div className="feature-icon">{f.icon}</div>
              <h3 className="feature-title">{f.title}</h3>
              <p className="feature-description">{f.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
