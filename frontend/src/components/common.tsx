import type { ReactNode } from "react";
import type { Mode, PositionRow } from "../api";
import { money, pct, shares } from "../format";

export function PageHead({ title, sub, crumb, children }: { title: ReactNode; sub?: ReactNode; crumb?: ReactNode; children?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        {crumb && <div className="crumb">{crumb}</div>}
        <h1>{title}</h1>
        {sub && <p>{sub}</p>}
      </div>
      {children && <div className="actions">{children}</div>}
    </div>
  );
}

export function Kpi({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="kpi">
      <div className="label">{label}</div>
      <div className={`value ${tone ?? ""}`}>{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

export function ErrorNote({ message }: { message: string | null }) {
  return message ? (
    <div className="notice error" role="alert">
      {message}
    </div>
  ) : null;
}

export function Loading({ what = "불러오는 중" }: { what?: string }) {
  return <div className="empty">{what}…</div>;
}

export function ModeBadge({ mode }: { mode: Mode }) {
  return <span className={`badge ${mode}`}>{mode === "demo" ? "DEMO · 합성 데이터" : "LIVE"}</span>;
}

export function DemoNote({ mode }: { mode: Mode }) {
  if (mode !== "demo") return null;
  return (
    <div className="notice">
      데모 모드입니다. 시세·재무는 합성 데이터이고 애널리스트 논거는 규칙 기반 휴리스틱입니다. 수익률은 전략의 성과를
      의미하지 않습니다.
    </div>
  );
}

export function Positions({ rows, cash, nav }: { rows: PositionRow[]; cash: number; nav: number }) {
  if (rows.length === 0) return <div className="empty">보유 포지션이 없습니다. 현금 {money(cash)}</div>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>종목</th>
            <th className="num">수량</th>
            <th className="num">가격</th>
            <th className="num">평가액</th>
            <th className="num">비중</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.ticker}>
              <td>
                <strong>{row.ticker}</strong> {row.shares < 0 && <span className="tag">숏</span>}
              </td>
              <td className="num">{shares(row.shares)}</td>
              <td className="num">{money(row.mark, 2)}</td>
              <td className="num">{money(row.value)}</td>
              <td className="num">
                <div className="bar-cell">
                  {pct(row.weight)}
                  <span className="bar-track" aria-hidden>
                    <span className={`bar-fill ${row.shares < 0 ? "short" : ""}`} style={{ width: `${Math.min(100, Math.abs(row.weight ?? 0) * 100)}%` }} />
                  </span>
                </div>
              </td>
            </tr>
          ))}
          <tr>
            <td className="muted">현금</td>
            <td />
            <td />
            <td className="num">{money(cash)}</td>
            <td className="num">{pct(nav ? cash / nav : null)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export function UniversePicker({ presets, value, onChange }: { presets: string[]; value: string[]; onChange: (next: string[]) => void }) {
  const toggle = (ticker: string) =>
    onChange(value.includes(ticker) ? value.filter((t) => t !== ticker) : [...value, ticker]);
  const extra = value.filter((ticker) => !presets.includes(ticker));
  return (
    <div>
      <span className="field-label">유니버스 (종목)</span>
      <div className="chips" role="group" aria-label="종목 프리셋">
        {presets.map((ticker) => (
          <button type="button" key={ticker} className="chip" aria-pressed={value.includes(ticker)} onClick={() => toggle(ticker)}>
            {ticker}
          </button>
        ))}
      </div>
      <input
        type="text"
        style={{ marginTop: 8 }}
        placeholder="직접 입력: 쉼표나 공백으로 구분 (예: COST, NFLX)"
        aria-label="종목 직접 입력"
        defaultValue={extra.join(", ")}
        onBlur={(event) => {
          const typed = event.target.value.toUpperCase().split(/[\s,]+/).filter(Boolean);
          const kept = value.filter((ticker) => presets.includes(ticker));
          onChange([...kept, ...typed.filter((ticker) => !kept.includes(ticker))]);
        }}
      />
      <div className="hint">선택됨: {value.length ? value.join(", ") : "없음"}</div>
    </div>
  );
}
