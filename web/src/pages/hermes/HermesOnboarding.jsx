import { useState } from 'react';
import hermesApi from '../../services/hermesApi';
import { message } from './hermesUtils';

export async function startInstagramConnection() {
  // Composio first: the person authorizes on Composio's page, no Meta developer app of their own is needed.
  const status = await hermesApi.getComposioSettings().catch(() => null);
  if (status?.configured) {
    if (status.enabled === false) await hermesApi.setComposioEnabled(true);
    const { redirect_url: link } = await hermesApi.connectComposioApp('instagram');
    const target = new URL(link);
    if (target.protocol !== 'https:' || target.username || target.password) throw new Error('The authorization link is invalid.');
    window.location.assign(target.href);
    return;
  }
  const { authorization_url: url } = await hermesApi.connectInstagram();
  window.location.assign(url);
}

const STEPS = [
  ['۱', 'اتصال اینستاگرام', 'با یک کلیک در صفحه‌ی امن Composio وارد می‌شوید؛ رمز یا کلیدی در EditorGPT وارد نمی‌شود.'],
  ['۲', 'بررسی حساب', 'پروفایل، پست‌های اخیر و آمار خوانده می‌شود تا ایده‌ها و برنامه برای خود حساب شما باشد.'],
  ['۳', 'ساخت محتوا', 'ایده، هوک، سناریو و کپشن می‌گیرید و با یک کلیک به ادیتور می‌دهید تا ویدیویش ساخته شود.'],
];

export default function HermesOnboarding() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function connect() {
    setBusy(true); setError('');
    try { await startInstagramConnection(); } catch (e) { setError(message(e)); setBusy(false); }
  }
  return <div className="hm-page hm-rise" dir="rtl">
    <section className="hm-hero-cta hm-panel">
      <div className="hm-hero-mark">◎</div>
      <div><span className="hm-eyebrow">GET STARTED</span><h2>اول اینستاگرامت را وصل کن</h2>
        <p>Hermes فقط وقتی کار می‌کند که پیج واقعی تو را ببیند: محتوای قبلی، آمار و کامنت‌ها. بعد از اتصال، ایده و سناریو می‌گیری و مستقیم به ادیتور می‌فرستی.</p></div>
      <button className="hm-btn hm-btn-primary" type="button" onClick={connect} disabled={busy}>{busy ? 'در حال باز کردن Composio…' : 'اتصال اینستاگرام'}</button>
    </section>
    {error && <div className="hm-alert" role="alert">{error}</div>}
    <ol className="hm-stack" style={{ listStyle: 'none', padding: 0 }}>
      {STEPS.map(([n, title, body]) => <li key={n} className="hm-panel"><strong>{n}. {title}</strong><p className="hm-tiny">{body}</p></li>)}
    </ol>
    <p className="hm-tiny">اتصال فقط‌خواندنی است؛ انتشار و ارسال پیام بدون تأیید صریح خودت انجام نمی‌شود.</p>
  </div>;
}
