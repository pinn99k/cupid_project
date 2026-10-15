"""
"시아야"의 마지막 "야"가 빨리 끝나는 느낌 보정.
- 압축을 앞부분("안녕 나는 시아")에만 적용하고, 마지막 "야"는 자연 속도(또는 더 길게)로 유지.
- "야" 끝에 부드러운 페이드아웃을 줘 뚝 끊기지 않게.
- 음정 유지(WSOLA), ffmpeg 불필요. 디코딩=afconvert, 인코딩=lameenc.

실행: venv/bin/python scripts/shorten_keep_tail.py
출력: audio/intro/sia_intro_2.2s_v2.mp3 (야 자연) / sia_intro_2.3s_long-ya.mp3 (야 길게)
"""

from pathlib import Path
import subprocess
import tempfile
import wave

import numpy as np
import lameenc
from audiotsm import wsola
from audiotsm.io.array import ArrayReader, ArrayWriter

SR = 24000
SRC = Path("audio/intro/sia_intro_calm_3.mp3")

# calm_3 파형 측정값(초): "야"는 2.16s 부근 골 다음에 시작해 2.60s까지 감쇠.
SPLIT_T = 2.16        # "시아" / "야" 경계(에너지 골)
LEAD_PAD = 0.04       # 발화 앞 여유
TAIL_DROP = 0.008     # 피크 대비 이 값 이하를 무음으로 보고 뒤를 자름
TAIL_PAD = 0.03
XFADE = 0.018         # head/tail 이음새 크로스페이드
FADEOUT = 0.07        # "야" 끝 페이드아웃


def decode(path: Path) -> np.ndarray:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        wav = Path(tf.name)
    subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16", "-c", "1",
                    str(path), str(wav)], check=True, capture_output=True)
    with wave.open(str(wav), "rb") as w:
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        ch = w.getnchannels()
    wav.unlink(missing_ok=True)
    if ch == 2:
        pcm = pcm.reshape(-1, 2).mean(1)
    return pcm.astype(np.float32) / 32768.0


def bounds(pcm: np.ndarray) -> tuple[int, int]:
    """발화 시작/끝 샘플(여운 포함). 끝은 낮은 임계로 잡아 '야' 꼬리 보존."""
    fl = int(SR * 0.02)
    peak = np.abs(pcm).max()
    rms = np.array([np.sqrt(np.mean(pcm[i:i + fl] ** 2)) for i in range(0, len(pcm), fl)])
    start_f = np.argmax(rms > peak * 0.03)
    end_f = len(rms) - 1 - np.argmax(rms[::-1] > peak * TAIL_DROP)
    start = max(0, int(start_f * 0.02 * SR - LEAD_PAD * SR))
    end = min(len(pcm), int((end_f + 1) * 0.02 * SR + TAIL_PAD * SR))
    return start, end


def stretch(seg: np.ndarray, speed: float) -> np.ndarray:
    """speed>1 빨라짐(짧아짐), <1 느려짐(길어짐). 1.0이면 그대로."""
    if abs(speed - 1.0) < 1e-3:
        return seg
    r = ArrayReader(seg.reshape(1, -1)); wri = ArrayWriter(channels=1)
    wsola(channels=1, speed=speed).run(r, wri)
    return wri.data.reshape(-1)


def join(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """등파워 크로스페이드로 a,b 연결(이음새 클릭 방지)."""
    n = int(SR * XFADE)
    if len(a) < n or len(b) < n:
        return np.concatenate([a, b])
    t = np.linspace(0, np.pi / 2, n)
    a_t, b_t = a.copy(), b.copy()
    a_t[-n:] *= np.cos(t); b_t[:n] *= np.sin(t)
    return np.concatenate([a_t[:-n], a_t[-n:] + b_t[:n], b_t[n:]])


def fade_out(seg: np.ndarray) -> np.ndarray:
    n = int(SR * FADEOUT)
    if len(seg) < n:
        return seg
    seg = seg.copy()
    seg[-n:] *= np.cos(np.linspace(0, np.pi / 2, n))  # 코사인 페이드
    return seg


def write_mp3(pcm: np.ndarray, out: Path) -> float:
    i16 = (np.clip(pcm, -1, 1) * 32767).astype(np.int16)
    enc = lameenc.Encoder()
    enc.set_bit_rate(192); enc.set_in_sample_rate(SR)
    enc.set_channels(1); enc.set_quality(2)
    out.write_bytes(enc.encode(i16.tobytes()) + enc.flush())
    return len(i16) / SR


def build(pcm, head, tail, total_target, tail_speed, out: Path):
    """head=발화앞 PCM, tail='야' PCM. tail은 tail_speed로, head는 total 맞춰 압축."""
    tail_out = stretch(tail, tail_speed)
    tail_out = fade_out(tail_out)
    head_target = total_target - len(tail_out) / SR - XFADE
    head_speed = (len(head) / SR) / head_target
    head_out = stretch(head, head_speed)
    final = join(head_out, tail_out)
    dur = write_mp3(final, out)
    print(f"  {out.name}: {dur:.3f}s  (앞 {head_speed*100:.0f}% / 야 {1/tail_speed*100:.0f}% 길이)")


def main():
    pcm = decode(SRC)
    s, e = bounds(pcm)
    split = int(SPLIT_T * SR)
    head, tail = pcm[s:split], pcm[split:e]
    print(f"발화 {s/SR:.2f}~{e/SR:.2f}s | 앞 '{(split-s)/SR:.2f}s' + 야 '{(e-split)/SR:.2f}s'")
    # (A) "야" 자연 속도 유지, 전체 ~2.25s
    build(pcm, head, tail, 2.25, 1.00, SRC.with_name("sia_intro_2.2s_v2.mp3"))
    # (B) "야" 더 길게(약 1.18x), 전체 ~2.35s — 끝까지 울리는 느낌
    build(pcm, head, tail, 2.35, 0.85, SRC.with_name("sia_intro_long-ya.mp3"))


if __name__ == "__main__":
    main()
