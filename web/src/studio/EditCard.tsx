import React from "react";
import { Icon, type IconName } from "../components/Icon";

function sectionIcon(title: string): IconName {
  if (/افکت|ترنزیشن/.test(title)) return "wand";
  if (/صدا|موسیقی/.test(title)) return "music";
  if (/متن|زیرنویس|فونت/.test(title)) return "captions";
  if (/برند|هویت|لوگو/.test(title)) return "user";
  if (/موشن/.test(title)) return "motion";
  if (/صحنه|لحظه/.test(title)) return "film";
  if (/تصویر|ظاهر|رنگ|کادر/.test(title)) return "image";
  return "advanced";
}

/**
 * One group of settings in the Edit tab: a card with a title, a one-line summary of what is set now, and the controls
 * behind it. Every engine's settings (talking plan, Localize, explainer scenes, Motion clips) use this, so the tab looks
 * and behaves the same whatever the video is.
 */
/** Inside the phone editor's sheet a card is just its body: the sheet already has the title and the tool that opened it. */
export const FlatCards = React.createContext(false);

export function EditCard({ title, summary, hint, children, tone, icon, onToggle }: {
  title: string; summary?: React.ReactNode; hint?: React.ReactNode; /** kept for callers; every card starts closed */ open?: boolean; children: React.ReactNode; tone?: "warning"; icon?: IconName; onToggle?: (open: boolean) => void;
}) {
  const flat = React.useContext(FlatCards);
  if (flat) return <div className="ec-flat" dir="rtl">{hint ? <p className="ec-hint">{hint}</p> : null}{children}</div>;
  return <details className="ec" dir="rtl" data-tone={tone} onToggle={event => onToggle?.(event.currentTarget.open)}>
    <summary>
      <Icon name={icon || sectionIcon(title)} size={20} className="ec-icon"/>
      <span className="ec-text"><b>{title}</b>{summary ? <small className="bidi" dir="auto">{summary}</small> : null}</span>
      <Icon name="chevronDown" size={16} className="ec-chev"/>
    </summary>
    <div className="ec-body">{hint ? <p className="ec-hint">{hint}</p> : null}{children}</div>
  </details>;
}

/** A row of labelled fields that wraps on narrow panels. */
export function EditGrid({ children }: { children: React.ReactNode }) {
  return <div className="ec-grid">{children}</div>;
}

/** A switch row: label and explanation on one side, the checkbox on the other. */
export function EditSwitch({ label, hint, checked, disabled, onChange }: {
  label: string; hint?: string; checked: boolean; disabled?: boolean; onChange: (value: boolean) => void;
}) {
  return <label className="ec-switch">
    <span><b>{label}</b>{hint ? <small>{hint}</small> : null}</span>
    <input type="checkbox" role="switch" checked={checked} disabled={disabled} onChange={event => onChange(event.target.checked)}/>
  </label>;
}
