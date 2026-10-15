"""
mp3 길이 줄이기: (1) 앞뒤 무음 컷 (속도 불변) (2) 정확한 목표 길이로 음정 유지 시간압축.

- 무음 컷: 말 속도는 그대로 두고 dead air만 제거 -> "빨라진 느낌" 없음.
- 목표 길이: WSOLA(음정 유지 time-stretch)로 발화를 살짝 압축. ffmpeg 불필요.
- mp3 디코딩은 macOS 내장 afconvert 사용, 인코딩은 lameenc.

실행: venv/bin/python scripts/shorten_mp3.py <입력.mp3> [목표초]
"""

from pathlib import Path
import subprocess
import sys
import tempfile
import wave

import numpy as np
import lameenc
from audiotsm import wsola
from audiotsm.io.array import ArrayReader, ArrayWriter

SR = 24000          # Gemini TTS 출력 샘플레이트
LEAD_PAD = 0.02     # 발화 앞에 남길 여유(초) - 자음 시작 안 잘리게
TAIL_PAD = 0.04     # 발화 뒤에 남길 여유(초) - 모음 끝 자연스럽게


def decode_mp3(path: Path) -> np.ndarray:
    """mp3 -> float32 mono PCM [-1,1] (afconvert로 24kHz/16bit WAV 경유)."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        wav = Path(tf.name)
    subprocess.run(
        ["afconvert", "-f", "WAVE", "-d", "LEI16", "-c", "1", str(path), str(wav)],
        check=True, capture_output=True,
    )
    with wave.open(str(wav), "rb") as w:
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        ch = w.getnchannels()
    wav.unlink(missing_ok=True)
    if ch == 2:
        pcm = pcm.reshape(-1, 2).mean(1)
    return pcm.astype(np.float32) / 32768.0


def speech_bounds(pcm: np.ndarray, frame=0.02, ratio=0.03) -> tuple[int, int]:
    """피크 대비 ratio 임계로 발화 시작/끝 샘플 인덱스 반환."""
    fl = int(SR * frame)
    peak = np.abs(pcm).max()
    thr = peak * ratio
    rms = np.array([
        np.sqrt(np.mean(pcm[i:i + fl] ** 2)) for i in range(0, len(pcm), fl)
    ])
    voiced = np.where(rms > thr)[0]
    if len(voiced) == 0:
        return 0, len(pcm)
    start = max(0, int((voiced[0] * frame - LEAD_PAD) * SR))
    end = min(len(pcm), int(((voiced[-1] + 1) * frame + TAIL_PAD) * SR))
    return start, end


def stretch_to(pcm: np.ndarray, target_s: float) -> np.ndarray:
    """현재 발화를 target_s초로 음정 유지 압축/신장 (WSOLA)."""
    cur = len(pcm) / SR
    speed = cur / target_s            # >1 이면 빨라짐(짧아짐)
    reader = ArrayReader(pcm.reshape(1, -1))
    writer = ArrayWriter(channels=1)
    wsola(channels=1, speed=speed).run(reader, writer)
    return writer.data.reshape(-1)


def write_mp3(pcm: np.ndarray, out: Path) -> float:
    """float PCM -> mp3. 반환: 길이(초)."""
    i16 = np.clip(pcm, -1, 1)
    i16 = (i16 * 32767).astype(np.int16)
    enc = lameenc.Encoder()
    enc.set_bit_rate(192)
    enc.set_in_sample_rate(SR)
    enc.set_channels(1)
    enc.set_quality(2)
    out.write_bytes(enc.encode(i16.tobytes()) + enc.flush())
    return len(i16) / SR


def main() -> None:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "audio/intro/sia_intro_calm_3.mp3")
    target = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0

    pcm = decode_mp3(src)
    s, e = speech_bounds(pcm)
    trimmed = pcm[s:e]
    print(f"원본 {len(pcm)/SR:.3f}s -> 무음컷 {len(trimmed)/SR:.3f}s "
          f"(앞 {s/SR:.3f}s / 뒤 {(len(pcm)-e)/SR:.3f}s 제거)")

    # (1) 무음만 컷 — 속도 그대로
    out_trim = src.with_name(src.stem + "_trim.mp3")
    d1 = write_mp3(trimmed, out_trim)
    print(f"  [무음컷]   {out_trim}  {d1:.3f}s  (속도 100%)")

    # (2) 목표 길이로 음정 유지 압축
    out_t = src.with_name(f"sia_intro_{target:g}s.mp3")
    stretched = stretch_to(trimmed, target)
    d2 = write_mp3(stretched, out_t)
    speedup = (len(trimmed) / SR) / target
    print(f"  [{target:g}초]    {out_t}  {d2:.3f}s  (속도 {speedup*100:.0f}%, 음정 유지)")


if __name__ == "__main__":
    main()
