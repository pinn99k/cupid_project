export default function STTInput({ isListening, onToggle }) {
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
          background: isListening
            ? 'linear-gradient(to right, rgba(76,175,80,0.15), rgba(76,175,80,0.05))'
            : '#f5f5f5',
          border: isListening
            ? '1px solid rgba(76,175,80,0.3)'
            : '1px solid #eee',
        }}
      >
        {/* Left: dot + label */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div
            style={{
              width: 10,
              height: 10,
              borderRadius: '50%',
              background: isListening ? 'var(--green, #4CAF50)' : '#bbb',
              animation: isListening ? 'pulse 1.5s infinite' : 'none',
            }}
          />
          <span style={{ fontSize: 13, color: isListening ? '#333' : '#999' }}>
            {isListening ? '음성 인식 중...' : '마이크를 눌러 시작'}
          </span>
        </div>

        {/* Right: mic button */}
        <button
          onClick={onToggle}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontSize: 20,
            padding: 4,
            filter: isListening ? 'none' : 'grayscale(100%)',
            opacity: isListening ? 1 : 0.5,
          }}
          title={isListening ? '음성 인식 중지' : '음성 인식 시작'}
        >
          🎤
        </button>
      </div>
    </>
  );
}
