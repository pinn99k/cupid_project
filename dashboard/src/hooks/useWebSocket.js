import { useCallback, useEffect, useRef, useState } from "react";

export function useWebSocket(url) {
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const dangerTimerRef = useRef(null);
  const disconnectedNotifiedRef = useRef(false);
  const [messages, setMessages] = useState([]);
  const [voiceState, setVoiceState] = useState("idle");
  const [manualRecordingState, setManualRecordingState] = useState("idle");
  const [latestDanger, setLatestDanger] = useState(null);
  const [latestObjects, setLatestObjects] = useState([]);
  const [serverState, setServerState] = useState({});
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let closedByEffect = false;

    const connect = () => {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        disconnectedNotifiedRef.current = false;
        setConnected(true);
      };
      ws.onclose = () => {
        setConnected(false);
        setManualRecordingState("idle");
        if (!closedByEffect && !disconnectedNotifiedRef.current) {
          disconnectedNotifiedRef.current = true;
          setMessages((prev) => [
            ...prev.slice(-50),
            {
              type: "error",
              message: "서버 연결이 끊어졌습니다.",
              timestamp: Date.now(),
            },
          ]);
        }
        if (!closedByEffect) {
          reconnectTimerRef.current = window.setTimeout(connect, 1500);
        }
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (event) => {
        let data;
        try {
          data = JSON.parse(event.data);
        } catch {
          return;
        }
        const type = data.type;

        if (type === "init_state" || type === "ack") {
          setServerState((prev) => ({ ...prev, ...data }));
          if (data.recording_state) setManualRecordingState(data.recording_state);
        }
        if (type === "ack" && ["new_session", "stop_learning"].includes(data.event)) {
          setMessages([]);
          setLatestDanger(null);
          setLatestObjects([]);
        }
        if (["user_stt", "stt_response", "narration", "danger", "error"].includes(type)) {
          setMessages((prev) => [...prev.slice(-50), data]);
        }
        if (type === "voice_listening") setVoiceState("listening");
        if (type === "voice_processing") setVoiceState("processing");
        if (type === "tts_start") setVoiceState("responding");
        if (type === "tts_done") setVoiceState("listening");
        if (type === "voice_idle") setVoiceState("idle");
        if (type === "recording_state") {
          setManualRecordingState(data.state || "idle");
        }
        if (type === "detections_update" && data.objects) {
          setLatestObjects(data.objects);
        }
        if (type === "danger") {
          setLatestDanger(data);
          window.clearTimeout(dangerTimerRef.current);
          dangerTimerRef.current = window.setTimeout(() => setLatestDanger(null), 3500);
        }
      };
    };

    connect();
    return () => {
      closedByEffect = true;
      window.clearTimeout(reconnectTimerRef.current);
      window.clearTimeout(dangerTimerRef.current);
      wsRef.current?.close();
    };
  }, [url]);

  const send = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  const clearMessages = useCallback(() => setMessages([]), []);

  return {
    messages,
    voiceState,
    manualRecordingState,
    latestDanger,
    latestObjects,
    serverState,
    connected,
    send,
    clearMessages,
  };
}
