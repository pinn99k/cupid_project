const STATE_CONFIG = {
  idle: {
    bg: '#f5f5f5',
    border: '1px solid #eee',
    dotColor: '#bbb',
    dotAnim: 'none',
    label: '마이크를 눌러 시작',
    labelColor: '#999',
  },
  listening: {
    bg: 'linear-gradient(to right, rgba(76,175,80,0.15), rgba(76,175,80,0.05))',
    border: '1px solid rgba(76,175,80,0.3)',
    dotColor: '#4CAF50',
    dotAnim: 'pulse 1.5s infinite',
    label: '음성 인식 중...',
    labelColor: '#333',
  },
  responding: {
    bg: 'linear-gradient(to right, rgba(244,167,167,0.2), rgba(244,167,167,0.05))',
    border: '1px solid rgba(244,167,167,0.4)',
    dotColor: '#F4A7A7',
    dotAnim: 'pulse 1.5s infinite',
    label: '시아가 말하는 중...',
    labelColor: '#666',
  },
};

export default function STTInput({ voiceState = 'idle', onToggle }) {
  const cfg = STATE_CONFIG[voiceState] || STATE_CONFIG.idle;

  return (
    <>
      <style>{`
        @keyframes pulse {
          0% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.5; transform: scale(1.3); }
          100% { opacity: 1; transform: scale(1); }
        }
      `}</style>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 16px',
          borderRadius: 24,
          background: cfg.bg,
          border: cfg.border,
          transition: 'all 0.3s ease',
        }}
      >
        {/* Left: dot + label */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div
            style={{
              width: 10,
              height: 10,
              borderRadius: '50%',
              background: cfg.dotColor,
              animation: cfg.dotAnim,
            }}
          />
          <span style={{ fontSize: 13, color: cfg.labelColor }}>
            {cfg.label}
          </span>
        </div>

        {/* Right: mic button (마스터 토글) */}
        <button
          onClick={onToggle}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontSize: 20,
            padding: 4,
            filter: voiceState === 'idle' ? 'grayscale(100%)' : 'none',
            opacity: voiceState === 'idle' ? 0.5 : 1,
          }}
          title={voiceState === 'idle' ? '음성 인식 시작' : '음성 인식 중지'}
        >
          🎤
        </button>
      </div>
    </>
  );
}
