import { useState } from 'react'
import StartupVideo from './components/StartupVideo.jsx'
import Nav from './components/Nav.jsx'
import Hero from './components/Hero.jsx'
import Features from './components/Features.jsx'
import HowItWorks from './components/HowItWorks.jsx'
import UseCases from './components/UseCases.jsx'
import Demo from './components/Demo.jsx'
import Docs from './components/Docs.jsx'
import Sponsor from './components/Sponsor.jsx'
import Footer from './components/Footer.jsx'

export default function App() {
  const [introComplete, setIntroComplete] = useState(false)

  return (
    <>
      {!introComplete && <StartupVideo onComplete={() => setIntroComplete(true)} />}
      <Nav />
      <main>
        <Hero />
        <Features />
        <HowItWorks />
        <UseCases />
        <Demo />
        <Docs />
        <Sponsor />
      </main>
      <Footer />
    </>
  )
}
