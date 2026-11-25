import React from "react";
import { Icon } from "../components/Icon";

export interface ManualQuestionData {
  id: string; title: string; description?: string; key?: string; input?: boolean;
  choices: { value: string; label: string; description?: string; swatch?: string; layout?: string; font?: string }[];
  summary?: { hook?: string; cta?: string; title?: string; style?: string; next?: string; storyboard?: any[]; scenes?: any[]; lines?: any[] } | string;
}

/** Only a live persisted backend question is interactive; no local wizard or fake stages. */
export function ManualQuestion({ question, busy, onAnswer }: { question: ManualQuestionData; busy: boolean; onAnswer: (value: string) => void }) {
  const summary = question.summary;
  // Scheduled-task setup: quick answers are small pills under the assistant's message (it already asked the question); the person can always type instead.
  if (question.key === "scheduled" && !question.description) return <div className="quick-replies" dir="rtl" aria-label="پاسخ‌های سریع">
    {question.choices.map(option => <button type="button" key={option.value} disabled={busy} title={option.description || undefined} onClick={() => onAnswer(option.value)}>{option.label}</button>)}
    <span className="quick-hint">یا پاسخ خودتان را بنویسید</span>
  </div>;
  return <section className="action-card manual-question" dir="rtl" aria-label={question.key === "scheduled" ? "تنظیم کار زمان‌بندی‌شده" : "تأیید مرحلهٔ دستی"}>
    {question.key === "scheduled" ? <div className="manual-heading"><Icon name="clock" size={16}/><span>کار زمان‌بندی‌شده</span></div> : <div className="manual-heading"><Icon name="hand" size={16}/><span>Manual</span></div>}
    <h3>{question.title}</h3>
    {question.description ? <p style={question.key === "scheduled" ? { whiteSpace: "pre-line" } : undefined}>{question.description}</p> : null}
    {typeof summary === "string" ? <p>{summary}</p> : summary ? <div className="manual-summary">
      {summary.hook || summary.title ? <p>{summary.hook || summary.title}</p> : null}
      {summary.cta ? <p>دعوت به اقدام: {summary.cta}</p> : null}
      {(summary.storyboard || summary.scenes || summary.lines)?.length ? <details><summary>مشاهدهٔ برنامه و متن</summary><ol>{(summary.storyboard || summary.scenes || summary.lines || []).map((row, i) => <li key={i}>{row.title || row.text || row.fa || row.narration || row.visual || `صحنهٔ ${i + 1}`}</li>)}</ol></details> : null}
      {summary.next ? <p>{summary.next}</p> : null}
    </div> : null}
    {question.key === "logo_asset" ? <p role="status">تصویر لوگو را با دکمهٔ + پیوست کنید؛ پس از آپلود، خودکار ثبت می‌شود.</p> : null}
    <div className="manual-choices">{question.choices.filter(option => question.key !== "logo_asset" || option.value !== "attached").map(option => <button type="button" key={option.value} disabled={busy} onClick={() => onAnswer(option.value)} className="manual-choice">
      {option.layout ? <span className="manual-layout" data-layout={option.layout} aria-hidden="true"><i/><i/></span> : option.swatch ? <i className="manual-swatch" style={{ background: option.swatch }} aria-hidden="true"/> : null}
      <span style={option.font ? { fontFamily: option.font } : undefined}><b>{option.label}</b>{option.description ? <small>{option.description}</small> : null}</span>
    </button>)}</div>
    {question.input ? <small className="muted-text">پاسخ دلخواه و فایل‌های رفرنس را با ورودی همین چت ارسال کنید.</small> : null}
  </section>;
}
