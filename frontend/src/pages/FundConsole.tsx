import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Job, type Preview } from "../api";
import { DemoNote, ErrorNote, Kpi, Loading, PageHead, Positions } from "../components/common";
import { DecisionView, PerformanceCharts, ScorecardView, SessionPanel, SessionsTable } from "../components/records";
import { money, signedPct, tone } from "../format";
import { useJob, useLoad } from "../hooks";

const EVENT_LABEL: Record<string, string> = {
  tick: "세션 실행", tick_failed: "실행 실패", halt: "정지", resume: "재개", redo: "재실행",
};

export function FundConsolePage() {
  const { name = "" } = useParams();
  const fund = useLoad(() => api.fund(name), [name]);
  // A fund with no sessions has nothing to grade; don't ask.
  const hasSessions = (fund.data?.n_sessions ?? 0) > 0;
  const scorecard = useLoad(() => (hasSessions ? api.fundScorecard(name) : Promise.resolve(null)), [name, hasSessions]);

  const [session, setSession] = useState<string | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [count, setCount] = useState(1);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = () => {
    fund.reload();
    scorecard.reload();
  };

  const job = useJob(jobId, (done: Job) => {
    setJobId(null);
    if (done.status === "succeeded") {
      const ran = done.result?.sessions ?? [];
      setNote(
        `${ran.length}개 세션 실행: ${ran[0]}${ran.length > 1 ? ` → ${ran[ran.length - 1]}` : ""}` +
          (done.result?.stopped_reason ? " · 더 실행할 완료 세션이 없어 멈췄습니다." : ""),
      );
      if (ran.length) setSession(ran[ran.length - 1]);
    } else setError(done.error ?? "실행에 실패했습니다.");
    refresh();
  });
  const running = jobId !== null;

  const act = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await action();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const openPreview = (sessions: number) =>
    act(async () => {
      setCount(sessions);
      setPreview(await api.preview(name));
    });

  const confirmRun = () =>
    act(async () => {
      const due = preview?.due ?? undefined;
      setPreview(null);
      const { job_id } = await api.tick(name, count, due);
      setJobId(job_id);
    });

  const halt = () => {
    const reason = window.prompt("정지 사유를 입력하세요. 재개할 때까지 어떤 세션도 실행되지 않습니다.");
    if (reason?.trim()) act(() => api.halt(name, reason).then(refresh));
  };

  if (!fund.data) return fund.error ? <ErrorNote message={fund.error} /> : <Loading what="펀드를 불러오는 중" />;
  const f = fund.data;
  return (
    <>
      <PageHead
        crumb={<Link to="/funds">페이퍼 펀드</Link>}
        title={
          <>
            {f.name} {f.halted && <span className="badge halt">정지</span>}
          </>
        }
        sub={
          <>
            맨데이트 {f.mandate} · {f.universe.join(", ")} · {f.cadence} · 벤치마크 {f.benchmark}
            {f.llm_model && <> · LLM <code>{f.llm_model}</code></>}
          </>
        }
      >
        <button className="primary" disabled={running || busy || !!f.halted || f.intraday} onClick={() => openPreview(1)}>
          다음 세션 실행
        </button>
        <button disabled={running || busy || !!f.halted || f.intraday} onClick={() => openPreview(20)}>
          밀린 세션 따라잡기 (최대 20)
        </button>
        {f.halted ? (
          <button disabled={busy} onClick={() => act(() => api.resume(name).then(refresh))}>재개</button>
        ) : (
          <button className="danger" disabled={busy || running} onClick={halt}>정지 (킬 스위치)</button>
        )}
      </PageHead>

      <DemoNote mode={f.mode} notes={f.notes} />
      {f.halted && <div className="notice error">정지 사유: {f.halted}</div>}
      {f.intraday && <div className="notice">분 단위 펀드는 웹에서 실행할 수 없습니다. 터미널에서 <code>aihf paper run {f.name}</code>을 사용하세요.</div>}
      <ErrorNote message={error} />
      {note && <div className="notice info" role="status">{note}</div>}
      {running && (
        <div className="card" aria-live="polite">
          <strong>세션 실행 중…</strong>
          <div className="progress">
            <div style={{ width: `${job?.progress.total ? (job.progress.done / job.progress.total) * 100 : 0}%` }} />
          </div>
          <span className="muted">{job?.progress.done ?? 0} / {job?.progress.total ?? count}</span>
        </div>
      )}

      <div className="kpis">
        <Kpi label="NAV" value={money(f.nav)} sub={`시작 자본 ${money(f.capital)}`} />
        <Kpi label="누적 수익률" value={signedPct(f.return_pct, 2)} tone={tone(f.return_pct)} />
        <Kpi label="현금" value={money(f.cash)} />
        <Kpi label="세션" value={String(f.n_sessions)} sub={f.last_session ? `마지막 ${f.last_session}` : "아직 실행 전"} />
      </div>

      {f.n_sessions === 0 ? (
        <div className="card empty">
          아직 세션이 없습니다. "다음 세션 실행"을 누르면 첫 세션에서 애널리스트들이 결정을 내리고, 그다음 세션 종가에 체결됩니다.
        </div>
      ) : (
        <>
          {f.n_sessions > 1 && (
            <PerformanceCharts dates={f.dates} nav={f.nav_series} benchmarkNav={f.benchmark_nav} drawdown={f.drawdown} benchmark={f.benchmark} />
          )}
          <div className="grid two">
            <div className="card">
              <h2>포지션</h2>
              <Positions rows={f.positions} cash={f.cash} nav={f.nav} />
            </div>
            <div className="card">
              <h2>대기 중인 결정</h2>
              {f.pending ? (
                <>
                  <p className="muted">{f.pending.as_of} 종가에 내린 결정 · 다음 세션 종가에 체결됩니다.</p>
                  <DecisionView decision={f.pending} compact />
                </>
              ) : (
                <div className="empty">대기 중인 결정이 없습니다. 다음 리밸런싱 세션에 새로 결정합니다.</div>
              )}
            </div>
          </div>

          <div className="split">
            <div className="card">
              <h2>세션 이력</h2>
              <SessionsTable sessions={f.sessions} selected={session} onSelect={setSession} />
            </div>
            <div className="card">
              <h2>{session ? `세션 상세 · ${session}` : "세션 상세"}</h2>
              {session ? (
                <SessionPanel session={session} load={(s) => api.fundSession(name, s)} />
              ) : (
                <div className="empty">세션을 고르면 논거와 체결 내역이 보입니다.</div>
              )}
            </div>
          </div>
          {scorecard.data && <ScorecardView card={scorecard.data} />}
        </>
      )}

      <div className="card">
        <h2>이벤트 로그</h2>
        {f.events.length === 0 ? (
          <div className="empty">이벤트가 없습니다.</div>
        ) : (
          <div className="table-wrap" style={{ maxHeight: 260, overflowY: "auto" }}>
            <table>
              <tbody>
                {f.events.map((event, i) => (
                  <tr key={i}>
                    <td className="muted" style={{ whiteSpace: "nowrap" }}>{event.time.replace("T", " ").slice(0, 19)}</td>
                    <td>{EVENT_LABEL[event.kind] ?? event.kind}</td>
                    <td className="muted">
                      {[event.session, event.reason, event.error].filter(Boolean).join(" · ")}
                      {typeof event.nav === "number" && ` · NAV ${money(event.nav)}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {preview && (
        <div className="dialog-backdrop" role="dialog" aria-modal="true" aria-label="세션 실행 확인">
          <div className="dialog">
            <h2>{preview.due ? `${preview.due} 세션을 실행할까요?` : "지금은 실행할 수 없습니다"}</h2>
            {preview.due ? (
              <>
                {count > 1 && <p className="muted">이 세션부터 차례로 최대 {count}개 세션을 실행합니다. 세션은 건너뛰지 않습니다.</p>}
                {preview.pending ? (
                  <>
                    <h3>이 세션 종가에 체결될 결정 ({preview.pending.as_of})</h3>
                    <DecisionView decision={preview.pending} compact />
                  </>
                ) : (
                  <p>체결할 대기 결정이 없습니다. 장부만 평가합니다.</p>
                )}
                <p className="hint">
                  {preview.rebalance
                    ? "리밸런싱 세션입니다. 체결 후 애널리스트들이 다음 결정을 새로 내립니다."
                    : "리밸런싱 세션이 아닙니다. 새 결정은 내리지 않습니다."}
                </p>
              </>
            ) : (
              <p>{preview.reason}</p>
            )}
            <div className="actions">
              <button onClick={() => setPreview(null)}>{preview.due ? "취소" : "닫기"}</button>
              {preview.due && <button className="primary" onClick={confirmRun}>실행</button>}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
