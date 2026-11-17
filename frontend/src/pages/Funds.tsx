import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useApp } from "../App";
import { DemoNote, ErrorNote, Loading, PageHead, UniversePicker } from "../components/common";
import { money, signedPct, tone } from "../format";
import { useLoad } from "../hooks";

export function FundsPage() {
  const { settings } = useApp();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const funds = useLoad(api.funds, []);
  const mandates = useLoad(api.mandates, []);
  const catalog = useLoad(api.catalog, []);

  const [name, setName] = useState("");
  const [mandate, setMandate] = useState(params.get("mandate") ?? "");
  const [universe, setUniverse] = useState<string[]>(["AAPL", "MSFT", "NVDA"]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Minute mandates (made in the CLI) cannot be run from the web.
  const usable = (mandates.data ?? []).filter((m) => !m.error && m.rebalance !== "minute");
  useEffect(() => {
    if (!mandate && usable.length > 0) setMandate(usable[0].name);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mandates.data]);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const fund = await api.createFund({ name: name.trim(), mandate, universe });
      navigate(`/funds/${fund.name}`);
    } catch (reason) {
      setError((reason as Error).message);
      setBusy(false);
    }
  };

  return (
    <>
      <PageHead title="페이퍼 펀드" sub="맨데이트를 유니버스에 배치해 가상 자금으로 한 세션씩 운용합니다. 모든 세션은 해시 체인 원장에 남습니다." />
      <DemoNote mode={settings.mode} />
      <ErrorNote message={error ?? funds.error} />

      <div className="card">
        <h2>운용 중인 펀드</h2>
        {!funds.data ? (
          <Loading />
        ) : funds.data.length === 0 ? (
          <div className="empty">아직 펀드가 없습니다. 아래에서 배치하세요.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>펀드</th>
                  <th>맨데이트 · 유니버스</th>
                  <th className="num">세션</th>
                  <th className="num">NAV</th>
                  <th className="num">수익률</th>
                </tr>
              </thead>
              <tbody>
                {funds.data.map((fund) =>
                  fund.error ? (
                    <tr key={fund.name}>
                      <td>{fund.name}</td>
                      <td colSpan={4} className="down">{fund.error}</td>
                    </tr>
                  ) : (
                    <tr key={fund.name}>
                      <td>
                        <Link to={`/funds/${fund.name}`}><strong>{fund.name}</strong></Link>{" "}
                        {fund.halted && <span className="badge halt">정지</span>}
                      </td>
                      <td>
                        {fund.mandate} <span className="muted">· {fund.universe.join(", ")} · {fund.cadence}</span>
                      </td>
                      <td className="num">
                        {fund.n_sessions}
                        <div className="muted">{fund.last_session ?? "미시작"}</div>
                      </td>
                      <td className="num">{money(fund.nav)}</td>
                      <td className={`num ${tone(fund.return_pct)}`}>{signedPct(fund.return_pct, 2)}</td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <h2>새 펀드 배치</h2>
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
                <span>펀드 이름</span>
                <input type="text" value={name} placeholder="예: alpha" onChange={(e) => setName(e.target.value)} />
              </label>
              <label className="field">
                <span>맨데이트</span>
                <select value={mandate} onChange={(e) => setMandate(e.target.value)}>
                  {usable.map((m) => (
                    <option key={m.name} value={m.name}>{m.name}</option>
                  ))}
                </select>
              </label>
            </div>
            <UniversePicker presets={catalog.data.universe_presets} value={universe} onChange={setUniverse} />
            <p className="hint" style={{ marginTop: 10 }}>
              배치하면 맨데이트가 스냅샷으로 고정되고 유니버스도 바꿀 수 없습니다.
              {settings.mode === "demo" && " 데모 펀드는 90일 전부터 시작해 바로 여러 세션을 넘겨 볼 수 있습니다."}
            </p>
            <div className="actions">
              <button className="primary" disabled={busy || !name.trim() || !mandate || universe.length === 0} onClick={create}>
                {busy ? "배치 중…" : "펀드 배치"}
              </button>
            </div>
          </>
        )}
      </div>
    </>
  );
}
