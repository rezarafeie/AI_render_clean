import React from "react";
import { api } from "../api";
import { AuthenticatedMedia } from "../AuthenticatedMedia";

export interface DesignQuestion {
  id: string; title: string; description?: string; recommended?: string;
  options: { key: string; name: string; description?: string; type_voice?: string; motion?: string; palette?: Record<string, string>; attachment_id?: string | null }[];
}

/** Which LOOK should the video have: a picture of each candidate (its palette, its type voice, the real headline), or the person's own words about the look. */
export function DesignChoice({ question, conversationId, busy, onAnswer }: { question: DesignQuestion; conversationId: string; busy: boolean; onAnswer: (choice: string, text: string) => void }) {
  const [text, setText] = React.useState("");
  return <section className="action-card design-choice" dir="rtl" aria-label="انتخاب سبک طراحی">
    <h3>{question.title}</h3>
    {question.description ? <p>{question.description}</p> : null}
    <div className="design-options">{question.options.map(option => <button type="button" key={option.key} disabled={busy} className="design-option" onClick={() => onAnswer(option.key, "")}>
      {option.attachment_id ? <AuthenticatedMedia as="img" src={api.studioAttachmentUrl(conversationId, option.attachment_id)} alt={option.name}/> : null}
      <b>{option.name}{option.key === question.recommended ? " · پیشنهاد من" : ""}</b>
      {option.description ? <small>{option.description}</small> : null}
      {option.type_voice || option.motion ? <small className="muted-text">{[option.type_voice, option.motion].filter(Boolean).join(" · ")}</small> : null}
    </button>)}</div>
    <div className="design-own">
      <textarea dir="auto" rows={2} value={text} disabled={busy} onChange={event => setText(event.target.value)} placeholder="یا ظاهر دلخواهت را توضیح بده: رنگ‌ها، حس، نوع حروف، حرکت…"/>
      <button type="button" className="btn btn-secondary" disabled={busy || !text.trim()} onClick={() => onAnswer("", text.trim())}>با این توضیح بساز</button>
    </div>
  </section>;
}
