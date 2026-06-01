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
    ):
        """
        Args:
            device_index: 마이크 장치 인덱스 (None=시스템 기본)
            sample_rate: 샘플링 레이트 (16kHz — STT 최적)
            silence_threshold: 무음 판정 RMS 임계값
            silence_duration: 발화 종료 판정 무음 시간 (초)
            max_duration: 최대 녹음 시간 (초)
        """
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.silence_threshold = silence_threshold
        self.silence_duration = silence_duration
        self.max_duration = max_duration
        # 직전 녹음의 평균 RMS(저음량 되묻기 판정용, Unit 4). 발화 없으면 0.0.
        self.last_rms: float = 0.0
        self.last_error: str | None = None

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

        recorded: list[np.ndarray] = []
        pre_roll: deque[np.ndarray] = deque(maxlen=pre_roll_chunks)
        speech_rms: list[float] = []  # 발화 구간 RMS (평균 음량 계산용)
        speech_started = False
        silence_frames = 0
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

                while total_frames < max_frames:
                    chunk, _ = stream.read(chunk_size)
                    chunk = chunk.flatten()
                    rms = self._calc_rms(chunk)

                    if rms > self.silence_threshold:
                        # 음성 시작 로그 (최초 1회만)
                        if not speech_started:
                            print("[MicCapture] 음성 감지 시작")
                            recorded.extend(pre_roll)

                        speech_started = True
                        silence_frames = 0

                        recorded.append(chunk)
                        speech_rms.append(rms)

                    else:
                        # 무음 구간
                        if speech_started:
                            recorded.append(chunk)  # 후미 무음도 포함
                            silence_frames += 1

                            if silence_frames >= silence_frames_limit:
                                print("[MicCapture] 음성 감지 종료")
                                break
                        else:
                            pre_roll.append(chunk)

                    total_frames += 1

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
