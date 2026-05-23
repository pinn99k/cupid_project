import { useMemo } from 'react'
import Header from '../components/Header.jsx'
import StageStepper from '../components/StageStepper.jsx'
import CameraView from '../components/CameraView.jsx'
import DirectionPanel from '../components/DirectionPanel.jsx'
import ChatPanel from '../components/ChatPanel.jsx'
import STTInput from '../components/STTInput.jsx'
import ControlBar from '../components/ControlBar.jsx'

function DashboardPage({ send, connected, stage, setStage, ws, useWs }) {
  // useWebSocket에서 분류된 정보 추출
  const { messages, voiceState, latestObjects } = useWs || {
    messages: [],
    voiceState: 'idle',
    latestObjects: [],
  };

  // 세션 ID 추출 (메시지가 아닌 다른 곳에서)
  const sessionId = useMemo(() => {
    // TODO: 서버에서 별도로 전달받기
    return '';
  }, []);

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
            <ChatPanel messages={messages} stage={stage} />
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
