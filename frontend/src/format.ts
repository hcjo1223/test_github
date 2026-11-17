// Number formatting. Signs are always written: color never carries
// direction alone, and the minus is a real minus sign (U+2212).

const MINUS = "−";

export function money(value: number | null | undefined, digits = 0): string {
  if (value == null || !Number.isFinite(value)) return "–";
  const text = Math.abs(value).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return `${value < 0 ? MINUS : ""}$${text}`;
}

export function signedMoney(value: number | null | undefined, digits = 0): string {
  if (value == null || !Number.isFinite(value)) return "–";
  return value > 0 ? `+${money(value, digits)}` : money(value, digits);
}

export function pct(value: number | null | undefined, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return "–";
  const text = `${Math.abs(value * 100).toFixed(digits)}%`;
  return value < 0 ? `${MINUS}${text}` : text;
}

export function signedPct(value: number | null | undefined, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return "–";
  return value > 0 ? `+${pct(value, digits)}` : pct(value, digits);
}

export function num(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return "–";
  return value < 0 ? `${MINUS}${Math.abs(value).toFixed(digits)}` : value.toFixed(digits);
}

export function shares(value: number): string {
  return value < 0 ? `${MINUS}${Math.abs(value).toLocaleString("en-US")}` : value.toLocaleString("en-US");
}

/** "up" | "down" | "flat" — the class a signed number wears. */
export function tone(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value) || Math.abs(value) < 1e-9) return "flat";
  return value > 0 ? "up" : "down";
}

export const MODE_LABEL: Record<string, string> = {
  long_only: "롱 온리",
  long_short: "롱/숏",
  dollar_neutral: "달러 중립",
};

export const REBALANCE_LABEL: Record<string, string> = { daily: "매일", weekly: "매주", monthly: "매월" };

export const LIMIT_LABEL: Record<string, string> = {
  max_position_pct: "종목당 한도",
  max_gross_exposure: "총 노출 한도",
  max_net_exposure: "순 노출 한도",
  max_drawdown_pct: "낙폭 청산",
  halve_drawdown_pct: "낙폭 절반 축소",
  max_adv_pct: "거래량 대비 한도",
  max_beta: "베타 한도",
  max_sector_pct: "섹터 한도",
  max_volatility: "변동성 한도",
};
