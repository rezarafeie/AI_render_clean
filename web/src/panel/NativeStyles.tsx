import React from "react";
import {api, type StyleProfile} from "../api";
import {AuthenticatedMedia} from "../AuthenticatedMedia";
import {friendlyError} from "../ui";
import type {StyleReference} from "./types";

const versionKey = (value?: StyleReference | null) => value ? `${value.style_id}@${value.version}` : "";

export function NativeStyles({value, onChange}: {value?: StyleReference | null; onChange: (value: StyleReference | null) => void}) {
  const [profiles, setProfiles] = React.useState<StyleProfile[]>([]);
  const [loaded, setLoaded] = React.useState(false);
  const [error, setError] = React.useState("");
  const chosen = profiles.find(row => versionKey(row) === versionKey(value));
  const asset = chosen?.evidence?.find(item => typeof item?.asset === "string")?.asset;
  React.useEffect(() => {
    let active = true;
    api.getStyleLibrary().then(data => {
      if (active) setProfiles(data.profiles.filter(row => row.state === "approved"));
    }).catch(e => { if (active) setError(friendlyError(e, "load approved styles")); })
      .finally(() => { if (active) setLoaded(true); });
    return () => { active = false; };
  }, []);

  return <section className="mp-inspector" aria-label="سبک تأییدشدهٔ پروژه">
    <label>سبک تأییدشده<select className="input" value={versionKey(value)} disabled={!loaded} onChange={e => {
      const next = profiles.find(row => versionKey(row) === e.target.value);
      onChange(next ? {style_id: next.style_id, version: next.version} : null);
    }}>
      <option value="">پیش‌فرض تدوین</option>
      {value && !chosen && <option value={versionKey(value)}>نسخهٔ ذخیره‌شده · {value.version}</option>}
      {profiles.map(row => <option value={versionKey(row)} key={versionKey(row)}>{row.name} · نسخهٔ {row.version}</option>)}
    </select></label>
    {asset && <AuthenticatedMedia as="img" loading="lazy" alt={`نمونهٔ مرجع ${chosen?.name}`}
      className="mp-setup-media" src={api.styleEvidenceUrl(asset)}/>}
    {chosen && !asset && <p className="mp-muted">برای این نسخه تصویری در کتابخانه ثبت نشده است.</p>}
    {loaded && !profiles.length && !error && <p className="mp-muted">سبک تأییدشده‌ای برای انتخاب موجود نیست.</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
