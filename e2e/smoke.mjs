// End-to-end smoke test: the three core scenarios, through the real UI,
// against a running server in demo mode.
//
//   AIHF_WEB_HOME=$(mktemp -d) uv run --project backend uvicorn app.main:app --app-dir backend &
//   node e2e/smoke.mjs [baseUrl] [screenshotDir]
//
// Needs a fresh home directory (it creates a mandate and a fund by name).

import { createRequire } from "node:module";

// require() so a globally installed Playwright (NODE_PATH) is found too.
const { chromium } = createRequire(import.meta.url)("playwright");

const base = process.argv[2] ?? "http://127.0.0.1:8000";
const shots = process.argv[3] ?? null;
const steps = [];
const problems = [];

function check(condition, message) {
  steps.push(`${condition ? "ok  " : "FAIL"} ${message}`);
  if (!condition) problems.push(message);
}

/** True once the locator is visible; waits a little, since data loads after navigation. */
const seen = (locator) => locator.first().waitFor({ timeout: 8000 }).then(() => true, () => false);

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 });
const page = await context.newPage();
// The duplicate-name step expects a 409; any other console error is a problem.
page.on("console", (m) => m.type() === "error" && !m.text().includes("409") && problems.push(`console: ${m.text()}`));
page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
const shot = async (name, fullPage = true) => shots && page.screenshot({ path: `${shots}/${name}.png`, fullPage });

try {
  // 1. Dashboard, demo by default.
  await page.goto(base);
  await page.getByRole("heading", { name: "대시보드" }).waitFor();
  check(await seen(page.getByText("DEMO · 합성 데이터")), "dashboard shows the DEMO badge");

  // 2. Build a mandate.
  await page.goto(`${base}/mandates/new`);
  await page.getByPlaceholder("예: quality-drift").fill("quality-drift");
  await page.getByRole("button", { name: /Deep Value/ }).click();
  await page.getByRole("button", { name: /Earnings Drift/ }).click();
  await page.getByLabel("deep-value 비중").fill("3");
  check(await seen(page.getByRole("cell", { name: "75%" })), "capital split previews 75% / 25%");
  await shot("01-mandate-builder");
  await page.getByRole("button", { name: "맨데이트 저장" }).click();
  await page.waitForURL(`${base}/mandates`);
  check(await seen(page.getByRole("heading", { name: "quality-drift" })), "the new mandate is listed");

  // A bad name comes back with the server's reason.
  await page.goto(`${base}/mandates/new`);
  await page.getByPlaceholder("예: quality-drift").fill("quality-drift");
  await page.getByRole("button", { name: /Deep Value/ }).click();
  await page.getByRole("button", { name: "맨데이트 저장" }).click();
  check(await seen(page.getByRole("alert").filter({ hasText: "이미 있습니다" })), "a duplicate name is refused with a message");

  // 3. Backtest it.
  await page.goto(`${base}/backtests?mandate=quality-drift`);
  await page.getByRole("button", { name: "JPM", exact: true }).click();
  await page.getByRole("button", { name: "XOM", exact: true }).click();
  check((await page.getByLabel("맨데이트").inputValue()) === "quality-drift", "the mandate is preselected from the link");
  await page.getByRole("button", { name: "백테스트 실행" }).click();
  await page.waitForURL(/\/backtests\/quality-drift-/, { timeout: 120000 });
  await page.getByText("총수익률").waitFor();
  check(await seen(page.getByRole("img", { name: /펀드 NAV와 SPY 비교/ })), "the equity chart renders");
  check((await page.locator(".kpi .value").first().innerText()).match(/^[+−]?\d/) !== null, "total return is a signed number");

  // Hover: the crosshair reads both series.
  const chart = page.getByRole("img", { name: /펀드 NAV와 SPY 비교/ });
  const box = await chart.boundingBox();
  await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.5);
  check(await seen(page.locator(".tooltip")), "hovering the chart shows a tooltip");
  await shot("02-backtest-report");

  await page.locator("tr.clickable").last().click(); // the oldest session: the first decision
  await page.getByText("이 세션에 내린 결정").waitFor();
  check((await page.getByText(/^\[demo\]/).count()) > 0, "session detail shows the analysts' theses, marked [demo]");
  await page.mouse.move(0, 0);
  await shot("03-session-detail");

  // 4. Deploy and run a paper fund.
  await page.goto(`${base}/funds?mandate=quality-drift`);
  await page.getByPlaceholder("예: alpha").fill("alpha");
  await page.getByRole("button", { name: "펀드 배치" }).click();
  await page.waitForURL(`${base}/funds/alpha`);
  await page.getByRole("button", { name: "다음 세션 실행" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByText("세션을 실행할까요?").waitFor();
  check(await seen(dialog.getByText("체결할 대기 결정이 없습니다")), "first run: the approval step says nothing is pending");
  await dialog.getByRole("button", { name: "실행" }).click();
  await page.getByRole("status").filter({ hasText: "1개 세션 실행" }).waitFor({ timeout: 60000 });
  check(await seen(page.getByRole("heading", { name: "대기 중인 결정" })), "after one session a decision is pending");

  await page.getByRole("button", { name: /밀린 세션 따라잡기/ }).click();
  check(await seen(dialog.getByText("이 세션 종가에 체결될 결정")), "the approval step shows the decision about to execute");
  await shot("04-approval-dialog", false);
  await dialog.getByRole("button", { name: "실행" }).click();
  await page.getByRole("status").filter({ hasText: "20개 세션 실행" }).waitFor({ timeout: 120000 });
  check(await seen(page.getByRole("img", { name: /펀드 NAV와 SPY 비교/ })), "the fund's NAV chart appears");
  await page.locator(".kpi .value").nth(3).filter({ hasText: /^21$/ }).waitFor({ timeout: 8000 }).catch(() => {});
  check((await page.locator(".kpi .value").nth(3).innerText()) === "21", "21 sessions are on the ledger");
  await shot("05-fund-console");

  // Kill switch.
  page.once("dialog", (d) => d.accept("E2E 점검"));
  await page.getByRole("button", { name: /킬 스위치/ }).click();
  await page.getByText("정지 사유: E2E 점검").waitFor();
  check(await page.getByRole("button", { name: "다음 세션 실행" }).isDisabled(), "a halted fund cannot be run");
  await page.getByRole("button", { name: "재개" }).click();
  await page.getByRole("button", { name: /킬 스위치/ }).waitFor();
  check(await page.getByRole("button", { name: "다음 세션 실행" }).isEnabled(), "resume clears the kill switch");

  // 5. Settings: live is locked without a data key.
  await page.goto(`${base}/settings`);
  check(await page.getByRole("button", { name: /^LIVE/ }).isDisabled(), "LIVE is disabled without a data key");
  await shot("06-settings");

  // 6. Dashboard reflects the work; phone width does not scroll sideways.
  await page.goto(base);
  await page.getByRole("link", { name: "alpha" }).waitFor();
  await shot("07-dashboard");
  await page.setViewportSize({ width: 390, height: 800 });
  for (const path of ["/", "/backtests", "/funds/alpha", "/mandates/new"]) {
    await page.goto(base + path);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    check(overflow <= 0, `no horizontal scroll at 390px on ${path} (overflow ${overflow}px)`);
  }
  await shot("08-mobile-builder", false);

  // Dark theme renders with its own tokens.
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto(`${base}/funds/alpha`);
  await page.getByRole("img", { name: /펀드 NAV와 SPY 비교/ }).waitFor();
  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  check(bg === "rgb(18, 18, 17)", `dark theme applies (body ${bg})`);
  await shot("09-fund-console-dark", false);
} catch (error) {
  problems.push(`aborted: ${error.message.split("\n")[0]}`);
  if (shots) await page.screenshot({ path: `${shots}/failure.png`, fullPage: true }).catch(() => {});
} finally {
  await browser.close();
}

console.log(steps.join("\n"));
if (problems.length) {
  console.log(`\n${problems.length} problem(s):\n- ${problems.join("\n- ")}`);
  process.exit(1);
}
console.log(`\nall ${steps.length} checks passed`);
