"""
웹캠 및 오디오 출력 디바이스 확인 스크립트.
실행: python scripts/check_devices.py
"""

import sys


def check_webcam():
    print("[웹캠 확인] OpenCV로 카메라 연결 중...")
    try:
        import cv2
    except ImportError:
        print("  FAIL: opencv-python이 설치되지 않았습니다.")
        sys.exit(1)

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("  FAIL: 카메라 인덱스 0 열기 실패. 카메라 연결을 확인하세요.")
        sys.exit(1)

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        print("  FAIL: 프레임 읽기 실패.")
        sys.exit(1)

    h, w = frame.shape[:2]
    print(f"  OK: 웹캠 정상 ({w}x{h} 해상도)")


def check_audio():
    print("[오디오 확인] pygame mixer 초기화 중...")
    try:
        import pygame
    except ImportError:
        print("  FAIL: pygame이 설치되지 않았습니다.")
        sys.exit(1)

    try:
        pygame.mixer.init()
        print(f"  OK: pygame mixer 초기화 성공 {pygame.mixer.get_init()}")
        pygame.mixer.quit()
    except Exception as e:
        print(f"  FAIL: pygame mixer 초기화 실패 — {e}")
        sys.exit(1)


if __name__ == "__main__":
    check_webcam()
    check_audio()
    print("\n[결과] 웹캠 + 오디오 확인 완료. Phase 1 진행 가능.")
