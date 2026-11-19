import React from "react";
import { api, type StudioProject } from "../api";
import { Icon } from "../components/Icon";
import { friendlyError } from "../ui";
import type { PanelTranscript } from "./types";

type Cut = {sentence: number; remove: boolean};
export function Speech({project, seek, onChanged}: {project: StudioProject; seek: (seconds: number) => void; onChanged: () => Promise<unknown>}) {
  const [data, setData] = React.useState<PanelTranscript | null>(null);
  const [selected, setSelected] = React.useState<number | null>(null);
  const [past, setPast] = React.useState<Cut[]>([]);
  const [future, setFuture] = React.useState<Cut[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [query, setQuery] = React.useState("");
  const [count, setCount] = React.useState(40);
  const [caption, setCaption] = React.useState("");
  const [previewWords, setPreviewWords] = React.useState(false);

  React.useEffect(() => {
    let live = true;
    api.panelTranscript(project.id).then(value => { if (live) { setData(value); setError(""); } })
      .catch(e => { if (live) setError(friendlyError(e, "open the transcript")); });
    return () => { live = false; };
  }, [project.id, project.updated_at]);

  async function modify(cut: Cut, from: "new" | "undo" | "redo") {
    if (!data?.version_id || busy) return;
    setBusy(true); setError("");
    try {
      await api.editPanelSentence(project.id, data.version_id, cut.sentence, cut.remove);
      setData(await api.panelTranscript(project.id));
      if (from === "undo") {
        setPast(old => old.slice(0, -1)); setFuture(old => [...old, {...cut, remove: !cut.remove}]);
      } else {
        setPast(old => [...old, cut]);
        if (from === "redo") setFuture(old => old.slice(0, -1)); else setFuture([]);
      }
      await onChanged();
    } catch (e) { setError(friendlyError(e, "change the cut")); }
    finally { setBusy(false); }
  }

  const chosen = data?.sentences.find(item => item.id === selected);
  async function saveCaption() {
    if (!data?.version_id || !chosen || !caption.trim() || busy) return;
    setBusy(true); setError("");
    try {
      const doc = await api.studioDocument(project.id);
      const captions = doc.tracks.find(track => track.id === "captions")?.elements ?? [];
      const matches = captions.filter(item => item.props.sentence === chosen.id || item.id === `caption:${chosen.id}`);
      if (matches.length !== 1) throw new Error("برای این جمله یک زیرنویس یکتا در تایم‌لاین وجود ندارد. آن را از تایم‌لاین باز کنید.");
      const item = matches[0];
      const saved = project.state?.plan?.versions?.at(-1)?.content?.timeline_edits?.[item.id] || {};
      await api.editStudioTimeline(project.id, data.version_id, [{...saved, id: item.id, text: caption.trim()}]);
      await onChanged();
    } catch (e) { setError(friendlyError(e, "save the caption")); }
    finally { setBusy(false); }
  }

  const filtered = data?.sentences.filter(item => item.text.includes(query.trim())) ?? [];
  return <section className="mp-inspector" aria-label="ویرایش گفتار">
    <div className="mp-section-head"><h2>گفتار</h2><div className="mp-actions">
      <button className="btn btn-secondary btn-sm" disabled={busy || !data?.editable || !past.length} onClick={() => {
        const edit = past[past.length - 1]; if (edit) void modify({...edit, remove: !edit.remove}, "undo");
      }}>واگرد</button>
      <button className="btn btn-secondary btn-sm" disabled={busy || !data?.editable || !future.length} onClick={() => {
        const edit = future[future.length - 1]; if (edit) void modify(edit, "redo");
      }}>انجام دوباره</button>
    </div></div>
    {error && <p role="alert" className="notice" data-tone="error">{error}</p>}
    {!data ? <p role="status">متن گفتار بعد از تحلیل در دسترس است.</p> : <>
      <label>جستجو در گفتار<input className="input" type="search" value={query} onChange={e => {setQuery(e.target.value); setCount(40);}}/></label>
      {!data.editable && <p className="mp-muted">برش تصویر و صدا در این سبک یا در حین پردازش قابل ویرایش نیست.</p>}
      <ul className="mp-speech">
        {filtered.slice(0, count).map(sentence => <li key={sentence.id} data-cut={sentence.dropped || undefined}>
          <button className="mp-sentence" aria-pressed={selected === sentence.id} onClick={() => {
            setSelected(sentence.id); setCaption(sentence.text); seek(sentence.start);
          }}><time dir="ltr">{sentence.start.toFixed(1)}s</time><span>{sentence.text}</span>{sentence.dropped && <small>حذف‌شده</small>}</button>
        </li>)}
      </ul>
      {filtered.length > count && <button className="btn btn-secondary btn-sm" onClick={() => setCount(n => n + 40)}>جمله‌های بیشتر</button>}
      {chosen && <div className="mp-speech-tools">
        <div className="mp-actions">
          <button className="btn btn-secondary" onClick={() => seek(chosen.start)}><Icon name="play" size={16}/>پخش از اول جمله</button>
          <button className="btn btn-secondary" disabled={busy || !data.editable}
            onClick={() => void modify({sentence: chosen.id, remove: !chosen.dropped}, "new")}>
            {chosen.dropped ? "بازگرداندن جمله" : "حذف تصویر و صدای جمله"}
          </button>
          <button className="btn btn-secondary" aria-expanded={previewWords} onClick={() => setPreviewWords(v => !v)}>زمان کلمه‌ها</button>
        </div>
        {previewWords && <div className="mp-word-list">{chosen.words.map((word, i) => <button key={i} className="btn btn-secondary btn-sm" onClick={() => seek(word.start)}
           title={`${word.start.toFixed(2)}–${word.end.toFixed(2)} s`}>{word.text}</button>)}</div>}
        <label>متن زیرنویس جمله<input className="input" maxLength={400} value={caption} onChange={e => setCaption(e.target.value)}/></label>
        <button className="btn btn-secondary" disabled={!data.editable || busy || !caption.trim()} onClick={() => void saveCaption()}>ثبت اصلاح زیرنویس</button>
      </div>}
    </>}
  </section>;
}
