/**
 * WebSocket 커스텀 훅
 * 메시지 타입별 분류 저장:
 * - messages: 대화 메시지만 (user_stt, stt_response, narration, error)
 * - voiceState: 최신 음성 상태 (voice_listening, tts_start, tts_done)
 * - latestDanger: 최신 위험 정보 (danger, Stage 3 전용)
 * - latestObjects: 최신 감지 객체 (narration, danger에서 추출)
 */

import { useEffect, useRef, useState, useCallback } from "react";

export function useWebSocket(url) {
  const wsRef = useRef(null);
  const [messages, setMessages] = useState([]); // 대화 메시지만
  const [voiceState, setVoiceState] = useState('idle'); // 최신 음성 상태
  const [latestDanger, setLatestDanger] = useState(null); // 최신 위험 정보
  const [latestObjects, setLatestObjects] = useState([]); // 최신 감지 객체
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const ws = new WebSocket(url);
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      const type = data.type;

      // 1. 대화 메시지 저장 (user_stt, stt_response, narration, error)
      if (type === 'user_stt' || type === 'stt_response' || type === 'narration' || type === 'error') {
        setMessages((prev) => [...prev.slice(-50), data]);
      }

      // 2. 음성 상태 업데이트
      if (type === 'voice_listening') setVoiceState('listening');
      if (type === 'voice_processing') setVoiceState('processing');
      if (type === 'tts_start') setVoiceState('responding');
      if (type === 'tts_done') setVoiceState('listening');
      if (type === 'voice_idle') setVoiceState('idle');

      // 3. 위험 정보 업데이트 (Stage 3 전용)
      if (type === 'danger') {
        setLatestDanger(data);
        setLatestObjects([{
          label: data.object,
          direction: data.direction,
          distance_cm: data.distance_cm
        }]);
      }

      // 4. 감지 객체 업데이트 (narration에서)
      if (type === 'narration' && data.objects) {
        setLatestObjects(data.objects);
      }
    };
    wsRef.current = ws;
    return () => ws.close();
  }, [url]);

  const send = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  const clearMessages = useCallback(() => setMessages([]), []);

  return {
    ws: wsRef.current,
    messages,        // 대화 메시지만
    voiceState,      // 최신 음성 상태
    latestDanger,    // 최신 위험 정보
    latestObjects,   // 최신 감지 객체
    connected,
    send,
    clearMessages
  };
}
