"""
웹캠 및 오디오 출력 디바이스 확인 스크립트.
실행: python scripts/check_devices.py
"""

import sys
import argparse


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


def check_microphones():
    print("[마이크 확인] sounddevice 입력 장치 확인 중...")
    try:
        import sounddevice as sd
    except ImportError:
        print("  FAIL: sounddevice가 설치되지 않았습니다.")
        sys.exit(1)

    try:
        devices = sd.query_devices()
        default_input = sd.query_devices(kind="input")
    except Exception as e:
        print(f"  FAIL: 마이크 장치 조회 실패 — {e}")
        print("  macOS 시스템 설정 > 개인정보 보호 및 보안 > 마이크 권한을 확인하세요.")
        sys.exit(1)

    input_devices = [
        (idx, dev)
        for idx, dev in enumerate(devices)
        if dev.get("max_input_channels", 0) > 0
    ]

    if not input_devices:
        print("  FAIL: 사용 가능한 입력 마이크가 없습니다.")
        sys.exit(1)

    print(f"  OK: 기본 입력 장치: {default_input.get('name', '알 수 없음')}")
    print("  입력 장치 목록:")
    for idx, dev in input_devices:
        print(
            "   "
            f" [{idx}] {dev.get('name')} "
            f"(channels={dev.get('max_input_channels')}, "
            f"rate={dev.get('default_samplerate')})"
        )
    print("  특정 장치를 쓰려면 .env에 MIC_DEVICE_INDEX=장치번호 를 추가하세요.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mic-only",
        action="store_true",
        help="웹캠/스피커 확인을 건너뛰고 마이크 입력 장치만 확인",
    )
    args = parser.parse_args()

    if args.mic_only:
        check_microphones()
        print("\n[결과] 마이크 확인 완료.")
    else:
        check_webcam()
        check_audio()
        check_microphones()
        print("\n[결과] 웹캠 + 오디오 + 마이크 확인 완료. Phase 1 진행 가능.")
