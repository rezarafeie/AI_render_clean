import React from "react";

/* A film style's own mini-scene for the wizard: the scene grammar of the style (a terminal types, a light table glows under a loupe, a blueprint draws
   itself, Bauhaus shapes fit together...) in the style's palette, with the person's title. One of ~20 archetypes, chosen per style. */

export type Archetype = "terminal" | "paper" | "blueprint" | "swiss" | "deco" | "bauhaus" | "newsreel" | "lighttable" | "isometric" | "toy" | "anime"
  | "neon" | "data" | "map" | "cinema" | "minimal" | "riso" | "vhs" | "assembly" | "sketch";
export const ARCHETYPES: Archetype[] = ["terminal", "paper", "blueprint", "swiss", "deco", "bauhaus", "newsreel", "lighttable", "isometric", "toy", "anime",
  "neon", "data", "map", "cinema", "minimal", "riso", "vhs", "assembly", "sketch"];

const KEYWORDS: [RegExp, Archetype][] = [
  [/ascii|terminal|crt|code|hacker|console|pixel|8.?bit/i, "terminal"], [/light.?table|archive|negative|slide|evidence|museum/i, "lighttable"],
  [/blueprint|technical|schematic|engineering|patent|briefing/i, "blueprint"], [/deco|gatsby|luxury|gold/i, "deco"], [/bauhaus|shape|geometric|primitive/i, "bauhaus"],
  [/news|caption|broadcast|report|headline|ticker|documentary/i, "newsreel"], [/iso|isometric|city|diorama|miniature/i, "isometric"],
  [/brick|toy|lego|clay|plastic/i, "toy"], [/anime|manga|cel|cartoon|comic/i, "anime"], [/neon|cyber|synth|glow|night/i, "neon"],
  [/chart|data|graph|stat|infograph|number|dashboard/i, "data"], [/map|route|travel|geo|atlas/i, "map"], [/cinema|film noir|trailer|epic|letterbox|movie/i, "cinema"],
  [/riso|halftone|print|screen.?print|zine|offset/i, "riso"], [/vhs|tape|found footage|liminal|backroom|camcorder|analog/i, "vhs"],
  [/assembly|conveyor|factory|process|line diagram|pipeline/i, "assembly"], [/sketch|whiteboard|hand.?drawn|doodle|chalk|pencil/i, "sketch"],
  [/paper|collage|cut.?out|vox|scrapbook|craft|popup/i, "paper"], [/swiss|grid|typograph|kinetic|poster/i, "swiss"], [/minimal|clean|calm|zen/i, "minimal"],
];
export function archetypeOf(id: string, text: string, given?: string): Archetype {
  if (given && (ARCHETYPES as string[]).includes(given)) return given as Archetype;
  const hay = `${id} ${text}`;
  return KEYWORDS.find(([re]) => re.test(hay))?.[1] ?? ARCHETYPES[[...id].reduce((a, c) => a + c.charCodeAt(0), 0) % ARCHETYPES.length];
}

export function StylePreview({ archetype, palette, title, font, playing = true, aspect = "vertical", big = false }:
  { archetype: Archetype; palette: string[]; title: string; font?: string; playing?: boolean; aspect?: string; big?: boolean }) {
  const [bg, surface, accent, ink] = [palette[0] || "#111318", palette[1] || "#1d2230", palette[2] || "#f2b84b", palette[3] || "#f5f1e8"];
  const ratio = aspect === "landscape" ? "16 / 9" : aspect === "square" ? "1 / 1" : "9 / 16";
  const t = title || "عنوان ویدیوی تو";
  const vars = { aspectRatio: ratio, ["--bg" as string]: bg, ["--sf" as string]: surface, ["--ac" as string]: accent, ["--ink" as string]: ink,
    ...(font ? { ["--font" as string]: font } : {}) };
  return <div className="sp" data-a={archetype} data-play={playing || undefined} data-big={big || undefined} style={vars}>
    <Scene a={archetype} t={t}/>
  </div>;
}

function Scene({ a, t }: { a: Archetype; t: string }) {
  switch (a) {
    case "terminal": return <>
      <div className="sp-scan"/><div className="sp-term"><span className="sp-mono dim">$ editor --render</span>
        <span className="sp-mono sp-type">{t}</span><span className="sp-mono dim">█ loading ▓▓▓▓░░ 68%</span></div></>;
    case "lighttable": return <>
      <div className="sp-glow"/>{[0, 1, 2, 3].map(i => <i key={i} className={`sp-slide s${i}`}/>)}<div className="sp-loupe"><b>{t}</b></div></>;
    case "blueprint": return <>
      <svg className="sp-svg" viewBox="0 0 90 160"><defs><pattern id="g" width="10" height="10" patternUnits="userSpaceOnUse"><path d="M10 0H0V10" fill="none" stroke="var(--ink)" strokeOpacity=".18" strokeWidth=".5"/></pattern></defs>
        <rect width="90" height="160" fill="url(#g)"/><path className="sp-draw" d="M15 110h60v-40H15z M15 70l30-22 30 22" fill="none" stroke="var(--ink)" strokeWidth="1"/>
        <path className="sp-draw d2" d="M15 122h60 M15 118v8 M75 118v8" fill="none" stroke="var(--ac)" strokeWidth=".8"/></svg>
      <b className="sp-title sp-mono top">{t}</b></>;
    case "deco": return <>
      <svg className="sp-svg" viewBox="0 0 90 160">{Array.from({ length: 9 }, (_, i) => <line key={i} className="sp-ray" style={{ animationDelay: `${i * .08}s` }}
        x1="45" y1="120" x2={45 + Math.cos(Math.PI + i * Math.PI / 8) * 60} y2={120 + Math.sin(Math.PI + i * Math.PI / 8) * 60} stroke="var(--ac)" strokeWidth=".9"/>)}
        <path d="M10 134h70 M16 140h58" stroke="var(--ac)" strokeWidth=".8"/></svg>
      <b className="sp-title center serif">{t}</b></>;
    case "bauhaus": return <>
      <i className="sp-shape circle"/><i className="sp-shape tri"/><i className="sp-shape sq"/><b className="sp-title bottom heavy">{t}</b></>;
    case "newsreel": return <>
      <div className="sp-grain"/><span className="sp-live">● زنده</span><div className="sp-photo"/>
      <div className="sp-lower"><b>{t}</b><small>گزارش ویژه · ۲۰۲۶</small></div></>;
    case "isometric": return <>
      {[0, 1, 2, 3, 4].map(i => <i key={i} className={`sp-cube c${i}`}/>)}<b className="sp-title top">{t}</b></>;
    case "toy": return <>
      {[0, 1, 2].map(i => <i key={i} className={`sp-brick b${i}`}><em/><em/><em/></i>)}<b className="sp-title top round">{t}</b></>;
    case "anime": return <>
      <div className="sp-speed"/><div className="sp-burst"/><b className="sp-title center heavy tilt">{t}</b></>;
    case "neon": return <><div className="sp-haze"/><b className="sp-title center neon">{t}</b><i className="sp-neonline"/></>;
    case "data": return <>
      <div className="sp-bars">{[38, 62, 48, 86, 70].map((h, i) => <i key={i} style={{ ["--h" as string]: `${h}%`, animationDelay: `${i * .12}s` }}/>)}</div>
      <b className="sp-title top">{t}</b><span className="sp-num">+۸۶٪</span></>;
    case "map": return <>
      <svg className="sp-svg" viewBox="0 0 90 160"><path d="M8 40 Q30 20 50 44 T86 52 M4 100 Q40 86 60 110 T90 120" stroke="var(--ink)" strokeOpacity=".15" fill="none"/>
        <path className="sp-draw" d="M20 120 C30 90 60 100 55 70 S70 40 72 32" stroke="var(--ac)" strokeWidth="1.4" strokeDasharray="3 2" fill="none"/>
        <circle cx="20" cy="120" r="3" fill="var(--ac)"/><circle className="sp-pin" cx="72" cy="32" r="3.5" fill="var(--ac)"/></svg>
      <b className="sp-title bottom">{t}</b></>;
    case "cinema": return <><i className="sp-box top"/><i className="sp-box bot"/><div className="sp-flare"/><b className="sp-title center serif fade">{t}</b></>;
    case "minimal": return <><i className="sp-dot"/><b className="sp-title center light">{t}</b></>;
    case "riso": return <><div className="sp-halftone"/><b className="sp-title center heavy riso" data-t={t}>{t}</b></>;
    case "vhs": return <><div className="sp-noise"/><span className="sp-rec">● REC</span><span className="sp-stamp">۰۳:۱۴ ق.ظ ۱۴۰۵/۰۹/۰۲</span>
      <b className="sp-title bottom mono-ish">{t}</b></>;
    case "assembly": return <><i className="sp-belt"/>{[0, 1, 2].map(i => <i key={i} className="sp-crate" style={{ animationDelay: `${i * -1.2}s` }}/>)}
      <b className="sp-title top">{t}</b></>;
    case "sketch": return <>
      <svg className="sp-svg" viewBox="0 0 90 160"><path className="sp-draw" d="M18 96 c10-20 30-28 52-8 M22 108 c18 8 34 6 48-4 M30 70 l6-12 6 12" stroke="var(--ink)" strokeWidth="1.2" fill="none" strokeLinecap="round"/>
        <circle className="sp-draw d2" cx="45" cy="58" r="14" stroke="var(--ac)" strokeWidth="1.2" fill="none"/></svg>
      <b className="sp-title top hand">{t}</b></>;
    case "paper": return <>
      <i className="sp-paper p0"/><i className="sp-paper p1"/><i className="sp-tape"/><div className="sp-cut"><b>{t}</b></div></>;
    case "swiss": default: return <>
      <i className="sp-block k0"/><i className="sp-block k1"/><b className="sp-title giant">{t}</b><span className="sp-index">01 / 05</span></>;
  }
}
