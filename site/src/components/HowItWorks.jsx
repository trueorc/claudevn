import { useEffect, useRef } from 'react'

const steps = [
  {
    number: '01',
    title: 'Set Your Goals',
    description: 'Describe what you want in plain language. You focus on what needs to happen — ClaudeVN figures out how.',
    color: 'var(--primary)',
  },
  {
    number: '02',
    title: 'Work Gets Planned',
    description: 'Goals break down into concrete tasks automatically. ClaudeVN manages priorities, dependencies, and assignments so agents stay productive.',
    color: 'var(--blue)',
  },
  {
    number: '03',
    title: 'Agents Collaborate',
    description: 'Claude Code instances pick up tasks, create branches, write code, and run tests — coordinating with each other through the shared network.',
    color: 'var(--green)',
  },
  {
    number: '04',
    title: 'Results Ship',
    description: 'Finished work flows through pull request review and merges automatically. Every change is tracked, tested, and auditable.',
    color: 'var(--amber)',
  },
]

export default function HowItWorks() {
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
    const items = ref.current?.querySelectorAll('.step')
    items?.forEach(item => observer.observe(item))
    return () => observer.disconnect()
  }, [])

  return (
    <section className="how-it-works section" id="how-it-works" ref={ref}>
      <div className="container">
        <span className="section-label">How It Works</span>
        <h2 className="section-title">From goals to shipped code</h2>
        <p className="section-subtitle">
          You set the direction. A distributed network of Claude Code agents
          handles the rest.
        </p>

        <div className="steps">
          {steps.map((s, i) => (
            <div
              key={s.number}
              className="step fade-in"
              style={{ transitionDelay: `${i * 120}ms` }}
            >
              <div className="step-number" style={{ color: s.color }}>
                {s.number}
              </div>
              <div className="step-content">
                <h3 className="step-title">{s.title}</h3>
                <p className="step-description">{s.description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
