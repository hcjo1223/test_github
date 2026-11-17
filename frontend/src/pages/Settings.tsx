import { useState } from "react";
import { api, type Mode } from "../api";
import { useApp } from "../App";
import { ErrorNote, Loading, PageHead } from "../components/common";
import { useLoad } from "../hooks";

export function SettingsPage() {
  const { settings, reloadSettings } = useApp();
  const catalog = useLoad(api.catalog, [settings]);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [contact, setContact] = useState(settings.contact ?? "");

  const run = async (action: () => Promise<unknown>, done: string) => {
    setError(null);
    setSaved(null);
    try {
      await action();
      setSaved(done);
      reloadSettings();
    } catch (reason) {
      setError((reason as Error).message);
    }
  };

  const MODE_NAME: Record<Mode, string> = { demo: "데모", free: "무료 데이터", live: "LIVE" };
  const setMode = (mode: Mode) => run(() => api.updateSettings({ mode }), `${MODE_NAME[mode]} 모드로 전환했습니다.`);
  const saveContact = () => run(() => api.updateSettings({ contact }), "연락처를 저장했습니다.");
  const saveKey = (envVar: string) =>
    run(async () => {
      await api.saveCredential(envVar, drafts[envVar]);
      setDrafts((d) => ({ ...d, [envVar]: "" }));
    }, `${envVar}를 저장했습니다.`);

  return (
    <>
      <PageHead title="설정" sub="실행 모드, LLM 모델, API 키." />
      <ErrorNote message={error} />
      {saved && <div className="notice info" role="status">{saved}</div>}

      <div className="card">
        <h2>실행 모드</h2>
        <div className="grid three">
          <button type="button" className="pick" aria-pressed={settings.mode === "demo"} onClick={() => setMode("demo")}>
            <strong>데모</strong>
            <small>키 없이 동작. 합성 시세·재무와 규칙 기반 애널리스트를 씁니다. 저장소는 web-demo/로 분리됩니다.</small>
          </button>
          <button type="button" className="pick" aria-pressed={settings.mode === "free"} disabled={!settings.free_ready} onClick={() => setMode("free")}>
            <strong>무료 데이터 (탐색용)</strong>
            <small>
              SEC EDGAR 재무(공시일 기준 시점 정합) + Yahoo 시세. 유료 키 없이 실제 종목을 돌려 봅니다. 단, 추정치가 없어 PEAD는 신호가 없고
              재무는 재구성한 근사값입니다. 결과를 성과 근거로 삼지 마세요.
              {!settings.free_ready && ` 사용하려면: ${settings.free_blockers.join(" ")}`}
            </small>
          </button>
          <button type="button" className="pick" aria-pressed={settings.mode === "live"} disabled={!settings.live_ready} onClick={() => setMode("live")}>
            <strong>LIVE</strong>
            <small>
              Financial Datasets 실데이터와 선택한 LLM을 씁니다. aihf CLI/TUI와 같은 ~/.hedge-fund를 공유합니다.
              {!settings.live_ready && ` 사용하려면: ${settings.live_blockers.join(" ")}`}
            </small>
          </button>
        </div>
        {settings.free_ready && settings.free_uses_demo_llm && (
          <p className="hint" style={{ marginTop: 10 }}>
            무료 데이터 모드에서는 선택한 모델의 키가 없으면 투자자 에이전트가 규칙 기반 휴리스틱(`[demo]`)으로 동작합니다.
          </p>
        )}
        {settings.llm_warning && <p className="hint" style={{ marginTop: 10 }}>{settings.llm_warning}</p>}
      </div>

      <div className="card">
        <h2>무료 데이터 연락처 (SEC EDGAR)</h2>
        <p className="hint">
          SEC는 자동화 클라이언트가 <strong>실제 연락처</strong>로 자신을 밝히고 초당 10회 이하로 요청하길 요구합니다. 입력한 값은 SEC로 보내는
          요청의 User-Agent에만 쓰이며 <code>web-settings.json</code>에 저장됩니다. 가짜 주소는 쓰지 마세요.
        </p>
        <div className="row">
          <label className="field">
            <span>연락처</span>
            <input type="text" value={contact} placeholder="이름 name@example.com" onChange={(e) => setContact(e.target.value)} />
          </label>
          <div className="fixed">
            <button className="small" disabled={contact.trim() === (settings.contact ?? "")} onClick={saveContact}>저장</button>
          </div>
        </div>
      </div>

      <div className="card">
        <h2>LLM 모델 (LIVE·무료 모드에서 투자자 에이전트가 사용)</h2>
        {!catalog.data ? (
          <Loading />
        ) : (
          <label className="field" style={{ maxWidth: 420 }}>
            <span>모델</span>
            <select value={settings.model} onChange={(e) => run(() => api.updateSettings({ model: e.target.value }), "모델을 변경했습니다.")}>
              {catalog.data.models.map((m) => (
                <option key={m.model} value={m.model} disabled={!m.supported}>
                  {m.display_name} · {m.provider} {m.key_set ? "" : "(키 없음)"}
                </option>
              ))}
            </select>
            <div className="hint">퀀트 모델(PEAD)은 LLM을 쓰지 않습니다.</div>
          </label>
        )}
      </div>

      <div className="card">
        <h2>API 키</h2>
        <p className="hint">
          키는 이 컴퓨터의 <code>~/.hedge-fund/.env</code>(권한 0600)에 저장되며, 저장 후에는 마스킹된 값만 표시됩니다.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>용도</th>
                <th>상태</th>
                <th>새 값</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {settings.credentials.map((c) => (
                <tr key={c.env_var}>
                  <td>
                    {c.label}
                    <div className="muted"><code>{c.env_var}</code></div>
                  </td>
                  <td>{c.set ? <code>{c.masked}</code> : <span className="muted">미등록</span>}</td>
                  <td>
                    <input
                      type="password" autoComplete="off" aria-label={`${c.env_var} 값`} value={drafts[c.env_var] ?? ""}
                      onChange={(e) => setDrafts({ ...drafts, [c.env_var]: e.target.value })}
                    />
                  </td>
                  <td>
                    <button className="small" disabled={!drafts[c.env_var]?.trim()} onClick={() => saveKey(c.env_var)}>저장</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
