"""
가짜 디바이스 (ESP32-CAM 흉내) — 노트북에서 실행.
실제 칩 없이 서버/파이프라인 전체를 테스트하거나, 시연 중 디바이스 사망 시 폴백.

엔드포인트:
  GET  /stream             : MJPEG 스트림 (합성 프레임 또는 --video 파일)
  GET  /distance           : {"cm": <현재값>, "ts": <ms>}  (날것 cm)
  POST /set_distance?cm=30 : 거리값 수동/자동 주입

실행:
  python tools/mock_device.py                 # 합성 프레임
  python tools/mock_device.py --video clip.mp4 --port 9000

서버 연결 (.env):
  CAM_SOURCE=http://127.0.0.1:9000/stream
  ULTRASONIC_URL=http://127.0.0.1:9000/distance
"""

import argparse
import time

import cv2
import numpy as np


class MockDevice:
    """가짜 디바이스 코어 — 포트 바인딩 없이 단위테스트 가능."""

    def __init__(self, video_path: str | None = None):
        self._distance_cm: float = 100.0
        self._video_path = video_path
        self._cap = None
        self._t0 = time.time()
        if video_path:
            self._cap = cv2.VideoCapture(video_path)

    # ----- 초음파 -----
    def set_distance(self, cm: float):
        """거리값 주입 (수동 제어/자동 테스트용)."""
        self._distance_cm = float(cm)

    def distance_payload(self) -> dict:
        """디바이스 /distance 응답 형식 (날것 cm + 타임스탬프)."""
        return {"cm": self._distance_cm, "ts": int(time.time() * 1000)}

    # ----- 영상 -----
    def synthetic_frame(self) -> np.ndarray:
        """카메라 없이 만드는 합성 프레임 (움직이는 사각형)."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:] = (40, 40, 40)
        t = time.time() - self._t0
        x = int((np.sin(t) * 0.5 + 0.5) * 540)
        cv2.rectangle(frame, (x, 180), (x + 100, 320), (0, 200, 255), -1)
        cv2.putText(frame, "MOCK DEVICE", (180, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        return frame

    def next_frame(self) -> np.ndarray:
        """영상 파일이 있으면 그 프레임, 없으면 합성 프레임."""
        if self._cap is not None:
            ok, frame = self._cap.read()
            if not ok:  # 끝나면 처음으로 되감기 (루프)
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self._cap.read()
            if ok:
                return frame
        return self.synthetic_frame()

    @staticmethod
    def encode_jpeg(frame: np.ndarray) -> bytes | None:
        """프레임 → JPEG bytes."""
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return buf.tobytes() if ok else None


# ---------------------------------------------------------------------------
# 얇은 HTTP 서버 (FastAPI) — 실행 전용, 테스트는 위 MockDevice 코어로
# ---------------------------------------------------------------------------
def build_app(device: MockDevice):
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse, StreamingResponse

    app = FastAPI(title="Mock ESP32-CAM")

    @app.get("/distance")
    async def distance():
        return JSONResponse(device.distance_payload())

    @app.post("/set_distance")
    async def set_distance(cm: float):
        device.set_distance(cm)
        return {"ok": True, "cm": cm}

    def gen():
        while True:
            jpeg = device.encode_jpeg(device.next_frame())
            if jpeg:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
            time.sleep(0.042)

    @app.get("/stream")
    async def stream():
        return StreamingResponse(
            gen(), media_type="multipart/x-mixed-replace; boundary=frame"
        )

    return app


def main():
    parser = argparse.ArgumentParser(description="가짜 ESP32-CAM 디바이스")
    parser.add_argument("--video", default=None, help="MJPEG로 내보낼 영상 파일")
    parser.add_argument("--port", type=int, default=9000)
    args = parser.parse_args()

    import uvicorn

    device = MockDevice(video_path=args.video)
    print(f"[MOCK] http://127.0.0.1:{args.port}/stream  /distance  /set_distance?cm=30")
    uvicorn.run(build_app(device), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
