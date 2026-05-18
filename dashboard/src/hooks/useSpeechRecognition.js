/**
 * Step 1-7: Web Speech API → WebSocket → LLM → TTS
 * Chrome 한국어 음성 인식 → WebSocket으로 서버 전송
 */

import { useRef, useCallback } from "react";

export function useSpeechRecognition(ws, enabled = true) {
  const recognitionRef = useRef(null);

  const start = useCallback(() => {
    if (!("webkitSpeechRecognition" in window)) {
      console.error("Web Speech API 미지원 브라우저");
      return;
    }
    const recognition = new window.webkitSpeechRecognition();
    recognition.lang = "ko-KR";
    recognition.continuous = true;
    recognition.interimResults = false;

    recognition.onresult = (event) => {
      const last = event.results[event.results.length - 1];
      if (last.isFinal) {
        const text = last[0].transcript.trim();
        console.log(`[STT] "${text}"`);
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ stt_text: text }));
        }
      }
    };
    recognition.onerror = (e) => console.error("[STT Error]", e.error);
    recognition.onend = () => { if (enabled) recognition.start(); };
    recognition.start();
    recognitionRef.current = recognition;
  }, [ws, enabled]);

  const stop = useCallback(() => { recognitionRef.current?.stop(); }, []);

  return { start, stop };
}
