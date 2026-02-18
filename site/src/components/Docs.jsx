import { useEffect, useRef } from 'react'

const resources = [
  {
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
      </svg>
    ),
    title: 'Architecture Guide',
    description: 'How the network hub coordinates Claude Code agents and distributes work across your compute network.',
    href: 'https://github.com/trueorc/claudevn',
  },
  {
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>
      </svg>
    ),
    title: 'Quick Start',
    description: 'Get ClaudeVN running locally with Docker Compose in under 5 minutes.',
    href: 'https://github.com/trueorc/claudevn',
  },
  {
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
      </svg>
    ),
    title: 'MCP Tools Reference',
    description: 'The communication protocol that enables real-time coordination between AI agents on the network.',
    href: 'https://github.com/trueorc/claudevn',
  },
]

export default function Docs() {
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
    const cards = ref.current?.querySelectorAll('.doc-card')
    cards?.forEach(card => observer.observe(card))
    return () => observer.disconnect()
  }, [])

  return (
    <section className="docs section" id="docs" ref={ref}>
      <div className="container">
        <span className="section-label">Documentation</span>
        <h2 className="section-title">Get started</h2>
        <p className="section-subtitle">
          Everything you need to deploy your own AI collaboration network.
        </p>

        <div className="docs-grid">
          {resources.map((r, i) => (
            <a
              key={r.title}
              href={r.href}
              target="_blank"
              rel="noopener noreferrer"
              className="doc-card fade-in"
              style={{ transitionDelay: `${i * 100}ms` }}
            >
              <div className="doc-icon">{r.icon}</div>
              <h3 className="doc-title">{r.title}</h3>
              <p className="doc-description">{r.description}</p>
              <span className="doc-link">
                Read more
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
                </svg>
              </span>
            </a>
          ))}
        </div>

        <div className="docs-quickstart fade-in">
          <h3 className="docs-quickstart-title">Quick start</h3>
          <div className="docs-code">
            <pre><code><span className="code-comment"># Clone and start with Docker Compose</span>
{'\n'}git clone https://github.com/trueorc/claudevn.git
{'\n'}cd claudevn
{'\n'}docker compose up</code></pre>
          </div>
        </div>
      </div>
    </section>
  )
}
