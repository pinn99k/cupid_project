const STAGES = [
  { num: 1, ko: "수용", en: "ACCEPTANCE" },
  { num: 2, ko: "방향", en: "DIRECTION" },
  { num: 3, ko: "기술", en: "SKILL" },
];

export default function StageStepper({ stage, compact = false }) {
  return (
    <div
      style={{
        display: "flex",
        gap: compact ? 10 : 24,
        padding: compact ? "8px 2px" : "12px 24px",
        flexWrap: compact ? "wrap" : "nowrap",
      }}
    >
      {STAGES.map((s) => {
        const active = s.num === stage;
        return (
          <div
            key={s.num}
            style={{
              display: "flex",
              alignItems: "center",
              gap: compact ? 6 : 10,
              paddingBottom: compact ? 4 : 8,
              borderBottom: active ? "3px solid #F4A7A7" : "3px solid transparent",
            }}
          >
            <div
              style={{
                width: compact ? 22 : 28,
                height: compact ? 22 : 28,
                borderRadius: "50%",
                background: active ? "#F4A7A7" : "#ddd",
                color: active ? "#fff" : "#999",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: compact ? 12 : 13,
                fontWeight: "bold",
              }}
            >
              {s.num}
            </div>
            <span
              style={{
                fontSize: compact ? 13 : 14,
                fontWeight: active ? "bold" : "normal",
                color: active ? "var(--text-primary)" : "#bbb",
              }}
            >
              {compact ? s.ko : `${s.ko} ${s.en}`}
            </span>
          </div>
        );
      })}
    </div>
  );
}
