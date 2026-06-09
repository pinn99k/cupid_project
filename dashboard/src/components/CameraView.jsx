import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

const STAGE_LABELS = {
  1: "LIVE · 수용 단계",
  2: "REC · 방향 단계",
  3: "REC · 기술 단계 · 감시 중",
};

// 카메라를 프레임에 꽉 채워(검은띠 없이) 출력하고, bbox는 렌더 사각형 보정으로 영상 위에 정확히 정렬한다.
// FIT_MODE: "cover"  = 프레임을 꽉 채우고 넘치는 부분만 잘라냄(검은띠 0). 화면 크기에 맞춰 최적화.
//           "contain" = 비율 유지 + 남는 곳 검정. (필요 시 한 줄만 바꾸면 전환)
// 회전은 서버(CAMERA_ROTATION)에서 처리하므로 프론트는 받은 영상을 그대로 표시한다.
const FIT_MODE = "cover";

// 프레임 크기 + 영상 원본 크기로 실제 렌더되는 영상 사각형(offset/크기)을 구한다.
// bbox(영상 정규좌표 0..1)를 이 사각형 기준 px로 변환하면 cover로 잘려도 정렬이 맞는다.
function computeRenderRect(frameW, frameH, videoW, videoH, mode) {
  if (frameW <= 0 || frameH <= 0 || videoW <= 0 || videoH <= 0) return null;
  const scale = mode === "cover"
    ? Math.max(frameW / videoW, frameH / videoH)
    : Math.min(frameW / videoW, frameH / videoH);
  const w = videoW * scale;
  const h = videoH * scale;
  return { left: (frameW - w) / 2, top: (frameH - h) / 2, width: w, height: h };
}

export default function CameraView({ stage, objects = [], danger }) {
  const [retryKey, setRetryKey] = useState(0);
  const [imgError, setImgError] = useState(false);
  const imgRef = useRef(null);
  const frameRef = useRef(null);
  // 프레임 픽셀 크기(화면 리사이즈 대응) + 영상 원본 해상도.
  const [frameSize, setFrameSize] = useState({ w: 0, h: 0 });
  const [videoSize, setVideoSize] = useState({ w: 0, h: 0 });

  const videoUrl = useMemo(
    () => `http://${window.location.hostname}:8000/video_feed?retry=${retryKey}`,
    [retryKey],
  );

  // 프레임 크기를 ResizeObserver로 추적(폴링 아님 → 이벤트 기반, 창 크기 변화에 자동 대응).
  useLayoutEffect(() => {
    const el = frameRef.current;
    if (!el) return undefined;
    const update = () => setFrameSize({ w: el.clientWidth, h: el.clientHeight });
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // 영상 원본 해상도는 onLoad에서 읽음(회전/재연결 시 onLoad 재발생 → 자동 갱신).
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

  const renderRect = computeRenderRect(frameSize.w, frameSize.h, videoSize.w, videoSize.h, FIT_MODE);
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
    // 프레임: 가용 공간을 그대로 채우는 검은 박스. 영상·bbox·오버레이 모두 이 프레임 기준 → 정렬 일치.
    <div
      ref={frameRef}
      style={{ position: "relative", flex: 1, minHeight: 0, width: "100%", background: "#000", borderRadius: 8, overflow: "hidden" }}
    >
      {!imgError ? (
        <img
          ref={imgRef}
          src={videoUrl}
          style={{ display: "block", width: "100%", height: "100%", objectFit: FIT_MODE }}
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
