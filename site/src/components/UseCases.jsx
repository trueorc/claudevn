import { useEffect, useRef } from 'react'

const cases = [
  {
    label: 'Team & Hobbyist',
    title: 'Start with what you have',
    description:
      'Run the hub on your machine. Connect your laptop, a friend\'s desktop, and a cloud instance. Manage it all from your phone. Every device you add is another AI agent ready to collaborate — no special infrastructure, just the machines already on your desk.',
    nodes: ['Laptop', 'Desktop', 'Cloud VM'],
    color: 'var(--green)',
  },
  {
    label: 'Enterprise',
    title: 'Scale across your organization',
    description:
      'Deploy a private compute network across your infrastructure. Control which agents access which resources. Route sensitive work to secure nodes. Scale AI collaboration across teams, regions, and projects — with full audit trails and access controls built in.',
    nodes: ['Team A', 'Team B', 'Region EU', 'Region US'],
    color: 'var(--blue)',
  },
]

export default function UseCases() {
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
    const cards = ref.current?.querySelectorAll('.usecase-card')
    cards?.forEach(card => observer.observe(card))
    return () => observer.disconnect()
  }, [])

  return (
    <section className="usecases section" id="use-cases" ref={ref}>
      <div className="container">
        <span className="section-label">Use Cases</span>
        <h2 className="section-title">Your network, your rules</h2>
        <p className="section-subtitle">
          ClaudeVN is a private AI compute network. You own it. You decide
          who's on it, what they can access, and how it scales. The same
          architecture works whether it's three laptops or three hundred
          cloud instances.
        </p>

        <div className="usecases-grid">
          {cases.map((c, i) => (
            <div
              key={c.label}
              className="usecase-card fade-in"
              style={{ transitionDelay: `${i * 120}ms` }}
            >
              <span className="usecase-label" style={{ color: c.color }}>
                {c.label}
              </span>
              <h3 className="usecase-title">{c.title}</h3>
              <p className="usecase-description">{c.description}</p>
              <div className="usecase-nodes">
                {c.nodes.map(node => (
                  <span
                    key={node}
                    className="usecase-node"
                    style={{ borderColor: c.color, color: c.color }}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>
                    </svg>
                    {node}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>

        <p className="usecases-footer fade-in">
          Same protocol. Same tools. The only difference is how many machines
          are on the network.
        </p>
      </div>
    </section>
  )
}
