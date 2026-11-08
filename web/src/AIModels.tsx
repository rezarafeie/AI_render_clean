import React from "react";
import { AuthenticatedMedia } from './AuthenticatedMedia';
import { aiAdminRequest as request, aiAdminCsv } from "./api";
import "./ai-models.css";
import DirectFallbacks from "./AIDirectFallbacks";
import { movePriority, logQuery } from "./ai-models-utils";

type Model = {id:string; name:string; provider:string|null; enabled:boolean; available:boolean; status:string; declared:string[]; verified:string[]; test_latency_ms?:number; last_error?:string};
type Route = {id:string; title:string; capability:string; models:string[]; endpoint:string; enabled:boolean; timeout:number; max_retries:number; temperature:number|null; max_tokens:number; streaming:boolean; automatic_fallback:boolean; specialized_fallback:boolean};
type Log = {id:string; timestamp:string; user_id:string|null; job_id:string|null; route:string; requested_model:string; actual_model:string|null; provider:string|null; status:string; latency_ms:number; input_tokens:number|null; output_tokens:number|null; cost:number|null; [key:string]:unknown};
type Stats = {requests:number; successful:number; failed:number; average_latency_ms:number|null; tokens:number|null; cost:number|null; cost_reported_requests:number; total_matching:number; truncated:boolean; models:({id:string}&Stats)[]; daily:{date:string; requests:number; failed:number}[]};
type Config = {enabled:boolean; capture_messages:boolean; log_char_limit:number; direct_mode:boolean; direct_ready:boolean; configured:boolean; base_url:string; concurrency_per_worker:number};
const options = ["chat","vision","reasoning","image","video","speech","transcription","embeddings","structured","tools","streaming"];
const json = (body:unknown, method="POST"):RequestInit => ({method,headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
const display = (value:unknown) => value === null || value === undefined ? "—" : String(value);

function LogMedia({value}:{value:unknown}) {
  if (!Array.isArray(value)) return null;
  return <>{value.map((item:any)=> {
    if (!item || typeof item.url!=='string' || !item.url.startsWith('/api/admin/ai/media/')) return null;
    const kind=String(item.mime_type||'').split('/')[0];
    if (!['image','audio','video'].includes(kind)) return null;
    return <AuthenticatedMedia key={item.id} as={kind==='image'?'img':kind as 'audio'|'video'} src={item.url} alt="Generated media" controls={kind!=='image'} style={{maxWidth:'100%',maxHeight:420}}/>;
  })}</>;
}

function Pager({page,total,size,onChange}:{page:number;total:number;size:number;onChange:(page:number)=>void}) {
  return <div className="ai-pager"><button disabled={page<=1} onClick={()=>onChange(page-1)}>Previous</button><span>{page} / {Math.max(1,Math.ceil(total/size))} · {total} records</span><button disabled={page*size>=total} onClick={()=>onChange(page+1)}>Next</button></div>;
}

export default function AIModels() {
  const [allowed,setAllowed]=React.useState<boolean|null>(null);
  const [tab,setTab]=React.useState("Models");
  const [error,setError]=React.useState("");
  const [notice,setNotice]=React.useState("");
  const [busy,setBusy]=React.useState(false);
  const [refresh,setRefresh]=React.useState(0);
  React.useEffect(()=>{request<{allowed:boolean}>("/access").then(r=>setAllowed(r.allowed)).catch(e=>setError(String(e)));},[]);
  async function action(task:()=>Promise<unknown>, message="Saved") {
    setBusy(true);setError("");setNotice("");
    try {await task();setNotice(message);setRefresh(n=>n+1);} catch(e){setError(e instanceof Error?e.message:String(e));}
    finally {setBusy(false);}
  }
  if(allowed===false) return <main className="eg-page"><h1>Administrator access required</h1><p>This panel is restricted by server-side permissions.</p></main>;
  if(allowed===null) return <main className="eg-page" role="status">{error||"Checking access…"}</main>;
  return <main className="eg-page ai-panel">
    <header className="eg-page-header"><span className="eg-eyebrow">Administration</span><h1>AI Models &amp; Logs</h1><p>One gateway. Exact model IDs. Verified capabilities.</p></header>
    <nav className="ai-tabs" aria-label="AI administration tabs">{["Models","Routing","Direct fallbacks","Request Logs","Analytics"].map(name=><button key={name} aria-pressed={tab===name} onClick={()=>setTab(name)}>{name}</button>)}</nav>
    {error&&<div role="alert" className="ai-alert">{error}</div>}{notice&&<p role="status">{notice}</p>}
    {busy&&<p role="status">Working… Model probes may take up to the configured timeout.</p>}
    {tab==="Models"&&<Models refresh={refresh} busy={busy} action={action}/>}
    {tab==="Routing"&&<Routing refresh={refresh} busy={busy} action={action}/>}
    {tab==="Direct fallbacks"&&<DirectFallbacks/>}
    {tab==="Request Logs"&&<Logs action={action}/>}
    {tab==="Analytics"&&<Analytics refresh={refresh}/>}
  </main>;
}

type Actions={refresh:number;busy:boolean;action:(task:()=>Promise<unknown>,message?:string)=>Promise<void>};
function Models({refresh,busy,action}:Actions) {
  const [rows,setRows]=React.useState<Model[]>([]),[total,setTotal]=React.useState(0),[page,setPage]=React.useState(1);
  const [q,setQ]=React.useState(""),[provider,setProvider]=React.useState(""),[cap,setCap]=React.useState("");
  const [providers,setProviders]=React.useState<string[]>([]),[detail,setDetail]=React.useState<Model|null>(null),[probe,setProbe]=React.useState("chat"),[error,setError]=React.useState("");
  const [stats,setStats]=React.useState<Stats|null>(null);
  React.useEffect(()=>{const ctrl=new AbortController();const timer=setTimeout(()=>{
    request<{items:Model[];total:number;providers:string[]}>(`/models?${new URLSearchParams({q,provider,capability:cap,page:String(page)})}`,{signal:ctrl.signal}).then(r=>{setRows(r.items);setTotal(r.total);setProviders(r.providers);setError("");}).catch(e=>{if(!ctrl.signal.aborted)setError(String(e));});
  },200);return()=>{clearTimeout(timer);ctrl.abort();};},[q,provider,cap,page,refresh]);
  React.useEffect(()=>{request<Stats>("/analytics").then(setStats).catch(()=>setStats(null));},[refresh]);
  return <section>
    <div className="ai-toolbar"><input aria-label="Search models" placeholder="Search model name or exact ID" value={q} onChange={e=>{setQ(e.target.value);setPage(1);}}/><select aria-label="Provider" value={provider} onChange={e=>{setProvider(e.target.value);setPage(1);}}><option value="">All providers</option>{providers.map(p=><option key={p}>{p}</option>)}</select><select aria-label="Capability" value={cap} onChange={e=>{setCap(e.target.value);setPage(1);}}><option value="">All capabilities</option>{options.map(v=><option key={v}>{v}</option>)}</select><button disabled={busy} onClick={()=>void action(()=>request("/models/sync",json({})),"Catalog synchronized; untested models remain Untested")}>Sync models</button></div>
    {error&&<p role="alert">{error}</p>}<div className="ai-table-wrap"><table><thead><tr>{["Model / exact ID","Provider","Type / evidence","Status","Avg latency","Success","Requests","Actions"].map(x=><th key={x}>{x}</th>)}</tr></thead><tbody>{rows.map(row=>{const metric=stats?.models.find(m=>m.id===row.id);return <tr key={row.id}><td><button className="ai-text-button" onClick={()=>setDetail(row)}>{row.name}</button><small>{row.id}</small></td><td>{row.provider||"Unknown"}</td><td>{[...new Set([...row.declared,...row.verified])].join(", ")||"Unknown"}</td><td><span className="ai-badge">{!row.enabled?"Disabled":!row.available?"Unavailable":row.status}</span></td><td>{metric?.average_latency_ms??row.test_latency_ms??"—"} ms</td><td>{metric?.requests?`${Math.round(metric.successful/metric.requests*100)}%`:"—"}</td><td>{metric?.requests??0}</td><td><button disabled={busy} onClick={()=>void action(()=>request("/models",json({id:row.id,enabled:!row.enabled},"PATCH")))}>{row.enabled?"Disable":"Enable"}</button><button disabled={busy||!row.enabled} onClick={()=>{setDetail(row);setProbe("chat");}}>Test / Details</button></td></tr>;})}</tbody></table></div>
    <Pager page={page} total={total} size={50} onChange={setPage}/>
    {detail&&<div className="ai-sheet-shade" onClick={()=>setDetail(null)}><section role="dialog" aria-modal="true" aria-label="Model details" className="ai-sheet" onClick={e=>e.stopPropagation()}><button className="ai-close" aria-label="Close details" onClick={()=>setDetail(null)}>×</button><h2>{detail.name}</h2><code>{detail.id}</code><p>Verified: {detail.verified.join(", ")||"None"}</p><p>Declared by catalog: {detail.declared.join(", ")||"None"}</p>{detail.last_error&&<p role="alert">{detail.last_error}</p>}{busy&&<p role="status">Testing capability…</p>}<label>Bounded capability probe<select value={probe} onChange={e=>setProbe(e.target.value)}>{["chat","responses","messages","vision","embeddings","structured","tools","streaming"].map(x=><option key={x}>{x}</option>)}</select></label><p className="eg-muted">One small request, maximum 120 output tokens (stream probe: 256). No paid media generation test.</p><button disabled={busy||!detail.enabled} onClick={()=>void action(async()=>{try{const result=await request<Model>("/models/test",json({id:detail.id,capability:probe}));setDetail(result);}catch(error){setDetail({...detail,last_error:error instanceof Error?error.message:String(error)});throw error;}},"Capability verified")}>Run test</button></section></div>}
  </section>;
}

function Routing({refresh,busy,action}:Actions) {
  const [routes,setRoutes]=React.useState<Route[]>([]),[selected,setSelected]=React.useState<Route|null>(null),[models,setModels]=React.useState<Model[]>([]),[total,setTotal]=React.useState(0),[providers,setProviders]=React.useState<string[]>([]),[provider,setProvider]=React.useState(""),[query,setQuery]=React.useState(""),[choice,setChoice]=React.useState(""),[drag,setDrag]=React.useState<number|null>(null),[error,setError]=React.useState(""),[untested,setUntested]=React.useState<{id:string;caps:string[]}|null>(null);
  React.useEffect(()=>{request<Route[]>("/routes").then(setRoutes).catch(e=>setError(String(e)));},[refresh]);
  React.useEffect(()=>{const ctrl=new AbortController();const timer=setTimeout(()=>{request<{items:Model[];total:number;providers:string[]}>(`/models?${new URLSearchParams({size:"200",q:query,provider})}`,{signal:ctrl.signal}).then(r=>{setModels(r.items);setTotal(r.total);setProviders(r.providers);}).catch(e=>{if(!ctrl.signal.aborted)setError(String(e));});},200);return()=>{clearTimeout(timer);ctrl.abort();};},[query,provider,refresh]);
  function move(from:number,to:number){if(!selected||from===to)return;setSelected({...selected,models:movePriority(selected.models,from,to)});}
  function saveBody(route:Route){const {id,title,capability,specialized_fallback,...body}=route;void id;void title;void capability;void specialized_fallback;return body;}
  /** Save the route. If the gateway refuses because a model has not passed the capability it needs, explain exactly which one. */
  async function saveRoute(route:Route){
    setUntested(null);
    try{return await request(`/routes/${encodeURIComponent(route.id)}`,json(saveBody(route),"PUT"));}
    catch(e){
      const match=/Test the required capability first: (.+)$/.exec(e instanceof Error?e.message:String(e));
      if(match){
        const id=match[1].trim(),required=[route.capability==="vision"?"vision":route.endpoint,...(route.streaming?["streaming"]:[])];
        let missing=required;
        try{const found=await request<{items:Model[]}>(`/models?${new URLSearchParams({q:id,size:"20"})}`);const row=found.items.find(m=>m.id===id);if(row)missing=required.filter(c=>!row.verified.includes(c)&&!row.declared.includes(c));}catch{/* fall back to the full list */}
        setUntested({id,caps:missing.length?missing:required});
      }
      throw e;
    }
  }
  async function testThenSave(route:Route,pending:{id:string;caps:string[]}){
    for(const capability of pending.caps) await request<Model>("/models/test",json({id:pending.id,capability}));
    return saveRoute(route);
  }
  return <section><p className="ai-hint">Priority: Jarvis → Sarovi → ArvanCloud; Gemini / Google models go to Google first. <button disabled={busy} onClick={()=>void action(async()=>{await request("/routes/prioritize",json({}));setSelected(null);},"Priority applied to every route and to the direct fallbacks")}>Apply priority to all routes</button></p><div className="ai-route-layout"><nav aria-label="Model routes">{routes.map(r=><button key={r.id} aria-pressed={selected?.id===r.id} onClick={()=>{setSelected({...r,models:[...r.models]});setChoice("");}}>{r.title}<small>{r.enabled?"Enabled":"Existing provider / disabled"}</small></button>)}</nav><div>{error&&<p role="alert">{error}</p>}{!selected?<p>Select a route to manage its model order.</p>:<><h2>{selected.title}</h2><p>Drag to reorder, or use the arrow buttons. Changes apply to new requests after Save.</p>{selected.specialized_fallback&&<p className="ai-alert">LM media execution is not verified. Existing ElevenLabs / Arvan media services remain active.</p>}
      <ol className="ai-priorities">{selected.models.map((mid,index)=><li key={mid} draggable onDragStart={()=>setDrag(index)} onDragOver={e=>e.preventDefault()} onDrop={()=>{if(drag!==null)move(drag,index);setDrag(null);}}><span aria-hidden>⠿</span><div><small>{index===0?"Primary":"Fallback"}</small><code>{mid}</code></div><button aria-label={`Move ${mid} up`} disabled={index===0} onClick={()=>move(index,index-1)}>↑</button><button aria-label={`Move ${mid} down`} disabled={index===selected.models.length-1} onClick={()=>move(index,index+1)}>↓</button><button aria-label={`Remove ${mid}`} onClick={()=>setSelected({...selected,models:selected.models.filter(m=>m!==mid)})}>×</button></li>)}</ol>
      <div className="ai-toolbar"><input aria-label="Find catalog model" placeholder="Search actual catalog…" value={query} onChange={e=>setQuery(e.target.value)}/><select aria-label="Provider" value={provider} onChange={e=>setProvider(e.target.value)}><option value="">All providers</option>{providers.map(x=><option key={x} value={x}>{x}</option>)}</select><select aria-label="Add model" value={choice} onChange={e=>setChoice(e.target.value)}><option value="">Select a model</option>{models.filter(m=>m.enabled&&!selected.models.includes(m.id)).map(m=><option key={m.id} value={m.id}>{m.id} · {m.status}</option>)}</select><button disabled={!choice||selected.models.length>=8} onClick={()=>{setSelected({...selected,models:[...selected.models,choice]});setChoice("");}}>Add</button></div>
      <p className="ai-hint" role="status">{total>models.length?`Showing the first ${models.length} of ${total} models. Search or pick a provider to narrow the list.`:`${total} model${total===1?"":"s"} match.`}</p>
      <div className="ai-form-grid"><label>Endpoint<select value={selected.endpoint} onChange={e=>setSelected({...selected,endpoint:e.target.value})}>{["chat","responses","messages","embeddings","image","speech","video","transcription","music"].map(x=><option key={x}>{x}</option>)}</select></label><label>Timeout (seconds)<input type="number" min={5} max={3600} value={selected.timeout} onChange={e=>setSelected({...selected,timeout:Number(e.target.value)})}/></label><label>Maximum retries<input type="number" min={0} max={2} value={selected.max_retries} onChange={e=>setSelected({...selected,max_retries:Number(e.target.value)})}/></label><label>Output token limit<input type="number" min={32} max={32000} value={selected.max_tokens} onChange={e=>setSelected({...selected,max_tokens:Number(e.target.value)})}/></label><label>Temperature (blank = omit)<input type="number" step="0.1" min={0} max={2} value={selected.temperature??""} onChange={e=>setSelected({...selected,temperature:e.target.value===""?null:Number(e.target.value)})}/></label></div>
      <div className="ai-checks">{([['enabled','Enabled'],['automatic_fallback','Automatic fallback'],['streaming','Streaming']] as const).map(([key,label])=><label key={key}><input type="checkbox" checked={selected[key]} onChange={e=>setSelected({...selected,[key]:e.target.checked})}/>{label}</label>)}</div>
      {untested&&<div className="ai-alert" role="alert"><p><code>{untested.id}</code> has not passed {untested.caps.length>1?"these capability tests":"this capability test"} yet: <b>{untested.caps.join(", ")}</b>. The gateway only lets a model join an enabled route after a successful probe.</p><p className="eg-muted">Each test is one small request (max 120 output tokens; streaming 256). If a test fails, that model does not support it: remove it, or turn off Streaming.</p><button disabled={busy} onClick={()=>void action(()=>testThenSave(selected,untested),"Capability verified and routing saved")}>Run {untested.caps.join(" + ")} test{untested.caps.length>1?"s":""} and save</button></div>}
      <button disabled={busy||!selected.models.length} onClick={()=>void action(()=>saveRoute(selected),"Routing saved; new requests use this order immediately")}>Save route</button>
    </>}</div></div><GatewaySettings action={action} busy={busy} refresh={refresh}/></section>;
}

function GatewaySettings({action,busy,refresh}:Actions) {
  const [cfg,setCfg]=React.useState<Config|null>(null);
  React.useEffect(()=>{request<Config>("/settings").then(setCfg).catch(()=>setCfg(null));},[refresh]);
  return cfg?<details className="ai-global"><summary>Gateway &amp; privacy settings</summary><p>{cfg.base_url} · {cfg.configured?"Server credential configured":"Missing server credential"} · {cfg.concurrency_per_worker} requests per worker</p><div className="ai-checks"><label><input type="checkbox" checked={cfg.enabled} onChange={e=>setCfg({...cfg,enabled:e.target.checked})}/>Gateway enabled</label><label><input type="checkbox" checked={cfg.capture_messages} onChange={e=>setCfg({...cfg,capture_messages:e.target.checked})}/>Capture redacted request / response text</label><label><input type="checkbox" checked={cfg.direct_mode} disabled={!cfg.direct_ready&&!cfg.direct_mode} onChange={e=>setCfg({...cfg,direct_mode:e.target.checked})}/>Direct mode — switch the gateway off and call the providers' own APIs (Jarvis, …)</label></div>{cfg.direct_mode&&<p className="ai-alert" role="alert">Direct mode is on: requests no longer go through {cfg.base_url}. Chat, vision, images, speech and embeddings use the providers on the Direct fallbacks tab (their keys and priority); routes still decide the models. Web search uses the web_search route (a model that searches natively). Gateway model catalog sync and gateway transcription are unavailable until it is switched off.</p>}{!cfg.direct_ready&&!cfg.direct_mode&&<p className="eg-muted">Direct mode needs a provider with an API key on the Direct fallbacks tab.</p>}<label>Maximum logged characters<input type="number" min={256} max={12000} value={cfg.log_char_limit} onChange={e=>setCfg({...cfg,log_char_limit:Number(e.target.value)})}/></label><button disabled={busy} onClick={()=>void action(()=>request("/settings",json({enabled:cfg.enabled,capture_messages:cfg.capture_messages,log_char_limit:cfg.log_char_limit,direct_mode:cfg.direct_mode},"PUT")))}>Save settings</button></details>:null;
}

function Logs({action}:{action:Actions["action"]}) {
  const [rows,setRows]=React.useState<Log[]>([]),[total,setTotal]=React.useState(0),[page,setPage]=React.useState(1),[auto,setAuto]=React.useState(true),[tick,setTick]=React.useState(0),[detail,setDetail]=React.useState<Log|null>(null),[error,setError]=React.useState("");
  const [filters,setFilters]=React.useState({id:"",model:"",status:"",user_id:"",since:"",until:""});
  const query=React.useMemo(()=>{return logQuery(filters);},[filters]);
  React.useEffect(()=>{if(!auto)return;const timer=setInterval(()=>setTick(t=>t+1),5000);return()=>clearInterval(timer);},[auto]);
  React.useEffect(()=>{const ctrl=new AbortController();request<{items:Log[];total:number}>(`/logs?${query}&page=${page}`,{signal:ctrl.signal}).then(r=>{setRows(r.items);setTotal(r.total);setError("");}).catch(e=>{if(!ctrl.signal.aborted)setError(String(e));});return()=>ctrl.abort();},[page,query,tick]);
  return <section><div className="ai-toolbar">{([['id','Request ID'],['model','Exact model ID'],['user_id','User ID'],['since','From (UTC)'],['until','Through (UTC)']] as const).map(([key,label])=><label key={key}>{label}<input type={key==="since"||key==="until"?"date":"text"} value={filters[key]} onChange={e=>{setPage(1);setFilters({...filters,[key]:e.target.value});}}/></label>)}<select aria-label="Request status" value={filters.status} onChange={e=>{setPage(1);setFilters({...filters,status:e.target.value});}}><option value="">All statuses</option><option value="success">Successful</option><option value="failed">Failed</option></select><label><input type="checkbox" checked={auto} onChange={e=>setAuto(e.target.checked)}/>Auto refresh</label><button onClick={()=>void action(()=>aiAdminCsv(query),"CSV downloaded")}>Export CSV</button></div>
    {error&&<p role="alert">{error}</p>}<div className="ai-table-wrap"><table><thead><tr>{["Time","User / Route","Requested → Actual","Provider","Status","Latency","Input / Output tokens","Cost"].map(x=><th key={x}>{x}</th>)}</tr></thead><tbody>{rows.map(r=><tr key={r.id}><td><button className="ai-text-button" onClick={()=>setDetail(r)}>{new Date(r.timestamp).toLocaleString()}</button><small>{r.id}</small></td><td>{r.user_id||"Background"}<small>{r.route}</small></td><td>{r.requested_model}<small>→ {r.actual_model||"Not reported"}</small></td><td>{r.provider||"Not reported"}</td><td>{r.status}</td><td>{r.latency_ms} ms</td><td>{display(r.input_tokens)} / {display(r.output_tokens)}</td><td>{display(r.cost)}</td></tr>)}</tbody></table></div><Pager page={page} total={total} size={50} onChange={setPage}/>
    {detail&&<div className="ai-sheet-shade" onClick={()=>setDetail(null)}><section className="ai-sheet" role="dialog" aria-modal="true" aria-label="Request details" onClick={e=>e.stopPropagation()}><button className="ai-close" aria-label="Close request details" onClick={()=>setDetail(null)}>×</button><h2>Request details</h2><LogMedia value={detail.media}/><h3>Request</h3><pre dir="auto">{display(detail.request_message)||'Not retained'}</pre><h3>Response</h3><pre dir="auto">{display(detail.response_message)||'Not retained'}</pre>{Object.entries(detail).filter(([key])=>!['request_message','response_message','media'].includes(key)).map(([key,value])=><div key={key} className="ai-log-detail"><b>{key.replace(/_/g," ")}</b><pre dir="auto">{typeof value==="object"&&value!==null?JSON.stringify(value,null,2):display(value)}</pre></div>)}</section></div>}
  </section>;
}

function Analytics({refresh}:{refresh:number}) {
  const [stats,setStats]=React.useState<Stats|null>(null),[error,setError]=React.useState("");
  React.useEffect(()=>{request<Stats>("/analytics").then(setStats).catch(e=>setError(String(e)));},[refresh]);
  if(!stats)return <p role="status">{error||"Loading observed metrics…"}</p>;
  const max=Math.max(1,...stats.daily.map(v=>v.requests));
  const mostRequests=Math.max(1,...stats.models.map(v=>v.requests));
  const maxLatency=Math.max(1,...stats.models.map(v=>v.average_latency_ms||0));
  return <section>{stats.truncated&&<p className="ai-alert">Showing the latest 50,000 of {stats.total_matching} retained requests. Narrow the date range via the API for complete metrics.</p>}<div className="ai-metrics">{[["Requests",stats.requests],["Successful",stats.successful],["Failed",stats.failed],["Average latency",stats.average_latency_ms===null?null:`${stats.average_latency_ms} ms`],["Reported tokens",stats.tokens],["Reported cost",stats.cost]].map(([label,value])=><article key={String(label)}><small>{label}</small><strong>{display(value)}</strong></article>)}</div><p className="eg-muted">Missing usage / cost is shown as —, never estimated. Cost reported for {stats.cost_reported_requests} requests.</p><h2>Requests &amp; errors over time</h2><div className="ai-chart" role="img" aria-label="Daily request counts and failed requests">{stats.daily.map(day=><div key={day.date}><span>{day.date}</span><div><i style={{width:`${day.requests/max*100}%`}}/><em style={{width:`${day.failed/max*100}%`}}/></div><span>{day.requests} / {day.failed} failed</span></div>)}</div><h2>Model usage &amp; latency</h2><div className="ai-table-wrap"><table><thead><tr><th>Model</th><th>Requests</th><th>Failed</th><th>Average latency</th><th>Tokens</th></tr></thead><tbody>{stats.models.map(m=><tr key={m.id}><td>{m.id}</td><td>{m.requests}<div className="ai-inline-bar" role="img" aria-label={`${m.requests} requests`}><i style={{width:`${m.requests/mostRequests*100}%`}}/></div></td><td>{m.failed}</td><td>{display(m.average_latency_ms)} ms{m.average_latency_ms!==null&&<div className="ai-inline-bar" role="img" aria-label={`${m.average_latency_ms} milliseconds`}><i style={{width:`${m.average_latency_ms/maxLatency*100}%`}}/></div>}</td><td>{display(m.tokens)}</td></tr>)}</tbody></table></div></section>;
}
