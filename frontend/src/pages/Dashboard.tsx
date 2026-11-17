import { Link } from "react-router-dom";
import { api } from "../api";
import { useApp } from "../App";
import { DemoNote, ErrorNote, Kpi, Loading, PageHead } from "../components/common";
import { money, num, signedPct, tone } from "../format";
import { useLoad } from "../hooks";

export function DashboardPage() {
  const { settings } = useApp();
  const mandates = useLoad(api.mandates, []);
  const backtests = useLoad(api.backtests, []);
  const funds = useLoad(api.funds, []);
  const error = mandates.error ?? backtests.error ?? funds.error;

  return (
    <>
      <PageHead title="대시보드" sub="맨데이트를 설계하고, 과거로 검증하고, 가상 자금으로 운용합니다." />
      <ErrorNote message={error} />
      <DemoNote mode={settings.mode} />
      {settings.mode === "live" && settings.llm_warning && (
        <div className="notice">
          {settings.llm_warning} <Link to="/settings">설정으로 이동</Link>
        </div>
      )}

      <div className="kpis">
        <Kpi label="맨데이트" value={mandates.data ? String(mandates.data.length) : "…"} sub="펀드 설계서" />
        <Kpi label="백테스트" value={backtests.data ? String(backtests.data.length) : "…"} sub="저장된 결과" />
        <Kpi label="페이퍼 펀드" value={funds.data ? String(funds.data.length) : "…"} sub="운용 중" />
      </div>

      <div className="grid two">
        <div className="card">
          <h2>최근 백테스트</h2>
          {!backtests.data ? (
            <Loading />
          ) : backtests.data.length === 0 ? (
            <div className="empty">
              아직 결과가 없습니다. <Link to="/backtests">첫 백테스트 실행</Link>
            </div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>맨데이트</th>
                    <th className="num">수익률</th>
                    <th className="num">초과</th>
                    <th className="num">샤프</th>
                  </tr>
                </thead>
                <tbody>
                  {backtests.data.slice(0, 5).map((row) => (
                    <tr key={row.id}>
                      <td>
                        <Link to={`/backtests/${row.id}`}>{row.fund}</Link>
                        <div className="muted">{row.start} → {row.end}</div>
                      </td>
                      <td className={`num ${tone(row.total)}`}>{signedPct(row.total)}</td>
                      <td className={`num ${tone(row.excess)}`}>{signedPct(row.excess)}</td>
                      <td className="num">{num(row.sharpe)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        <div className="card">
          <h2>페이퍼 펀드</h2>
          {!funds.data ? (
            <Loading />
          ) : funds.data.length === 0 ? (
            <div className="empty">
              배치된 펀드가 없습니다. <Link to="/funds">맨데이트를 펀드로 배치</Link>
            </div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>펀드</th>
                    <th className="num">NAV</th>
                    <th className="num">수익률</th>
                  </tr>
                </thead>
                <tbody>
                  {funds.data.map((fund) => (
                    <tr key={fund.name}>
                      <td>
                        <Link to={`/funds/${fund.name}`}>{fund.name}</Link>{" "}
                        {fund.halted && <span className="badge halt">정지</span>}
                        <div className="muted">{fund.error ?? `${fund.n_sessions}세션 · ${fund.last_session ?? "미시작"}`}</div>
                      </td>
                      <td className="num">{money(fund.nav)}</td>
                      <td className={`num ${tone(fund.return_pct)}`}>{signedPct(fund.return_pct, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
