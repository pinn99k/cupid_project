import { useState } from "react";

const STAGE_LABELS = {
  1: "LIVE · 수용 단계",
  2: "REC · 방향 단계",
  3: "REC · 기술 단계 · 감시 중",
};

export default function CameraView({ stage }) {
  const [imgError, setImgError] = useState(false);

  const overlayBase = {
    position: "absolute",
    background: "rgba(0,0,0,0.6)",
    padding: "6px 12px",
    borderRadius: 6,
    color: "#fff",
    fontSize: 13,
    display: "flex",
    alignItems: "center",
    gap: 6,
  };

  const recLabel = STAGE_LABELS[stage] || STAGE_LABELS[1];
  const isAnalyzing = stage >= 2;

  return (
    <div
      style={{
        background: "#1E1E1E",
        borderRadius: 8,
        position: "relative",
        aspectRatio: "16/9",
        overflow: "hidden",
      }}
    >
      {imgError ? (
        <div
          style={{
            width: "100%",
            height: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "rgba(255,255,255,0.5)",
            fontFamily: "monospace",
            fontSize: 14,
          }}
        >
          카메라 연결 대기 중...
        </div>
      ) : (
        <img
          src="http://localhost:8000/video_feed"
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
          onError={() => setImgError(true)}
          alt="camera feed"
        />
      )}

      {/* Top-left: 상태 표시 */}
      <div style={{ ...overlayBase, top: 12, left: 12 }}>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: isAnalyzing ? "var(--red)" : "var(--green)",
            display: "inline-block",
          }}
        />
        {recLabel}
      </div>

      {/* Top-right: YOLO (Stage 2+ 에서만) */}
      {isAnalyzing && (
        <div style={{ ...overlayBase, top: 12, right: 12 }}>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: "var(--green)",
              display: "inline-block",
            }}
          />
          YOLO · active
        </div>
      )}

      {/* Bottom center */}
      <div
        style={{
          position: "absolute",
          bottom: 10,
          left: "50%",
          transform: "translateX(-50%)",
          fontFamily: "monospace",
          fontSize: 12,
          color: "rgba(255,255,255,0.5)",
        }}
      >
        LIVE CAM
      </div>
    </div>
  );
}
