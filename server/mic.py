"""
마이크 입력 캡처 + 발화 감지 (VAD).
- MicCapture: sounddevice로 마이크 스트림, 에너지 기반 VAD
- listen(): 발화 감지 → 녹음 → WAV bytes 반환
"""

import asyncio
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
        silence_threshold: int = 500,
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
        frames_per_sec = self.sample_rate / chunk_size

        # 무음 연속 프레임 수 임계값
        silence_frames_limit = int(self.silence_duration * frames_per_sec)
        max_frames = int(self.max_duration * frames_per_sec)

        recorded: list[np.ndarray] = []
        speech_started = False
        silence_frames = 0

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
                        # 음성 구간
                        speech_started = True
                        silence_frames = 0
                        recorded.append(chunk)
                    else:
                        # 무음 구간
                        if speech_started:
                            recorded.append(chunk)  # 후미 무음도 포함
                            silence_frames += 1
                            if silence_frames >= silence_frames_limit:
                                # 충분한 무음 → 발화 종료
                                break
                        # 아직 발화 시작 전이면 대기만 (녹음 안 함)

                    total_frames += 1

        except Exception as e:
            print(f"[MicCapture] 녹음 오류: {e}")
            return None

        if not recorded:
            return None

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
