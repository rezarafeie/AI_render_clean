import {useState} from "react";
import {useSearchParams} from "react-router-dom";
import {ensureFreshToken} from "./auth";

export default function TelegramLink() {
  const [params] = useSearchParams();
  const code = params.get("code") || "";
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [linked, setLinked] = useState(false);

  async function change(connect: boolean) {
    setBusy(true);
    try {
      const token = await ensureFreshToken();
      if (!token) throw new Error("نشست شما پایان یافته است. دوباره وارد EditorGPT شوید.");
      const result = await fetch("/api/integrations/telegram/link", {
        method: connect ? "POST" : "DELETE",
        headers: {Authorization: `Bearer ${token}`, "Content-Type": "application/json"},
        body: connect ? JSON.stringify({code}) : undefined,
      });
      if (!result.ok) {
        const data = await result.json();
        throw new Error(typeof data.detail === "string" ? data.detail : "اتصال انجام نشد.");
      }
      setLinked(connect);
      setMessage(connect ? "حساب متصل شد. به چت ربات برگردید." : "اتصال تلگرام قطع شد.");
      if (connect) window.history.replaceState(window.history.state, "", "/telegram/link");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "اتصال انجام نشد.");
    } finally {
      setBusy(false);
    }
  }

  const button = {display: "block", width: "100%", minHeight: 50, padding: "12px 18px",
    border: "1px solid #aaa", borderRadius: 14, cursor: "pointer", font: "inherit"};

  return <main dir="rtl" style={{maxWidth: 480, margin: "48px auto", padding: 24, lineHeight: 1.75}}>
    <h1 style={{fontSize: 25, marginBottom: 12}}>اتصال تلگرام به EditorGPT</h1>
    {code && !linked && <>
      <p style={{marginBottom: 20}}>برای دسترسی به پروژه‌هایتان از ربات، اتصال این حساب را تأیید کنید.</p>
      <button type="button" style={{...button, background: "#2463eb", borderColor: "#2463eb", color: "#fff", fontWeight: 700}}
        disabled={busy} onClick={() => void change(true)}>{busy ? "در حال اتصال…" : "تأیید اتصال این حساب"}</button>
    </>}
    {!code && <button type="button" style={{...button, background: "transparent", color: "inherit"}}
      disabled={busy} onClick={() => void change(false)}>قطع اتصال تلگرام</button>}
    {linked && <a href="https://t.me/editorgptbot" style={{...button, textAlign: "center", marginTop: 18}}>بازگشت به ربات</a>}
    <p role="status" style={{marginTop: 16}}>{message}</p>
  </main>;
}
