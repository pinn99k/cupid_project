import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

const STAGE_LABELS = {
  1: "LIVE · 수용 단계",
  2: "REC · 방향 단계",
  3: "REC · 기술 단계 · 감시 중",
};

// 카메라 박스를 '실제 영상 비율'에 맞춰 만든다 → 세로/가로 무관하게 왜곡·잘림 없이 꽉 채움.
// 디바이스가 옆으로 장착돼 서버(CAMERA_ROTATION)가 회전 보정하면 세로(portrait) 영상이
// 들어오고, 박스도 자동으로 세로가 된다. img·bbox·오버레이 모두 이 박스 기준 → 정렬 일치.
// 박스 크기는 가용 영역 안에 영상 비율을 contain으로 맞춰 JS로 계산(레이아웃 흔들림 없음).

export default function CameraView({ stage, objects = [], danger }) {
  const [retryKey, setRetryKey] = useState(0);
  const [imgError, setImgError] = useState(false);
  const imgRef = useRef(null);
  const containerRef = useRef(null);
  const [containerSize, setContainerSize] = useState({ w: 0, h: 0 });
  // 회전 보정 후 기본 세로(480x640 = 3:4). 첫 프레임 onLoad에서 실제 비율로 자동 갱신.
  const [videoAspect, setVideoAspect] = useState(3 / 4);

  const videoUrl = useMemo(
    () => `http://${window.location.hostname}:8000/video_feed?retry=${retryKey}`,
    [retryKey],
  );

  // 가용 영역 픽셀 크기를 ResizeObserver로 추적(이벤트 기반, 창 크기 변화 자동 대응).
  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return undefined;
    const update = () => setContainerSize({ w: el.clientWidth, h: el.clientHeight });
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // 영상 실제 비율을 onLoad에서 읽음(회전/재연결 시 onLoad 재발생 → 자동 갱신).
  const handleImgLoad = () => {
    const img = imgRef.current;
    if (!img) return;
    const { naturalWidth: w, naturalHeight: h } = img;
    if (w > 0 && h > 0) {
      const next = w / h;
      setVideoAspect((prev) => (Math.abs(prev - next) > 0.01 ? next : prev));
    }
  };

  useEffect(() => {
    if (!imgError) return undefined;
    const timer = window.setTimeout(() => {
      setImgError(false);
      setRetryKey((key) => key + 1);
    }, 1500);
    return () => window.clearTimeout(timer);
  }, [imgError]);

  // 가용 영역 안에 영상 비율을 contain으로 맞춘 박스 픽셀 크기.
  const box = useMemo(() => {
    const { w, h } = containerSize;
    if (w <= 0 || h <= 0) return { w: 0, h: 0 };
    const fitByWidth = { w, h: w / videoAspect };
    return fitByWidth.h <= h ? fitByWidth : { w: h * videoAspect, h };
  }, [containerSize, videoAspect]);

  const overlayBase = {
    position: "absolute",
    background: "rgba(0,0,0,0.64)",
    padding: "6px 12px",
    borderRadius: 6,
    color: "#fff",
    fontSize: 13,
    display: "flex",
    alignItems: "center",
    gap: 6,
    zIndex: 3,
  };
  const isAnalyzing = stage >= 2;

  return (
    // 가용 영역을 차지하고 카메라 박스를 가운데 정렬(세로 영상이면 좌우 여백 = 페이지 배경).
    <div
      ref={containerRef}
      style={{ flex: 1, minHeight: 0, display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden" }}
    >
      {/* 카메라 박스: 실제 영상 비율 그대로. 박스=영상이므로 bbox %가 정확히 정렬됨. */}
      <div style={{ position: "relative", width: box.w, height: box.h, background: "#000", borderRadius: 8, overflow: "hidden" }}>
        {!imgError ? (
          <img
            ref={imgRef}
            src={videoUrl}
            style={{ display: "block", width: "100%", height: "100%", objectFit: "fill" }}
            onLoad={handleImgLoad}
            onError={() => setImgError(true)}
            alt="camera feed"
          />
        ) : (
          <div style={{ width: "100%", height: "100%", display: "grid", placeItems: "center", color: "rgba(255,255,255,0.55)", fontFamily: "monospace" }}>
            카메라 다시 연결 중...
          </div>
        )}

        {isAnalyzing && objects.map((obj, index) => obj.bbox && (
          <div
            key={`${obj.label}-${index}`}
            title={`${obj.label} ${obj.direction} ${obj.distance_est}`}
            style={{
              position: "absolute",
              left: `${obj.bbox.x * 100}%`,
              top: `${obj.bbox.y * 100}%`,
              width: `${obj.bbox.w * 100}%`,
              height: `${obj.bbox.h * 100}%`,
              border: `2px solid ${danger?.object === obj.label ? "#FF3B30" : "#F4A7A7"}`,
              boxShadow: "0 0 0 1px rgba(0,0,0,0.35)",
              zIndex: 2,
            }}
          >
            <span style={{ position: "absolute", top: -22, left: -2, padding: "2px 6px", borderRadius: 3, whiteSpace: "nowrap", color: "#fff", fontSize: 11, background: danger?.object === obj.label ? "#E53935" : "#A94F67" }}>
              {obj.label} · {obj.direction}
            </span>
          </div>
        ))}

        <div style={{ ...overlayBase, top: 12, left: 12 }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: isAnalyzing ? "var(--red)" : "var(--green)" }} />
          {STAGE_LABELS[stage] || STAGE_LABELS[1]}
        </div>
        {isAnalyzing && <div style={{ ...overlayBase, top: 12, right: 12 }}>YOLO · active</div>}

        {danger && (
          <div style={{ position: "absolute", inset: 0, zIndex: 5, display: "grid", placeItems: "center", background: "rgba(229,57,53,0.84)", color: "#fff", textAlign: "center" }}>
            <div>
              <div style={{ fontSize: 20, fontWeight: 700 }}>위험 감지</div>
              <div style={{ marginTop: 8, fontSize: 38, fontWeight: 900 }}>{danger.direction} · {danger.object}</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
