import { useEffect } from 'react'

function StartPage({ connected, onStart }) {
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.code === 'Space') {
        e.preventDefault()
        onStart()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onStart])

  return (
    <div style={{
      minHeight: '100vh',
      background: 'radial-gradient(ellipse at center, #FFF5F5 0%, #FDE8E8 50%, #FAF0E6 100%)',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      position: 'relative',
    }}>
      {/* Top left - CUPID badge */}
      <div style={{
        position: 'absolute',
        top: 24,
        left: 24,
        display: 'flex',
        alignItems: 'center',
        gap: 10,
      }}>
        <div style={{
          width: 36,
          height: 36,
          borderRadius: '50%',
          background: 'var(--pink-primary)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'white',
          fontSize: 11,
          fontWeight: 700,
        }}>
          CUPID
        </div>
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
          CUPID · SIA
        </span>
      </div>

      {/* Top right - connection status */}
      <div style={{
        position: 'absolute',
        top: 24,
        right: 24,
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '8px 16px',
        borderRadius: 20,
        background: 'rgba(255,255,255,0.7)',
        backdropFilter: 'blur(8px)',
      }}>
        <div style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: connected ? 'var(--green)' : 'var(--red)',
        }} />
        <span style={{ fontSize: 13, color: 'var(--text-primary)' }}>
          {connected ? '서버 연결됨' : '서버 연결 끊김'}
        </span>
      </div>

      {/* Center content */}
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 16,
      }}>
        <h1 style={{
          fontSize: 140,
          fontWeight: 900,
          letterSpacing: -4,
          color: '#1E1E1E',
          margin: 0,
          lineHeight: 1,
        }}>
          SIA
        </h1>

        <p style={{
          fontSize: 18,
          color: 'var(--text-secondary)',
          margin: '0 0 32px 0',
        }}>
          시각장애 유아 보행 교육 파트너 · by CUPID
        </p>

        <button
          onClick={onStart}
          style={{
            background: 'var(--pink-primary)',
            padding: '18px 64px',
            borderRadius: 28,
            fontSize: 24,
            color: 'white',
            fontWeight: 600,
            boxShadow: '0 4px 20px rgba(244, 167, 167, 0.4)',
            transition: 'transform 0.15s, box-shadow 0.15s',
          }}
        >
          시작하기
        </button>
      </div>

      {/* Bottom hint */}
      <div style={{
        position: 'absolute',
        bottom: 32,
        letterSpacing: 3,
        fontSize: 13,
        color: 'var(--text-secondary)',
      }}>
        SPACE BAR OR TAP TO BEGIN
      </div>
    </div>
  )
}

export default StartPage
