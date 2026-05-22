/**
 * 반이중 음성 인식 훅.
 * - start/stop: 사용자 토글 (마스터 스위치)
 * - pause/resume: 시스템 제어 (TTS 재생 중 자동 정지/복귀)
 * - onend 시 activeRef && !pausedRef 일 때만 자동 재시작
 */

import { useRef, useCallback } from "react";

export function useSpeechRecognition(ws) {
  const recognitionRef = useRef(null);
  const activeRef = useRef(false);   // 사용자가 STT를 켠 상태
  const pausedRef = useRef(false);   // TTS 재생으로 시스템이 일시정지

  const _createRecognition = useCallback(() => {
    if (!("webkitSpeechRecognition" in window)) {
      console.error("Web Speech API 미지원 브라우저");
      return null;
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

    recognition.onerror = (e) => {
      // "aborted"는 pause/stop 시 정상 발생 — 무시
      if (e.error !== "aborted") {
        console.error("[STT Error]", e.error);
      }
    };

    recognition.onend = () => {
      // 사용자가 켜놨고 + 시스템이 일시정지하지 않았을 때만 재시작
      if (activeRef.current && !pausedRef.current) {
        try {
          recognition.start();
        } catch (e) {
          // 이미 시작된 경우 무시
        }
      }
    };

    return recognition;
  }, [ws]);

  /** 사용자가 STT 켜기 */
  const start = useCallback(() => {
    activeRef.current = true;
    pausedRef.current = false;
    // 기존 인스턴스 정리
    try { recognitionRef.current?.stop(); } catch (e) { /* ignore */ }
    const rec = _createRecognition();
    if (rec) {
      rec.start();
      recognitionRef.current = rec;
    }
  }, [_createRecognition]);

  /** 사용자가 STT 끄기 (마스터 오프) */
  const stop = useCallback(() => {
    activeRef.current = false;
    pausedRef.current = false;
    try { recognitionRef.current?.stop(); } catch (e) { /* ignore */ }
  }, []);

  /** TTS 재생 시작 → STT 일시정지 */
  const pause = useCallback(() => {
    pausedRef.current = true;
    try { recognitionRef.current?.stop(); } catch (e) { /* ignore */ }
  }, []);

  /** TTS 재생 완료 → STT 복귀 (사용자가 켜놨을 때만) */
  const resume = useCallback(() => {
    pausedRef.current = false;
    if (activeRef.current) {
      try { recognitionRef.current?.stop(); } catch (e) { /* ignore */ }
      const rec = _createRecognition();
      if (rec) {
        rec.start();
        recognitionRef.current = rec;
      }
    }
  }, [_createRecognition]);

  return { start, stop, pause, resume };
}
