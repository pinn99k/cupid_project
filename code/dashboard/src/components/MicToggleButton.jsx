import { useEffect, useMemo, useState } from "react";

const MAX_SECONDS = 15;

function MicIcon({ kind = "mic", size = 38 }) {
  if (kind === "speaker") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M4 9v6h4l5 4V5L8 9H4Z" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M16.5 8.5a5 5 0 0 1 0 7" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
        <path d="M19 6a8 8 0 0 1 0 12" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
      </svg>
    );
  }

  if (kind === "spinner") {
    return (
      <svg className="mic-toggle-spin" width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M12 3a9 9 0 1 0 9 9" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" />
      </svg>
    );
  }

  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="9" y="3" width="6" height="11" rx="3" stroke="currentColor" strokeWidth="1.9" />
      <path d="M5.5 11a6.5 6.5 0 0 0 13 0" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
      <path d="M12 17.5V21" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
      <path d="M8.5 21h7" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  );
}

export default function MicToggleButton({ state = "idle", connected = true, send, compact = false }) {
  const [optimisticState, setOptimisticState] = useState(state);
  const [remaining, setRemaining] = useState(MAX_SECONDS);

  useEffect(() => {
    const timer = window.setTimeout(() => setOptimisticState(state || "idle"), 0);
    return () => window.clearTimeout(timer);
  }, [state]);

  useEffect(() => {
    if (!connected) {
      const timer = window.setTimeout(() => setOptimisticState("idle"), 0);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [connected]);

  useEffect(() => {
    if (optimisticState !== "recording") {
      const timer = window.setTimeout(() => setRemaining(MAX_SECONDS), 0);
      return () => window.clearTimeout(timer);
    }
    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      const elapsed = Math.floor((Date.now() - startedAt) / 1000);
      setRemaining(Math.max(0, MAX_SECONDS - elapsed));
    }, 250);
    return () => window.clearInterval(timer);
  }, [optimisticState]);

  const view = useMemo(() => {
    if (!connected) {
      return {
        bg: "#F9FAFB",
        border: "#E5E7EB",
        color: "#9CA3AF",
        label: "서버 연결 대기 중",
        labelColor: "#6B7280",
        icon: "mic",
        disabled: true,
      };
    }
    if (optimisticState === "recording") {
      return {
        bg: "#EF4444",
        border: "#EF4444",
        color: "#FFFFFF",
        label: `녹음 중 · 다시 클릭하면 종료 (Space) · 남은 시간 ${remaining}초`,
        labelColor: "#DC2626",
        icon: "mic",
        disabled: false,
      };
    }
    if (optimisticState === "processing") {
      return {
        bg: "#F59E0B",
        border: "#F59E0B",
        color: "#FFFFFF",
        label: "처리 중...",
        labelColor: "#B45309",
        icon: "spinner",
        disabled: true,
      };
    }
    if (optimisticState === "speaking") {
      return {
        bg: "#EC4899",
        border: "#EC4899",
        color: "#FFFFFF",
        label: "시아 응답 중...",
        labelColor: "#DB2777",
        icon: "speaker",
        disabled: true,
      };
    }
    return {
      bg: "#F9FAFB",
      border: "#E5E7EB",
      color: "#374151",
      label: "클릭해서 말하기 (Space)",
      labelColor: "#6B7280",
      icon: "mic",
      disabled: false,
    };
  }, [connected, optimisticState, remaining]);

  const toggle = () => {
    if (view.disabled) return;
    if (optimisticState === "idle") {
      setOptimisticState("recording");
      setRemaining(MAX_SECONDS);
      send({ event: "start_recording" });
      return;
    }
    if (optimisticState === "recording") {
      setOptimisticState("processing");
      send({ event: "stop_recording" });
    }
  };

  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.code !== "Space") return;
      const target = event.target;
      const tag = target?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || target?.isContentEditable) return;
      event.preventDefault();
      toggle();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  const isRecording = optimisticState === "recording";

  const buttonSize = compact ? 52 : 96;

  return (
    <div className={`mic-toggle-wrap${compact ? " compact" : ""}`}>
      <style>{`
        .mic-toggle-wrap {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 9px;
          margin: 8px 0 4px;
        }
        .mic-toggle-wrap.compact {
          margin: 0;
          gap: 0;
          flex-shrink: 0;
        }
        .mic-toggle-button {
          position: relative;
          width: 96px;
          height: 96px;
          border-radius: 999px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          transition: background-color 200ms ease, border-color 200ms ease, transform 200ms ease, box-shadow 200ms ease;
          outline: none;
        }
        .mic-toggle-button:hover:not(:disabled) {
          transform: translateY(-1px);
          box-shadow: 0 12px 30px rgba(17, 24, 39, 0.12);
        }
        .mic-toggle-button.idle:hover:not(:disabled) {
          background: #F3F4F6 !important;
        }
        .mic-toggle-button:disabled {
          cursor: not-allowed;
          opacity: 0.92;
        }
        .mic-toggle-button.recording {
          animation: mic-toggle-scale 1s ease-in-out infinite;
        }
        .mic-toggle-ping {
          position: absolute;
          inset: -8px;
          border-radius: 999px;
          background: rgba(239, 68, 68, 0.28);
          animation: mic-toggle-ping 1s cubic-bezier(0, 0, 0.2, 1) infinite;
          pointer-events: none;
        }
        .mic-toggle-spin {
          animation: mic-toggle-spin 0.9s linear infinite;
        }
        .mic-toggle-label {
          min-height: 20px;
          font-size: 12px;
          font-weight: 600;
          text-align: center;
          transition: color 200ms ease;
        }
        @keyframes mic-toggle-scale {
          0%, 100% { transform: scale(1); }
          50% { transform: scale(1.1); }
        }
        @keyframes mic-toggle-ping {
          0% { transform: scale(0.92); opacity: 0.65; }
          75%, 100% { transform: scale(1.32); opacity: 0; }
        }
        @keyframes mic-toggle-spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
      <button
        type="button"
        className={`mic-toggle-button ${optimisticState}`}
        onClick={toggle}
        disabled={view.disabled}
        aria-label={view.label}
        title={view.label}
        style={{
          background: view.bg,
          border: `2px solid ${view.border}`,
          color: view.color,
          cursor: view.disabled ? "not-allowed" : "pointer",
          width: buttonSize,
          height: buttonSize,
        }}
      >
        {isRecording && <span className="mic-toggle-ping" />}
        <span style={{ position: "relative", zIndex: 1, display: "inline-flex" }}>
          <MicIcon kind={view.icon} size={compact ? 26 : 38} />
        </span>
      </button>
      {!compact && (
        <div className="mic-toggle-label" style={{ color: view.labelColor }}>
          {view.label}
        </div>
      )}
    </div>
  );
}
