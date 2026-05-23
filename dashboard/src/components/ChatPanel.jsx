import { useRef, useEffect } from 'react';

function formatTime(ts) {
  const d = ts ? new Date(ts) : new Date();
  return d.toLocaleTimeString('ko-KR');
}

export default function ChatPanel({ messages, stage }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Stage별 필터링:
  // Stage 1, 2: 대화 메시지만 (user_stt, stt_response, error)
  // Stage 3: 대화 + 위험 메시지 (user_stt, stt_response, error, danger)
  const visible = (messages || []).filter((m) => {
    if (m.type === 'danger') {
      return stage === 3; // danger는 Stage 3일 때만 표시
    }
    return true; // user_stt, stt_response, error는 모두 표시
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '12px 16px',
          borderBottom: '1px solid #eee',
        }}
      >
        <span style={{ fontWeight: 'bold', fontSize: 16 }}>실시간 대화</span>
        <span style={{ color: 'grey', fontSize: 13 }}>
          {visible.length} messages
        </span>
      </div>

      {/* Message area */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
        {visible.map((msg, i) => (
          <MessageRow key={i} msg={msg} />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function MessageRow({ msg }) {
  const ts = formatTime(msg.timestamp);

  // error — centered red
  if (msg.type === 'error') {
    return (
      <div
        style={{
          textAlign: 'center',
          fontSize: 12,
          color: '#E53935',
          margin: '8px 0',
        }}
      >
        {msg.message}
      </div>
    );
  }

  // user_stt — child bubble (right)
  if (msg.type === 'user_stt') {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'flex-end',
          alignItems: 'flex-start',
          margin: '6px 0',
          gap: 8,
        }}
      >
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 11, color: 'grey', marginBottom: 2 }}>
            아이 {ts}
          </div>
          <div
            style={{
              background: '#EDE7F6',
              borderRadius: 12,
              padding: '10px 14px',
              maxWidth: '85%',
              display: 'inline-block',
              textAlign: 'left',
              fontSize: 14,
            }}
          >
            {msg.message}
          </div>
        </div>
        <div
          style={{
            width: 20,
            height: 20,
            borderRadius: '50%',
            background: '#B39DDB',
            color: 'white',
            fontSize: 11,
            fontWeight: 'bold',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          U
        </div>
      </div>
    );
  }

  // SIA bubbles: stt_response, danger
  const isDanger = msg.type === 'danger';
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'flex-start',
        alignItems: 'flex-start',
        margin: '6px 0',
        gap: 8,
      }}
    >
      <div
        style={{
          width: 20,
          height: 20,
          borderRadius: '50%',
          background: '#F4A7A7',
          color: 'white',
          fontSize: 11,
          fontWeight: 'bold',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        SIA
      </div>
      <div>
        <div style={{ fontSize: 11, color: 'grey', marginBottom: 2 }}>
          시아 {ts}
        </div>
        <div
          style={{
            background: isDanger ? '#FFF0F0' : '#fff',
            border: isDanger
              ? '1px solid #FFCDD2'
              : '1px solid #eee',
            borderRadius: 12,
            padding: '10px 14px',
            maxWidth: '85%',
            fontSize: 14,
          }}
        >
          {isDanger ? `위험: ${msg.object}` : msg.message}
        </div>
      </div>
    </div>
  );
}
