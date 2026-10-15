import { useState, useEffect } from "react";

export default function Header({ connected, sessionId, compact = false }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");

  // 좁은 우측 컬럼용 콤팩트 헤더 (세로 스택)
  if (compact) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: "2px 2px 4px 2px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 18, fontWeight: "bold", color: "var(--text-primary)" }}>SIA</span>
          <span style={{ fontSize: 10, color: "var(--text-secondary)" }}>BY CUPID</span>
          <span
            style={{
              marginLeft: "auto",
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              padding: "3px 10px",
              borderRadius: 999,
              fontSize: 11,
              fontWeight: 500,
              color: "#fff",
              background: connected ? "var(--green)" : "var(--red)",
            }}
          >
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#fff", display: "inline-block" }} />
            {connected ? "연결됨" : "끊김"}
          </span>
        </div>
        <div style={{ display: "flex", gap: 12, fontFamily: "monospace", fontSize: 12, color: "var(--text-secondary)" }}>
          <span style={{ color: "var(--text-primary)" }}>{mm}분 {ss}초</span>
          {sessionId && <span>{sessionId}</span>}
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "16px 24px",
      }}
    >
      {/* Left */}
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div
          style={{
            width: 40,
            height: 40,
            borderRadius: "50%",
            background: "#FDE8E8",
            border: "2px solid #F4A7A7",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 12,
            fontWeight: "bold",
            color: "var(--text-primary)",
          }}
        >
          CUPID
        </div>
        <span style={{ fontSize: 24, fontWeight: "bold", color: "var(--text-primary)" }}>
          SIA
        </span>
        <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>BY CUPID</span>
      </div>

      {/* Right */}
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <span
          style={{
            fontFamily: "monospace",
            fontSize: 13,
            color: "var(--text-secondary)",
          }}
        >
          {sessionId}
        </span>
        <span
          style={{
            fontFamily: "monospace",
            fontSize: 13,
            color: "var(--text-primary)",
          }}
        >
          {mm}분 {ss}초
        </span>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            padding: "4px 12px",
            borderRadius: 999,
            fontSize: 12,
            fontWeight: 500,
            color: "#fff",
            background: connected ? "var(--green)" : "var(--red)",
          }}
        >
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: "#fff",
              display: "inline-block",
            }}
          />
          {connected ? "서버 연결됨" : "서버 연결 끊김"}
        </span>
      </div>
    </div>
  );
}
