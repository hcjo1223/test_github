import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, type Job } from "../api";
import { useApp } from "../App";
import { DemoNote, ErrorNote, Loading, PageHead, UniversePicker } from "../components/common";
import { LineChart } from "../components/LineChart";
import { money, num, pct, signedPct, tone } from "../format";
import { useJob, useLoad } from "../hooks";

export function BacktestsPage() {
  const { settings } = useApp();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const mandates = useLoad(api.mandates, []);
  const catalog = useLoad(api.catalog, []);
  const results = useLoad(api.backtests, []);

  const [mandate, setMandate] = useState(params.get("mandate") ?? "");
  const [universe, setUniverse] = useState<string[]>(["AAPL", "MSFT", "NVDA"]);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const usable = (mandates.data ?? []).filter((m) => !m.error);
  useEffect(() => {
    if (!mandate && usable.length > 0) setMandate(usable[0].name);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mandates.data]);

  const job = useJob(jobId, (done: Job) => {
    if (done.status === "succeeded" && done.result?.backtest_id) navigate(`/backtests/${done.result.backtest_id}`);
    else {
      setError(done.error ?? "백테스트가 실패했습니다.");
      setJobId(null);
    }
  });
  const running = jobId !== null;

  const submit = async () => {
    setError(null);
    try {
      const { job_id } = await api.startBacktest({ mandate, universe, start: start || undefined, end: end || undefined });
      setJobId(job_id);
    } catch (reason) {
      setError((reason as Error).message);
    }
  };

  const remove = async (id: string) => {
    if (!window.confirm("이 백테스트 결과를 삭제할까요?")) return;
    try {
      await api.deleteBacktest(id);
      results.reload();
    } catch (reason) {
      setError((reason as Error).message);
    }
  };

  const partial = job?.partial;
  const progress = job?.progress;
  return (
    <>
      <PageHead title="백테스트" sub="맨데이트를 과거 구간에 재생합니다. T일 종가의 결정은 T+1일 종가에 체결됩니다." />
      <DemoNote mode={settings.mode} />
      <ErrorNote message={error ?? mandates.error ?? results.error} />

      <div className="card">
        <h2>새 백테스트</h2>
        {!mandates.data || !catalog.data ? (
          <Loading />
        ) : usable.length === 0 ? (
          <div className="empty">
            먼저 <Link to="/mandates/new">맨데이트를 만드세요</Link>.
          </div>
        ) : (
          <>
            <div className="row">
              <label className="field">
                <span>맨데이트</span>
                <select value={mandate} onChange={(e) => setMandate(e.target.value)} disabled={running}>
                  {usable.map((m) => (
                    <option key={m.name} value={m.name}>{m.name}</option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>시작일</span>
                <input type="date" value={start} onChange={(e) => setStart(e.target.value)} disabled={running} />
              </label>
              <label className="field">
                <span>종료일</span>
                <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} disabled={running} />
              </label>
            </div>
            <div className="hint" style={{ marginTop: -6, marginBottom: 12 }}>
              날짜를 비우면 가장 최근 완료 세션까지 {catalog.data.defaults.backtest_days}일을 재생합니다.
            </div>
            <UniversePicker presets={catalog.data.universe_presets} value={universe} onChange={setUniverse} />
            <div className="actions" style={{ marginTop: 14 }}>
              <button className="primary" disabled={running || !mandate || universe.length === 0} onClick={submit}>
                {running ? "실행 중…" : "백테스트 실행"}
              </button>
            </div>
          </>
        )}

        {running && (
          <div style={{ marginTop: 16 }} aria-live="polite">
            <strong>{job?.label ?? "대기 중"}</strong>
            <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={progress?.total ?? 0} aria-valuenow={progress?.done ?? 0}>
              <div style={{ width: `${progress?.total ? (progress.done / progress.total) * 100 : 0}%` }} />
            </div>
            <div className="muted">
              {job?.status === "queued" ? "대기열에서 기다리는 중" : `${progress?.done ?? 0} / ${progress?.total ?? "?"} 세션`}
            </div>
            {partial?.dates && partial.nav && partial.benchmark_nav && partial.dates.length > 1 && (
              <LineChart
                label="진행 중인 백테스트의 NAV"
                height={200}
                dates={partial.dates}
                series={[
                  { name: "펀드", color: "var(--series-1)", values: partial.nav },
                  { name: "벤치마크", color: "var(--series-2)", values: partial.benchmark_nav },
                ]}
                format={(v) => money(v)}
              />
            )}
          </div>
        )}
      </div>

      <div className="card">
        <h2>결과 이력</h2>
        {!results.data ? (
          <Loading />
        ) : results.data.length === 0 ? (
          <div className="empty">저장된 결과가 없습니다.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>맨데이트 · 기간</th>
                  <th>유니버스</th>
                  <th className="num">수익률</th>
                  <th className="num">벤치마크</th>
                  <th className="num">초과</th>
                  <th className="num">샤프</th>
                  <th className="num">MDD</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {results.data.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <Link to={`/backtests/${row.id}`}>{row.fund}</Link>
                      <div className="muted">{row.start} → {row.end}</div>
                    </td>
                    <td>{row.universe.join(", ")}</td>
                    <td className={`num ${tone(row.total)}`}>{signedPct(row.total)}</td>
                    <td className="num">{signedPct(row.benchret)}</td>
                    <td className={`num ${tone(row.excess)}`}>{signedPct(row.excess)}</td>
                    <td className="num">{num(row.sharpe)}</td>
                    <td className="num">{pct(row.maxdd)}</td>
                    <td className="num">
                      <button className="small danger" onClick={() => remove(row.id)} aria-label={`${row.fund} 결과 삭제`}>삭제</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
