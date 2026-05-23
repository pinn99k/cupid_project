import { useState, useEffect } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import StartPage from './pages/StartPage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'

function App() {
  const [page, setPage] = useState('start')
  const [stage, setStage] = useState(1)

  const useWs = useWebSocket('ws://localhost:8000/ws')
  const { ws, messages, connected, send, clearMessages } = useWs

  useEffect(() => {
    const last = messages[messages.length - 1]
    if (!last) return
    if (last.type === 'init_state') setStage(last.stage)
    if (last.type === 'ack' && last.stage) setStage(last.stage)
  }, [messages])

  // 세션 리셋 시 메시지 초기화
  useEffect(() => {
    const last = messages[messages.length - 1]
    if (!last) return
    if (last.type === 'ack' && (last.event === 'new_session' || last.event === 'stop_learning')) {
      clearMessages()
    }
  }, [messages, clearMessages])

  if (page === 'start') {
    return <StartPage connected={connected} onStart={() => setPage('dashboard')} />
  }

  return (
    <DashboardPage
      send={send}
      connected={connected}
      stage={stage}
      setStage={setStage}
      ws={ws}
      useWs={useWs}
    />
  )
}

export default App
