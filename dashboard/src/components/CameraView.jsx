import { useState } from "react";

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

  if (stage === 1) {
    return (
      <div
        style={{
          background: "#1E1E1E",
          borderRadius: 8,
          position: "relative",
          aspectRatio: "16/9",
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 12,
        }}
      >
        <span style={{ fontSize: 48, opacity: 0.5 }}>👁‍🗨</span>
        <span
          style={{
            fontFamily: "monospace",
            fontSize: 14,
            color: "rgba(255,255,255,0.5)",
          }}
        >
          CAMERA OFF · 수용 단계는 대화만
        </span>
      </div>
    );
  }

  const recLabel =
    stage === 2 ? "REC · 방향 단계" : "REC · 기술 단계 · 감시 중";

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

      {/* Top-left: REC */}
      <div style={{ ...overlayBase, top: 12, left: 12 }}>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: "var(--red)",
            display: "inline-block",
          }}
        />
        {recLabel}
      </div>

      {/* Top-right: YOLO */}
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
        YOLO · -- fps
      </div>

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
        LIVE CAM · 1920 × 1080 · 24 fps
      </div>
    </div>
  );
}
