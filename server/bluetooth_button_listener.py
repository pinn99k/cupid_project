"""
골전도 이어폰(COSY) 가운데 버튼 → 마이크 토글.

실측 확인: HFP 활성(이어폰 마이크 열림) 상태에서 가운데 버튼을 누르면 bluetoothd가
  "Received call hangup event (AT+CHUP) from device ..." 를 Debug 레벨로 로깅한다.
서버는 수동 모드에서 이어폰 마이크를 계속 열어두므로(HFP 유지) 버튼을 누를 때마다
이 이벤트가 발생한다. 이 모듈이 그 줄을 감시해 토글 콜백을 실행한다.

설계:
- 별도 스레드 + 서브프로세스(log stream) → 이벤트 루프 비블로킹.
- ⚠️ 이벤트가 Debug 레벨이라 log stream 에 --info --debug 가 필수.
- debounce(중복) + 시작 유예(초기 잡음 무시) + 예외 시 리스너만 재시작(서버 불사).
- macOS 아니면 no-op.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import threading
import time
from typing import Awaitable, Callable

# COSY 가운데 버튼(HFP 모드) = AT+CHUP = 통화 종료 이벤트. 정적 문자열이라 predicate로 매칭.
_MARKER = "Received call hangup event"

_LOG_CMD = [
    "/usr/bin/log", "stream",
    "--info", "--debug",   # ★ 이벤트가 Debug 레벨 → 필수
    "--style", "compact",
    "--predicate", f'eventMessage contains "{_MARKER}"',
]


class BluetoothButtonListener:
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        on_toggle: Callable[[], Awaitable[None]],
        debounce_sec: float = 0.5,
        startup_grace_sec: float = 2.0,
    ):
        self._loop = loop
        self._on_toggle = on_toggle
        self._debounce_sec = debounce_sec
        self._startup_grace_sec = startup_grace_sec
        self._last_fire = 0.0
        self._grace_until = 0.0
        self._running = False
        self._thread: threading.Thread | None = None
        self._proc: subprocess.Popen | None = None

    def start(self) -> None:
        if sys.platform != "darwin":
            print("[BT_BUTTON] macOS 아님 → 비활성")
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="bt-button", daemon=True)
        self._thread.start()
        print(f"[BT_BUTTON] 리스너 시작 — 감시 문자열: {_MARKER!r}")

    def stop(self) -> None:
        self._running = False
        self._kill_proc()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=2)

    def _kill_proc(self) -> None:
        p = self._proc
        self._proc = None
        if p and p.poll() is None:
            try:
                p.terminate()
                try:
                    p.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    p.kill()
            except Exception:
                pass

    def _run(self) -> None:
        backoff = 1.0
        while self._running:
            try:
                self._proc = subprocess.Popen(
                    _LOG_CMD, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, bufsize=1,
                )
                backoff = 1.0
                # 스트림 attach 직후 유예 — 초기 버스트/헤더 무시.
                self._grace_until = time.monotonic() + self._startup_grace_sec
                assert self._proc.stdout is not None
                for line in self._proc.stdout:
                    if not self._running:
                        break
                    # log stream 헤더(predicate echo)는 마커를 포함하므로 스킵.
                    if "Filtering the log data using" in line:
                        continue
                    if _MARKER in line:
                        self._handle()
            except Exception as e:
                print(f"[BT_BUTTON] 오류(리스너만 재시작): {type(e).__name__}: {e}")
            finally:
                self._kill_proc()
            if self._running:
                time.sleep(backoff)
                backoff = min(backoff * 2, 10.0)
        print("[BT_BUTTON] 리스너 종료")

    def _handle(self) -> None:
        now = time.monotonic()
        if now < self._grace_until:
            print("[BT_BUTTON] ignored startup event")
            return
        if now - self._last_fire < self._debounce_sec:
            return  # debounce
        self._last_fire = now
        print("[BT_BUTTON] 가운데 버튼 감지 → 마이크 토글")
        try:
            asyncio.run_coroutine_threadsafe(self._on_toggle(), self._loop)
        except Exception as e:
            print(f"[BT_BUTTON] 토글 스케줄 실패: {e}")
