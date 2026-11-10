import { useSyncExternalStore } from "react";

export type Lang = "en" | "fa";
const key = "editorgpt.lang";

/** The language of the whole app: the person's saved choice, else Persian for a Persian browser, else English. */
export function currentLang(): Lang {
  try {
    const stored = localStorage.getItem(key);
    if (stored === "fa" || stored === "en") return stored;
  } catch { /* storage may be blocked */ }
  return typeof navigator !== "undefined" && /^fa\b/i.test(navigator.language || "") ? "fa" : "en";
}

/** Direction and language of the page follow the language (right-to-left for Persian). */
export function applyLang(lang: Lang = currentLang()) {
  const root = document.documentElement;
  root.lang = lang;
  root.dir = lang === "fa" ? "rtl" : "ltr";
  root.dataset.lang = lang;
}

export function setLang(lang: Lang) {
  try { localStorage.setItem(key, lang); } catch { /* keep going: the reload below reads the default */ }
  applyLang(lang);
  window.location.reload();                    // every screen is drawn again in the new language
}

export function useLang(): Lang {
  return useSyncExternalStore(() => () => undefined, currentLang, () => "en" as Lang);
}
