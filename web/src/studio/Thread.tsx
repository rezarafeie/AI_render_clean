import React from "react";
import { api, StudioConversation, StudioEvent, StudioProject } from "../api";
import { useAuthenticatedMediaUrl } from "../AuthenticatedMedia";
import { Icon } from "../components/Icon";
import { ActivityBlock, ThinkingRow } from "./Activity";
import { RenderCard } from "./RenderCard";
import { DiscoveryPanel } from "./Discovery";
import { MotionGraphicCard } from "./MotionGraphic";
import { RichText } from "./RichText";
import { TimelineItem } from "./model";
import { ImagePreview } from "./ImagePreview";

export interface LocalFileInfo { name: string; type: string; url: string }

/** Lazy preview for an attachment we only know by id: nothing downloads until asked. */
function RemoteAttachment({ conversationId, id, index, autoOpen }: { conversationId: string; id: string; index: number; autoOpen?: boolean }) {
  const [open, setOpen] = React.useState(Boolean(autoOpen));
  const url = useAuthenticatedMediaUrl(open ? api.studioAttachmentUrl(conversationId, id) : undefined);
  const [kind, setKind] = React.useState<"image" | "video" | "audio" | "">("");
  React.useEffect(() => {
    if (!url) return;
    let active = true;
    void fetch(url).then(r => r.blob()).then(blob => { if (active) setKind(blob.type.startsWith("image/") ? "image" : blob.type.startsWith("audio/") ? "audio" : "video"); }).catch(() => active && setKind("video"));
    return () => { active = false; };
  }, [url]);
  if (!open) return <button className="attach-chip attach-button" onClick={() => setOpen(true)}><span className="attach-icon"><Icon name="paperclip" size={16}/></span><span className="attach-meta"><b>Attachment {index + 1}</b><small>Tap to preview</small></span></button>;
  if (!url || !kind) return <div className="attach-chip"><span className="spinner"/><span className="attach-meta"><small>Loading preview…</small></span></div>;
  return <div className="attach-preview">{kind === "image" ? <ImagePreview src={url} alt={`Attachment ${index + 1}`}/> : kind === "audio" ? <audio src={url} controls/> : <video src={url} controls playsInline preload="metadata"/>}</div>;
}

function Attachments({ conversationId, ids, local, autoOpen }: { conversationId?: string; ids: string[]; local?: LocalFileInfo[]; autoOpen?: boolean }) {
  if (local?.length) return <div className="msg-files">{local.map((file, index) => file.type.startsWith("image/")
    ? <div className="attach-preview" key={index}><ImagePreview src={file.url} alt={file.name}/></div>
    : <div className="attach-chip" key={index}><span className="attach-icon"><Icon name={file.type.startsWith("video/") ? "video" : "music"} size={16}/></span><span className="attach-meta"><b className="wrap-safe">{file.name}</b></span></div>)}</div>;
  if (!ids.length || !conversationId) return null;
  return <div className="msg-files">{ids.map((id, index) => <RemoteAttachment key={id} conversationId={conversationId} id={id} index={index} autoOpen={autoOpen}/>)}</div>;
}

/** Time and a copy button under a message: shown on hover (mouse) or when the message is tapped (touch). */
function MessageMeta({ text, at }: { text: string; at: number }) {
  const [copied, setCopied] = React.useState(false);
  const copy = async (event: React.MouseEvent) => {
    event.stopPropagation();
    try { await navigator.clipboard.writeText(text); }
    catch { const area = document.createElement("textarea"); area.value = text; document.body.appendChild(area); area.select(); try { document.execCommand("copy"); } catch { /* clipboard unavailable */ } area.remove(); }
    setCopied(true); window.setTimeout(() => setCopied(false), 1500);
  };
  return <div className="msg-meta">
    {Number.isFinite(at) && at > 0 ? <time dateTime={new Date(at).toISOString()}>{new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(at)}</time> : null}
    {text ? <button type="button" className="msg-copy" onClick={copy} aria-label={copied ? "Copied" : "Copy message"}><Icon name={copied ? "check" : "copy"} size={14}/><span>{copied ? "Copied" : "Copy"}</span></button> : null}
  </div>;
}

function MessageRow({ item, conversationId, localFiles, linkTitles, onRetryMessage }: { item: Extract<TimelineItem, { kind: "message" }>; conversationId?: string; localFiles?: LocalFileInfo[]; linkTitles: Record<string, string>; onRetryMessage: () => void }) {
  const [tapped, setTapped] = React.useState(false);
  const toggle = (event: React.MouseEvent) => { if ((event.target as HTMLElement).closest("a,button,summary,input,textarea,video,audio")) return; if (window.getSelection()?.toString()) return; setTapped(value => !value); };
  return <li className={`msg msg-${item.role}`} data-pending={item.pending || undefined} data-meta={tapped || undefined} onClick={toggle}>
    {item.role === "user"
      ? <>
          <div className="bubble">
            <Attachments conversationId={conversationId} ids={item.attachments} local={item.pending || item.failed ? localFiles : undefined}/>
            {item.content ? <RichText text={item.content} linkTitles={linkTitles}/> : null}
            {item.failed ? <div className="msg-failed"><Icon name="alert" size={14}/>Not sent <button className="link-btn" onClick={onRetryMessage}>Retry</button></div> : null}
          </div>
          {!item.pending && !item.failed ? <MessageMeta text={item.content} at={item.createdAt}/> : null}
        </>
      : <div className="assistant"><span className="assistant-mark" aria-hidden="true"><Icon name="spark" size={13}/></span><div className="assistant-body"><RichText text={item.content} linkTitles={linkTitles}/><Attachments conversationId={conversationId} ids={item.attachments} autoOpen/><MessageMeta text={item.content} at={item.createdAt}/></div></div>}
  </li>;
}

export function Thread({ items, conversation, projects, localFiles, thinking, compactRender, retryHref, onOpenPreview, onEditAgain, onChoice, onRetryMessage, sourceUrl, linkTitles = {}, events = [] }: {
  items: TimelineItem[]; conversation: StudioConversation | null; projects: StudioProject[]; localFiles?: LocalFileInfo[];
  thinking?: string; compactRender?: boolean; retryHref?: string; onOpenPreview: (projectId: string) => void; onEditAgain: (projectId: string) => void;
  onChoice: (choice: string) => void; onRetryMessage: () => void; sourceUrl?: string; linkTitles?: Record<string, string>; events?: StudioEvent[];
}) {
  return <ol className="thread" aria-label="Conversation">
    {items.map(item => {
      if (item.kind === "message") return <MessageRow key={item.id} item={item} conversationId={conversation?.id} localFiles={localFiles} linkTitles={linkTitles} onRetryMessage={onRetryMessage}/>;
      if (item.kind === "motion") return <li key={item.id} className="thread-aux"><MotionGraphicCard motionId={item.motionId} events={events}/></li>;
      if (item.kind === "discovery") return <li key={item.id} className="thread-aux thread-wide"><DiscoveryPanel analysisId={item.analysisId} events={events}/></li>;
      if (item.kind === "activity") return <li key={item.id} className="thread-aux"><ActivityBlock steps={item.steps} live={item.live} retryHref={retryHref}/></li>;
      if (item.kind === "render") {
        const project = projects.find(p => p.id === item.projectId);
        return project ? <li key={item.id} className="thread-aux"><RenderCard project={project} sourceUrl={sourceUrl} startedAt={item.startedAt} compact={compactRender} onOpenPreview={() => onOpenPreview(project.id)} onEditAgain={() => onEditAgain(project.id)} retryHref={retryHref}/></li> : null;
      }
      if (item.kind === "question") return item.choices.length && !item.style ? <li key={item.id} className="thread-aux"><div className="choices" role="group" aria-label={item.question || "Quick replies"}>{item.choices.map(choice => <button key={choice.value} className="chip" onClick={() => onChoice(choice.value)}>{choice.label}</button>)}</div></li> : null;
      return null;
    })}
    {thinking ? <li className="thread-aux"><ThinkingRow label={thinking}/></li> : null}
  </ol>;
}
