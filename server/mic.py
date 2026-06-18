"""
마이크 입력 캡처 + 발화 감지 (VAD).
- MicCapture: sounddevice로 마이크 스트림, 에너지 기반 VAD
- listen(): 발화 감지 → 녹음 → WAV bytes 반환
"""

import asyncio
from collections import deque
import io
import threading
import time
import wave

import numpy as np
import sounddevice as sd


# 적응형 무음 임계 상한 — ambient 가 비정상적으로 커도 발화 감지가 불가능해지지
# 않도록 동적 임계의 절대 상한을 둔다(기존 _record_sync 의 800 상한과 동일).
_ADAPTIVE_THRESHOLD_CAP = 800

# 블루투스(골전도 이어폰) 마이크는 stream 오픈 직후 HFP 링크가 붙기까지 ~1초간
# 디지털 무음(RMS≈0)을 흘린다. 이 구간을 배경소음으로 측정하거나 청취 예산으로
# 까먹지 않도록, stream 오픈 직후 '오디오가 실제로 흐를 때까지' 무음 프레임을 버린다.
# - 이미 웜업된(유선/내장) 마이크는 첫 프레임부터 신호가 있어 즉시 통과(지연 0).
# - 시끄러운 시연장은 ambient 가 floor 를 바로 넘으므로 추가 지연이 거의 없다.
_BT_WARMUP_MAX_SEC = 1.5      # 최대 대기(초) — 이 안에 신호 없으면 그냥 진행
_WARMUP_SILENCE_FLOOR = 5.0   # 이 RMS 이하는 '아직 무음(링크 미연결)'으로 간주


def compute_silence_threshold(
    ambient_rms: float,
    base_threshold: float,
    factor: float = 2.0,
    adaptive: bool = True,
    cap: float = _ADAPTIVE_THRESHOLD_CAP,
) -> float:
    """무음 판정 임계값(감지 임계)을 계산하는 순수 함수.

    하드웨어 의존이 없어 단위테스트 가능. _record_sync 에서 호출된다.

    Args:
        ambient_rms: 녹음 초입에서 측정한 배경소음 RMS(noise floor).
        base_threshold: 고정 기준값(VAD_SILENCE_THRESHOLD).
        factor: ambient 에 곱하는 계수(VAD_AMBIENT_FACTOR).
        adaptive: False 면 적응형 보정 없이 base_threshold 를 그대로 반환(킬스위치).
        cap: 동적 임계의 절대 상한.

    Returns:
        적용할 무음/감지 임계값(float).
        - adaptive=False: base_threshold
        - adaptive=True:  min(max(base_threshold, ambient_rms * factor), cap)
    """
    if not adaptive:
        return float(base_threshold)
    dynamic = max(float(base_threshold), float(ambient_rms) * float(factor))
    return float(min(dynamic, cap))


class MicCapture:
    """마이크 입력 캡처 + 에너지 기반 VAD."""

    def __init__(
        self,
        device_index=None,
        device_name: str | None = None,
        sample_rate: int = 16000,
        silence_threshold: int = 100,
        silence_duration: float = 1.5,
        max_duration: float = 10,
        audio_playing_check=None,
        adaptive: bool | None = None,
        ambient_factor: float | None = None,
        manual_max_sec: int = 15,
    ):
        """
        Args:
            device_index: 마이크 장치 인덱스 (None=시스템 기본)
            device_name: 마이크 이름 부분일치(대소문자 무시). 지정 시 매 stream 오픈마다
                이름으로 인덱스를 재탐색 → 블루투스 재연결로 인덱스가 바뀌어도 항상
                같은 마이크(예: 골전도 'COSY')를 선택. 못 찾으면 device_index로 폴백.
            sample_rate: 샘플링 레이트 (16kHz — STT 최적)
            silence_threshold: 무음 판정 RMS 임계값
            silence_duration: 발화 종료 판정 무음 시간 (초)
            max_duration: 최대 녹음 시간 (초)
            audio_playing_check: () -> bool. 오디오 재생 중 여부 확인 콜백.
                재생 중인 프레임은 VAD 처리를 건너뜀 — 골전도 이어폰 echo 방지.
            adaptive: 적응형 무음 임계(ambient calibration) on/off 킬스위치.
                None=config.VAD_ADAPTIVE 사용. False면 silence_threshold 고정.
            ambient_factor: 동적 임계 계수. None=config.VAD_AMBIENT_FACTOR 사용.
        """
        self.device_index = device_index
        self.device_name = device_name
        self._last_resolved_index = None  # 변경 시에만 로그 출력용
        self.sample_rate = sample_rate
        self.silence_threshold = silence_threshold
        self.silence_duration = silence_duration
        self.max_duration = max_duration
        self._audio_playing_check = audio_playing_check

        # 적응형 임계 설정 — 인자 미지정 시 config 기본값 사용.
        # config import 실패(테스트 등)에도 안전하게 폴백.
        if adaptive is None or ambient_factor is None:
            try:
                from server import config as _cfg
                _cfg_adaptive = _cfg.VAD_ADAPTIVE
                _cfg_factor = _cfg.VAD_AMBIENT_FACTOR
            except Exception:
                _cfg_adaptive = True
                _cfg_factor = 2.0
            if adaptive is None:
                adaptive = _cfg_adaptive
            if ambient_factor is None:
                ambient_factor = _cfg_factor
        self.adaptive = bool(adaptive)
        self.ambient_factor = float(ambient_factor)
        # 직전 녹음의 평균 RMS(저음량 되묻기 판정용, Unit 4). 발화 없으면 0.0.
        self.last_rms: float = 0.0
        self.last_error: str | None = None
        # 직전 녹음의 종료 원인/길이 — 파이프라인 타이밍 진단용
        self.last_exit_reason: str = "none"
        self.last_record_sec: float = 0.0
        # 최근 10회 종료 원인 통계 (silence / max_duration)
        self._exit_stats: deque[str] = deque(maxlen=10)

        # ── 수동 녹음 모드 상태 ─────────────────────────────────────────
        # 항상 켜진 캡처 스레드가 프레임을 읽어 pre-roll(200ms)을 유지하고,
        # _manual_active 동안에는 _manual_frames 에 누적한다. (VAD 미사용)
        self._manual_max_sec = manual_max_sec
        self._manual_lock = threading.Lock()
        self._manual_active = False
        self._manual_frames: list[np.ndarray] = []
        _chunk = 1024
        self._manual_preroll: deque[np.ndarray] = deque(
            maxlen=max(1, int(0.2 * self.sample_rate / _chunk))  # 200ms
        )
        self._manual_stream_running = False
        self._manual_stream_thread: threading.Thread | None = None
        self._manual_start_t = 0.0
        self._manual_hardcap_hit = False

    # ------------------------------------------------------------------
    # 공개 비동기 인터페이스
    # ------------------------------------------------------------------

    async def listen(self) -> bytes | None:
        """발화를 감지하고 녹음한 WAV bytes를 반환."""
        return await asyncio.to_thread(self._record_sync)

    # ------------------------------------------------------------------
    # 수동 녹음 모드 (운영자 토글 버튼)
    # ------------------------------------------------------------------

    def start_manual_capture_stream(self) -> None:
        """수동 모드 진입 시 1회 호출 — 항상 켜진 캡처 스레드를 띄운다.
        녹음 중이 아닐 때도 pre-roll(200ms)을 유지해, start 시 직전 음성을 포함한다."""
        if self._manual_stream_running:
            return
        self._manual_stream_running = True
        self._manual_stream_thread = threading.Thread(
            target=self._manual_stream_loop, name="mic-manual", daemon=True
        )
        self._manual_stream_thread.start()

    def stop_manual_capture_stream(self) -> None:
        """캡처 스레드 종료(셧다운용)."""
        self._manual_stream_running = False
        t = self._manual_stream_thread
        if t and t.is_alive():
            t.join(timeout=2)

    def _manual_stream_loop(self) -> None:
        """캡처 스레드 본체. 항상 프레임을 읽어 pre-roll 유지 + 녹음 중엔 누적."""
        chunk_size = 1024
        try:
            with sd.InputStream(
                device=self._resolve_device(),
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                blocksize=chunk_size,
            ) as stream:
                self._warmup_stream(stream, chunk_size)  # BT 콜드스타트 무음 버림
                while self._manual_stream_running:
                    try:
                        chunk, _ = stream.read(chunk_size)
                    except Exception:
                        break
                    chunk = chunk.flatten()
                    with self._manual_lock:
                        if self._manual_active:
                            self._manual_frames.append(chunk)
                            # 안전 하드캡: 운영자/타이머가 못 멈춰도 버퍼 폭주 방지
                            if time.monotonic() - self._manual_start_t > self._manual_max_sec:
                                self._manual_hardcap_hit = True
                                self._manual_active = False
                        else:
                            self._manual_preroll.append(chunk)
        except Exception as e:
            self.last_error = self._format_recording_error(e)
            print(f"[MicCapture] 수동 캡처 스트림 오류: {self.last_error}")
        finally:
            self._manual_stream_running = False

    def start_manual_recording(self) -> bool:
        """녹음 즉시 시작(VAD 끔). pre-roll 200ms 포함. 이미 녹음 중이면 False."""
        with self._manual_lock:
            if self._manual_active:
                return False
            self._manual_frames = list(self._manual_preroll)  # 직전 200ms 포함
            self._manual_start_t = time.monotonic()
            self._manual_hardcap_hit = False
            self._manual_active = True
        self.last_error = None
        return True

    def stop_manual_recording(self) -> bytes | None:
        """녹음 즉시 종료 → WAV bytes 반환(없으면 None)."""
        with self._manual_lock:
            self._manual_active = False
            frames = self._manual_frames
            self._manual_frames = []
        if not frames:
            self.last_record_sec = 0.0
            self.last_exit_reason = "manual_empty"
            return None
        audio = np.concatenate(frames, axis=0)
        self.last_record_sec = len(audio) / self.sample_rate
        self.last_exit_reason = "manual"
        # 발화 평균 RMS(저음량 판정 등 호환용)
        try:
            self.last_rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
        except Exception:
            self.last_rms = 0.0
        return self._to_wav_bytes(audio)

    @property
    def is_manual_recording(self) -> bool:
        with self._manual_lock:
            return self._manual_active

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
                device=self._resolve_device(),
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                blocksize=chunk_size,
            ) as stream:
                total_frames = 0

                # BT(골전도) 콜드스타트 보정: 신호가 흐를 때까지 무음 프레임을 버려
                # 배경소음을 0으로 잘못 측정하거나 발화 앞부분을 놓치지 않게 한다.
                self._warmup_stream(stream, chunk_size)

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

                # 25퍼센타일 사용(mean 아님): 체험자가 응답 직후 곧바로 말해
                # 배경측정 구간에 음성이 섞여도, 조용한 프레임 기준으로 배경을 잡아
                # 임계값이 부풀어 발화를 놓치는 문제를 방지(연속 발화 안정성 핵심).
                bg_rms = float(np.percentile(bg_rms_samples, 25)) if bg_rms_samples else 0.0
                # 적응형 무음 임계(ambient calibration). 킬스위치 off면 고정 임계.
                adaptive_threshold = compute_silence_threshold(
                    ambient_rms=bg_rms,
                    base_threshold=self.silence_threshold,
                    factor=self.ambient_factor,
                    adaptive=self.adaptive,
                )
                silence_exit_threshold = adaptive_threshold * 0.75
                spike_reset_threshold  = adaptive_threshold * 0.8

                print(
                    f"[VAD] adaptive={'on' if self.adaptive else 'off'}"
                    f" ambient_rms={bg_rms:.0f}"
                    f" factor={self.ambient_factor}"
                    f" → silence_threshold={adaptive_threshold:.0f}"
                    f" (base={self.silence_threshold})"
                )

                # 청취 예산을 배경측정/에코스킵과 분리 — max_duration 전체를
                # '실제 청취'에 사용(배경측정 0.3s가 녹음 시간을 깎지 않음).
                total_frames = 0

                print(
                    f"[MicCapture] 배경RMS(25%)={bg_rms:.0f}"
                    f" 감지임계={adaptive_threshold}"
                    f" 침묵임계={silence_exit_threshold:.0f}"
                    f" silence_limit={silence_frames_limit}프레임"
                    f" post_buffer={post_buffer_frames}프레임"
                    f" pre_roll={pre_roll_chunks}프레임"
                    f" onset={_ONSET_REQUIRED}프레임"
                )
                # ──────────────────────────────────────────────────────────

                # 에코스킵이 예산을 무한정 깎지 않도록 절대 반복 상한
                _iter_guard = 0
                _iter_guard_max = max_frames * 4
                while total_frames < max_frames and _iter_guard < _iter_guard_max:
                    _iter_guard += 1
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
                        # 에코 재생 중 프레임은 청취 예산(total_frames)에서 제외
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
                last_rms_str = " ".join(f"{r:.0f}" for r in rms_history)
                if speech_started:
                    print(
                        f"[MicCapture] 종료 원인: {exit_reason}"
                        f" | speech={speech_frames}프레임"
                        f" silence={silence_frames}프레임"
                        f" total={total_frames}프레임"
                        f" echo스킵={echo_skip_frames}프레임"
                    )
                    print(f"[MicCapture] 종료 직전 10프레임 RMS: [{last_rms_str}]")
                else:
                    # 발화 미감지: 임계값보다 큰 음성이 한 번도 안 들어옴
                    _max_seen = max(rms_history) if rms_history else 0
                    print(
                        f"[MicCapture] ⚠️ 발화 미감지 — 감지임계({adaptive_threshold})를"
                        f" 넘는 음성 없음 (관측 최대RMS={_max_seen:.0f})."
                        f"\n  → 마이크에 더 가까이/크게 말하거나, 배경이 너무 시끄러우면"
                        f" VAD_SILENCE_THRESHOLD를 낮춰 민감도↑ 또는 마이크 게인↑ 필요."
                        f"\n  최근10RMS=[{last_rms_str}]"
                    )

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

        # 파이프라인이 읽어 [MIC_STATE] 로그에 사용
        self.last_exit_reason = exit_reason if speech_started else "no_speech"
        self.last_record_sec = duration

        print(
            f"[RECORDED AUDIO]"
            f" duration={duration:.2f}s"
            f" samples={total_samples}"
            f" frames={len(recorded)}"
            f" exit={self.last_exit_reason}"
        )

        return self._to_wav_bytes(audio_data)

    # ------------------------------------------------------------------
    # 유틸리티
    # ------------------------------------------------------------------

    def _resolve_device(self):
        """사용할 입력 장치 인덱스를 결정.
        우선순위: device_name(이름 부분일치) → device_index → None(시스템 기본).
        매 stream 오픈마다 호출 → BT 재연결로 인덱스가 바뀌어도 이름으로 재탐색.
        인덱스가 바뀐 경우에만 로그를 남긴다.
        """
        idx = self.device_index
        if self.device_name:
            try:
                target = self.device_name.lower()
                found = next(
                    (i for i, d in enumerate(sd.query_devices())
                     if d["max_input_channels"] > 0 and target in d["name"].lower()),
                    None,
                )
                if found is not None:
                    idx = found
                else:
                    print(f"[MicCapture] ⚠️ 마이크 '{self.device_name}' 못 찾음 "
                          f"→ index={self.device_index}/기본으로 폴백")
            except Exception as e:
                print(f"[MicCapture] 장치 이름 조회 실패({e}) → index 폴백")
        if idx != self._last_resolved_index:
            try:
                name = sd.query_devices(idx)["name"] if idx is not None \
                    else sd.query_devices(kind="input")["name"]
            except Exception:
                name = "unknown"
            print(f"[MicCapture] 입력 장치 → [{idx}] {name}")
            self._last_resolved_index = idx
        return idx

    def _warmup_stream(self, stream, chunk_size: int) -> int:
        """BT HFP 콜드스타트 보정: 신호가 흐를 때까지 무음 프레임을 버린다.
        반환: 버린 프레임 수(0이면 이미 웜업 상태/대상 아님).

        이름으로 마이크를 고정(device_name)했을 때만 동작한다 — 이 경로가 곧
        블루투스(골전도) 고정 시나리오다. 기본/인덱스 경로는 기존 동작 유지.
        """
        if not self.device_name:
            return 0
        max_frames = int(_BT_WARMUP_MAX_SEC * self.sample_rate / chunk_size)
        dropped = 0
        for _ in range(max_frames):
            try:
                chunk, _ = stream.read(chunk_size)
            except Exception:
                break
            if self._calc_rms(chunk.flatten()) > _WARMUP_SILENCE_FLOOR:
                break  # 오디오가 흐르기 시작 → 웜업 완료
            dropped += 1
        if dropped:
            print(f"[MicCapture] BT 웜업: 무음 {dropped}프레임"
                  f"({dropped*chunk_size/self.sample_rate:.2f}s) 버림")
        return dropped

    @property
    def _device_label(self) -> str:
        """로그용 마이크 장치 이름."""
        try:
            idx = self._resolve_device()
            info = (
                sd.query_devices(kind="input")
                if idx is None
                else sd.query_devices(idx)
            )
            return f"[{idx}]{info['name']}"
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
