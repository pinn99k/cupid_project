"""
이어폰 볼륨 버튼 → 마이크 토글.

가운데(전원) 버튼은 통화(SCO) 상태일 때만 신호를 보내 간헐적이라 신뢰 불가.
대신 '볼륨 +/-' 버튼을 토글로 쓴다. 볼륨 버튼은 어떤 상태에서도 macOS 시스템 출력
볼륨을 확실히 바꾸므로, 그 변화를 감지해 토글하고 볼륨은 baseline 으로 즉시 복원한다.

⚠️ 구현 주의: 서버는 asyncio(uvloop) 이벤트 루프를 쓰는데, 스레드에서 매번
   subprocess.run(osascript)를 호출하면 uvloop의 SIGCHLD 자식 watcher와 waitpid 가
   충돌해 hang 한다(실측 확인). 그래서 osascript 를 매 폴마다 띄우지 않고:
     - reader: 볼륨을 주기적으로 stdout 에 찍는 '장기 프로세스 1개' → stdout 라인 읽기
     - setter: stdin 으로 받은 값을 볼륨에 set 하는 '장기 프로세스 1개' → stdin write
   둘 다 bash 루프라 osascript 자식은 bash 가 reap → python 은 waitpid 안 함 → 충돌 없음.
   (이전 bluetoothd log stream 도 같은 '장기 Popen + stdout' 패턴이라 잘 됐다.)

⚠️ 클래스명/인터페이스(BluetoothButtonListener, start/stop, (loop, on_toggle))는
   기존 배선 호환을 위해 유지. 실제 트리거는 '볼륨 버튼'이다.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
import time
from typing import Awaitable, Callable

_VOL_DEBUG = os.getenv("VOL_DEBUG", "").lower() in ("1", "true", "yes", "on")

# 고정 baseline 볼륨. + 버튼이 더 올라갈 헤드룸이 있어야 변화가 감지되므로 100은 불가.
# 95 = 사실상 최대 음량 + 헤드룸(95→100 변화 감지). BT_VOL_BASELINE로 조절 가능.
_BASELINE_TARGET = max(20, min(95, int(os.getenv("BT_VOL_BASELINE", "95"))))

# 볼륨 변경 시 뜨는 화면 OSD(볼륨 막대) 억제. OSDUIHelper(렌더러)를 계속 종료.
# SIP 때문에 영구 비활성화는 불가 → 떴을 때 즉시 죽이는 방식(잠깐 깜빡일 수 있음).
_SUPPRESS_OSD = os.getenv("BT_SUPPRESS_OSD", "1").lower() in ("1", "true", "yes", "on")


class BluetoothButtonListener:
    """이어폰 볼륨 버튼 → on_toggle 코루틴. (이름은 호환 위해 유지)"""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        on_toggle: Callable[[], Awaitable[None]],
        debounce_sec: float = 0.6,
        poll_sec: float = 0.12,
        **_ignored,
    ):
        self._loop = loop
        self._on_toggle = on_toggle
        self._debounce_sec = debounce_sec
        self._poll_sec = poll_sec
        self._running = False
        self._thread: threading.Thread | None = None
        self._reader: subprocess.Popen | None = None
        self._setter: subprocess.Popen | None = None
        self._osd_killer: subprocess.Popen | None = None
        self._baseline: int | None = None
        self._last_fire = 0.0

    def start(self) -> None:
        if sys.platform != "darwin":
            print("[VOL_BUTTON] macOS 아님 → 비활성")
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="vol-button", daemon=True)
        self._thread.start()
        print("[VOL_BUTTON] 볼륨 버튼 토글 리스너 시작 (볼륨 +/- → 마이크 토글)")

    def stop(self) -> None:
        self._running = False
        for p in (self._reader, self._setter, self._osd_killer):
            if p and p.poll() is None:
                try:
                    p.terminate()
                    try:
                        p.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        p.kill()
                except Exception:
                    pass
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=2)

    def _set_volume(self, vol: int) -> None:
        """setter 프로세스 stdin 으로 볼륨 값 전달(파이썬 waitpid 회피)."""
        try:
            if self._setter and self._setter.stdin:
                self._setter.stdin.write(f"{int(vol)}\n")
                self._setter.stdin.flush()
        except Exception:
            pass

    def _run(self) -> None:
        poll = self._poll_sec
        # ⚠️ 부모(서버) PID에 kill -0 가드를 건다. 서버를 kill -9 로 죽이면 이 bash
        #    루프들은 고아로 남아 계속 osascript 를 띄운다(실측: 재시작 누적으로
        #    bash 루프 13개·osascript 8개가 쌓여 폴링이 서로 경합 → 볼륨 reader 가
        #    못 따라가 버튼 먹통). 부모가 사라지면 다음 폴에서 kill -0 실패 → 루프 종료.
        ppid = os.getpid()
        reader_cmd = [
            "/bin/bash", "-c",
            f"while kill -0 {ppid} 2>/dev/null; do "
            f"osascript -e 'output volume of (get volume settings)'; "
            f"sleep {poll}; done",
        ]
        setter_cmd = [
            "/bin/bash", "-c",
            f'while kill -0 {ppid} 2>/dev/null && IFS= read -r v; do '
            'osascript -e "set volume output volume $v" >/dev/null 2>&1; done',
        ]
        while self._running:
            try:
                self._reader = subprocess.Popen(
                    reader_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, bufsize=1,
                )
                self._setter = subprocess.Popen(
                    setter_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, text=True, bufsize=1,
                )
                # OSD(볼륨 막대) 억제기: OSDUIHelper가 뜨면 즉시 종료(별도 bash → 충돌 없음).
                if _SUPPRESS_OSD and (self._osd_killer is None or self._osd_killer.poll() is not None):
                    self._osd_killer = subprocess.Popen(
                        ["/bin/bash", "-c",
                         f"while kill -0 {ppid} 2>/dev/null; do "
                         f"killall OSDUIHelper 2>/dev/null; sleep 0.08; done"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                    print("[VOL_BUTTON] OSD(볼륨막대) 억제 ON")
                self._baseline = None
                _dbg_n = 0
                assert self._reader.stdout is not None
                for line in self._reader.stdout:
                    if not self._running:
                        break
                    s = line.strip()
                    if not s.isdigit():
                        continue
                    v = int(s)
                    # baseline = 고정 높은 값(95). + 버튼이 100으로 올라가는 변화를 감지.
                    if self._baseline is None:
                        self._baseline = _BASELINE_TARGET
                        self._set_volume(self._baseline)
                        print(
                            f"[VOL_BUTTON] baseline 볼륨={self._baseline}(고정) "
                            f"— + 누르면 토글 후 즉시 복원 → 볼륨 항상 {self._baseline} 유지"
                        )
                        continue
                    if _VOL_DEBUG:
                        _dbg_n += 1
                        if _dbg_n % 10 == 0 or v != self._baseline:
                            print(f"[VOL_BUTTON DBG] read={v} baseline={self._baseline}")
                    if v == self._baseline:
                        continue
                    # 볼륨 버튼 눌림 → 즉시 복원 + (debounce 통과 시) 토글
                    self._set_volume(self._baseline)
                    now = time.monotonic()
                    if now - self._last_fire < self._debounce_sec:
                        continue
                    self._last_fire = now
                    print(f"[VOL_BUTTON] 볼륨 변화 감지({v}→{self._baseline}) → 마이크 토글")
                    try:
                        asyncio.run_coroutine_threadsafe(self._on_toggle(), self._loop)
                    except Exception as e:
                        print(f"[VOL_BUTTON] 토글 스케줄 실패: {e}")
            except Exception as e:
                print(f"[VOL_BUTTON] 오류(리스너만 재시작): {type(e).__name__}: {e}")
            finally:
                for p in (self._reader, self._setter):
                    if p and p.poll() is None:
                        try:
                            p.kill()
                        except Exception:
                            pass
            if self._running:
                time.sleep(1.0)
        print("[VOL_BUTTON] 리스너 종료")
