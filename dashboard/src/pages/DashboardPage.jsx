import { useMemo } from 'react'
import Header from '../components/Header.jsx'
import StageStepper from '../components/StageStepper.jsx'
import CameraView from '../components/CameraView.jsx'
import DirectionPanel from '../components/DirectionPanel.jsx'
import ChatPanel from '../components/ChatPanel.jsx'
import STTInput from '../components/STTInput.jsx'
import ControlBar from '../components/ControlBar.jsx'
import FallbackPanel from '../components/FallbackPanel.jsx'

function DashboardPage({ send, connected, stage, setStage, ws, useWs }) {
  // useWebSocket에서 분류된 정보 추출
  const { messages, voiceState, latestDanger, latestObjects, serverState } = useWs || {
    messages: [],
    voiceState: 'idle',
    latestDanger: null,
    latestObjects: [],
    serverState: {},
  };

  // 세션 ID 추출 (메시지가 아닌 다른 곳에서)
  const sessionId = useMemo(() => {
    return serverState.session_id || '';
  }, [serverState.session_id]);

  const handleStageChange = (newStage) => {
    setStage(newStage);
    send({ event: 'start_learning', stage: newStage });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--cream-bg)' }}>
      <Header connected={connected} sessionId={sessionId} />

      <StageStepper stage={stage} />

      {/* Main content */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Left panel */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: '0 16px 16px 16px' }}>
          <CameraView stage={stage} objects={latestObjects} danger={latestDanger} />
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
            <ChatPanel messages={messages} stage={stage} />
          </div>
          <div style={{ marginTop: 12 }}>
            <STTInput voiceState={voiceState} />
          </div>
          <details style={{ marginTop: 10, background: '#fff', border: '1px solid #eee', borderRadius: 8, padding: 10 }}>
            <summary style={{ cursor: 'pointer', fontSize: 12, color: 'var(--text-secondary)' }}>운영자 Fallback</summary>
            <div style={{ marginTop: 10 }}>
              <FallbackPanel send={send} />
            </div>
          </details>
        </div>
      </div>

      <ControlBar send={send} stage={stage} onStageChange={handleStageChange} />
    </div>
  )
}

export default DashboardPage
