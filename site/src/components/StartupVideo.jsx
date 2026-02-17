import { useState, useRef, useEffect } from 'react'

export default function StartupVideo({ onComplete }) {
  const [fading, setFading] = useState(false)
  const [done, setDone] = useState(false)
  const videoRef = useRef(null)

  useEffect(() => {
    // Fallback timeout in case video doesn't fire onEnded
    const timeout = setTimeout(() => handleEnd(), 9000)
    return () => clearTimeout(timeout)
  }, [])

  function handleEnd() {
    if (fading || done) return
    setFading(true)
    setTimeout(() => {
      setDone(true)
      onComplete()
    }, 800) // match CSS fade-out duration
  }

  if (done) return null

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 10000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#0a0a0a',
        backgroundImage: 'url(/complex-network.png)',
        backgroundSize: 'cover',
        backgroundPosition: 'center',
        opacity: fading ? 0 : 1,
        transition: 'opacity 0.8s ease-out',
      }}
    >
      {/* Dim overlay to fade the background image */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.7)',
        }}
      />
      <video
        ref={videoRef}
        src="/startup2.mp4"
        autoPlay
        muted
        playsInline
        onEnded={handleEnd}
        style={{
          position: 'relative',
          maxWidth: '100%',
          maxHeight: '100%',
          mixBlendMode: 'screen',
          filter: 'contrast(1.8) brightness(1.2)',
        }}
      />
    </div>
  )
}
