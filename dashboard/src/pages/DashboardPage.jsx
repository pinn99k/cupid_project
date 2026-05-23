import { useMemo } from 'react'
import Header from '../components/Header.jsx'
import StageStepper from '../components/StageStepper.jsx'
import CameraView from '../components/CameraView.jsx'
import DirectionPanel from '../components/DirectionPanel.jsx'
import ChatPanel from '../components/ChatPanel.jsx'
import STTInput from '../components/STTInput.jsx'
import ControlBar from '../components/ControlBar.jsx'

function DashboardPage({ send, messages, connected, stage, setStage, ws }) {
  // 음성 상태: 서버 WebSocket 메시지에서 파생
  // idle: 파이프라인 꺼짐
  // listening: 음성 인식 중
  // processing: LLM 처리 중
  // responding: TTS 재생 중
  const voiceState = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i]
      if (m.type === 'voice_listening') return 'listening'
      if (m.type === 'voice_processing') return 'processing'
      if (m.type === 'tts_start') return 'responding'
      if (m.type === 'tts_done') return 'listening'
      if (m.type === 'voice_idle') return 'idle'
    }
    return 'idle'
  }, [messages])

  // messages에서 최신 감지 객체 추출 (DirectionPanel용)
  const latestObjects = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i]
      if (m.type === 'narration' && m.objects) return m.objects
      if (m.type === 'danger' && m.object) {
        return [{ label: m.object, direction: m.direction, distance_cm: m.distance_cm }]
      }
    }
    return []
  }, [messages])

  // 세션 ID 추출
  const sessionId = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i]
      if (m.type === 'ack' && m.session_id) return m.session_id
      if (m.type === 'init_state' && m.session_id) return m.session_id
    }
    return ''
  }, [messages])

  const handleStageChange = (newStage) => {
    setStage(newStage)
    send({ event: 'start_learning', stage: newStage })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--cream-bg)' }}>
      <Header connected={connected} sessionId={sessionId} />

      <StageStepper stage={stage} />

      {/* Main content */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Left panel */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: '0 16px 16px 16px' }}>
          <CameraView stage={stage} />
          <DirectionPanel objects={latestObjects} />
        </div>

        {/* Right panel */}
        <div style={{
          width: 380,
          borderLeft: '1px solid #eee',
          display: 'flex',
          flexDirection: 'column',
          padding: '0 16px 16px 16px',
        }}>
          <div style={{ flex: 1, background: 'white', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
            <ChatPanel messages={messages} />
          </div>
          <div style={{ marginTop: 12 }}>
            <STTInput voiceState={voiceState} />
          </div>
        </div>
      </div>

      <ControlBar send={send} stage={stage} onStageChange={handleStageChange} />
    </div>
  )
}

export default DashboardPage
