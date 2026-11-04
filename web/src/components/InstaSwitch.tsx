import React from "react";
import { NavLink } from "react-router-dom";
import { api, InstagramSummary } from "../api";
import { Icon } from "./Icon";

/** 12400 → "12.4K"; a number the page does not have yet stays out of the button instead of showing a dash. */
export function compactCount(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "";
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

let remembered: InstagramSummary | null = null;

/**
 * The InstaGPT button of the top bar. It is one small round button: the Instagram mark, or, once the page is known to be connected, its photo
 * (its first letter when there is none) and the follower count. No label; the name is in aria-label and the tooltip.
 */
export function InstaSwitch({ enabled, onPointerEnter }: { enabled: boolean; onPointerEnter?: () => void }) {
  const [info, setInfo] = React.useState<InstagramSummary | null>(remembered);
  const [broken, setBroken] = React.useState(false);
  React.useEffect(() => {
    if (!enabled || remembered?.connected) return;
    const controller = new AbortController();
    api.studioInstagram(controller.signal).then(value => { if (!controller.signal.aborted) { remembered = value; setInfo(value); setBroken(false); } }).catch(() => undefined);
    return () => controller.abort();
  }, [enabled]);
  const connected = info?.connected === true;
  const followers = connected ? compactCount(info?.followers) : "";
  const name = connected && info?.username ? `InstaGPT · @${info.username}` : "Switch to InstaGPT";
  return <NavLink to="/hermes" className="switch-btn" data-connected={connected || undefined} aria-label={name} title={name} onPointerEnter={onPointerEnter} onTouchStart={onPointerEnter}>
    {connected ? (info?.picture && !broken
      ? <img className="switch-avatar" src={info.picture} alt="" referrerPolicy="no-referrer" onError={() => setBroken(true)} draggable={false}/>
      : <span className="switch-avatar" aria-hidden="true">{(info?.username || "i").slice(0, 1).toUpperCase()}</span>)
      : <Icon name="instagram" size={18}/>}
    {followers ? <span className="switch-count">{followers}</span> : null}
  </NavLink>;
}
