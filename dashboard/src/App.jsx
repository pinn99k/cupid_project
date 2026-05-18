/**
 * Step 1-9: SIA 대시보드 메인 앱
 * WebSocket 연결 + 세션 관리 + Fallback + 실시간 로그
 */

import { useWebSocket } from "./hooks/useWebSocket";
import { useSpeechRecognition } from "./hooks/useSpeechRecognition";
import SessionControl from "./components/SessionControl";
import FallbackPanel from "./components/FallbackPanel";

const WS_URL = "ws://localhost:8000/ws";

function App() {
  const { ws, messages, connected, send } = useWebSocket(WS_URL);
  const { start: startSTT, stop: stopSTT } = useSpeechRecognition(ws);

  return (
    <div style={{ padding: 24, fontFamily: "sans-serif", maxWidth: 800, margin: "0 auto" }}>
      <h1>SIA Dashboard</h1>

      {/* 연결 상태 */}
      <p style={{ color: connected ? "green" : "red" }}>
        {connected ? "서버 연결됨" : "서버 연결 끊김"}
      </p>

      {/* 세션 컨트롤 */}
      <h2>세션 관리</h2>
      <SessionControl send={send} />

      {/* STT 컨트롤 */}
      <h2>음성 인식 (STT)</h2>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <button onClick={startSTT}>STT 시작</button>
        <button onClick={stopSTT}>STT 중지</button>
      </div>

      {/* Fallback 패널 */}
      <h2>Fallback 오디오</h2>
      <FallbackPanel send={send} />

      {/* 실시간 로그 */}
      <h2>실시간 메시지</h2>
      <div style={{
        maxHeight: 300, overflow: "auto",
        border: "1px solid #ccc", padding: 8, borderRadius: 4,
        backgroundColor: "#f9f9f9", fontSize: 13
      }}>
        {messages.length === 0 && <p style={{ color: "#999" }}>대기 중...</p>}
        {messages.map((msg, i) => (
          <div key={i} style={{
            padding: "4px 0",
            borderBottom: "1px solid #eee",
            color: msg.type === "danger" ? "red" : "inherit"
          }}>
            <strong>[{msg.type}]</strong> {msg.message || JSON.stringify(msg)}
          </div>
        ))}
      </div>
    </div>
  );
}

export default App;
