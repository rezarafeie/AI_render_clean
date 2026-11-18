import React from "react";
import { api, type StudioProject } from "../api";
import { friendlyError } from "../ui";
import { NativeLayers } from "./NativeLayers";
import type { LayerChange, NativeTimeline as Timeline, Segment, SegmentChange } from "./types";

export function NativeTimeline({project, refresh, seek}: {project: StudioProject; refresh: () => Promise<unknown>; seek?: (seconds: number) => void}) {
  const [data, setData] = React.useState<Timeline | null>(null);
  const [selected, setSelected] = React.useState<Segment | null>(null);
  const [range, setRange] = React.useState({start: "0", end: "0"});
  const [trim, setTrim] = React.useState({start: "0", end: "0"});
  const [restore, setRestore] = React.useState("");
  const [split, setSplit] = React.useState("");
  const [dragged, setDragged] = React.useState<string | null>(null);
  const [past, setPast] = React.useState<number[]>([]);
  const [future, setFuture] = React.useState<number[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [hint, setHint] = React.useState("");
  const [mode, setMode] = React.useState<"trim" | "remove_range">("trim");
  const [cursor, setCursor] = React.useState(0);
  const [zoom, setZoom] = React.useState(45);
  React.useEffect(() => {
    let active = true;
    api.panelSegments(project.id).then(value => { if (active) setData(value); }).catch(() => {});
    return () => {active = false;};
  }, [project.id, project.updated_at]);

  if (!data) return null; // The project's existing document view remains available for other motion engines.
  const blocked = busy || data.busy;
  const width = Math.max(280, data.duration * zoom);
  const lastFrame = Math.max(0, Math.round(data.duration * data.fps) - 1);
  function select(segment: Segment) {
    setSelected(segment);
    setCursor(segment.start);
    seek?.(segment.source_in);
    setRange({start: segment.start.toFixed(3), end: segment.end.toFixed(3)});
    setTrim({start: segment.source_in.toFixed(3), end: segment.source_out.toFixed(3)});
    setSplit(((segment.source_in + segment.source_out) / 2).toFixed(3));
  }
  async function save(work: () => Promise<Timeline>, history: "new" | "undo" | "redo" = "new") {
    const previous = data!.version;
    setBusy(true); setError(""); setHint("");
    try {
      const updated = await work();
      setData(updated);
      if (previous !== null && previous !== updated.version) {
        if (history === "undo") { setPast(items => items.slice(0, -1)); setFuture(items => [...items, previous]); }
        else {
          setPast(items => [...items, previous]);
          if (history === "redo") setFuture(items => items.slice(0, -1)); else setFuture([]);
        }
      }
      setSelected(null);
      setCursor(0);
      setHint("نسخهٔ جدید ذخیره شد. برای دیدن تغییرات، دوباره رندر بگیرید.");
      await refresh();
      return true;
    } catch (e) { setError(friendlyError(e, "save the timeline change")); return false; }
    finally { setBusy(false); }
  }
  function submit(change: SegmentChange) { return save(() => api.editPanelSegments(project.id, change)); }
  function editLayer(change: LayerChange) { return save(() => api.editPanelLayer(project.id, change)); }
  function restoreHistory(kind: "undo" | "redo") {
    const entries = kind === "undo" ? past : future;
    const restore_version = entries[entries.length - 1];
    if (restore_version) void save(() => api.editPanelSegments(project.id, {
      operation: "restore", version: data!.version, restore_version,
    }), kind);
  }
  async function render(preview: boolean) {
    if (!data) return;
    setBusy(true); setHint(""); setError("");
    try { await api.renderPanelSegments(project.id, data.version, preview); setHint(preview ? "رندر پیش‌نمایش آغاز شد." : "رندر خروجی آغاز شد."); await refresh(); }
    catch (e) { setError(friendlyError(e, "start the render")); }
    finally { setBusy(false); }
  }
  const activeRange = mode === "trim" ? trim : range;
  const updateRange = mode === "trim" ? setTrim : setRange;
  const selectedIndex = data.segments.findIndex(item => item.id === selected?.id);
  function move(offset: -1 | 1) {
    const neighbor = data!.segments[selectedIndex + offset];
    if (selected && neighbor) void submit({version: data!.version, operation: "move", segment_id: selected.id,
                                            target_id: neighbor.id, after: offset === 1});
  }
  const serverTarget = project.state?.render_target !== "browser";
  const valid = activeRange.start !== "" && activeRange.end !== "" &&
    Number(activeRange.start) >= 0 && Number(activeRange.end) > Number(activeRange.start);

  return <section className="mp-inspector">
    <div className="mp-section-head"><h2>برش‌های تدوین</h2><span className="badge">{data.duration.toFixed(2)} ثانیه · {data.fps} fps</span>
      <div className="mp-actions">
        <button className="btn btn-secondary btn-sm" disabled={blocked || !past.length} onClick={() => restoreHistory("undo")}>واگرد</button>
        <button className="btn btn-secondary btn-sm" disabled={blocked || !future.length} onClick={() => restoreHistory("redo")}>انجام دوباره</button>
      </div></div>
    <label>بزرگ‌نمایی تایم‌لاین<input type="range" min={14} max={110} value={zoom} onChange={e => setZoom(Number(e.target.value))}/></label>
    {seek && <label>جابه‌جایی در تایم‌لاین · {cursor.toFixed(2)} ثانیه
      <input aria-label="جابه‌جایی در تایم‌لاین" type="range" dir="ltr" min={0} max={lastFrame}
        value={Math.min(Math.round(cursor * data.fps), lastFrame)} onChange={event => {
          const position = Number(event.target.value) / data.fps;
          const segment = [...data.segments].reverse().find(item => position >= item.start && position < item.end);
          setCursor(position);
          if (segment) seek(Math.min(segment.source_out, segment.source_in + position - segment.start));
        }}/>
    </label>}
    <NativeLayers data={data} blocked={blocked} width={width} cursor={cursor} onChange={editLayer}>
      <div className="mp-native-track" aria-label="قطعه‌های ویدیو">
        {data.segments.map((segment, i) => <button key={segment.id} type="button"
          style={{left: `${segment.start / data.duration * 100}%`, width: `${(segment.end - segment.start) / data.duration * 100}%`}}
          aria-pressed={selected?.id === segment.id} onClick={() => select(segment)}
          draggable={data.arrange && !blocked}
          onDragStart={event => {setDragged(segment.id); event.dataTransfer.effectAllowed = "move";}}
          onDragEnd={() => setDragged(null)}
          onDragOver={event => {if (dragged && dragged !== segment.id && !blocked) event.preventDefault();}}
          onDrop={event => {
            event.preventDefault();
            if (!dragged || dragged === segment.id || blocked) return;
            const bounds = event.currentTarget.getBoundingClientRect();
            void submit({version: data.version, operation: "move", segment_id: dragged, target_id: segment.id,
                         after: event.clientX > bounds.left + bounds.width / 2});
            setDragged(null);
          }}
          title={`${segment.start.toFixed(2)}–${segment.end.toFixed(2)} s`}>{i + 1}</button>)}
        {seek && <span className="mp-playhead" aria-hidden="true" style={{left: `${Math.min(100, cursor / data.duration * 100)}%`}}/>}
      </div>
    </NativeLayers>
    <div className="mp-actions">
      <button className="btn btn-secondary btn-sm" aria-pressed={mode === "trim"} onClick={() => setMode("trim")}>کوتاه‌کردن قطعه</button>
      <button className="btn btn-secondary btn-sm" aria-pressed={mode === "remove_range"} onClick={() => setMode("remove_range")}>حذف بازهٔ خروجی</button>
    </div>
    {(mode === "remove_range" || selected) && <fieldset className="mp-reset" disabled={blocked}>
      <legend>{mode === "trim" ? "زمان در منبع (ثانیه)" : "زمان در خروجی (ثانیه)"}</legend>
      <div className="mp-form-grid">
        <label>از<input type="number" className="input" min={0} step={1 / data.fps} value={activeRange.start}
          onChange={e => updateRange(old => ({...old, start: e.target.value}))}/></label>
        <label>تا<input type="number" className="input" min={0} step={1 / data.fps} value={activeRange.end}
          onChange={e => updateRange(old => ({...old, end: e.target.value}))}/></label>
      </div>
      <button className="btn btn-secondary" disabled={!valid} onClick={() => {
        const values = {version: data.version, start: Number(activeRange.start), end: Number(activeRange.end)};
        if (mode === "trim" && selected) void submit({...values, operation: "trim", segment_id: selected.id});
        if (mode === "remove_range") void submit({...values, operation: "remove_range"});
      }}>{mode === "trim" ? "ذخیرهٔ برش" : "حذف این بازه و جابه‌جایی ادامهٔ تایم‌لاین"}</button>
    </fieldset>}
    {data.arrange && selected && <fieldset className="mp-reset" disabled={blocked}>
      <legend>چیدمان قطعه</legend>
      <div className="mp-actions">
        <button className="btn btn-secondary btn-sm" disabled={selectedIndex <= 0} onClick={() => move(-1)}>یک قطعه عقب‌تر</button>
        <button className="btn btn-secondary btn-sm" disabled={selectedIndex >= data.segments.length - 1} onClick={() => move(1)}>یک قطعه جلوتر</button>
        <button className="btn btn-secondary btn-sm" onClick={() => void submit({version: data.version, operation: "duplicate", segment_id: selected.id})}>تکثیر</button>
      </div>
      <label>زمان تقسیم در منبع<input className="input" type="number" dir="ltr" min={selected.source_in} max={selected.source_out}
        value={split} step={1 / data.fps} onChange={e => setSplit(e.target.value)}/></label>
      <button className="btn btn-secondary" disabled={Number(split) <= selected.source_in || Number(split) >= selected.source_out}
        onClick={() => void submit({version: data.version, operation: "split", segment_id: selected.id, start: Number(split)})}>تقسیم قطعه</button>
    </fieldset>}
    {data.versions.length > 1 && <label>بازگردانی برنامه<select className="input" value={restore} disabled={blocked} onChange={e => setRestore(e.target.value)}>
      <option value="">نسخه را انتخاب کنید</option>
      {[...data.versions].reverse().map(item => <option value={item.version} key={item.version}>نسخهٔ {item.version}</option>)}
    </select></label>}
    <div className="mp-actions">
      {restore && <button className="btn btn-secondary" disabled={blocked || Number(restore) === data.version} onClick={() =>
        void submit({version: data.version, operation: "restore", restore_version: Number(restore)})}>بازگردانی به‌عنوان نسخهٔ جدید</button>}
      <button className="btn btn-secondary" disabled={blocked || !serverTarget} onClick={() => void render(true)}>رندر پیش‌نمایش</button>
      <button className="btn btn-primary" disabled={blocked || !serverTarget} onClick={() => void render(false)}>رندر خروجی</button>
    </div>
    {hint && <p className="mp-muted" role="status">{hint}</p>}
    {error && <p className="notice" data-tone="error" role="alert">{error}</p>}
  </section>;
}
