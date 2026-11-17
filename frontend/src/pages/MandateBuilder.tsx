import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type BlendMode, type Catalog, type StrategySpec } from "../api";
import { ErrorNote, Loading, PageHead } from "../components/common";
import { MODE_LABEL, pct } from "../format";
import { useLoad } from "../hooks";

interface Draft {
  weights: Record<string, number>; // strategy name -> capital slice (relative)
  custom: string[]; // analysts in the hand-built strategy
}

function buildStrategies(catalog: Catalog, draft: Draft): StrategySpec[] {
  const picked: StrategySpec[] = catalog.strategies
    .filter((s) => s.name in draft.weights)
    .map((s) => ({ name: s.name, display_name: s.display_name, models: s.models, blend: s.blend, weight: draft.weights[s.name] }));
  if (draft.custom.length > 0) {
    // Same rule as the engine's custom_strategy: any analyst that may short
    // makes the pod long/short.
    const shorts = draft.custom.some((name) => catalog.analysts.find((a) => a.name === name)?.approach === "long_short");
    const mode: BlendMode = shorts ? "long_short" : "long_only";
    picked.push({
      name: "custom", models: draft.custom.map((name) => ({ name, weight: 1 })),
      blend: { mode }, weight: draft.weights.custom ?? 1,
    });
  }
  return picked;
}

export function MandateBuilderPage() {
  const navigate = useNavigate();
  const catalog = useLoad(api.catalog, []);
  const [name, setName] = useState("");
  const [draft, setDraft] = useState<Draft>({ weights: {}, custom: [] });
  const [risk, setRisk] = useState({ max_position_pct: 25, max_gross_exposure: 100, halve_drawdown_pct: 10, max_drawdown_pct: 20 });
  const [capital, setCapital] = useState(100000);
  const [rebalance, setRebalance] = useState("weekly");
  const [benchmark, setBenchmark] = useState("SPY");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const strategies = useMemo(() => (catalog.data ? buildStrategies(catalog.data, draft) : []), [catalog.data, draft]);
  const total = strategies.reduce((sum, s) => sum + s.weight, 0);

  if (!catalog.data) return catalog.error ? <ErrorNote message={catalog.error} /> : <Loading />;
  const data = catalog.data;

  const toggleStrategy = (key: string) =>
    setDraft((d) => {
      const weights = { ...d.weights };
      if (key in weights) delete weights[key];
      else weights[key] = 1;
      return { ...d, weights };
    });
  const toggleAnalyst = (analyst: string) =>
    setDraft((d) => ({ ...d, custom: d.custom.includes(analyst) ? d.custom.filter((a) => a !== analyst) : [...d.custom, analyst] }));

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.createMandate({
        name: name.trim(),
        strategies,
        risk: {
          max_position_pct: risk.max_position_pct / 100,
          max_gross_exposure: risk.max_gross_exposure / 100,
          halve_drawdown_pct: risk.halve_drawdown_pct / 100,
          max_drawdown_pct: risk.max_drawdown_pct / 100,
        },
        capital,
        rebalance,
        benchmark: benchmark.trim().toUpperCase(),
      });
      navigate("/mandates");
    } catch (reason) {
      setError((reason as Error).message);
      setSaving(false);
    }
  };

  const riskField = (key: keyof typeof risk, label: string, hint: string) => (
    <label className="field">
      <span>{label} (%)</span>
      <input type="number" min={1} max={300} value={risk[key]} onChange={(e) => setRisk({ ...risk, [key]: Number(e.target.value) })} />
      <div className="hint">{hint}</div>
    </label>
  );

  return (
    <>
      <PageHead crumb="맨데이트" title="새 맨데이트" sub="전략을 고르고 자본·리스크·주기를 정합니다. 서버가 엔진의 규칙으로 검증합니다." />

      <div className="card">
        <label className="field" style={{ maxWidth: 360 }}>
          <span>이름</span>
          <input type="text" value={name} placeholder="예: quality-drift" onChange={(e) => setName(e.target.value)} />
          <div className="hint">영문·숫자로 시작, 영문/숫자/./_/- 사용</div>
        </label>
      </div>

      <div className="card">
        <h2>1. 전략 라이브러리</h2>
        <div className="grid two">
          {data.strategies.map((s) => (
            <button type="button" key={s.name} className="pick" aria-pressed={s.name in draft.weights} onClick={() => toggleStrategy(s.name)}>
              <strong>
                {s.title} <span className="tag">{s.kind === "systematic" ? "시스템" : "재량(LLM)"}</span>
                <span className="tag">{MODE_LABEL[s.blend.mode]}</span>
              </strong>
              <small>{s.models.map((m) => (m.weight !== 1 ? `${m.name}×${m.weight}` : m.name)).join(", ")}</small>
              <small>{s.description}</small>
            </button>
          ))}
        </div>

        <h2 style={{ marginTop: 20 }}>또는 직접 조합 (custom)</h2>
        <div className="chips" role="group" aria-label="애널리스트 선택">
          {data.analysts.map((a) => (
            <button type="button" key={a.name} className="chip" aria-pressed={draft.custom.includes(a.name)} onClick={() => toggleAnalyst(a.name)}>
              {a.display_name} · {a.kind === "llm" ? "LLM" : "퀀트"} · {a.approach === "long_short" ? "롱/숏" : "롱"}
            </button>
          ))}
        </div>
        <div className="hint">숏이 가능한 애널리스트가 하나라도 있으면 롱/숏 전략이 됩니다.</div>
      </div>

      <div className="card">
        <h2>2. 자본 배분</h2>
        {strategies.length === 0 ? (
          <div className="muted">전략을 하나 이상 고르세요.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>전략</th>
                  <th>방식</th>
                  <th style={{ width: 120 }}>비중 (상대값)</th>
                  <th className="num">자본 몫</th>
                </tr>
              </thead>
              <tbody>
                {strategies.map((s) => (
                  <tr key={s.name}>
                    <td>{s.display_name ?? s.name}</td>
                    <td>{MODE_LABEL[s.blend.mode]}</td>
                    <td>
                      <input
                        type="number" min={0.1} step={0.1} value={s.weight} aria-label={`${s.name} 비중`}
                        onChange={(e) => setDraft((d) => ({ ...d, weights: { ...d.weights, [s.name]: Number(e.target.value) } }))}
                      />
                    </td>
                    <td className="num">{pct(total ? s.weight / total : 0, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <h2>3. 리스크 한도</h2>
        <div className="row">
          {riskField("max_position_pct", "종목당 한도", "한 종목이 순자산에서 차지할 수 있는 최대 비중")}
          {riskField("max_gross_exposure", "총 노출", "롱+숏 합계. 100% = 무차입")}
          {riskField("halve_drawdown_pct", "절반 축소 낙폭", "고점 대비 이만큼 빠지면 절반 크기로 운용")}
          {riskField("max_drawdown_pct", "전량 청산 낙폭", "고점 대비 이만큼 빠지면 현금화")}
        </div>
      </div>

      <div className="card">
        <h2>4. 자본과 주기</h2>
        <div className="row">
          <label className="field">
            <span>자본 (USD)</span>
            <input type="number" min={1000} step={1000} value={capital} onChange={(e) => setCapital(Number(e.target.value))} />
          </label>
          <label className="field">
            <span>리밸런싱</span>
            <select value={rebalance} onChange={(e) => setRebalance(e.target.value)}>
              <option value="daily">매일</option>
              <option value="weekly">매주 (첫 거래일)</option>
              <option value="monthly">매월 (첫 거래일)</option>
            </select>
          </label>
          <label className="field">
            <span>벤치마크</span>
            <input type="text" value={benchmark} onChange={(e) => setBenchmark(e.target.value)} />
          </label>
        </div>
      </div>

      <ErrorNote message={error} />
      <div className="actions">
        <button className="primary" disabled={saving || !name.trim() || strategies.length === 0} onClick={save}>
          {saving ? "저장 중…" : "맨데이트 저장"}
        </button>
        <button onClick={() => navigate("/mandates")}>취소</button>
      </div>
    </>
  );
}
