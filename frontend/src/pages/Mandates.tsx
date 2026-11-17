import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { ErrorNote, Loading, PageHead } from "../components/common";
import { MODE_LABEL, REBALANCE_LABEL, money, pct, signedPct, tone } from "../format";
import { useLoad } from "../hooks";

export function MandatesPage() {
  const navigate = useNavigate();
  const mandates = useLoad(api.mandates, []);
  const [error, setError] = useState<string | null>(null);

  const remove = async (name: string) => {
    if (!window.confirm(`맨데이트 "${name}"를 삭제할까요? 이미 배치된 펀드와 백테스트 결과는 그대로 남습니다.`)) return;
    try {
      await api.deleteMandate(name);
      setError(null);
      mandates.reload();
    } catch (reason) {
      setError((reason as Error).message);
    }
  };

  return (
    <>
      <PageHead title="맨데이트" sub="펀드 설계서: 전략, 애널리스트, 리스크, 자본, 리밸런싱 주기. 종목은 실행할 때 정합니다.">
        <button className="primary" onClick={() => navigate("/mandates/new")}>새 맨데이트</button>
      </PageHead>
      <ErrorNote message={error ?? mandates.error} />
      {!mandates.data ? (
        <Loading />
      ) : mandates.data.length === 0 ? (
        <div className="card empty">맨데이트가 없습니다. 새로 만들어 보세요.</div>
      ) : (
        mandates.data.map((m) => {
          const total = (m.strategies ?? []).reduce((sum, s) => sum + s.weight, 0);
          return (
            <div className="card" key={m.file}>
              <div className="page-head" style={{ marginBottom: 8 }}>
                <div>
                  <h2 style={{ marginBottom: 2 }}>{m.name}</h2>
                  {m.error ? (
                    <span className="down">읽을 수 없는 파일: {m.error}</span>
                  ) : (
                    <span className="muted">
                      자본 {money(m.capital)} · {REBALANCE_LABEL[m.rebalance ?? ""] ?? m.cadence_label} 리밸런싱 · 벤치마크 {m.benchmark}
                    </span>
                  )}
                </div>
                <div className="actions">
                  {!m.error && <Link to={`/backtests?mandate=${encodeURIComponent(m.name)}`}>백테스트</Link>}
                  {!m.error && <Link to={`/funds?mandate=${encodeURIComponent(m.name)}`}>펀드로 배치</Link>}
                  <button className="small danger" onClick={() => remove(m.error ? m.file : m.name)}>삭제</button>
                </div>
              </div>
              {(m.strategies ?? []).map((s) => (
                <div key={s.name} style={{ marginTop: 6 }}>
                  <strong>{s.title}</strong> <span className="tag">{MODE_LABEL[s.mode]}</span>
                  <span className="muted">자본 {pct(s.weight / total, 0)} · </span>
                  {s.models.map((model) => (
                    <span className="tag" key={model}>{model}</span>
                  ))}
                </div>
              ))}
              {m.last_backtest && (
                <p className="hint" style={{ marginTop: 10 }}>
                  최근 백테스트:{" "}
                  <Link to={`/backtests/${m.last_backtest.id}`}>
                    <span className={tone(m.last_backtest.total)}>{signedPct(m.last_backtest.total)}</span> ({m.last_backtest.benchmark} 대비{" "}
                    {signedPct(m.last_backtest.excess)})
                  </Link>
                </p>
              )}
            </div>
          );
        })
      )}
    </>
  );
}
