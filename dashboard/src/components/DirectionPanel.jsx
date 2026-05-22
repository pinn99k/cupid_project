const DIRS = [
  { key: "left", label: "왼쪽", hint: "L" },
  { key: "center", label: "정면", hint: "C" },
  { key: "right", label: "오른쪽", hint: "R" },
];

export default function DirectionPanel({ objects = [] }) {
  const grouped = { left: [], center: [], right: [] };
  objects.forEach((obj) => {
    if (grouped[obj.direction]) {
      grouped[obj.direction].push(obj);
    }
  });

  return (
    <div style={{ display: "flex", gap: 8 }}>
      {DIRS.map((d) => (
        <div
          key={d.key}
          style={{
            flex: 1,
            background: "#fff",
            border: "1px solid #eee",
            borderRadius: 8,
            padding: 12,
            minHeight: 70,
          }}
        >
          {/* Top row */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 8,
            }}
          >
            <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
              {d.label}
            </span>
            <span
              style={{
                width: 20,
                height: 20,
                borderRadius: "50%",
                background: "var(--pink-light)",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 11,
                fontWeight: "bold",
                color: "var(--text-primary)",
              }}
            >
              {d.hint}
            </span>
          </div>

          {/* Object tags */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {grouped[d.key].map((obj, i) => (
              <span
                key={i}
                style={{
                  background: "var(--pink-light)",
                  padding: "4px 8px",
                  borderRadius: 4,
                  fontSize: 12,
                  color: "var(--text-primary)",
                }}
              >
                {obj.label}{" "}
                {obj.distance_est ? obj.distance_est.toUpperCase() : ""}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
