export default function Hero() {
  return (
    <section className="hero" id="hero">
      {/* Gradient mesh background */}
      <div className="hero-bg">
        <div className="hero-gradient hero-gradient--1" />
        <div className="hero-gradient hero-gradient--2" />
        <div className="hero-grid" />
      </div>

      <div className="hero-content container">
        <div className="hero-badge">
          <span className="hero-badge-dot" />
          Open Source
        </div>

        <h1 className="hero-title">
          Distributed AI<br />
          <span className="hero-title-accent">Collaboration</span>
        </h1>

        <p className="hero-subtitle">
          The first virtual network for Claude Code. Connect multiple
          instances into a distributed compute network where AI agents
          collaborate on real work — writing code, reviewing changes,
          and shipping results.
        </p>

        <div className="hero-actions">
          <a
            href="https://github.com/guarrdon"
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-primary"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/>
            </svg>
            View on GitHub
          </a>
          <a href="#demo" className="btn btn-secondary">
            Watch Demo
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="5 3 19 12 5 21 5 3" />
            </svg>
          </a>
        </div>
      </div>
    </section>
  )
}
