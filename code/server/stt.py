"""
음성→텍스트 변환 (Speech-to-Text).
- STTClient: SpeechRecognition 라이브러리로 Google 무료 STT 사용
- transcribe(): WAV bytes → 텍스트
"""

import asyncio
import io
import logging
import os
import wave

import numpy as np
import speech_recognition as sr
from scipy import signal as _sps

# STT 전처리 옵션 (노이즈 환경 최적화). 문제가 생기면 env로 끌 수 있다.
# ⚠️ 스펙트럼 노이즈제거(noisereduce)는 이 환경에서 torch/numpy 충돌 + 신호 왜곡이라
#    쓰지 않는다. '안전한' 처리만: 고역통과(럼블 제거) + 완만한 저음량 증폭.
_STT_HPF_HZ = float(os.getenv("STT_HPF_HZ", "90"))     # 고역통과 차단주파수(0=끔)
_STT_MAX_GAIN = float(os.getenv("STT_MAX_GAIN", "4"))  # 저음량 최대 증폭배수(과증폭=노이즈↑ 방지)

logger = logging.getLogger(__name__)


def _preprocess_for_stt(
    wav_bytes: bytes, target_peak: float = 0.8
) -> tuple[bytes, float, float, float, str]:
    """STT 인식률을 위한 '안전한' 전처리.

    순서: (1) 고역통과로 럼블/HVAC/핸들링 저주파 노이즈 제거(발화 대역은 보존) →
          (2) 저음량 자동 증폭(노트북 마이크가 작게 잡을 때만, 과증폭은 노이즈도
              키우므로 _STT_MAX_GAIN로 제한).
    스펙트럼 노이즈제거는 왜곡 위험이 커서 쓰지 않는다. 실패 시 원본으로 폴백.
    반환: (처리된 wav_bytes, rms[0~1], peak[0~1], gain, 적용단계 문자열).
    """
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            nch, sw, fr = wf.getnchannels(), wf.getsampwidth(), wf.getframerate()
            raw = wf.readframes(wf.getnframes())
        if sw != 2:  # int16만 처리
            return wav_bytes, 0.0, 0.0, 1.0, "skip(non-int16)"
        a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if nch > 1:
            a = a.reshape(-1, nch).mean(axis=1)
        if a.size == 0:
            return wav_bytes, 0.0, 0.0, 1.0, "skip(empty)"

        peak0 = float(np.max(np.abs(a)))
        rms = float(np.sqrt(np.mean(a * a)))
        steps: list[str] = []

        # (1) 고역통과 — 럼블/저주파 노이즈 제거 (90Hz↓만 깎아 발화는 보존)
        if _STT_HPF_HZ > 0 and fr > 2 * _STT_HPF_HZ:
            sos = _sps.butter(2, _STT_HPF_HZ / (fr / 2), btype="highpass", output="sos")
            a = _sps.sosfilt(sos, a).astype(np.float32)
            steps.append(f"hpf{int(_STT_HPF_HZ)}")

        # (2) 저음량 증폭 — 피크가 낮을 때만, 최대 _STT_MAX_GAIN배(클리핑 없이)
        peak = float(np.max(np.abs(a)))
        gain = 1.0
        if 0.0 < peak < target_peak:
            gain = min(_STT_MAX_GAIN, target_peak / peak)
            a = np.clip(a * gain, -1.0, 1.0)
            steps.append(f"gain{gain:.1f}x")

        out = io.BytesIO()
        with wave.open(out, "wb") as wo:
            wo.setnchannels(1)
            wo.setsampwidth(2)
            wo.setframerate(fr)
            wo.writeframes((a * 32767.0).astype(np.int16).tobytes())
        return out.getvalue(), rms, peak0, gain, "+".join(steps) or "none"
    except Exception as e:
        return wav_bytes, 0.0, 0.0, 1.0, f"error({type(e).__name__})"


def _wav_to_float32(wav_bytes: bytes) -> np.ndarray:
    """WAV bytes(16kHz int16) → float32 mono [-1,1] numpy 배열 (Whisper 입력용)."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        channels = wf.getnchannels()
        raw = wf.readframes(wf.getnframes())
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio


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
            # 노이즈 환경 최적화 전처리(고역통과+노이즈감소+저음량증폭) + 음량 통계.
            norm_bytes, rms, peak, gain, steps = _preprocess_for_stt(wav_bytes)

            buf = io.BytesIO(norm_bytes)
            with sr.AudioFile(buf) as source:
                audio = self._recognizer.record(source)

            # WAV 헤더(44byte) 제외한 오디오 데이터 크기로 실제 길이 계산
            # int16(2byte), 16kHz, mono
            audio_bytes = len(wav_bytes) - 44
            audio_sec = max(0.0, audio_bytes / (16000 * 2))

            # 런타임 언어(운영자 토글)에 맞춰 인식 언어 선택. ko→ko-KR, en→en-US.
            from server.config import get_runtime_language, STT_LANG_CODES
            lang_code = STT_LANG_CODES.get(get_runtime_language(), self._language)

            # 진단 로그: 어떤 언어로 인식하는지 + 음량(rms/peak) + 적용 게인.
            # peak가 0.02 미만이면 사실상 무음 → 마이크가 발화를 못 잡은 것(거리/장치 문제).
            _quiet = " ⚠️거의무음(마이크 확인)" if peak < 0.02 else ""
            print(
                f"[STT INPUT]"
                f" duration={audio_sec:.2f}s"
                f" bytes={len(wav_bytes)}"
                f" lang={lang_code}"
                f" rms={rms:.3f} peak={peak:.3f} gain={gain:.1f}x"
                f" proc=[{steps}]{_quiet}"
            )

            text = self._recognizer.recognize_google(audio, language=lang_code)
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


class WhisperSTTClient:
    """로컬 Whisper(faster-whisper) STT. STTClient와 동일 인터페이스.

    오프라인·무료. 모델은 최초 사용 시 1회 로드(워밍업 권장).
    실패 시 fallback(STTClient)으로 폴백 → 데모 안전.
    """

    def __init__(
        self,
        model_size: str = "small",
        device: str = "auto",
        compute_type: str = "int8",
        language: str = "ko",
        beam_size: int = 5,
        vad_filter: bool = False,
        no_speech_threshold: float = 0.6,
        logprob_threshold: float = -1.0,
        fallback: "STTClient | None" = None,
    ):
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._language = language
        self._beam_size = beam_size
        self._vad_filter = vad_filter
        self._no_speech_threshold = no_speech_threshold
        self._logprob_threshold = logprob_threshold
        self._fallback = fallback
        self._model = None  # lazy load
        self.last_status: str = "ok"

    def _ensure_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel  # noqa: PLC0415
            print(
                f"[STT] Whisper 모델 로드: {self._model_size}"
                f" (device={self._device}, compute={self._compute_type})"
            )
            self._model = WhisperModel(
                self._model_size, device=self._device, compute_type=self._compute_type
            )

    def warmup(self) -> None:
        """모델 로드 + 무음 더미 추론(콜드스타트 방지). best-effort, 동기."""
        try:
            self._ensure_model()
            silent = np.zeros(16000, dtype=np.float32)
            segs, _ = self._model.transcribe(silent, language=self._language, beam_size=1)
            list(segs)  # generator 소진
            print("[STT] Whisper 워밍업 완료")
        except Exception as e:
            print(f"[STT] Whisper 워밍업 오류(무시): {e}")

    async def transcribe(self, wav_bytes: bytes) -> str | None:
        return await asyncio.to_thread(self._transcribe_sync, wav_bytes)

    def _transcribe_sync(self, wav_bytes: bytes) -> str | None:
        try:
            self._ensure_model()
            audio = _wav_to_float32(wav_bytes)
            # 임계값을 transcribe()에 직접 전달 → faster-whisper가 올바른 AND 로직
            # (no_speech_prob 높음 그리고 avg_logprob 낮음)으로 내부 필터.
            segments, _info = self._model.transcribe(
                audio,
                language=self._language,
                beam_size=self._beam_size,
                vad_filter=self._vad_filter,
                condition_on_previous_text=False,  # 환각 루프 방지
                no_speech_threshold=self._no_speech_threshold,
                log_prob_threshold=self._logprob_threshold,
            )
            # ⚠️ 추가 OR-필터 제거: 시끄러운 환경에서 실제 발화까지 과도하게 버려
            #    "인식 결과 없음"이 양산되던 근본 원인. 내부 필터 결과를 그대로 사용.
            text = " ".join(seg.text.strip() for seg in segments).strip()
            if text:
                self.last_status = "ok"
                return text
            self.last_status = "unrecognized"
            print("[STT] Whisper 인식 결과 없음")
            return None
        except Exception as e:
            print(f"[STT] ⚠ Whisper 오류: {type(e).__name__}: {e}")
            if self._fallback is not None:
                print("[STT] → Google STT로 폴백")
                txt = self._fallback._transcribe_sync(wav_bytes)
                self.last_status = self._fallback.last_status
                return txt
            self.last_status = "error"
            return None


def create_stt_client(
    engine: str = "google",
    language: str = "ko-KR",
    *,
    model_size: str = "small",
    device: str = "auto",
    compute_type: str = "int8",
    beam_size: int = 5,
    vad_filter: bool = False,
    no_speech_threshold: float = 0.6,
    logprob_threshold: float = -1.0,
):
    """STT_ENGINE에 따라 STT 클라이언트 생성.

    engine="whisper" + faster-whisper 설치됨 → WhisperSTTClient(google 폴백 내장).
    그 외(미설치 포함) → STTClient(google).
    """
    google = STTClient(language=language)
    if engine == "whisper":
        try:
            import faster_whisper  # noqa: F401, PLC0415  설치 확인만
        except Exception as e:
            print(
                f"[STT] faster-whisper 미설치({type(e).__name__}) → Google STT 사용."
                " (pip install faster-whisper)"
            )
            return google
        lang = (language or "ko").split("-")[0]
        print(f"[STT] 엔진=whisper (model={model_size}, lang={lang}), 실패 시 Google 폴백")
        return WhisperSTTClient(
            model_size=model_size,
            device=device,
            compute_type=compute_type,
            language=lang,
            beam_size=beam_size,
            vad_filter=vad_filter,
            no_speech_threshold=no_speech_threshold,
            logprob_threshold=logprob_threshold,
            fallback=google,
        )
    print("[STT] 엔진=google")
    return google
