import { useMemo } from 'react'
import Header from '../components/Header.jsx'
import StageStepper from '../components/StageStepper.jsx'
import CameraView from '../components/CameraView.jsx'
import DirectionPanel from '../components/DirectionPanel.jsx'
import ChatPanel from '../components/ChatPanel.jsx'
import STTInput from '../components/STTInput.jsx'
import ControlBar from '../components/ControlBar.jsx'
import FallbackPanel from '../components/FallbackPanel.jsx'
import MicToggleButton from '../components/MicToggleButton.jsx'

function DashboardPage({ send, connected, stage, setStage, useWs, onExit }) {
  // useWebSocket에서 분류된 정보 추출
  const { messages, voiceState, manualRecordingState, latestDanger, latestObjects, serverState } = useWs || {
    messages: [],
    voiceState: 'idle',
    manualRecordingState: 'idle',
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
      {/* 본문 — 좌: 카메라(최상단까지)+방향(아래) / 우: 헤더·단계·대화.
          풀폭 Header/StageStepper를 우측으로 옮겨 카메라가 화면 최상단까지 닿게 함. */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* 좌+중: 카메라(최상단부터) + 방향패널(캠 바로 아래) */}
        <div style={{ flex: 1, minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
          <CameraView stage={stage} objects={latestObjects} danger={latestDanger} />
          <div style={{ padding: '12px 16px 16px 16px' }}>
            <DirectionPanel objects={latestObjects} />
            <MicToggleButton
              state={manualRecordingState}
              connected={connected}
              send={send}
            />
          </div>
        </div>

        {/* 우: 헤더 + 단계 + 대화 */}
        <div style={{
          width: 380,
          minWidth: 340,
          borderLeft: '1px solid #eee',
          display: 'flex',
          flexDirection: 'column',
          padding: '12px 16px 16px 16px',
        }}>
          <Header connected={connected} sessionId={sessionId} compact />
          <StageStepper stage={stage} compact />
          <div style={{ flex: 1, background: 'white', borderRadius: 'var(--radius)', overflow: 'hidden', marginTop: 12 }}>
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

      <ControlBar send={send} stage={stage} onStageChange={handleStageChange} onExit={onExit} />
    </div>
  )
}

export default DashboardPage
