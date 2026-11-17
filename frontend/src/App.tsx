import { createContext, useContext } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { api, type Settings } from "./api";
import { ErrorNote, Loading, ModeBadge } from "./components/common";
import { useLoad } from "./hooks";
import { BacktestReportPage } from "./pages/BacktestReport";
import { BacktestsPage } from "./pages/Backtests";
import { DashboardPage } from "./pages/Dashboard";
import { FundConsolePage } from "./pages/FundConsole";
import { FundsPage } from "./pages/Funds";
import { MandateBuilderPage } from "./pages/MandateBuilder";
import { MandatesPage } from "./pages/Mandates";
import { SettingsPage } from "./pages/Settings";

interface AppState {
  settings: Settings;
  reloadSettings: () => void;
}

const AppContext = createContext<AppState | null>(null);

export function useApp(): AppState {
  const state = useContext(AppContext);
  if (!state) throw new Error("useApp outside <App>");
  return state;
}

const NAV = [
  { to: "/", label: "대시보드", end: true },
  { to: "/mandates", label: "맨데이트" },
  { to: "/backtests", label: "백테스트" },
  { to: "/funds", label: "페이퍼 펀드" },
  { to: "/settings", label: "설정" },
];

export function App() {
  const settings = useLoad(api.settings, []);

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          AIHF Web
          <small>ai-hedge-fund 엔진 콘솔</small>
        </div>
        <nav className="nav" aria-label="주 메뉴">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="foot">
          {settings.data && <ModeBadge mode={settings.data.mode} />}
          <p style={{ marginTop: 8 }}>교육·연구 목적 전용. 실제 주문을 내지 않으며 투자 자문이 아닙니다.</p>
        </div>
      </aside>
      <main className="main">
        {settings.error && <ErrorNote message={settings.error} />}
        {!settings.data ? (
          !settings.error && <Loading />
        ) : (
          // Remount every page when the mode flips: each mode has its own data.
          <AppContext.Provider key={settings.data.mode} value={{ settings: settings.data, reloadSettings: settings.reload }}>
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/mandates" element={<MandatesPage />} />
              <Route path="/mandates/new" element={<MandateBuilderPage />} />
              <Route path="/backtests" element={<BacktestsPage />} />
              <Route path="/backtests/:id" element={<BacktestReportPage />} />
              <Route path="/funds" element={<FundsPage />} />
              <Route path="/funds/:name" element={<FundConsolePage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<div className="empty">페이지를 찾을 수 없습니다.</div>} />
            </Routes>
          </AppContext.Provider>
        )}
      </main>
    </div>
  );
}
