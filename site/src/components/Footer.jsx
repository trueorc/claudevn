export default function Footer() {
  return (
    <footer className="footer">
      <div className="footer-inner container">
        <div className="footer-links">
          <div className="footer-col">
            <h4 className="footer-col-title">Project</h4>
            <a href="https://github.com/guarrdon" target="_blank" rel="noopener noreferrer">GitHub</a>
            <a href="#features">Features</a>
            <a href="#docs">Documentation</a>
          </div>
          <div className="footer-col">
            <h4 className="footer-col-title">Resources</h4>
            <a href="#how-it-works">How It Works</a>
            <a href="#demo">Demo</a>
            <a href="https://github.com/guarrdon" target="_blank" rel="noopener noreferrer">Issues</a>
          </div>
          <div className="footer-col">
            <h4 className="footer-col-title">Support</h4>
            <a href="https://github.com/sponsors/Guarrdon" target="_blank" rel="noopener noreferrer">Sponsor</a>
          </div>
        </div>

        <div className="footer-bottom">
          <p>&copy; {new Date().getFullYear()} ClaudeVN. Open source under AGPL-3.0 license.</p>
        </div>
      </div>
    </footer>
  )
}
