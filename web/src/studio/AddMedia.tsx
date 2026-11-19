import React from "react";
import { CloudFile, StudioFile } from "../api";
import { Icon } from "../components/Icon";
import { CloudPicker } from "./CloudPicker";
import { FilesPicker } from "./FilesPicker";

export type AddMediaTab = "device" | "library" | "drive";

/**
 * One place to add files to a message: from this device (pick or drop), from the person's library (uploads, Drive imports and videos made in
 * any chat) and from Google Drive. The library and the Drive connection are prefetched when the studio opens, so both tabs open at once.
 */
export function AddMedia({ onClose, onFiles, onAttach, onImport, initial = "device" }: {
  onClose: () => void;
  /** Files from this device (the composer's own upload path). */
  onFiles: (files: File[]) => void;
  onAttach?: (files: StudioFile[]) => Promise<void> | void;
  onImport?: (files: CloudFile[]) => Promise<void> | void;
  initial?: AddMediaTab;
}) {
  const [tab, setTab] = React.useState<AddMediaTab>(initial);
  const [dragging, setDragging] = React.useState(false);
  const input = React.useRef<HTMLInputElement>(null);
  // iOS Files greys out what its cloud providers do not type as media (Drive .mov): no filter there, the server still checks.
  const ios = typeof navigator !== "undefined" && (/iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1));
  const tabs: [AddMediaTab, string, string][] = [
    ["device", "این دستگاه", "paperclip"],
    ...(onAttach ? [["library", "فایل‌های شما", "library"] as [AddMediaTab, string, string]] : []),
    ...(onImport ? [["drive", "گوگل درایو", "link"] as [AddMediaTab, string, string]] : []),
  ];
  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const take = (list: FileList | File[] | null) => {
    const files = Array.from(list || []);
    if (files.length) { onFiles(files); onClose(); }
  };

  return <div className="overlay" role="dialog" aria-modal="true" aria-label="افزودن فایل" dir="rtl" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="dialog addmedia">
      <header className="addmedia-head">
        <h3>افزودن فایل</h3>
        <button className="icon-btn" onClick={onClose} aria-label="بستن"><Icon name="close" size={18}/></button>
      </header>
      <div className="addmedia-tabs" role="tablist" aria-label="منبع فایل">
        {tabs.map(([id, label, icon]) => <button key={id} type="button" role="tab" aria-selected={tab === id} className="addmedia-tab" onClick={() => setTab(id)}>
          <Icon name={icon as any} size={16}/><span>{label}</span></button>)}
      </div>
      {tab === "device" ? <div className="addmedia-pane">
        <button type="button" className="addmedia-drop" data-dragging={dragging || undefined} onClick={() => input.current?.click()}
          onDragOver={event => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)}
          onDrop={event => { event.preventDefault(); setDragging(false); take(event.dataTransfer.files); }}>
          <Icon name="paperclip" size={30}/>
          <b>انتخاب از این دستگاه</b>
          <small>یا فایل‌ها را همین‌جا بکشید و رها کنید · ویدیو، صدا یا تصویر</small>
        </button>
        <input ref={input} type="file" multiple hidden accept={ios ? undefined : "video/*,image/*,audio/*,.mp4,.mov,.m4v,.webm,.mkv,.png,.jpg,.jpeg,.webp,.mp3,.wav,.m4a,.aac,.ogg"}
          onChange={event => { const files = event.target.files; take(files ? Array.from(files) : null); event.target.value = ""; }}/>
        {onAttach || onImport ? <div className="addmedia-shortcuts">
          {onAttach ? <button type="button" className="btn btn-sm btn-secondary" onClick={() => setTab("library")}><Icon name="library" size={15}/>از فایل‌های قبلی شما</button> : null}
          {onImport ? <button type="button" className="btn btn-sm btn-secondary" onClick={() => setTab("drive")}><Icon name="link" size={15}/>از گوگل درایو</button> : null}
        </div> : null}
      </div> : null}
      {tab === "library" && onAttach ? <FilesPicker embedded onClose={onClose} onAttach={onAttach}/> : null}
      {tab === "drive" && onImport ? <CloudPicker embedded onClose={onClose} onImport={onImport}/> : null}
    </div>
  </div>;
}
