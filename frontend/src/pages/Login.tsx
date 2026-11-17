import { useState, type FormEvent } from "react";
import { api } from "../api";
import { ErrorNote, PageHead } from "../components/common";

/** The owner's password gate. Shown only when the server requires a login. */
export function LoginPage({ onDone }: { onDone: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(password);
      onDone();
    } catch (reason) {
      setError((reason as Error).message);
      setBusy(false);
    }
  };

  return (
    <div className="main" style={{ maxWidth: 420, margin: "10vh auto" }}>
      <PageHead title="AIHF Web" sub="비밀번호를 입력하세요." />
      <form className="card" onSubmit={submit}>
        <ErrorNote message={error} />
        <label className="field">
          <span>비밀번호</span>
          <input
            type="password" autoComplete="current-password" autoFocus value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <div className="actions">
          <button className="primary" type="submit" disabled={busy || password.length === 0}>
            {busy ? "확인 중…" : "로그인"}
          </button>
        </div>
        <p className="hint" style={{ marginTop: 12 }}>
          교육·연구 목적 전용입니다. 실제 주문을 내지 않으며 투자 자문이 아닙니다.
        </p>
      </form>
    </div>
  );
}
