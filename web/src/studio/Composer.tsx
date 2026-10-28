import React from "react";
import { Icon } from "../components/Icon";
import { Menu } from "../components/Menu";
import { templates } from "../templateData";
import { formatBytes } from "../format";
import { AgentMode } from "../api";
import { AgentModeSelector } from "./AgentMode";

export type PendingFile = { key: string; file: File; progress: number; attachmentId?: string; url: string; localId?: string; localNote?: string };

interface ComposerProps {
  text: string; setText: (value: string) => void;
  files: PendingFile[]; onRemoveFile: (file: PendingFile) => void; onFiles: (files: FileList | File[]) => void;
  /** Work is in flight. */
  processing: boolean;
  /** The backend can cancel the current work (a running project). When false we show a non-cancelable indicator. */
  onStop?: () => void;
  onSend: () => void;
  error: string; onDismissError: () => void;
  hasSpeech: boolean; listening: boolean; onListen: () => void;
  autoFocus?: boolean; placeholder?: string; variant?: "home" | "dock";
  textareaRef?: React.RefObject<HTMLTextAreaElement>;
  manual?: boolean; onManualChange?: () => void;
  /** No attachments or templates: for chats that only exchange text (the Hermes agent). */
  textOnly?: boolean;
  agentMode?: AgentMode; onAgentModeChange?: (mode: AgentMode) => void;
}

export function Composer(props: ComposerProps) {
  const { text, setText, files, onRemoveFile, onFiles, processing, onStop, onSend, error, onDismissError, hasSpeech, listening, onListen, placeholder, variant = "dock" } = props;
  const own = React.useRef<HTMLTextAreaElement>(null);
  const ref = props.textareaRef || own;
  const fileInput = React.useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = React.useState(false);
  const [templateMenu, setTemplateMenu] = React.useState(false);
  const menuFirst = React.useRef<HTMLButtonElement>(null);
  React.useEffect(() => { menuFirst.current?.focus({ preventScroll: true }); }, [templateMenu]);
  const uploading = files.some(file => !file.attachmentId && file.progress >= 0);

  // Auto-resize: grows with content up to a cap, then scrolls.
  React.useLayoutEffect(() => {
    const node = ref.current; if (!node) return;
    node.style.height = "auto";
    node.style.height = `${Math.min(node.scrollHeight, 200)}px`;
  }, [text, ref]);
  React.useEffect(() => { if (props.autoFocus) ref.current?.focus({ preventScroll: true }); }, [props.autoFocus, ref]);

  const hasInput = text.trim().length > 0 || files.length > 0;
  // Working and nothing typed: the button is Stop. As soon as something is typed it is Send again (a message can be sent while work continues).
  const canSend = !uploading && hasInput;
  const submit = () => { if (canSend) onSend(); };

  return <div className={`composer composer-${variant}`}>
    <div className="composer-box" data-dragging={dragging || undefined}
      onDragOver={event => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)}
      onDrop={event => { event.preventDefault(); setDragging(false); void onFiles(Array.from(event.dataTransfer.files)); }}>
      {error ? <div className="notice composer-error" data-tone="error" role="alert"><span className="grow">{error}</span><button className="icon-btn" style={{ ["--size" as string]: "24px" }} onClick={onDismissError} aria-label="Dismiss error"><Icon name="close" size={14}/></button></div> : null}
      {files.length ? <ul className="attach-row" aria-label="Attachments">{files.map((item, index) => <li key={item.key} className="attach-chip">
        {item.file.type.startsWith("image/") ? <img src={item.url} alt=""/> : <span className="attach-icon"><Icon name={item.file.type.startsWith("video/") ? "video" : "music"} size={18}/></span>}
        <span className="attach-meta"><b className="wrap-safe">{item.file.name}</b><small>{item.attachmentId ? formatBytes(item.file.size) : item.progress < 0 ? `On this device · ${formatBytes(item.file.size)}` : `Uploading ${Math.round(item.progress)}%`}</small>{item.localNote ? <small>{item.localNote}</small> : null}</span>
        <button className="icon-btn" style={{ ["--size" as string]: "24px" }} onClick={() => onRemoveFile(item)} aria-label={`Remove ${item.file.name}`}><Icon name="close" size={14}/></button>
        {!item.attachmentId && item.progress >= 0 ? <i className="attach-progress" style={{ width: `${item.progress}%` }}/> : null}
      </li>)}</ul> : null}

      <textarea ref={ref} className="composer-input bidi" dir="auto" rows={1} value={text} placeholder={placeholder || "Describe your video or edit…"}
        aria-label="Message EditorGPT" enterKeyHint="send"
        onChange={event => setText(event.target.value)}
        onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); submit(); } }}/>

      <div className="composer-bar">
        {props.textOnly ? null : (
        <Menu label={templateMenu ? "Templates" : "Add to message"} side="top" trigger={triggerProps => <button type="button" className="icon-btn" {...triggerProps} onClick={() => { setTemplateMenu(false); triggerProps.onClick(); }} aria-label="Attach or choose a template" data-tip="Attach or choose a template" data-tip-pos="top"><Icon name="plus" size={20}/></button>}>
          {close => <>
            {templateMenu ? <>
              <button ref={menuFirst} type="button" role="menuitem" className="menu-item" onClick={() => setTemplateMenu(false)}><Icon name="chevronLeft" size={18}/><span>Back</span></button>
              <div className="menu-sep"/>
              <div className="menu-label">Templates</div>
              {templates.map(item => <button type="button" key={item.id} role="menuitem" className="menu-item" onClick={() => { setText(item.prompt); close(); ref.current?.focus(); }}><Icon name={item.icon} size={18}/><span>{item.title}</span></button>)}
            </> : <>
              <button ref={menuFirst} type="button" role="menuitem" className="menu-item" onClick={() => { close(); fileInput.current?.click(); }}><Icon name="paperclip" size={18}/><span>Attach media</span></button>
              <button type="button" role="menuitem" className="menu-item" onClick={() => setTemplateMenu(true)}><Icon name="grid" size={18}/><span>Templates</span><Icon name="chevron" size={14}/></button>
            </>}
          </>}
        </Menu>
        )}
        <input ref={fileInput} type="file" multiple hidden accept="video/*,image/*,audio/*" onChange={event => { const picked = Array.from(event.target.files || []); event.target.value = ""; if (picked.length) void onFiles(picked); }}/>
        {props.onAgentModeChange ? <AgentModeSelector value={props.agentMode || "lite"} onChange={props.onAgentModeChange}/> : null}
        <span className="grow"/>
        {hasSpeech ? <button type="button" className="icon-btn" aria-pressed={listening} onClick={onListen} aria-label={listening ? "Stop voice input" : "Use voice input"} data-tip="Voice input" data-tip-pos="top"><Icon name="mic" size={19}/></button> : null}
        {props.onManualChange ? <button type="button" className="icon-btn composer-manual" aria-label="Manual mode" aria-pressed={Boolean(props.manual)} disabled={processing}
          onClick={props.onManualChange} data-tip={props.manual ? "Manual · تأیید مرحله‌به‌مرحله" : "Auto · فعال‌کردن حالت دستی"} data-tip-pos="top"><Icon name="hand" size={18}/></button> : null}
        {processing && !hasInput
          ? onStop
            ? <button type="button" className="icon-btn icon-btn-solid icon-btn-lg composer-send" onClick={onStop} aria-label="Stop" data-tip="Stop" data-tip-pos="top"><Icon name="stop" size={18}/></button>
            : <button type="button" className="icon-btn icon-btn-solid icon-btn-lg composer-send" disabled aria-label="Working…"><span className="spinner composer-spinner"/></button>
          : <button type="button" className="icon-btn icon-btn-solid icon-btn-lg composer-send" onClick={submit} disabled={!canSend} aria-label="Send message" data-tip="Send" data-tip-pos="top"><Icon name="send" size={19}/></button>}
      </div>
    </div>
  </div>;
}
