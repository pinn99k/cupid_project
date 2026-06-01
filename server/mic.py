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
        # 오디오 재생 중 여부 확인 콜백 (echo 방지용)
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
        """
        발화를 감지하고 녹음한 WAV bytes를 반환.

        - 음성이 감지될 때까지 대기
        - 음성 감지 후 silence_duration만큼 무음이면 녹음 종료
        - max_duration 초과 시 강제 종료
        - 반환: WAV 포맷 bytes 또는 None (실패 시)

        블로킹 녹음 로직을 asyncio.to_thread로 래핑하여 이벤트 루프 차단 방지.
        """
        return await asyncio.to_thread(self._record_sync)

    # ------------------------------------------------------------------
    # 내부 동기 로직
    # ------------------------------------------------------------------

    def _record_sync(self) -> bytes | None:

        """동기 녹음 로직. asyncio.to_thread에서 실행.

        sounddevice.InputStream으로 프레임 단위 읽기 후
        RMS 에너지로 음성/무음 판정.
        음성 시작 → 녹음 → 무음 지속 → 종료 흐름.
        """
        chunk_size = 1024  # 프레임 단위 읽기 크기
        pre_roll_chunks = max(1, int(0.4 * self.sample_rate / chunk_size))

        frames_per_sec = self.sample_rate / chunk_size
        # 무음 연속 프레임 수 임계값
        silence_frames_limit = int(self.silence_duration * frames_per_sec)
        max_frames = int(self.max_duration * frames_per_sec)

        # .env에 이전 값(1.8 등)이 남아있으면 silence_limit이 28+ → 방지
        # silence_duration > 0.8s 는 골전도 환경에서 거의 동작하지 않음
        max_silence_limit = max(3, int(0.8 * frames_per_sec))  # 상한 ~12프레임
        if silence_frames_limit > max_silence_limit:
            print(
                f"[MicCapture] ⚠️ VAD_SILENCE_DURATION={self.silence_duration}s"
                f" → silence_limit={silence_frames_limit}프레임 과도."
                f" {max_silence_limit}프레임(0.8s)으로 제한."
                f" .env의 VAD_SILENCE_DURATION을 0.5로 수정하세요."
            )
            silence_frames_limit = max_silence_limit

        recorded: list[np.ndarray] = []
        pre_roll: deque[np.ndarray] = deque(maxlen=pre_roll_chunks)
        # 최근 4프레임(≈256ms) 평균 RMS — 골전도 이어폰 스파이크 억제용
        rms_window: deque[float] = deque(maxlen=4)
        # 최근 10프레임 RMS 기록 — silence_reset 발생 시 진단 로그용
        rms_history: deque[float] = deque(maxlen=10)
        speech_rms: list[float] = []  # 발화 구간 RMS (평균 음량 계산용)
        speech_started = False
        silence_frames = 0
        # 음성 시작 판정용: 연속 3프레임(≈192ms) 이상 임계 초과 후 녹음 시작
        speech_onset_frames = 0
        _ONSET_REQUIRED = 3
        # 연속 발화 프레임 수: 3프레임 이상 연속해야 진짜 재발화로 인정(스파이크 구분)
        consecutive_speech = 0
        exit_reason = "max_duration"  # 종료 원인 추적 (silence | max_duration)
        # 에코 방지: 오디오 재생 중 스킵된 프레임 수 (진단용)
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

                # ── 배경 소음 측정 (첫 0.3초) ──────────────────────────────
                # 고정 silence_threshold=100은 방 배경 소음을 초과해
                # 침묵 감지가 실패 → max_duration까지 녹음되는 문제가 있음.
                # 해결: 시작 직후 0.3초를 측정해 동적 임계값을 계산.
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
                # 발화 감지 임계값: 배경 * 2.0, 하한=config값, 상한=800
                adaptive_threshold = min(
                    max(self.silence_threshold, int(bg_rms * 2.0)),
                    800,
                )
                # 침묵 판정 임계값 (히스테리시스): 감지 임계값의 75%
                # ─ 0.6이면 배경노이즈(bg * 1.2~1.5)가 임계값을 초과해 침묵 카운트 불가.
                # ─ 0.75로 상향: bg * 1.5 수준의 노이즈를 침묵으로 인정.
                silence_exit_threshold = adaptive_threshold * 0.75
                # silence_frames 리셋 기준: 평균 RMS가 감지 임계값의 80% 이상일 때만 리셋
                # ─ 단일 스파이크(골전도 이어폰 등)로 인한 카운터 리셋 방지
                spike_reset_threshold = adaptive_threshold * 0.8
                print(
                    f"[MicCapture] 배경RMS={bg_rms:.0f}"
                    f" 감지임계={adaptive_threshold}"
                    f" 침묵임계={silence_exit_threshold:.0f}"
                    f" 리셋임계={spike_reset_threshold:.0f}"
                    f" silence_limit={silence_frames_limit}프레임"
                )
                # ─────────────────────────────────────────────────────────

                while total_frames < max_frames:
                    chunk, _ = stream.read(chunk_size)
                    chunk = chunk.flatten()
                    rms = self._calc_rms(chunk)
                    rms_history.append(rms)  # 진단용 — 항상 기록

                    # ── 에코 방지: 오디오 재생 중 VAD 처리 스킵 ─────────────
                    # TTS / narration / 경고음이 재생되면 골전도 이어폰은 그 소리를
                    # 마이크로 직접 전달해 silence_reset을 유발한다.
                    # 해결: 재생 중인 프레임은 VAD를 스킵하고 rms_window를 초기화.
                    # (실제 마이크를 끊지 않아 재생 종료 후 즉시 청취 재개 가능)
                    is_audio_playing = (
                        self._audio_playing_check()
                        if self._audio_playing_check else False
                    )
                    if is_audio_playing:
                        rms_window.clear()      # 재생 종료 후 이전 high-RMS가 평균에 섞이지 않도록
                        speech_onset_frames = 0  # onset 오판 방지
                        echo_skip_frames += 1
                        if speech_started:
                            recorded.append(chunk)
                        else:
                            pre_roll.append(chunk)
                        total_frames += 1
                        continue
                    # ─────────────────────────────────────────────────────────

                    # 롤링 평균: 최근 4프레임 평균 (스파이크 억제)
                    rms_window.append(rms)
                    avg_rms = float(np.mean(rms_window))

                    if rms > adaptive_threshold:
                        speech_onset_frames += 1

                        if not speech_started:
                            # 음성 시작 판정: 연속 _ONSET_REQUIRED 프레임 이상이어야 인정
                            if speech_onset_frames >= _ONSET_REQUIRED:
                                print(
                                    f"[MicCapture] 음성 감지 시작"
                                    f" (onset={speech_onset_frames}프레임, RMS={rms:.0f})"
                                )
                                recorded.extend(pre_roll)
                                speech_started = True
                            else:
                                # onset 미달 — pre_roll에 쌓으면서 대기
                                pre_roll.append(chunk)

                        if speech_started:
                            consecutive_speech += 1

                            # silence_frames 리셋 조건:
                            # ① 평균 RMS가 spike_reset_threshold 이상 (단순 스파이크 배제)
                            # ② 연속 3프레임(≈192ms) 이상 발화 지속 (진짜 재발화 vs 노이즈 구분)
                            # → 골전도 이어폰의 간헐적 스파이크로 silence_frames가 리셋되지 않음
                            if avg_rms > spike_reset_threshold and consecutive_speech >= 3:
                                if silence_frames > 0:
                                    rms_hist_str = " ".join(f"{r:.0f}" for r in rms_history)
                                    print(
                                        f"[MicCapture] silence_reset"
                                        f" consec={consecutive_speech}"
                                        f" rms={rms:.0f} avg={avg_rms:.0f}"
                                        f" 임계={spike_reset_threshold:.0f}"
                                        f"\n  [진단] 최근10RMS=[{rms_hist_str}]"
                                        f" echo스킵={echo_skip_frames}프레임"
                                        f" 장치={self._device_label}"
                                    )
                                silence_frames = 0

                            recorded.append(chunk)
                            speech_rms.append(rms)

                    else:
                        speech_onset_frames = 0   # onset 카운터 리셋 (연속 아니면 처음부터)
                        consecutive_speech = 0    # 발화 아닌 프레임에서 연속 카운터 리셋

                        if speech_started:
                            recorded.append(chunk)
                            # 침묵 카운트: 평균 RMS 기준 (스파이크 한 프레임이 임계값을 넘어도
                            # 평균이 낮으면 침묵으로 인정)
                            if avg_rms <= silence_exit_threshold:
                                silence_frames += 1
                                print(
                                    f"[MicCapture] silence_frames={silence_frames}/{silence_frames_limit}"
                                    f" avg_rms={avg_rms:.0f}"
                                )
                            # 중립 구간 (silence_exit_threshold < avg_rms <= adaptive_threshold):
                            # 카운트도 리셋도 안 함 — 잔향/배경 소음 구간

                            if silence_frames >= silence_frames_limit:
                                exit_reason = "silence"
                                break
                        else:
                            pre_roll.append(chunk)

                    total_frames += 1

                # 종료 원인 로그 + 누적 통계
                if speech_started:
                    print(
                        f"[MicCapture] 종료 원인: {exit_reason}"
                        f" (echo스킵={echo_skip_frames}프레임"
                        f" / 전체={total_frames}프레임)"
                    )
                self._exit_stats.append(exit_reason if speech_started else "no_speech")
                n = len(self._exit_stats)
                silence_cnt = sum(1 for s in self._exit_stats if s == "silence")
                maxdur_cnt = sum(1 for s in self._exit_stats if s == "max_duration")
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

        # 발화 구간 평균 음량 기록 (저음량 되묻기 판정용)
        if speech_rms:
            self.last_rms = float(np.mean(speech_rms))
            print(f"[MicCapture] 평균 RMS={self.last_rms:.0f}")

        duration = len(np.concatenate(recorded)) / self.sample_rate
        print(f"[MicCapture] 녹음 길이={duration:.2f}초")

        audio_data = np.concatenate(recorded, axis=0)

        return self._to_wav_bytes(audio_data)

    # ------------------------------------------------------------------
    # 유틸리티
    # ------------------------------------------------------------------

    @property
    def _device_label(self) -> str:
        """로그용 마이크 장치 이름 (silence_reset 진단에 사용)."""
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
        """chunk의 RMS(Root Mean Square) 에너지 계산."""
        return float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))

    def _to_wav_bytes(self, audio_data: np.ndarray) -> bytes:
        """numpy int16 array를 WAV bytes로 변환.

        io.BytesIO + wave 모듈을 사용하여 메모리 내 WAV 파일 생성.
        """
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # int16 = 2 bytes
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_data.tobytes())
        return buf.getvalue()

    @staticmethod
    def _format_recording_error(error: Exception) -> str:
        """마이크 입력 오류에 현장에서 바로 쓸 수 있는 안내를 덧붙인다."""
        message = str(error)
        hints = []
        if "-50" in message or "PaMacCore" in message or "Error opening InputStream" in message:
            hints.extend(
                [
                    "macOS 마이크 권한을 확인하세요.",
                    "마이크를 쓰는 Zoom/Discord/카카오톡 같은 앱을 종료하세요.",
                    "python scripts/check_devices.py로 입력 장치 인덱스를 확인한 뒤 MIC_DEVICE_INDEX를 설정하세요.",
                ]
            )
        if hints:
            return f"{message} | 해결 힌트: {' / '.join(hints)}"
        return message

    @staticmethod
    def list_devices() -> list[dict]:
        """사용 가능한 마이크 장치 목록 반환.

        디버깅 및 MIC_DEVICE_INDEX 설정 시 활용.
        Returns:
            dict 목록. 각 항목은 name, index, max_input_channels 포함.
        """
        devices = sd.query_devices()
        result = []
        for idx, dev in enumerate(devices):
            if dev["max_input_channels"] > 0:
                result.append(
                    {
                        "index": idx,
                        "name": dev["name"],
                        "max_input_channels": dev["max_input_channels"],
                        "default_samplerate": dev["default_samplerate"],
                    }
                )
        return result
