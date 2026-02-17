import { useEffect, useRef } from 'react'

const SPONSOR_URL = 'https://github.com/sponsors/Guarrdon'

export default function Sponsor() {
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
    const el = ref.current?.querySelector('.sponsor-card')
    if (el) observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return (
    <section className="sponsor section" id="sponsor" ref={ref}>
      <div className="container">
        <div className="sponsor-card fade-in">
          <div className="sponsor-icon">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
            </svg>
          </div>

          <h2 className="sponsor-title">Support the project</h2>
          <p className="sponsor-description">
            ClaudeVN is free and open source. If you find it useful, consider
            sponsoring to help cover infrastructure costs and keep development
            moving forward.
          </p>

          <a
            href={SPONSOR_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-sponsor"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
            </svg>
            Sponsor on GitHub
          </a>
        </div>
      </div>
    </section>
  )
}
