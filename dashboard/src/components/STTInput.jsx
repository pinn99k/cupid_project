const STATE_CONFIG = {
  idle: {
    bg: '#f5f5f5',
    border: '1px solid #eee',
    dotColor: '#bbb',
    dotAnim: 'none',
    label: '대기 중...',
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
  processing: {
    bg: 'linear-gradient(to right, rgba(33,150,243,0.15), rgba(33,150,243,0.05))',
    border: '1px solid rgba(33,150,243,0.3)',
    dotColor: '#2196F3',
    dotAnim: 'pulse 1.5s infinite',
    label: '생각하는 중...',
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

export default function STTInput({ voiceState = 'idle' }) {
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
          padding: '10px 16px',
          borderRadius: 24,
          background: cfg.bg,
          border: cfg.border,
          transition: 'all 0.3s ease',
        }}
      >
        {/* dot + label */}
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
      </div>
    </>
  );
}
