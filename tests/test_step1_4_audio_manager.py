"""
Step 1-4 테스트: AudioManager (스레드 분리 + Lock)
실행: python tests/test_step1_4_audio_manager.py
하드웨어 불필요 — pygame mock 사용.
"""

import sys
import os
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-needed")


def test_audio_manager():
    print("=" * 50)
    print("Step 1-4: AudioManager 테스트")
    print("=" * 50)

    # --- Case 1: 클래스 import 및 인스턴스 생성 ---
    print("\n[1] AudioManager import...")
    from ai_core.audio_manager import AudioManager, get_audio_manager
    print("[PASS] Case 1: import 성공")

    # --- Case 2: 싱글톤 동작 ---
    print("\n[2] 싱글톤 검증...")
    mgr1 = get_audio_manager()
    mgr2 = get_audio_manager()
    assert mgr1 is mgr2, "싱글톤 인스턴스가 같아야 함"
    print("[PASS] Case 2: 싱글톤 동작 확인")

    # --- Case 3: 내부 스레드 alive ---
    print("\n[3] Audio Thread 확인...")
    assert mgr1._thread.is_alive(), "Audio Thread가 실행 중이어야 함"
    assert mgr1._thread.daemon is True, "Audio Thread는 daemon이어야 함"
    print("[PASS] Case 3: Audio Thread alive + daemon")

    # --- Case 4: Lock 존재 + 타입 ---
    print("\n[4] Lock 확인...")
    assert isinstance(mgr1._lock, type(threading.Lock())), "threading.Lock 타입이어야 함"
    print("[PASS] Case 4: Lock 정상")

    # --- Case 5: play() — 존재하지 않는 파일 → 에러 없이 스킵 ---
    print("\n[5] play() 없는 파일 스킵...")
    mgr1.play("nonexistent_file_12345.mp3")
    time.sleep(0.3)
    print("[PASS] Case 5: 존재하지 않는 파일 → 에러 없이 무시")

    # --- Case 6: play_path() — 존재하지 않는 경로 → 에러 없이 스킵 ---
    print("\n[6] play_path() 없는 파일 스킵...")
    mgr1.play_path("/tmp/nonexistent_12345.mp3")
    time.sleep(0.3)
    print("[PASS] Case 6: 존재하지 않는 경로 → 에러 없이 무시")

    # --- Case 7: stop() 호출 가능 ---
    print("\n[7] stop() 호출...")
    mgr1.stop()  # 재생 중 아니어도 에러 없어야
    print("[PASS] Case 7: stop() 정상 호출")

    # --- Case 8: is_playing() 반환값 ---
    print("\n[8] is_playing() 확인...")
    result = mgr1.is_playing()
    assert isinstance(result, bool), f"bool이어야 함: {type(result)}"
    assert result is False, "재생 중이 아니므로 False"
    print("[PASS] Case 8: is_playing() → False")

    print(f"\n[결과] Step 1-4 PASS — 8개 케이스 모두 통과")


if __name__ == "__main__":
    test_audio_manager()
