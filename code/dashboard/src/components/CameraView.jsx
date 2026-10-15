import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

const STAGE_LABELS = {
  1: "LIVE · 수용 단계",
  2: "REC · 방향 단계",
  3: "REC · 기술 단계 · 감시 중",
};

// 고정 크기 검은 프레임 + 받아오는 영상 '전부' 표시(objectFit contain).
// 프레임은 가용 영역을 그대로 채우는 고정 사각형 → 영상 비율에 따라 크기가 변하지 않음.
// 영상은 잘리지 않고 통째로 들어가며(세로/가로 무관), 비율이 안 맞는 부분만 검정 여백.
// bbox는 실제 표시되는 영상 사각형(letterbox 보정) 기준 px → 회전/세로에서도 정확히 정렬.

// 프레임 안에 영상 비율을 contain으로 맞췄을 때 실제 표시되는 영상 사각형(offset/크기).
function computeRenderRect(frameW, frameH, videoW, videoH) {
  if (frameW <= 0 || frameH <= 0 || videoW <= 0 || videoH <= 0) return null;
  const scale = Math.min(frameW / videoW, frameH / videoH); // contain
  const w = videoW * scale;
  const h = videoH * scale;
  return { left: (frameW - w) / 2, top: (frameH - h) / 2, width: w, height: h };
}

export default function CameraView({ stage, objects = [], danger }) {
  const [retryKey, setRetryKey] = useState(0);
  const [imgError, setImgError] = useState(false);
  const imgRef = useRef(null);
  const frameRef = useRef(null);
  const [frameSize, setFrameSize] = useState({ w: 0, h: 0 });
  const [videoSize, setVideoSize] = useState({ w: 0, h: 0 });

  const videoUrl = useMemo(
    () => `http://${window.location.hostname}:8000/video_feed?retry=${retryKey}`,
    [retryKey],
  );

  // 고정 프레임 픽셀 크기를 ResizeObserver로 추적(창 크기 변화 자동 대응).
  useLayoutEffect(() => {
    const el = frameRef.current;
    if (!el) return undefined;
    const update = () => setFrameSize({ w: el.clientWidth, h: el.clientHeight });
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // 영상 원본 해상도(회전/재연결 시 onLoad 재발생 → 자동 갱신).
  const handleImgLoad = () => {
    const img = imgRef.current;
    if (!img) return;
    const { naturalWidth: w, naturalHeight: h } = img;
    if (w > 0 && h > 0) setVideoSize({ w, h });
  };

  useEffect(() => {
    if (!imgError) return undefined;
    const timer = window.setTimeout(() => {
      setImgError(false);
      setRetryKey((key) => key + 1);
    }, 1500);
    return () => window.clearTimeout(timer);
  }, [imgError]);

  const renderRect = computeRenderRect(frameSize.w, frameSize.h, videoSize.w, videoSize.h);
  const isAnalyzing = stage >= 2;

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

  return (
    // 고정 검은 프레임: 가용 영역을 그대로 채움(영상 비율에 따라 크기 안 변함).
    <div
      ref={frameRef}
      style={{ position: "relative", flex: 1, minHeight: 0, width: "100%", background: "#000", borderRadius: 8, overflow: "hidden" }}
    >
      {!imgError ? (
        <img
          ref={imgRef}
          src={videoUrl}
          // contain: 받아오는 영상 전부 표시(잘림 없음), 남는 곳은 검정.
          style={{ display: "block", width: "100%", height: "100%", objectFit: "contain" }}
          onLoad={handleImgLoad}
          onError={() => setImgError(true)}
          alt="camera feed"
        />
      ) : (
        <div style={{ width: "100%", height: "100%", display: "grid", placeItems: "center", color: "rgba(255,255,255,0.55)", fontFamily: "monospace" }}>
          카메라 다시 연결 중...
        </div>
      )}

      {isAnalyzing && renderRect && objects.map((obj, index) => obj.bbox && (
        <div
          key={`${obj.label}-${index}`}
          title={`${obj.label} ${obj.direction} ${obj.distance_est}`}
          style={{
            position: "absolute",
            left: renderRect.left + obj.bbox.x * renderRect.width,
            top: renderRect.top + obj.bbox.y * renderRect.height,
            width: obj.bbox.w * renderRect.width,
            height: obj.bbox.h * renderRect.height,
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
  );
}
