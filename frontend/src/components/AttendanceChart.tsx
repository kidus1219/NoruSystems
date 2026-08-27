import { useState } from "react";

export type DailyRow = { date: string; present: number; late: number; absent: number };

type Row = { date: string; onTime: number; late: number; absent: number; total: number };

// Stacks bottom to top. Status colours, not an arbitrary series palette.
const SERIES = [
  { key: "onTime", label: "On time", colour: "var(--ok)" },
  { key: "late", label: "Late", colour: "var(--warn)" },
  { key: "absent", label: "Absent", colour: "var(--bad)" },
] as const;

const W = 760;
const H = 200;
const PAD = { top: 10, right: 6, bottom: 24, left: 28 };
const GAP = 2;
const CAP = 3;

export function AttendanceChart({ data }: { data: DailyRow[] }) {
  const [hover, setHover] = useState<{ row: Row; x: number; y: number } | null>(null);

  if (!data.length) return <div className="blank"><b>Nothing to plot</b>No attendance in this period.</div>;

  const rows: Row[] = data.map((d) => {
    const onTime = Math.max(d.present - d.late, 0);
    return { date: d.date, onTime, late: d.late, absent: d.absent, total: onTime + d.late + d.absent };
  });

  const max = roundUp(Math.max(...rows.map((r) => r.total), 1));
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const step = plotW / rows.length;
  const barW = Math.min(step * 0.6, 22);
  const y = (v: number) => PAD.top + plotH - (v / max) * plotH;
  const labelEvery = Math.ceil(rows.length / 9);

  return (
    <figure className="chart" style={{ margin: 0 }}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Daily attendance by outcome">
        {[0, max / 2, max].map((tick) => (
          <g key={tick}>
            <line className="grid" x1={PAD.left} x2={W - PAD.right} y1={y(tick)} y2={y(tick)} />
            <text x={PAD.left - 8} y={y(tick) + 3.5} textAnchor="end">{Math.round(tick)}</text>
          </g>
        ))}
        <line className="axis" x1={PAD.left} x2={W - PAD.right} y1={y(0)} y2={y(0)} />

        {rows.map((row, i) => {
          const cx = PAD.left + step * i + step / 2;
          const x = cx - barW / 2;
          let base = 0;

          return (
            <g key={row.date} className={`col${hover && hover.row.date !== row.date ? " faded" : ""}`}>
              {SERIES.map((s, si) => {
                const value = row[s.key];
                if (!value) return null;
                const top = SERIES.slice(si + 1).every((later) => !row[later.key]);
                const yTop = y(base + value);
                const raw = y(base) - yTop;
                base += value;
                return (
                  <path
                    key={s.key}
                    className="seg"
                    fill={s.colour}
                    d={column(x, yTop, barW, Math.max(raw - (top ? 0 : GAP), 1), top ? CAP : 0)}
                  />
                );
              })}
              <rect
                className="hit"
                x={cx - step / 2}
                y={PAD.top}
                width={step}
                height={plotH}
                onMouseMove={(e) => setHover({ row, x: e.clientX, y: e.clientY })}
                onMouseLeave={() => setHover(null)}
              />
            </g>
          );
        })}

        {rows.map((row, i) =>
          i % labelEvery === 0 ? (
            <text key={row.date} x={PAD.left + step * i + step / 2} y={H - 7} textAnchor="middle">
              {fmt(row.date, { day: "numeric", month: "short" })}
            </text>
          ) : null,
        )}
      </svg>

      <figcaption className="legend">
        {SERIES.map((s) => (
          <span key={s.key}>
            <i className="swatch" style={{ background: s.colour }} />
            {s.label}
          </span>
        ))}
      </figcaption>

      {hover && (
        <div className="tip" style={{ left: hover.x + 14, top: hover.y - 10 }}>
          <div className="tip-head">{fmt(hover.row.date, { weekday: "short", day: "numeric", month: "long" })}</div>
          {SERIES.map((s) => (
            <div key={s.key} className="tip-row">
              <span style={{ display: "flex", alignItems: "center", gap: 7, color: "var(--text-3)" }}>
                <i className="swatch" style={{ background: s.colour }} />
                {s.label}
              </span>
              <b>{hover.row[s.key]}</b>
            </div>
          ))}
        </div>
      )}
    </figure>
  );
}

// Rounds the top corners only, so the bar still sits flat on the axis.
function column(x: number, top: number, w: number, h: number, radius: number) {
  const r = Math.min(radius, w / 2, h);
  return [
    `M${x},${top + h}`,
    `L${x},${top + r}`,
    `Q${x},${top} ${x + r},${top}`,
    `L${x + w - r},${top}`,
    `Q${x + w},${top} ${x + w},${top + r}`,
    `L${x + w},${top + h}`,
    "Z",
  ].join(" ");
}

function roundUp(value: number) {
  const mag = Math.pow(10, Math.floor(Math.log10(value)));
  return Math.ceil(value / (mag / 2)) * (mag / 2);
}

const fmt = (iso: string, options: Intl.DateTimeFormatOptions) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, options);
