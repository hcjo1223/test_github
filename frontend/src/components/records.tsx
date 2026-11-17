// Pieces shared by the backtest report and the paper fund console: both are
// views over the same engine records.

import { useEffect, useState } from "react";
import type { Clamp, Decision, Scorecard, SessionDetail, SessionSummary, Signal } from "../api";
import { LIMIT_LABEL, money, num, pct, shares, signedMoney, signedPct, tone } from "../format";
import { ErrorNote, Loading } from "./common";
import { LineChart } from "./LineChart";

export function PerformanceCharts({ dates, nav, benchmarkNav, drawdown, benchmark }: {
  dates: string[]; nav: number[]; benchmarkNav: number[]; drawdown: number[]; benchmark: string;
}) {
  return (
    <div className="grid two">
      <div className="card">
        <h2>수익 곡선</h2>
        <LineChart
          label={`펀드 NAV와 ${benchmark} 비교`}
          dates={dates}
          series={[
            { name: "펀드", color: "var(--series-1)", values: nav },
            { name: `${benchmark} (벤치마크)`, color: "var(--series-2)", values: benchmarkNav },
          ]}
          format={(v) => (Math.abs(v) >= 10000 ? `$${(v / 1000).toFixed(0)}k` : money(v))}
        />
      </div>
      <div className="card">
        <h2>낙폭 (고점 대비)</h2>
        <LineChart
          label="펀드 낙폭"
          dates={dates}
          series={[{ name: "낙폭", color: "var(--series-1)", values: drawdown }]}
          format={(v) => pct(v)}
          area
          includeZero
        />
      </div>
    </div>
  );
}

export function SessionsTable({ sessions, selected, onSelect }: {
  sessions: SessionSummary[]; selected: string | null; onSelect: (session: string) => void;
}) {
  const [all, setAll] = useState(false);
  // Sessions that only marked the book are noise by default.
  const active = sessions.filter((s) => s.executed || s.decided);
  const rows = [...(all ? sessions : active)].reverse();
  return (
    <>
      <div className="actions" style={{ justifyContent: "space-between", marginBottom: 8 }}>
        <span className="muted">
          {all ? `전체 ${sessions.length}개 세션` : `결정·체결이 있었던 ${active.length}개 세션`} · 행을 누르면 상세
        </span>
        <button className="small" onClick={() => setAll(!all)}>
          {all ? "결정·체결 세션만" : "전체 세션 보기"}
        </button>
      </div>
      {rows.length === 0 ? (
        <div className="empty">아직 세션이 없습니다.</div>
      ) : (
        <div className="table-wrap" style={{ maxHeight: 420, overflowY: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>세션</th>
                <th className="num">NAV</th>
                <th>체결</th>
                <th>결정</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr
                  key={s.session}
                  className={`clickable ${selected === s.session ? "selected" : ""}`}
                  onClick={() => onSelect(s.session)}
                  tabIndex={0}
                  onKeyDown={(e) => e.key === "Enter" && onSelect(s.session)}
                >
                  <td style={{ whiteSpace: "nowrap" }}>{s.session}</td>
                  <td className="num">{money(s.nav)}</td>
                  <td>
                    {s.executed ? (
                      <>
                        주문 {s.executed.n_orders}건 <span className="muted">· 비용 {money(s.executed.trading_cost, 2)}</span>
                      </>
                    ) : (
                      <span className="muted">–</span>
                    )}
                  </td>
                  <td>
                    {s.decided ? (
                      s.decided.stopped_out ? (
                        <span className="tag">낙폭 청산</span>
                      ) : (
                        <>
                          신호 {s.decided.n_signals}개
                          {s.decided.n_clamps > 0 && <span className="muted"> · 클램프 {s.decided.n_clamps}</span>}
                          {s.decided.halved && <span className="tag" style={{ marginLeft: 6 }}>절반 축소</span>}
                        </>
                      )
                    ) : (
                      <span className="muted">–</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function SignalCard({ signal }: { signal: Signal }) {
  const abstained = signal.metadata.abstained === true;
  const kind = abstained || signal.value === 0 ? "neutral" : signal.value > 0 ? "bull" : "bear";
  const word = abstained ? "기권" : signal.value > 0 ? "강세" : signal.value < 0 ? "약세" : "중립";
  return (
    <div className="signal">
      <div className="signal-head">
        <strong>{signal.ticker}</strong>
        <span className="tag">{signal.model_name}</span>
        <span className={`pill ${kind}`}>{word}</span>
        <span className="muted num">확신도 {signedPct(signal.value, 0)}</span>
      </div>
      {signal.reasoning && <p>{signal.reasoning}</p>}
    </div>
  );
}

function Weights({ target, final }: { target: Record<string, number>; final: Record<string, number> }) {
  const tickers = [...new Set([...Object.keys(target), ...Object.keys(final)])].sort();
  if (tickers.length === 0) return <div className="muted">목표 비중 없음 (전량 현금)</div>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>종목</th>
            <th className="num">목표 (리스크 전)</th>
            <th className="num">최종 (리스크 후)</th>
          </tr>
        </thead>
        <tbody>
          {tickers.map((ticker) => (
            <tr key={ticker}>
              <td>{ticker}</td>
              <td className="num">{signedPct(target[ticker] ?? 0)}</td>
              <td className={`num ${tone(final[ticker] ?? 0)}`}>
                <strong>{signedPct(final[ticker] ?? 0)}</strong>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function clampText(clamp: Clamp): string {
  const what = LIMIT_LABEL[clamp.limit] ?? clamp.limit;
  return `${what}${clamp.ticker ? ` · ${clamp.ticker}` : ""}: ${pct(clamp.before)} → ${pct(clamp.after)}`;
}

export function DecisionView({ decision, compact }: { decision: Decision; compact?: boolean }) {
  return (
    <div>
      {decision.stopped_out && <div className="notice error">낙폭 한도에 걸려 전량 청산을 결정했습니다.</div>}
      <Weights target={decision.target_weights} final={decision.final_weights} />
      {decision.clamps.length > 0 && (
        <p className="hint">
          리스크 클램프: {decision.clamps.map(clampText).join(" / ")}
        </p>
      )}
      {decision.skipped.length > 0 && (
        <p className="hint">제외된 종목: {decision.skipped.map((s) => `${s.ticker} (${s.reason})`).join(", ")}</p>
      )}
      {!compact &&
        decision.strategies.map((strategy) => (
          <div key={strategy.name} style={{ marginTop: 14 }}>
            <h3>
              {strategy.name} <span className="muted">· 자본 비중 {pct(strategy.slice, 0)}</span>
            </h3>
            {strategy.signals.length === 0 ? (
              <div className="muted">신호 없음</div>
            ) : (
              strategy.signals
                .filter((signal) => signal.reasoning || signal.value !== 0)
                .map((signal) => <SignalCard key={`${signal.model_name}-${signal.ticker}`} signal={signal} />)
            )}
            {strategy.signals.some((s) => !s.reasoning && s.value === 0) && (
              <div className="hint">
                중립(신호 없음): {strategy.signals.filter((s) => !s.reasoning && s.value === 0).map((s) => `${s.model_name}·${s.ticker}`).join(", ")}
              </div>
            )}
          </div>
        ))}
    </div>
  );
}

export function SessionPanel({ session, load }: { session: string; load: (session: string) => Promise<SessionDetail> }) {
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    setDetail(null);
    setError(null);
    load(session)
      .then((value) => current && setDetail(value))
      .catch((reason: Error) => current && setError(reason.message));
    return () => {
      current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]);

  if (error) return <ErrorNote message={error} />;
  if (!detail) return <Loading />;
  const executed = detail.executed;
  return (
    <div>
      <dl className="kv" style={{ marginBottom: 12 }}>
        <dt>NAV</dt>
        <dd className="num" style={{ textAlign: "left" }}>{money(detail.nav, 2)} <span className="muted">· 현금 {money(detail.cash, 2)}</span></dd>
        <dt>{detail.benchmark} 종가</dt>
        <dd>{money(detail.benchmark_close, 2)}</dd>
        {detail.llm_model && (
          <>
            <dt>LLM</dt>
            <dd><code>{detail.llm_model}</code></dd>
          </>
        )}
        <dt>원장 해시</dt>
        <dd><code title={detail.hash}>{detail.hash.slice(0, 16)}…</code></dd>
      </dl>

      {executed && (
        <div style={{ marginBottom: 16 }}>
          <h3>이 세션에 체결됨 — {executed.as_of} 결정</h3>
          {executed.fills.length === 0 ? (
            <div className="muted">주문 없음 (목표와 현재 보유가 같음)</div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>종목</th>
                    <th>방향</th>
                    <th className="num">수량</th>
                    <th className="num">체결가</th>
                    <th className="num">금액</th>
                  </tr>
                </thead>
                <tbody>
                  {executed.fills.map((fill, i) => (
                    <tr key={i}>
                      <td>{fill.ticker}</td>
                      <td className={fill.side === "buy" ? "up" : "down"}>{fill.side === "buy" ? "매수" : "매도"}</td>
                      <td className="num">{shares(fill.quantity)}</td>
                      <td className="num">{money(fill.price, 2)}</td>
                      <td className="num">{money(fill.quantity * fill.price)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="hint">
            거래대금 {money(executed.traded_notional)} · 거래비용 {money(executed.trading_cost, 2)} (슬리피지{" "}
            {money(executed.slippage, 2)} + 수수료 {money(executed.commission, 2)})
          </p>
        </div>
      )}

      {detail.decision ? (
        <div>
          <h3>이 세션에 내린 결정 — 다음 세션 종가에 체결</h3>
          <DecisionView decision={detail.decision} />
        </div>
      ) : (
        !executed && <div className="muted">리밸런싱 세션이 아니어서 장부 평가만 했습니다.</div>
      )}
    </div>
  );
}

export function ScorecardView({ card }: { card: Scorecard }) {
  return (
    <div className="grid two">
      <div className="card">
        <h2>애널리스트 성적표</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>애널리스트</th>
                <th className="num">채점</th>
                <th className="num">대기</th>
                <th className="num">적중률</th>
                <th className="num">IC</th>
                <th className="num">t</th>
              </tr>
            </thead>
            <tbody>
              {card.analysts.map((a) => (
                <tr key={a.name}>
                  <td>
                    {a.name} <span className="muted">· {a.horizon_days}일</span>
                  </td>
                  <td className="num">{a.n_views}</td>
                  <td className="num">{a.n_pending}</td>
                  <td className="num">{a.hit_rate == null ? "–" : `${pct(a.hit_rate, 0)} (${a.n_directional})`}</td>
                  <td className="num">{num(a.ic_mean)}</td>
                  <td className="num">{num(a.ic_t_stat)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="hint">
          견해는 각 애널리스트가 선언한 지평(거래일)이 지난 뒤에 채점됩니다. "대기"는 아직 지평에 닿지 않은 견해 수입니다.
        </p>
      </div>
      <div className="card">
        <h2>전략별 손익</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>전략</th>
                <th className="num">손익</th>
                <th className="num">수익률</th>
                <th className="num">승률</th>
                <th className="num">기여도</th>
              </tr>
            </thead>
            <tbody>
              {card.strategies.map((s) => (
                <tr key={s.name}>
                  <td>{s.name}</td>
                  <td className={`num ${tone(s.pnl)}`}>{signedMoney(s.pnl)}</td>
                  <td className={`num ${tone(s.return_pct)}`}>{signedPct(s.return_pct)}</td>
                  <td className="num">{s.win_rate == null ? "–" : pct(s.win_rate, 0)}</td>
                  <td className="num">{s.share_of_pnl == null ? "–" : pct(s.share_of_pnl, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="hint">
          펀드 손익 {signedMoney(card.fund_pnl)} · 거래비용 {money(card.trading_cost, 2)} · 미귀속 {signedMoney(card.unattributed)}
        </p>
      </div>
    </div>
  );
}
