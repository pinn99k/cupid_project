import { useMemo, useEffect, useState, useRef } from 'react'
import { useSpeechRecognition } from '../hooks/useSpeechRecognition'
import Header from '../components/Header.jsx'
import StageStepper from '../components/StageStepper.jsx'
import CameraView from '../components/CameraView.jsx'
import DirectionPanel from '../components/DirectionPanel.jsx'
import ChatPanel from '../components/ChatPanel.jsx'
import STTInput from '../components/STTInput.jsx'
import ControlBar from '../components/ControlBar.jsx'

// 음성 상태: idle → listening ↔ responding
// idle: STT 꺼짐
// listening: STT 켜짐, 사용자 말 대기
// responding: TTS 재생 중, STT 일시정지
const VOICE_IDLE = 'idle'
const VOICE_LISTENING = 'listening'
const VOICE_RESPONDING = 'responding'

function DashboardPage({ send, messages, connected, stage, setStage, ws, sttActive, setSttActive }) {
  const { start: sttStart, stop: sttStop, pause: sttPause, resume: sttResume } = useSpeechRecognition(ws)
  const [voiceState, setVoiceState] = useState(VOICE_IDLE)
  const prevMsgCountRef = useRef(0)

  // 서버 메시지에 따라 반이중 상태 전환
  useEffect(() => {
    // 새 메시지가 추가됐을 때만 처리
    if (messages.length <= prevMsgCountRef.current) return
    prevMsgCountRef.current = messages.length

    const last = messages[messages.length - 1]
    if (!last) return

    if (last.type === 'tts_start') {
      sttPause()
      setVoiceState(VOICE_RESPONDING)
    } else if (last.type === 'tts_done') {
      sttResume()
      setVoiceState(sttActive ? VOICE_LISTENING : VOICE_IDLE)
    }
  }, [messages, sttActive, sttPause, sttResume])

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

  // 마스터 토글: 켜면 listening, 끄면 idle
  const handleSttToggle = () => {
    if (sttActive) {
      sttStop()
      setSttActive(false)
      setVoiceState(VOICE_IDLE)
    } else {
      sttStart()
      setSttActive(true)
      setVoiceState(VOICE_LISTENING)
    }
  }

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
            <STTInput voiceState={voiceState} onToggle={handleSttToggle} />
          </div>
        </div>
      </div>

      <ControlBar send={send} stage={stage} onStageChange={handleStageChange} />
    </div>
  )
}

export default DashboardPage
