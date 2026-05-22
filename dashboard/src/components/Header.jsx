import { useState, useEffect } from "react";

export default function Header({ connected, sessionId }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");

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
