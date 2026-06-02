"""
음성→텍스트 변환 (Speech-to-Text).
- STTClient: SpeechRecognition 라이브러리로 Google 무료 STT 사용
- transcribe(): WAV bytes → 텍스트
"""

import asyncio
import io
import logging

import speech_recognition as sr

logger = logging.getLogger(__name__)


class STTClient:
    """Google Speech Recognition을 사용한 STT 클라이언트.

    SpeechRecognition 라이브러리의 Google 무료 API를 사용.
    별도 API 키 불필요 (Chrome Web Speech API와 동일 엔진).
    """

    def __init__(self, language: str = "ko-KR"):
        """
        Args:
            language: 인식 언어 코드 (기본값: 한국어 ko-KR)
        """
        self._recognizer = sr.Recognizer()
        self._language = language
        # 직전 결과 상태: "ok" | "unrecognized"(진짜 못알아들음) | "error"(네트워크/엔진 오류)
        self.last_status: str = "ok"

    # ------------------------------------------------------------------
    # 공개 비동기 인터페이스
    # ------------------------------------------------------------------

    async def transcribe(self, wav_bytes: bytes) -> str | None:
        """WAV bytes를 텍스트로 변환.

        블로킹 Google API 호출을 asyncio.to_thread로 래핑.

        Args:
            wav_bytes: WAV 포맷 오디오 데이터 (bytes)
        Returns:
            인식된 텍스트 str 또는 None (인식 불가 / 오류 시)
        """
        return await asyncio.to_thread(self._transcribe_sync, wav_bytes)

    # ------------------------------------------------------------------
    # 내부 동기 로직
    # ------------------------------------------------------------------

    def _transcribe_sync(self, wav_bytes: bytes) -> str | None:
        """동기 STT 처리.

        WAV bytes → sr.AudioData → Google STT API 호출.
        UnknownValueError: 음성 인식 불가 → None 반환
        RequestError: API 통신 오류 → None 반환 + 로그 기록
        """
        try:
            buf = io.BytesIO(wav_bytes)
            with sr.AudioFile(buf) as source:
                # STT INPUT 진단: 전달되는 오디오 길이 확인
                # (MicCapture 에서 잘린 경우 여기서 짧게 찍힘)
                audio = self._recognizer.record(source)

            # WAV 헤더(44byte) 제외한 오디오 데이터 크기로 실제 길이 계산
            # int16(2byte), 16kHz, mono
            audio_bytes = len(wav_bytes) - 44
            audio_sec = max(0.0, audio_bytes / (16000 * 2))
            print(
                f"[STT INPUT]"
                f" duration={audio_sec:.2f}s"
                f" bytes={len(wav_bytes)}"
                f" audio_bytes={audio_bytes}"
            )

            text = self._recognizer.recognize_google(audio, language=self._language)
            if text and text.strip():
                self.last_status = "ok"
                return text.strip()
            self.last_status = "unrecognized"
            return None

        except sr.UnknownValueError:
            # 음성이 있지만 인식 불가 (발음 불분명, 잡음 등) — 진짜 '못 알아들음'
            self.last_status = "unrecognized"
            print("[STT] 음성 인식 불가 (UnknownValueError)")
            return None

        except sr.RequestError as e:
            # Google 무료 STT 통신 오류(네트워크/할당량) — 사용자 잘못 아님
            self.last_status = "error"
            print(f"[STT] ⚠ Google STT API 오류(네트워크/할당량 의심): {e}")
            return None

        except Exception as e:
            self.last_status = "error"
            print(f"[STT] ⚠ 예상치 못한 오류: {type(e).__name__}: {e}")
            return None
