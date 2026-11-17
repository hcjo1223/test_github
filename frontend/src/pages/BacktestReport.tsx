import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { DemoNote, ErrorNote, Kpi, Loading, PageHead, Positions } from "../components/common";
import { PerformanceCharts, ScorecardView, SessionPanel, SessionsTable } from "../components/records";
import { REBALANCE_LABEL, money, num, pct, signedPct, tone } from "../format";
import { useLoad } from "../hooks";

export function BacktestReportPage() {
  const { id = "" } = useParams();
  const report = useLoad(() => api.backtest(id), [id]);
  const [session, setSession] = useState<string | null>(null);

  if (!report.data) return report.error ? <ErrorNote message={report.error} /> : <Loading what="리포트를 불러오는 중" />;
  const r = report.data;
  const m = r.metrics;
  return (
    <>
      <PageHead
        crumb={<Link to="/backtests">백테스트</Link>}
        title={r.fund}
        sub={
          <>
            {r.start} → {r.end} · {r.universe.join(", ")} · {REBALANCE_LABEL[r.rebalance] ?? r.rebalance} 리밸런싱 · 자본 {money(r.capital)}
            {r.llm_model && <> · LLM <code>{r.llm_model}</code></>}
          </>
        }
      />
      <DemoNote mode={r.mode} notes={r.notes} />

      <div className="kpis">
        <Kpi label="총수익률" value={signedPct(m.total_return_pct)} tone={tone(m.total_return_pct)} sub={`연환산 ${signedPct(m.annualized_return_pct)}`} />
        <Kpi label={`${r.benchmark} (벤치마크)`} value={signedPct(m.benchmark_return_pct)} />
        <Kpi label="초과수익" value={signedPct(m.excess_return_pct)} tone={tone(m.excess_return_pct)} sub="펀드 − 벤치마크" />
        <Kpi label="샤프 비율" value={num(m.sharpe_ratio)} sub="일간 수익률 연율화" />
        <Kpi label="최대 낙폭" value={pct(m.max_drawdown_pct)} sub="고점 대비" />
        <Kpi label="거래비용" value={money(m.trading_cost)} sub={`리밸런싱 ${m.n_cycles}회 · 주문 ${m.n_orders}건`} />
      </div>

      <PerformanceCharts dates={r.dates} nav={r.nav} benchmarkNav={r.benchmark_nav} drawdown={r.drawdown} benchmark={r.benchmark} />

      <div className="split">
        <div className="card">
          <h2>세션</h2>
          <SessionsTable sessions={r.sessions} selected={session} onSelect={setSession} />
        </div>
        <div className="card">
          <h2>{session ? `세션 상세 · ${session}` : "세션 상세"}</h2>
          {session ? (
            <SessionPanel session={session} load={(s) => api.backtestSession(id, s)} />
          ) : (
            <div className="empty">왼쪽에서 세션을 고르면 애널리스트 논거, 비중, 체결 내역이 보입니다.</div>
          )}
        </div>
      </div>

      <div className="card">
        <h2>최종 포지션 ({r.end})</h2>
        <Positions rows={r.positions} cash={r.cash} nav={r.nav[r.nav.length - 1]} />
      </div>

      <ScorecardView card={r.scorecard} />
    </>
  );
}
