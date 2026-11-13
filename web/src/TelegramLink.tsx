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

  return <main dir="rtl" style={{maxWidth: 480, margin: "64px auto", padding: 24}}>
    <h1>اتصال تلگرام به EditorGPT</h1>
    {code && !linked && <button className="btn-primary" disabled={busy} onClick={() => void change(true)}>تأیید اتصال این حساب</button>}
    <button className="btn-secondary" disabled={busy} onClick={() => void change(false)}>قطع اتصال تلگرام</button>
    <p role="status">{message}</p>
  </main>;
}
