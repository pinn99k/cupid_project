const STAGE_LABELS = ["수용", "방향", "기술"];

export default function ControlBar({ send, stage, onStageChange }) {
  const outlineBtn = {
    border: "1px solid var(--pink-primary)",
    color: "var(--pink-primary)",
    background: "#fff",
    borderRadius: 6,
    padding: "6px 16px",
    cursor: "pointer",
    fontSize: 13,
  };

  const greyOutlineBtn = {
    ...outlineBtn,
    border: "1px solid #ccc",
    color: "#666",
  };

  return (
    <div
      style={{
        position: "sticky",
        bottom: 0,
        background: "#fff",
        borderTop: "1px solid #eee",
        padding: "12px 24px",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
      }}
    >
      {/* Left: 세션 */}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span
          style={{
            fontSize: 12,
            color: "#999",
            letterSpacing: 4,
            marginRight: 4,
          }}
        >
          세 션
        </span>
        <button
          style={outlineBtn}
          onClick={() => send({ event: "new_session" })}
        >
          새 세션
        </button>
        <button
          style={greyOutlineBtn}
          onClick={() => send({ event: "clear_tts_cache" })}
        >
          캐시 초기화
        </button>
      </div>

      {/* Center: 단계 */}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span
          style={{
            fontSize: 12,
            color: "#999",
            letterSpacing: 4,
            marginRight: 4,
          }}
        >
          단 계
        </span>
        {STAGE_LABELS.map((label, i) => {
          const n = i + 1;
          const active = n === stage;
          return (
            <button
              key={n}
              style={{
                background: active ? "var(--pink-primary)" : "#eee",
                color: active ? "#fff" : "var(--dark)",
                border: "none",
                borderRadius: 6,
                padding: "6px 16px",
                cursor: "pointer",
                fontSize: 13,
                fontWeight: active ? "bold" : "normal",
              }}
              onClick={() => onStageChange(n)}
            >
              {label}
            </button>
          );
        })}
      </div>

      {/* Right */}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <button style={greyOutlineBtn}>서버 로그 펼치기</button>
        <button
          style={{
            background: "var(--red)",
            color: "#fff",
            border: "none",
            borderRadius: 6,
            padding: "8px 20px",
            fontWeight: "bold",
            cursor: "pointer",
            fontSize: 13,
          }}
          onClick={() => send({ event: "stop_learning" })}
        >
          긴급 정지
        </button>
      </div>
    </div>
  );
}
