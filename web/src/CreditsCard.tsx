import React from "react";
import { Link } from "react-router-dom";
import { api, CreditsState } from "./api";
import { short } from "./CreditsPage";
import "./styles/credits.css";

/** Settings → General → Account: the person's credit balance with a way to the usage and purchase page. */
export function CreditsCard() {
  const [state, setState] = React.useState<CreditsState | null>(null);
  React.useEffect(() => { void api.creditsMe().then(setState).catch(() => setState(null)); }, []);
  if (!state) return null;
  return <div className="set-control cc-card" dir="rtl">
    <span><b>اعتبار</b><small>مصرف‌شده: {short(state.used_total)} · هر درخواست به مدل‌های هوش مصنوعی از این اعتبار کم می‌شود</small></span>
    <span style={{ display: "flex", alignItems: "center", gap: 14 }}>
      <span className="num" style={state.exhausted ? { color: "var(--error, #d33)" } : undefined}>{state.unlimited ? "نامحدود" : short(state.balance)}</span>
      <Link to="/credits" className="btn btn-sm btn-secondary">جزئیات و خرید</Link>
    </span>
  </div>;
}
