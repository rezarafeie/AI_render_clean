import {useEffect, useState} from "react";
import {useSearchParams} from "react-router-dom";
import {ensureFreshToken} from "./auth";
import {AuthFrame} from "./auth/AuthPage";
import {useAuth} from "./auth/AuthContext";

const botUrl = "https://t.me/editorgptbot";

async function telegramLink(method: "GET" | "POST" | "DELETE", code?: string): Promise<{linked: boolean}> {
  const token = await ensureFreshToken();
  if (!token) throw new Error("برای اتصال دوباره وارد EditorGPT شوید.");
  const response = await fetch("/api/integrations/telegram/link", {
    method,
    headers: {Authorization: `Bearer ${token}`, "Content-Type": "application/json"},
    body: code ? JSON.stringify({code}) : undefined,
    cache: "no-store",
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "ارتباط با سرویس تلگرام برقرار نشد.");
  return data;
}

export default function TelegramLink() {
  const [params, setParams] = useSearchParams();
  const code = params.get("code") || "";
  const {user} = useAuth();
  const [linked, setLinked] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (code) return;
    let mounted = true;
    telegramLink("GET").then(
      result => { if (mounted) setLinked(result.linked); },
      error => { if (mounted) setMessage(error.message); },
    );
    return () => { mounted = false; };
  }, [code]);

  async function change(connect: boolean) {
    setBusy(true);
    setMessage("");
    try {
      const result = await telegramLink(connect ? "POST" : "DELETE", connect ? code : undefined);
      setLinked(result.linked);
      if (connect) {
        setParams({}, {replace: true});
        setMessage("حساب متصل شد. می‌توانید به ربات برگردید.");
      } else {
        setMessage("اتصال تلگرام قطع شد.");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "اتصال انجام نشد.");
    } finally {
      setBusy(false);
    }
  }

  return <AuthFrame title="اتصال به تلگرام" subtitle={
    code ? <span dir="rtl">حسابی که به ربات وصل می‌شود <b dir="ltr">{user?.email || user?.name}</b></span>
      : linked === true ? "ربات به حساب EditorGPT شما متصل است." : "حساب تلگرام خود را از طریق ربات EditorGPT وصل کنید."
  }>
    <div className="auth-form" dir="rtl">
      {code ? <button type="button" className="btn btn-lg btn-block" disabled={busy} onClick={() => void change(true)}>
        {busy ? "در حال اتصال…" : "تأیید و اتصال حساب"}
      </button> : null}
      <a href={botUrl} className={code ? "btn btn-lg btn-block btn-secondary" : "btn btn-lg btn-block"}>
        {code || linked ? "بازگشت به ربات" : "باز کردن ربات"}
      </a>
      {!code && linked === true ? <button type="button" className="btn btn-secondary btn-block" disabled={busy} onClick={() => void change(false)}>
        {busy ? "در حال قطع اتصال…" : "قطع اتصال تلگرام"}
      </button> : null}
      {message ? <p className="auth-switch" role="status">{message}</p> : null}
    </div>
  </AuthFrame>;
}
