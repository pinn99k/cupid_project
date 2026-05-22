const STAGES = [
  { num: 1, ko: "수용", en: "ACCEPTANCE" },
  { num: 2, ko: "방향", en: "DIRECTION" },
  { num: 3, ko: "기술", en: "SKILL" },
];

export default function StageStepper({ stage }) {
  return (
    <div style={{ display: "flex", gap: 24, padding: "12px 24px" }}>
      {STAGES.map((s) => {
        const active = s.num === stage;
        return (
          <div
            key={s.num}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              paddingBottom: 8,
              borderBottom: active ? "3px solid #F4A7A7" : "3px solid transparent",
            }}
          >
            <div
              style={{
                width: 28,
                height: 28,
                borderRadius: "50%",
                background: active ? "#F4A7A7" : "#ddd",
                color: active ? "#fff" : "#999",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 13,
                fontWeight: "bold",
              }}
            >
              {s.num}
            </div>
            <span
              style={{
                fontSize: 14,
                fontWeight: active ? "bold" : "normal",
                color: active ? "var(--text-primary)" : "#bbb",
              }}
            >
              {s.ko} {s.en}
            </span>
          </div>
        );
      })}
    </div>
  );
}
