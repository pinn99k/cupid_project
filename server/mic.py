"""
마이크 입력 캡처 + 발화 감지 (VAD).
- MicCapture: sounddevice로 마이크 스트림, 에너지 기반 VAD
- listen(): 발화 감지 → 녹음 → WAV bytes 반환
"""

import asyncio
from collections import deque
import io
import wave

import numpy as np
import sounddevice as sd


class MicCapture:
    """마이크 입력 캡처 + 에너지 기반 VAD."""

    def __init__(
        self,
        device_index=None,
        sample_rate: int = 16000,
        silence_threshold: int = 100,
        silence_duration: float = 1.5,
        max_duration: float = 10,
        audio_playing_check=None,
    ):
        """
        Args:
            device_index: 마이크 장치 인덱스 (None=시스템 기본)
            sample_rate: 샘플링 레이트 (16kHz — STT 최적)
            silence_threshold: 무음 판정 RMS 임계값
            silence_duration: 발화 종료 판정 무음 시간 (초)
            max_duration: 최대 녹음 시간 (초)
            audio_playing_check: () -> bool. 오디오 재생 중 여부 확인 콜백.
                재생 중인 프레임은 VAD 처리를 건너뜀 — 골전도 이어폰 echo 방지.
        """
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.silence_threshold = silence_threshold
        self.silence_duration = silence_duration
        self.max_duration = max_duration
        self._audio_playing_check = audio_playing_check
        # 직전 녹음의 평균 RMS(저음량 되묻기 판정용, Unit 4). 발화 없으면 0.0.
        self.last_rms: float = 0.0
        self.last_error: str | None = None
        # 최근 10회 종료 원인 통계 (silence / max_duration)
        self._exit_stats: deque[str] = deque(maxlen=10)

    # ------------------------------------------------------------------
    # 공개 비동기 인터페이스
    # ------------------------------------------------------------------

    async def listen(self) -> bytes | None:
        """발화를 감지하고 녹음한 WAV bytes를 반환."""
        return await asyncio.to_thread(self._record_sync)

    # ------------------------------------------------------------------
    # 내부 동기 로직
    # ------------------------------------------------------------------

    def _record_sync(self) -> bytes | None:
        """동기 녹음 로직. asyncio.to_thread에서 실행."""

        chunk_size = 1024
        frames_per_sec = self.sample_rate / chunk_size  # ≈ 15.625 fps

        # pre-roll: 발화 시작 직전 0.8초를 보존.
        # 이전 0.4초에서 확대 — 한국어 자음 전환 구간에서 onset 지연 시 앞부분 손실 방지.
        pre_roll_chunks = max(1, int(0.8 * self.sample_rate / chunk_size))

        # silence 판정 임계 프레임 수
        silence_frames_limit = int(self.silence_duration * frames_per_sec)
        max_frames = int(self.max_duration * frames_per_sec)

        # .env 구형 값(1.8s 등)으로 silence_limit 이 과도하게 큰 경우 상한 적용
        max_silence_limit = max(3, int(0.8 * frames_per_sec))  # ≈ 12프레임
        if silence_frames_limit > max_silence_limit:
            print(
                f"[MicCapture] ⚠️ VAD_SILENCE_DURATION={self.silence_duration}s 과도"
                f" → {max_silence_limit}프레임(0.8s)으로 제한"
                f" (.env VAD_SILENCE_DURATION=0.5 권장)"
            )
            silence_frames_limit = max_silence_limit

        # post-speech buffer: silence 판정 후 0.5초 추가 녹음.
        # "시아야 지금 내 앞에 뭐가 있어?" 의 마지막 어절 잘림 방지.
        POST_SPEECH_BUFFER_SEC = 0.5
        post_buffer_frames = max(1, int(POST_SPEECH_BUFFER_SEC * frames_per_sec))

        # ── 상태 변수 ────────────────────────────────────────────────────
        recorded: list[np.ndarray] = []
        pre_roll: deque[np.ndarray] = deque(maxlen=pre_roll_chunks)
        rms_window: deque[float] = deque(maxlen=4)    # 4프레임 평균 RMS (스파이크 억제)
        rms_history: deque[float] = deque(maxlen=10)  # 종료 직전 RMS 진단용
        speech_rms: list[float] = []   # 발화 구간 RMS (평균 음량 계산)

        speech_started = False
        speech_frames = 0        # speech_started 이후 recorded 에 쌓인 프레임 수
        silence_frames = 0
        consecutive_speech = 0   # silence_frames 리셋 조건에 사용

        # ★ onset guard: 1프레임으로 완화 (이전=3).
        # 이전 3프레임 연속 요구 때문에 한국어 자음-모음 전환 구간(내/앞/뭐/있 등)에서
        # onset 이 반복 리셋되어 녹음 시작이 최대 5~6초 지연 → STT 잘림 근본 원인.
        # adaptive_threshold 가 배경 소음 기반이므로 단일 프레임 초과만으로도 충분.
        _ONSET_REQUIRED = 1
        onset_frames = 0         # 연속 임계 초과 프레임 카운터

        # post-buffer 상태
        silence_confirmed = False   # silence 판정 완료 → post-buffer 진입
        silence_confirmed_at = 0    # silence 확정 시점 total_frames

        exit_reason = "max_duration"
        echo_skip_frames = 0
        self.last_rms = 0.0
        self.last_error = None

        try:
            with sd.InputStream(
                device=self.device_index,
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                blocksize=chunk_size,
            ) as stream:
                total_frames = 0

                # ── 배경 소음 측정 (첫 0.3초) ─────────────────────────────
                bg_measure_frames = min(
                    max_frames,
                    max(1, int(0.3 * self.sample_rate / chunk_size)),
                )
                bg_rms_samples: list[float] = []
                for _ in range(bg_measure_frames):
                    try:
                        chunk, _ = stream.read(chunk_size)
                    except Exception:
                        break
                    chunk = chunk.flatten()
                    bg_rms_samples.append(self._calc_rms(chunk))
                    pre_roll.append(chunk)
                    total_frames += 1

                bg_rms = float(np.mean(bg_rms_samples)) if bg_rms_samples else 0.0
                adaptive_threshold = min(
                    max(self.silence_threshold, int(bg_rms * 2.0)),
                    800,
                )
                silence_exit_threshold = adaptive_threshold * 0.75
                spike_reset_threshold  = adaptive_threshold * 0.8

                print(
                    f"[MicCapture] 배경RMS={bg_rms:.0f}"
                    f" 감지임계={adaptive_threshold}"
                    f" 침묵임계={silence_exit_threshold:.0f}"
                    f" silence_limit={silence_frames_limit}프레임"
                    f" post_buffer={post_buffer_frames}프레임"
                    f" pre_roll={pre_roll_chunks}프레임"
                    f" onset={_ONSET_REQUIRED}프레임"
                )
                # ──────────────────────────────────────────────────────────

                while total_frames < max_frames:
                    chunk, _ = stream.read(chunk_size)
                    chunk = chunk.flatten()
                    rms = self._calc_rms(chunk)
                    rms_history.append(rms)

                    # ── 에코 방지: TTS/경고음 재생 중 프레임 스킵 ──────────
                    is_audio_playing = (
                        self._audio_playing_check()
                        if self._audio_playing_check else False
                    )
                    if is_audio_playing:
                        rms_window.clear()   # 재생 종료 후 high-RMS 잔재 방지
                        onset_frames = 0
                        consecutive_speech = 0
                        echo_skip_frames += 1
                        if speech_started:
                            recorded.append(chunk)
                            speech_frames += 1
                        else:
                            pre_roll.append(chunk)
                        total_frames += 1
                        continue
                    # ──────────────────────────────────────────────────────

                    rms_window.append(rms)
                    avg_rms = float(np.mean(rms_window))

                    if rms > adaptive_threshold:
                        onset_frames += 1

                        # post-buffer 중 재발화 감지 → silence 판정 취소
                        if silence_confirmed:
                            silence_confirmed = False
                            silence_frames = 0
                            print(
                                f"[MicCapture] post_buffer 재발화(RMS={rms:.0f})"
                                f" → silence 판정 취소, 녹음 계속"
                            )

                        if not speech_started:
                            if onset_frames >= _ONSET_REQUIRED:
                                print(
                                    f"[MicCapture] 음성 감지 시작"
                                    f" (RMS={rms:.0f}"
                                    f" onset={onset_frames}"
                                    f" pre_roll={len(pre_roll)}프레임"
                                    f" total={total_frames}프레임)"
                                )
                                recorded.extend(pre_roll)
                                speech_frames += len(pre_roll)
                                speech_started = True
                            else:
                                pre_roll.append(chunk)

                        if speech_started:
                            consecutive_speech += 1
                            # silence_frames 리셋: 연속 3프레임 + 평균 RMS 조건
                            if avg_rms > spike_reset_threshold and consecutive_speech >= 3:
                                if silence_frames > 0:
                                    rms_hist_str = " ".join(
                                        f"{r:.0f}" for r in rms_history
                                    )
                                    print(
                                        f"[MicCapture] silence_reset"
                                        f" consec={consecutive_speech}"
                                        f" rms={rms:.0f} avg={avg_rms:.0f}"
                                        f"\n  최근10RMS=[{rms_hist_str}]"
                                        f" echo스킵={echo_skip_frames}"
                                    )
                                silence_frames = 0
                            recorded.append(chunk)
                            speech_frames += 1
                            speech_rms.append(rms)

                    else:
                        onset_frames = 0
                        consecutive_speech = 0

                        if speech_started:
                            recorded.append(chunk)
                            speech_frames += 1
                            if avg_rms <= silence_exit_threshold:
                                silence_frames += 1
                                print(
                                    f"[MicCapture] silence_frames={silence_frames}/{silence_frames_limit}"
                                    f" avg_rms={avg_rms:.0f}"
                                )
                            # silence 판정 → post-buffer 시작 (최초 1회만)
                            if (
                                silence_frames >= silence_frames_limit
                                and not silence_confirmed
                            ):
                                silence_confirmed = True
                                silence_confirmed_at = total_frames
                                print(
                                    f"[MicCapture] 침묵 판정 완료"
                                    f" → post_buffer {post_buffer_frames}프레임"
                                    f" ({POST_SPEECH_BUFFER_SEC}s) 대기"
                                )
                        else:
                            pre_roll.append(chunk)

                    # post-buffer 완료 체크
                    if silence_confirmed:
                        elapsed_post = total_frames - silence_confirmed_at
                        if elapsed_post >= post_buffer_frames:
                            exit_reason = "silence"
                            total_frames += 1
                            break

                    total_frames += 1

                # ── 종료 진단 로그 ───────────────────────────────────────
                if speech_started:
                    last_rms_str = " ".join(f"{r:.0f}" for r in rms_history)
                    print(
                        f"[MicCapture] 종료 원인: {exit_reason}"
                        f" | speech={speech_frames}프레임"
                        f" silence={silence_frames}프레임"
                        f" total={total_frames}프레임"
                        f" echo스킵={echo_skip_frames}프레임"
                    )
                    print(f"[MicCapture] 종료 직전 10프레임 RMS: [{last_rms_str}]")

                self._exit_stats.append(
                    exit_reason if speech_started else "no_speech"
                )
                n = len(self._exit_stats)
                silence_cnt  = sum(1 for s in self._exit_stats if s == "silence")
                maxdur_cnt   = sum(1 for s in self._exit_stats if s == "max_duration")
                print(
                    f"[MicCapture] 종료 통계(최근{n}회):"
                    f" silence={silence_cnt} max_duration={maxdur_cnt}"
                    f" no_speech={n - silence_cnt - maxdur_cnt}"
                )

        except Exception as e:
            self.last_error = self._format_recording_error(e)
            print(f"[MicCapture] 녹음 오류: {self.last_error}")
            return None

        if not recorded:
            return None

        if speech_rms:
            self.last_rms = float(np.mean(speech_rms))
            print(f"[MicCapture] 평균 RMS={self.last_rms:.0f}")

        audio_data = np.concatenate(recorded, axis=0)
        total_samples = len(audio_data)
        duration = total_samples / self.sample_rate

        print(
            f"[RECORDED AUDIO]"
            f" duration={duration:.2f}s"
            f" samples={total_samples}"
            f" frames={len(recorded)}"
        )

        return self._to_wav_bytes(audio_data)

    # ------------------------------------------------------------------
    # 유틸리티
    # ------------------------------------------------------------------

    @property
    def _device_label(self) -> str:
        """로그용 마이크 장치 이름."""
        try:
            info = (
                sd.query_devices(kind="input")
                if self.device_index is None
                else sd.query_devices(self.device_index)
            )
            return f"[{self.device_index}]{info['name']}"
        except Exception:
            return f"[{self.device_index}]unknown"

    @staticmethod
    def _calc_rms(chunk: np.ndarray) -> float:
        return float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))

    def _to_wav_bytes(self, audio_data: np.ndarray) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_data.tobytes())
        return buf.getvalue()

    @staticmethod
    def _format_recording_error(error: Exception) -> str:
        message = str(error)
        hints = []
        if "-50" in message or "PaMacCore" in message or "Error opening InputStream" in message:
            hints.extend([
                "macOS 마이크 권한을 확인하세요.",
                "마이크를 쓰는 Zoom/Discord/카카오톡 같은 앱을 종료하세요.",
                "python scripts/check_devices.py로 입력 장치 인덱스를 확인한 뒤 MIC_DEVICE_INDEX를 설정하세요.",
            ])
        if hints:
            return f"{message} | 해결 힌트: {' / '.join(hints)}"
        return message

    @staticmethod
    def list_devices() -> list[dict]:
        devices = sd.query_devices()
        result = []
        for idx, dev in enumerate(devices):
            if dev["max_input_channels"] > 0:
                result.append({
                    "index": idx,
                    "name": dev["name"],
                    "max_input_channels": dev["max_input_channels"],
                    "default_samplerate": dev["default_samplerate"],
                })
        return result
