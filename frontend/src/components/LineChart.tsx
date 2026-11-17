import { useId, useMemo, useRef, useState } from "react";

export interface Series {
  name: string;
  color: string; // a CSS variable reference, e.g. "var(--series-1)"
  values: number[];
}

interface Props {
  dates: string[];
  series: Series[];
  format: (value: number) => string;
  height?: number;
  /** Fill the first series down to zero (drawdown). */
  area?: boolean;
  /** Keep zero on the axis (drawdown); otherwise the axis hugs the data. */
  includeZero?: boolean;
  label: string;
}

const W = 760;
const PAD = { top: 10, right: 12, bottom: 22, left: 56 };

function niceTicks(min: number, max: number, count = 4): number[] {
  if (min === max) return [min];
  const raw = (max - min) / count;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? raw;
  const ticks = [];
  for (let tick = Math.ceil(min / step) * step; tick <= max + step * 1e-9; tick += step) ticks.push(tick);
  return ticks;
}

/**
 * A small line chart: one y-axis, 2px lines, hairline grid, and a
 * crosshair + tooltip that reads every series at the hovered date.
 */
export function LineChart({ dates, series, format, height = 240, area, includeZero, label }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const clip = useId();
  const n = dates.length;

  const { min, max } = useMemo(() => {
    const all = series.flatMap((s) => s.values);
    if (includeZero) all.push(0);
    let lo = Math.min(...all);
    let hi = Math.max(...all);
    if (lo === hi) {
      lo -= Math.abs(lo) * 0.01 || 1;
      hi += Math.abs(hi) * 0.01 || 1;
    }
    const pad = (hi - lo) * 0.06;
    return { min: includeZero && hi === 0 ? lo - pad : lo - pad, max: includeZero && hi === 0 ? 0 : hi + pad };
  }, [series, includeZero]);

  if (n === 0) return <div className="empty">표시할 데이터가 없습니다.</div>;

  const innerW = W - PAD.left - PAD.right;
  const innerH = height - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (n === 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const y = (v: number) => PAD.top + (1 - (v - min) / (max - min)) * innerH;
  const path = (values: number[]) => values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const ticks = niceTicks(min, max);
  const dateTicks = n <= 2 ? [0, n - 1] : [0, Math.floor((n - 1) / 2), n - 1];

  const onMove = (event: React.PointerEvent) => {
    const box = ref.current?.getBoundingClientRect();
    if (!box) return;
    const px = ((event.clientX - box.left) / box.width) * W;
    const index = Math.round(((px - PAD.left) / innerW) * (n - 1));
    setHover(Math.max(0, Math.min(n - 1, index)));
  };

  const tipLeft = hover == null ? 0 : (x(hover) / W) * 100;
  return (
    <div className="chart" ref={ref}>
      {series.length > 1 && (
        <div className="legend">
          {series.map((s) => (
            <span key={s.name}>
              <i style={{ background: s.color }} />
              {s.name}
            </span>
          ))}
        </div>
      )}
      <svg
        viewBox={`0 0 ${W} ${height}`}
        role="img"
        aria-label={label}
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        <defs>
          <clipPath id={clip}>
            <rect x={PAD.left} y={PAD.top} width={innerW} height={innerH} />
          </clipPath>
        </defs>
        {ticks.map((tick) => (
          <g key={tick}>
            <line className="gridline" x1={PAD.left} x2={W - PAD.right} y1={y(tick)} y2={y(tick)} />
            <text className="axis" x={PAD.left - 8} y={y(tick) + 4} textAnchor="end">
              {format(tick)}
            </text>
          </g>
        ))}
        {dateTicks.map((i, k) => (
          <text
            key={`${i}-${k}`}
            className="axis"
            x={x(i)}
            y={height - 6}
            textAnchor={k === 0 ? "start" : k === dateTicks.length - 1 ? "end" : "middle"}
          >
            {dates[i]}
          </text>
        ))}
        <g clipPath={`url(#${clip})`}>
          {area && n > 1 && (
            <path
              d={`${path(series[0].values)}L${x(n - 1).toFixed(1)},${y(0).toFixed(1)}L${x(0).toFixed(1)},${y(0).toFixed(1)}Z`}
              fill={series[0].color}
              opacity={0.16}
            />
          )}
          {/* Draw the last series first so the primary line sits on top. */}
          {[...series].reverse().map((s) => (
            <path key={s.name} d={path(s.values)} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          ))}
        </g>
        {hover != null && (
          <g>
            <line className="crosshair" x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={PAD.top + innerH} />
            {series.map((s) => (
              <circle key={s.name} cx={x(hover)} cy={y(s.values[hover])} r={4} fill={s.color} stroke="var(--surface)" strokeWidth={2} />
            ))}
          </g>
        )}
      </svg>
      {hover != null && (
        <div
          className="tooltip"
          style={{
            top: 28,
            left: `${tipLeft}%`,
            transform: tipLeft > 60 ? "translateX(calc(-100% - 12px))" : "translateX(12px)",
          }}
        >
          <div className="t-date">{dates[hover]}</div>
          {series.map((s) => (
            <div className="t-row" key={s.name}>
              <span>
                <i style={{ background: s.color }} />
                {s.name}
              </span>
              <strong>{format(s.values[hover])}</strong>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
