import { useEffect, useRef } from 'react'

export default function Demo() {
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
      { threshold: 0.1 }
    )
    if (ref.current) observer.observe(ref.current)
    return () => observer.disconnect()
  }, [])

  return (
    <section className="demo section" id="demo">
      <div className="container">
        <span className="section-label">Demo</span>
        <h2 className="section-title">See it in action</h2>
        <p className="section-subtitle">
          Watch AI agents collaborate in real time — distributing work,
          writing code, and merging results across a network of Claude Code instances.
        </p>

        <div className="demo-player fade-in" ref={ref}>
          {/* Replace the placeholder below with a YouTube/Loom embed:
              <iframe
                src="https://www.youtube.com/embed/YOUR_VIDEO_ID"
                title="ClaudeVN Demo"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />
          */}
          <div className="demo-placeholder">
            <div className="demo-placeholder-icon">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="5 3 19 12 5 21 5 3" />
              </svg>
            </div>
            <p className="demo-placeholder-text">Demo video coming soon</p>
            <p className="demo-placeholder-sub">
              Drop a YouTube or Loom URL into the embed slot to activate
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
