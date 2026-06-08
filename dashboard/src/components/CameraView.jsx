import { useEffect, useMemo, useState } from "react";

const STAGE_LABELS = {
  1: "LIVE · 수용 단계",
  2: "REC · 방향 단계",
  3: "REC · 기술 단계 · 감시 중",
};

// 카메라 박스 비율 — 박스 자체를 실제 영상 비율로 만들어 왜곡·잘림·까만띠 없이 꽉 채운다.
// 실제 스트림 해상도를 img onLoad에서 읽어 동적으로 맞춘다(회전 0/90/180/270 무관).
// 로드 전 기본값은 ESP32-CAM 기본 출력(가로 VGA 640x480 = 4:3).

export default function CameraView({ stage, objects = [], danger }) {
  const [retryKey, setRetryKey] = useState(0);
  const [imgError, setImgError] = useState(false);
  const videoUrl = useMemo(
    () => `http://${window.location.hostname}:8000/video_feed?retry=${retryKey}`,
    [retryKey],
  );

  useEffect(() => {
    if (!imgError) return undefined;
    const timer = window.setTimeout(() => {
      setImgError(false);
      setRetryKey((key) => key + 1);
    }, 1500);
    return () => window.clearTimeout(timer);
  }, [imgError]);

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
    // 바깥 래퍼: 가용 공간을 차지하고 카메라 박스를 가운데 정렬(좌우는 페이지 배경).
    <div style={{ flex: 1, minHeight: 0, display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden" }}>
      {/* 카메라 박스: 영상 비율(세로)로 만들어 왜곡·잘림·까만띠 없이 꽉 채움.
          가용 높이를 채우고 가로는 비율대로 자동. img·bbox·오버레이 모두 이 박스 기준 → 정렬 일치. */}
      <div style={{position: "relative", width: "100%", height: "100%", background: "#1E1E1E", borderRadius: 8, overflow: "hidden"}}>
        {!imgError ? (
         <img
            src={videoUrl}
            style={{
              display: "block",
              width: "100%",
              height: "100%",
              objectFit: "contain",
              transform: "rotate(-90deg)",
            }}
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
