// Types mirror the backend's view models (docs/04-api-spec.md).

export type Mode = "demo" | "live";

export interface Settings {
  mode: Mode;
  model: string;
  live_ready: boolean;
  live_blockers: string[];
  llm_warning: string | null;
  credentials: { env_var: string; label: string; set: boolean; masked: string | null }[];
}

export interface Analyst {
  name: string;
  display_name: string;
  short_name: string;
  kind: "llm" | "quant";
  approach: "long_only" | "long_short";
  horizon_days: number;
}

export type BlendMode = "long_only" | "long_short" | "dollar_neutral";

export interface StrategySpec {
  name: string;
  display_name?: string | null;
  weight: number;
  models: { name: string; weight: number; params?: Record<string, unknown> }[];
  blend: { mode: BlendMode; method?: string; gross_target?: number };
}

export interface LibraryStrategy extends StrategySpec {
  title: string;
  kind: "discretionary" | "systematic";
  description: string;
}

export interface Catalog {
  analysts: Analyst[];
  strategies: LibraryStrategy[];
  models: { display_name: string; model: string; provider: string; supported: boolean; key_set: boolean }[];
  universe_presets: string[];
  defaults: {
    risk: Record<string, number>;
    capital: number;
    backtest_days: number;
    rebalance: string;
    benchmark: string;
  };
}

export interface SpecSummary {
  name: string;
  capital: number;
  rebalance: string;
  cadence_label: string;
  benchmark: string;
  strategies: { name: string; title: string; mode: BlendMode; weight: number; models: string[] }[];
}

export interface MandateRow extends Partial<SpecSummary> {
  file: string;
  name: string;
  error: string | null;
  last_backtest?: { id: string; total: number; excess: number; benchmark: string } | null;
}

export interface BacktestRow {
  id: string;
  fund: string;
  universe: string[];
  start: string;
  end: string;
  benchmark: string;
  total: number;
  annualized: number;
  sharpe: number;
  maxdd: number;
  benchret: number;
  excess: number;
  n_cycles: number;
  created: string;
}

export interface Metrics {
  total_return_pct: number;
  annualized_return_pct: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  benchmark_return_pct: number;
  excess_return_pct: number;
  n_cycles: number;
  n_orders: number;
  traded_notional: number;
  trading_cost: number;
}

export interface SessionSummary {
  session: string;
  nav: number;
  cash: number;
  rebalance: boolean;
  executed: { as_of: string; n_orders: number; traded_notional: number; trading_cost: number } | null;
  decided: { n_signals: number; n_clamps: number; stopped_out: boolean; halved: boolean } | null;
}

export interface PositionRow {
  ticker: string;
  shares: number;
  mark: number | null;
  value: number | null;
  weight: number | null;
}

export interface AnalystScore {
  name: string;
  horizon_days: number;
  n_views: number;
  n_directional: number;
  n_abstained: number;
  n_pending: number;
  hit_rate: number | null;
  slugging: number | null;
  ic_mean: number | null;
  ic_t_stat: number | null;
  n_dates: number;
}

export interface StrategyScore {
  name: string;
  n_periods: number;
  pnl: number;
  return_pct: number;
  win_rate: number | null;
  t_stat: number | null;
  share_of_pnl: number | null;
  max_drawdown_pct: number;
}

export interface Scorecard {
  fund: string;
  first_session: string;
  last_session: string;
  analysts: AnalystScore[];
  strategies: StrategyScore[];
  fund_pnl: number;
  trading_cost: number;
  unattributed: number;
}

export interface BacktestReport {
  id: string;
  mode: Mode;
  fund: string;
  universe: string[];
  benchmark: string;
  start: string;
  end: string;
  rebalance: string;
  capital: number;
  llm_model: string | null;
  metrics: Metrics;
  dates: string[];
  nav: number[];
  benchmark_nav: number[];
  drawdown: number[];
  sessions: SessionSummary[];
  positions: PositionRow[];
  cash: number;
  spec: SpecSummary | null;
  scorecard: Scorecard;
}

export interface Signal {
  model_name: string;
  ticker: string;
  date: string;
  value: number;
  reasoning: string | null;
  metadata: { signal?: string; confidence?: number; abstained?: boolean; cached?: boolean; [key: string]: unknown };
}

export interface Clamp {
  limit: string;
  ticker: string | null;
  before: number;
  after: number;
}

export interface Decision {
  as_of: string;
  universe: string[];
  marks: Record<string, number>;
  skipped: { ticker: string; reason: string }[];
  strategies: {
    name: string;
    slice: number;
    signals: Signal[];
    convictions: Record<string, number>;
    weights: Record<string, number>;
    flat_reason?: string | null;
  }[];
  target_weights: Record<string, number>;
  clamps: Clamp[];
  final_weights: Record<string, number>;
  stopped_out: boolean;
  halved: boolean;
}

export interface Cycle extends Omit<Decision, "stopped_out" | "halved"> {
  equity_before: number;
  cash_before: number;
  orders: { ticker: string; side: "buy" | "sell"; quantity: number; price: number }[];
  fills: { ticker: string; side: "buy" | "sell"; quantity: number; price: number }[];
  positions: Record<string, number>;
  cash: number;
  nav: number;
  execution_as_of: string | null;
  traded_notional: number;
  trading_cost: number;
  slippage: number;
  commission: number;
}

export interface SessionDetail {
  session: string;
  nav: number;
  cash: number;
  benchmark: string;
  benchmark_close: number;
  rebalance: boolean;
  hash: string;
  prev_hash: string | null;
  llm_model: string | null;
  executed: Cycle | null;
  decision: Decision | null;
  positions_view: PositionRow[];
}

export interface FundRow {
  name: string;
  error: string | null;
  mandate: string;
  universe: string[];
  cadence: string;
  intraday: boolean;
  created: string;
  capital: number;
  n_sessions: number;
  last_session: string | null;
  nav: number;
  return_pct: number;
  halted: string | null;
}

export interface FundDetail extends FundRow {
  mode: Mode;
  spec: SpecSummary;
  risk: Record<string, number>;
  benchmark: string;
  dates: string[];
  nav_series: number[];
  benchmark_nav: number[];
  drawdown: number[];
  sessions: SessionSummary[];
  positions: PositionRow[];
  cash: number;
  pending: Decision | null;
  llm_model: string | null;
  events: { time: string; kind: string; [key: string]: unknown }[];
}

export interface Preview {
  due: string | null;
  reason: string | null;
  pending: Decision | null;
  rebalance: boolean;
  halted: string | null;
}

export interface Job {
  id: string;
  kind: string;
  label: string;
  status: "queued" | "running" | "succeeded" | "failed";
  progress: { done: number; total: number };
  partial: { dates?: string[]; nav?: number[]; benchmark_nav?: number[] };
  result: { backtest_id?: string; sessions?: string[]; stopped_reason?: string | null } | null;
  error: string | null;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "서버에 연결할 수 없습니다. 백엔드가 실행 중인지 확인하세요.");
  }
  if (response.status === 204) return undefined as T;
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((d) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`).join("; ")
          : `요청 실패 (${response.status})`;
    throw new ApiError(response.status, message);
  }
  return payload as T;
}

const enc = encodeURIComponent;

export const api = {
  settings: () => request<Settings>("GET", "/settings"),
  updateSettings: (body: { mode?: Mode; model?: string }) => request<Settings>("PUT", "/settings", body),
  saveCredential: (env_var: string, value: string) =>
    request<Settings>("PUT", "/settings/credentials", { env_var, value }),
  catalog: () => request<Catalog>("GET", "/catalog"),

  mandates: () => request<MandateRow[]>("GET", "/mandates"),
  createMandate: (spec: unknown) => request<unknown>("POST", "/mandates", spec),
  deleteMandate: (name: string) => request<void>("DELETE", `/mandates/${enc(name)}`),

  backtests: () => request<BacktestRow[]>("GET", "/backtests"),
  startBacktest: (body: { mandate: string; universe: string[]; start?: string; end?: string }) =>
    request<{ job_id: string }>("POST", "/backtests", body),
  backtest: (id: string) => request<BacktestReport>("GET", `/backtests/${enc(id)}`),
  backtestSession: (id: string, session: string) =>
    request<SessionDetail>("GET", `/backtests/${enc(id)}/sessions/${enc(session)}`),
  deleteBacktest: (id: string) => request<void>("DELETE", `/backtests/${enc(id)}`),

  funds: () => request<FundRow[]>("GET", "/funds"),
  createFund: (body: { name: string; mandate: string; universe: string[] }) =>
    request<FundRow>("POST", "/funds", body),
  fund: (name: string) => request<FundDetail>("GET", `/funds/${enc(name)}`),
  preview: (name: string) => request<Preview>("GET", `/funds/${enc(name)}/preview`),
  tick: (name: string, count: number, session?: string) =>
    request<{ job_id: string }>("POST", `/funds/${enc(name)}/tick`, { count, session }),
  halt: (name: string, reason: string) => request<FundRow>("POST", `/funds/${enc(name)}/halt`, { reason }),
  resume: (name: string) => request<FundRow>("POST", `/funds/${enc(name)}/resume`),
  fundSession: (name: string, session: string) =>
    request<SessionDetail>("GET", `/funds/${enc(name)}/sessions/${enc(session)}`),
  fundScorecard: (name: string) => request<Scorecard>("GET", `/funds/${enc(name)}/scorecard`),

  job: (id: string) => request<Job>("GET", `/jobs/${enc(id)}`),
};
