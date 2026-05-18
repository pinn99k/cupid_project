/**
 * Step 1-9: Fallback 오디오 수동 재생 패널
 * 대시보드 숨김 버튼 — 갈라쇼/긴급 시 수동 트리거용
 */

const BUTTONS = [
  { file: "warn_emergency.mp3", label: "멈춰!" },
  { file: "warn_obstacle.mp3", label: "앞에 뭔가" },
  { file: "praise_01.mp3", label: "잘하고 있어" },
  { file: "buffer_01.mp3", label: "잠깐만" },
  { file: "gala_01.mp3", label: "시작" },
  { file: "gala_03.mp3", label: "끝" },
];

export default function FallbackPanel({ send }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
      {BUTTONS.map(({ file, label }) => (
        <button key={file} onClick={() => send({ event: "fallback", audio_file: file })}>
          {label}
        </button>
      ))}
    </div>
  );
}
