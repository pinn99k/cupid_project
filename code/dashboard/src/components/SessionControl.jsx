/**
 * Step 1-9: 세션 컨트롤 컴포넌트
 * 새 세션(TTS 캐시 초기화), Stage 전환, 학습 정지
 */

export default function SessionControl({ send }) {
  return (
    <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
      <button onClick={() => send({ event: "new_session" })}>
        새 세션 (캐시 초기화)
      </button>
      <button onClick={() => send({ event: "start_learning", stage: 1 })}>
        Stage 1
      </button>
      <button onClick={() => send({ event: "start_learning", stage: 2 })}>
        Stage 2
      </button>
      <button onClick={() => send({ event: "start_learning", stage: 3 })}>
        Stage 3
      </button>
      <button onClick={() => send({ event: "stop_learning" })}>
        정지
      </button>
    </div>
  );
}
