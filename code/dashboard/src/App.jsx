import { useState, useEffect } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import StartPage from './pages/StartPage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'

function App() {
  const [page, setPage] = useState('start')
  const [stage, setStage] = useState(1)

  const useWs = useWebSocket(`ws://${window.location.hostname}:8000/ws`)
  const { messages, serverState, connected, send, clearMessages } = useWs

  useEffect(() => {
    if (!serverState.stage) return undefined
    const timer = window.setTimeout(() => setStage(serverState.stage), 0)
    return () => window.clearTimeout(timer)
  }, [serverState])

  // 세션 리셋 시 메시지 초기화
  useEffect(() => {
    const last = messages[messages.length - 1]
    if (!last) return
    if (last.type === 'ack' && (last.event === 'new_session' || last.event === 'stop_learning')) {
      clearMessages()
    }
  }, [messages, clearMessages])

  // 시작하기: 깨끗한 재시작(new_session) + stage 1 + 대시보드 진입
  const handleStart = () => {
    send({ event: 'new_session' })
    setStage(1)
    setPage('dashboard')
  }

  // 새 세션(대시보드 → StartPage 복귀): 서버 세션 리셋 + 시작화면으로
  const handleExit = () => {
    send({ event: 'new_session' })
    setStage(1)
    setPage('start')
  }

  if (page === 'start') {
    return <StartPage connected={connected} onStart={handleStart} />
  }

  return (
    <DashboardPage
      send={send}
      connected={connected}
      stage={stage}
      setStage={setStage}
      useWs={useWs}
      onExit={handleExit}
    />
  )
}

export default App
