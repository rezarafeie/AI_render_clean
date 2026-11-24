import React from "react";
import { quota, listAssets, removeAsset } from "./storage";
import { getUser } from "../auth";
import { processingPreferences, setProcessingPreferences, localApplicationURL, type ProcessingPreferences } from "./preferences";
import { pairWorker, workerRequest } from "./lan";
import { Icon } from "../components/Icon";
import { activateAppUpdate } from "./pwa";
import { verifyLocalBackend } from "./backend";

interface InstallPrompt extends Event { prompt(): Promise<void>; userChoice: Promise<{ outcome: string }> }
let appState: { install: InstallPrompt | null; update: ServiceWorkerRegistration | null; installed: boolean } = { install: null, update: null, installed: false };
const listeners = new Set<() => void>();
function publish(patch: Partial<typeof appState>) { appState = { ...appState, ...patch }; listeners.forEach(listener => listener()); }
function subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; }

export function AppFeatures() {
  React.useEffect(() => {
    const prompt = (event: Event) => { event.preventDefault(); publish({ install: event as InstallPrompt }); };
    const installed = () => publish({ install: null, installed: true });
    publish({ installed: window.matchMedia("(display-mode: standalone)").matches || Boolean((navigator as Navigator & { standalone?: boolean }).standalone) });
    window.addEventListener("beforeinstallprompt", prompt);
    window.addEventListener("appinstalled", installed);
    if (import.meta.env.PROD && isSecureContext && "serviceWorker" in navigator) {
      void navigator.serviceWorker.register("/sw.js", { updateViaCache: "none" }).then(reg => {
        const check = () => publish({ update: reg.waiting ? reg : null });
        check(); reg.addEventListener("updatefound", () => reg.installing?.addEventListener("statechange", check));
      }).catch(() => {});
    }
    return () => { window.removeEventListener("beforeinstallprompt", prompt); window.removeEventListener("appinstalled", installed); };
  }, []);
  return <NewVersionBanner/>;
}

/** The app keeps running the bundle it opened with; when the server has a newer build, offer a reload (never forced: a device render may be running). */
function NewVersionBanner() {
  const [fresh, setFresh] = React.useState(false);
  React.useEffect(() => {
    if (!import.meta.env.PROD) return;
    const mine = (document.querySelector('script[type="module"][src*="/assets/index-"]') as HTMLScriptElement | null)?.src.match(/index-[\w-]+\.js/)?.[0];
    if (!mine) return;
    let stop = false;
    const check = () => { if (document.visibilityState !== "visible" || stop) return;
      fetch("/index.html", { cache: "no-store" }).then(r => r.ok ? r.text() : "").then(html => { const live = html.match(/index-[\w-]+\.js/)?.[0]; if (live && live !== mine) setFresh(true); }).catch(() => {}); };
    const timer = setInterval(check, 3 * 60_000);
    document.addEventListener("visibilitychange", check);
    check();
    return () => { stop = true; clearInterval(timer); document.removeEventListener("visibilitychange", check); };
  }, []);
  if (!fresh) return null;
  return <div className="app-fresh" role="status"><span>A new version of EditorGPT is ready.</span>
    <button type="button" className="btn btn-sm" onClick={() => location.reload()}>Reload</button>
    <button type="button" className="icon-btn" aria-label="Later" onClick={() => setFresh(false)}><Icon name="close" size={14}/></button></div>;
}

export function InstallationSettings() {
  const { install, installed, update } = React.useSyncExternalStore(subscribe, () => appState);
  const [guide, setGuide] = React.useState(false);
  const [message, setMessage] = React.useState("");
  const [updating, setUpdating] = React.useState(false);
  return <section className="set-section" aria-labelledby="set-install"><h2 id="set-install">Application</h2>
    <div className="set-row"><span className="set-app-identity"><b>EditorGPT app</b><small>{installed ? "Installed on this device" : "Open from your Home Screen or desktop."}</small></span>
      {installed ? <span className="set-status"><Icon name="check" size={14}/>Installed</span> : <button className="btn btn-sm btn-secondary" aria-expanded={install ? undefined : guide} aria-controls={install ? undefined : "install-guide"} onClick={() => {
        if (!install) { setGuide(!guide); return; }
        void install.prompt().then(() => install.userChoice).then(result => { setMessage(result.outcome === "accepted" ? "Installation requested." : "You can install later from here."); }).catch(() => setGuide(true)).finally(() => publish({ install: null }));
      }}><Icon name="download" size={15}/>{install ? "Install EditorGPT" : "How to install"}</button>}
    </div>
    {guide ? <div className="set-detail-body" id="install-guide"><p>iPhone / iPad: open in Safari, tap Share, then Add to Home Screen.</p><p>Android / desktop: use your browser’s Install app action.</p><p className="set-hint">Installation requires a supported browser and HTTPS. A plain HTTP LAN address does not provide full PWA support.</p></div> : null}
    {update ? <div className="set-row set-update"><span><b>Update available</b><small>Save your work and finish device renders before reloading.</small></span><button className="btn btn-sm" disabled={updating} onClick={() => {
      if (!confirm("Reload now? An active device render will stop.")) return;
      setUpdating(true); setMessage("Installing update…");
      void activateAppUpdate(update, () => location.reload()).catch(error => setMessage(error.message)).finally(() => setUpdating(false));
    }}>{updating ? "Updating…" : "Update app"}</button></div> : null}
    {isSecureContext && "serviceWorker" in navigator ? <button className="btn btn-sm btn-secondary" disabled={updating} onClick={() => {
      setUpdating(true); setMessage("Checking for updates…");
      void navigator.serviceWorker.getRegistration().then(async reg => {
        if (!reg) throw new Error("Open the HTTPS production app to enable updates.");
        await reg.update();
        publish({ update: reg.waiting ? reg : null });
        setMessage(reg.waiting ? "Update ready. Save your work, then choose Update app." : reg.installing ? "Downloading update. Keep the app open." : "You are using the latest app version.");
      }).catch(error => setMessage(error.message || "Could not check for updates. Check your connection.")).finally(() => setUpdating(false));
    }}>Check for updates</button> : null}
    {message ? <p className="set-feedback" role="status">{message}</p> : null}
  </section>;
}

export function DeviceSettings() {
  const [preferences, setPreferences] = React.useState(processingPreferences);
  const [pairCode, setPairCode] = React.useState("");
  const [workerStatus, setWorkerStatus] = React.useState("");
  const [network, setNetwork] = React.useState<{ local: string; lan: string[]; https?: string[]; certificate?: string; fingerprint?: string } | null>(null);
  const [space, setSpace] = React.useState<Awaited<ReturnType<typeof quota>> | null>(null);
  const [message, setMessage] = React.useState("");
  const [modeSaving, setModeSaving] = React.useState(false);
  const verifyLocal = verifyLocalBackend;
  React.useEffect(() => {
    void quota().then(setSpace).catch(() => {});
    if (new URLSearchParams(location.search).get("processing") === "lan") {
      void verifyLocal().then(() => {
        const next: ProcessingPreferences={...processingPreferences(),mode:"lan",localApp:location.origin};
        setProcessingPreferences(next);setPreferences(next);
      }).catch(e=>setMessage(String(e)));
      history.replaceState(null,"",location.pathname);
    }
    if (new URLSearchParams(location.search).get("processing") === "online") {
      const next: ProcessingPreferences={...processingPreferences(),mode:"online"};
      setProcessingPreferences(next);setPreferences(next);history.replaceState(null,"",location.pathname);
    }
    void fetch("/__local/runtime", {cache:"no-store"}).then(r => r.ok?r.json():null).then(value=>{if(value?.lan)setNetwork(value);}).catch(() => {});
  }, []);
  const save = (next: ProcessingPreferences) => { setProcessingPreferences(next); setPreferences(next); setMessage("Processing settings saved."); };
  return <>
  <section className="set-section" aria-labelledby="set-processing"><h2 id="set-processing">Processing</h2>
    <div className="set-controls">
    <div className="set-control"><label htmlFor="processing-mode"><b>Processing mode</b><small>Choose where your media is handled.</small></label><select id="processing-mode" aria-label="Processing mode" aria-busy={modeSaving} disabled={modeSaving} className="input" value={preferences.mode} onChange={e => {
      const mode = e.target.value as ProcessingPreferences["mode"];
      let localApp = preferences.localApp;
      if (mode === "lan") {
        try {
          const origin = localApplicationURL(preferences.localApp.trim() || location.origin);
          localApp = origin;
          if (origin !== location.origin) {
            if (confirm("Open your local EditorGPT installation? Sign in there; cloud projects and files are not automatically transferred.")) location.assign(origin + "/settings?processing=lan");
            return;
          }
        } catch (error) { setMessage(String(error)); return; }
      }
      if (mode === "lan") {
        setModeSaving(true);setMessage("Checking the local backend…");
        void verifyLocal().then(()=>save({...preferences,mode,localApp})).catch(e=>setMessage(String(e))).finally(()=>setModeSaving(false));
      } else { try { save({...preferences,mode}); } catch(e) { setMessage(String(e)); } }
    }}><option value="online">Online</option><option value="device">This device</option><option value="lan">Local network (LAN)</option></select></div>
    <p className="set-control-hint">{preferences.mode === "online" ? "Original workflow. Selected media uploads to this installation’s backend." : preferences.mode === "device" ? "Keep media here; approve uploads only when AI or server processing is needed." : "Use your local backend. Cloud AI providers still receive the content their models require."}</p>
    {message ? <p className="set-control-hint" role="status">{message}</p> : null}
    {preferences.mode === "lan" && !isSecureContext ? <p className="set-control-hint">LAN is connected over HTTP. Use the trusted HTTPS address for PWA installation, secure storage and computer pairing.</p> : null}
    <div className="set-control"><label htmlFor="export-engine"><b>Export engine</b><small>Auto recommends; transfers still need approval.</small></label><select id="export-engine" className="input" value={preferences.engine} onChange={e=>save({...preferences,engine:e.target.value as ProcessingPreferences["engine"]})}><option value="auto">Auto (recommended)</option><option value="device">This device</option><option value="lan">Local computer</option><option value="cloud">Cloud render</option></select></div>
    </div>
    <details className="set-details"><summary><span>Local connection</span><Icon name="chevron" size={16}/></summary><div className="set-detail-body">
      <p>For full AI editing on your Mac, open its EditorGPT URL and choose LAN. Chat, AI routing, analysis and native rendering use that installation; no companion pairing is needed. Cloud AI providers still receive required analysis inputs.</p>
      <p>The optional render companion below is only for quick standalone trims, not the AI project timeline.</p>
      <div className="set-field"><label htmlFor="local-app-url">Local EditorGPT URL</label><input id="local-app-url" className="input" type="url" autoCapitalize="none" spellCheck={false} value={preferences.localApp} placeholder="https://editor-mac.local:5187" onChange={e=>setPreferences({...preferences,localApp:e.target.value})}/></div>
      <div className="set-field"><label htmlFor="local-worker-url">Render companion URL</label><input id="local-worker-url" className="input" type="url" autoCapitalize="none" spellCheck={false} value={preferences.worker} placeholder="https://editor-mac.local:5188" onChange={e=>setPreferences({...preferences,worker:e.target.value})}/></div>
      <div className="set-actions"><button className="btn btn-sm btn-secondary" onClick={()=>{try { if(preferences.localApp)localApplicationURL(preferences.localApp); save(preferences); }catch(e){setMessage(String(e));}}}>Save addresses</button></div>
      <div className="set-pair"><div className="set-field"><label htmlFor="local-pair-code">Pairing code</label><input id="local-pair-code" className="input" type="password" autoComplete="off" placeholder="Code shown on your computer" value={pairCode} onChange={e=>setPairCode(e.target.value)}/></div>
      <button className="btn btn-sm btn-secondary" disabled={!preferences.worker || !pairCode} onClick={()=>{void pairWorker(preferences.worker,pairCode).then(async worker=>{
        sessionStorage.setItem(`editorgpt.worker.${getUser()?.id || "guest"}`,JSON.stringify(worker));setPairCode("");
        const status=await (await workerRequest(worker,"/health")).json();setWorkerStatus(status.ok?"Paired and available":"FFmpeg unavailable on computer");
      }).catch(e=>setWorkerStatus(String(e)));}}>Pair computer</button></div>
      {workerStatus?<p className="set-feedback" role="status">{workerStatus}</p>:null}
    </div></details>
    {network ? <details className="set-details"><summary><span>Local network access</span><Icon name="chevron" size={16}/></summary><div className="set-detail-body"><p>Open a network address on trusted Wi-Fi. Other devices must sign in; never forward this port on your router.</p><p><a href={network.local}>{network.local}</a></p>{network.lan.map(url => <p key={url}><a href={url}>{url}</a></p>)}
      {network.https?.map(url=><p key={url}><a href={url}>{url}</a> · HTTPS / PWA</p>)}
      {network.certificate?<><p><a href={network.certificate}>Download this Mac’s public LAN certificate</a></p><p>iPhone/iPad: install the downloaded profile in Settings, then General → About → Certificate Trust Settings. Enable only this Mac’s certificate after verifying its fingerprint. This trusts certificates signed by this local CA; remove it when no longer needed.</p><p>SHA-256: <code>{network.fingerprint}</code></p></>:null}
      <p>HTTP provides basic access; trusted HTTPS is needed for full PWA and secure browser features.</p></div></details> : null}
  </section>
  <section className="set-section" aria-labelledby="set-device"><h2 id="set-device">Storage &amp; notifications</h2>
    <div className="set-controls"><div className="set-control"><span><b>Local media</b><small>{space ? `${Math.round(space.used / 1024**2)} MB used · ${space.persistent ? "Persistence granted" : "Best-effort storage"}` : "Private to this browser and account."}</small></span>
      <button className="btn btn-sm btn-secondary" onClick={() => { const user = getUser()?.id; if (!user || !confirm("Delete this account’s local media copies? Original files and cloud projects remain unchanged.")) return;
        void listAssets(user).then(items => Promise.all(items.map(a => removeAsset(a.id, user)))).then(() => quota()).then(setSpace).catch(e => setMessage(String(e))); }}>Clear media</button></div>
    <div className="set-control"><span><b>Keep local drafts</b><small>Request persistent storage. Always keep your originals.</small></span><button className="btn btn-sm btn-secondary" disabled={space?.persistent || typeof navigator.storage?.persist !== "function"} onClick={() => { void navigator.storage?.persist?.().then(ok => { setMessage(ok ? "Persistence granted; still keep backups." : "Browser did not grant persistence."); return quota().then(setSpace); }); }}>{space?.persistent ? "Granted" : "Request"}</button></div>
    <div className="set-control"><span><b>Completion notifications</b><small>Notify when a supported render finishes.</small></span><button className="btn btn-sm btn-secondary" onClick={() => { if ("Notification" in window) void Notification.requestPermission().then(setMessage); else setMessage("Notifications unavailable in this browser/context."); }}>Enable</button></div></div>
    <p className="set-footnote">Browsers, especially iOS, may remove local storage. Keep a backup of your media.</p>
  </section>
  {message ? <p className="set-feedback" role="status">{message}</p> : null}
  </>;
}

export function completionFeedback() {
  navigator.vibrate?.(80);
  if ("Notification" in window && Notification.permission === "granted") {
    void navigator.serviceWorker?.getRegistration().then(reg => reg?.showNotification("EditorGPT", { body: "Your render is ready.", icon: "/icons/app-192.png" })).catch(() => {});
  }
}
