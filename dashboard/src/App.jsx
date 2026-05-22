import { useState, useEffect } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import StartPage from './pages/StartPage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'

function App() {
  const [page, setPage] = useState('start')
  const [stage, setStage] = useState(1)
  const [sttActive, setSttActive] = useState(false)

  const { ws, messages, connected, send } = useWebSocket('ws://localhost:8000/ws')

  useEffect(() => {
    const last = messages[messages.length - 1]
    if (!last) return
    if (last.type === 'init_state') setStage(last.stage)
    if (last.type === 'ack' && last.stage) setStage(last.stage)
  }, [messages])

  if (page === 'start') {
    return <StartPage connected={connected} onStart={() => setPage('dashboard')} />
  }

  return (
    <DashboardPage
      send={send}
      messages={messages}
      connected={connected}
      stage={stage}
      setStage={setStage}
      ws={ws}
      sttActive={sttActive}
      setSttActive={setSttActive}
    />
  )
}

export default App
