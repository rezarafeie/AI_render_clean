import React from "react";
import { createPortal } from "react-dom";
import { Icon } from "../components/Icon";

/** Keep authenticated blob URLs local; opening an image never needs another API call. */
export function ImagePreview({ src, alt, frame }: { src: string; alt: string;
  /** Opened like the render frames (centred, no card, dim scrim) instead of the zoom viewer: pictures a Pro agent showed. */ frame?: boolean }) {
  const dialog = React.useRef<HTMLDialogElement>(null);
  const [open, setOpen] = React.useState(false);
  const [zoom, setZoom] = React.useState(100);
  React.useEffect(() => {
    if (!open || !frame) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, frame]);
  React.useEffect(() => {
    if (!open || frame) return;
    const element = dialog.current;
    element?.showModal();
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      element?.close();
      document.body.style.overflow = previous;
    };
  }, [open, frame]);
  if (frame) return <>
    <button type="button" className="attach-image-open" aria-label={`Open image: ${alt}`} onClick={() => setOpen(true)}><img src={src} alt={alt}/></button>
    {open ? createPortal(<div className="overlay" role="dialog" aria-modal="true" aria-label={alt} onMouseDown={event => { if (event.target === event.currentTarget) setOpen(false); }}>
      <figure className="mg-lightbox">
        <img src={src} alt={alt}/>
        <button type="button" className="icon-btn mg-lightbox-close" onClick={() => setOpen(false)} aria-label="بستن"><Icon name="close" size={18}/></button>
      </figure>
    </div>, document.body) : null}
  </>;
  return <>
    <button type="button" className="attach-image-open" aria-label={`Open image: ${alt}`} onClick={() => { setZoom(100); setOpen(true); }}>
      <img src={src} alt={alt}/>
    </button>
    {open ? createPortal(<dialog ref={dialog} className="chat-image-dialog" aria-label={alt} onCancel={() => setOpen(false)} onClose={() => setOpen(false)} onClick={event => { if (event.target === event.currentTarget) setOpen(false); }}>
      <div className="chat-image-viewer">
        <div className="chat-image-toolbar">
          <label>Zoom <input aria-label="Image zoom" type="range" min="50" max="200" step="25" value={zoom} onChange={event => setZoom(Number(event.target.value))}/><span>{zoom}%</span></label>
          <button type="button" aria-label="Close image" onClick={() => setOpen(false)} autoFocus><Icon name="close" size={22}/></button>
        </div>
        <div className="chat-image-scroll" tabIndex={0} aria-label="Full image">
          <img src={src} alt={alt} style={{ width: `${zoom}%` }}/>
        </div>
      </div>
    </dialog>, document.body) : null}
  </>;
}
