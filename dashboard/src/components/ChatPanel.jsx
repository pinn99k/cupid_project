import { useRef, useEffect } from 'react';

function formatTime(ts) {
  const d = ts ? new Date(ts) : new Date();
  return d.toLocaleTimeString('ko-KR');
}

export default function ChatPanel({ messages }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const visible = (messages || []).filter((m) => m.type !== 'init_state');

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

  // ack — centered system message
  if (msg.type === 'ack') {
    return (
      <div
        style={{
          textAlign: 'center',
          fontSize: 12,
          color: 'grey',
          margin: '8px 0',
        }}
      >
        &middot; {msg.message || `${msg.event || ''}`}
      </div>
    );
  }

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

  // SIA bubbles: stt_response, narration, danger
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
          {msg.message}
        </div>
      </div>
    </div>
  );
}
