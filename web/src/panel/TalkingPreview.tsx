import React from "react";

/* A talking-edit style's own mini-reel for the wizard, drawn from what each renderer really does (engine/talking_styles):
   talking_1 full frame with wide/close cuts, a pinned hook box and a lower third, a black-and-white flash;
   talking_2 educational split: a picture card zooming on a coloured top half, the speaker below, a small white lead word over a big yellow keyword
   on the seam, glassy chips listing things; talking_3 cinematic split: a full-bleed picture pushing in, a soft dark seam, teal-orange grade, grain,
   vignette, an editorial chapter title; talking_5 a style pack: a news panel above a rounded speaker card, hard cuts to full frame, a key-word slam;
   premium: full frame with word-by-word kinetic captions and motion accents. The speaker is a neutral silhouette. */

const Speaker = ({ className = "" }: { className?: string }) => <svg className={`tp-speaker ${className}`} viewBox="0 0 100 100" preserveAspectRatio="xMidYMax meet" aria-hidden>
  <path d="M10 100 C12 80 28 72 50 72 C72 72 88 80 90 100 Z" fill="#2c3440"/>
  <path d="M40 72 L50 86 L60 72 Z" fill="#e9e4dc"/>
  <path d="M43 60 h14 v12 c-4 5 -10 5 -14 0z" fill="#c29275"/>
  <ellipse cx="35.5" cy="47" rx="2.6" ry="4" fill="#c99a7c"/><ellipse cx="64.5" cy="47" rx="2.6" ry="4" fill="#c99a7c"/>
  <ellipse cx="50" cy="45" rx="14.5" ry="18" fill="#d8ad91"/>
  <path d="M35 46 C32 22 68 20 65 46 C64 36 59 31 50 31 C41 31 36 36 35 46Z" fill="#2a211c"/>
  <path d="M43 45.5 h4 M53 45.5 h4" stroke="#3a2a22" strokeWidth="1.6" strokeLinecap="round"/>
  <path d="M46 55 q4 2.5 8 0" stroke="#9c6a55" strokeWidth="1.3" fill="none" strokeLinecap="round"/>
  <circle cx="61" cy="84" r="1.8" fill="#111"/>
</svg>;

const Picture = ({ cine = false }: { cine?: boolean }) => <svg className="tp-picsvg" viewBox="0 0 120 90" preserveAspectRatio="xMidYMid slice" aria-hidden>
  <defs><linearGradient id={cine ? "tp-sky-c" : "tp-sky"} x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stopColor={cine ? "#ff9a4d" : "#8fd3ff"}/><stop offset="1" stopColor={cine ? "#6b2f3a" : "#e8f6ff"}/></linearGradient></defs>
  <rect width="120" height="90" fill={`url(#${cine ? "tp-sky-c" : "tp-sky"})`}/>
  <circle cx={cine ? 60 : 88} cy={cine ? 52 : 22} r={cine ? 14 : 9} fill={cine ? "#ffd27a" : "#ffe27a"}/>
  <path d="M0 70 L28 40 L46 58 L68 30 L120 74 V90 H0Z" fill={cine ? "#1d3b46" : "#4f9d63"}/>
  <path d="M0 80 L40 60 L80 78 L120 66 V90 H0Z" fill={cine ? "#0f2329" : "#2f7a45"}/>
</svg>;

export function TalkingPreview({ style, big = false, playing = true }: { style: string; big?: boolean; playing?: boolean }) {
  return <div className="tp" data-s={style} data-big={big || undefined} data-play={playing || undefined}>
    {style === "talking_2" ? <>
      <div className="tp-top"><div className="tp-card"><div className="tp-pic"><Picture/></div></div>
        <div className="tp-chips"><span>۱. ایده</span><span>۲. ساخت</span><span>۳. انتشار</span></div></div>
      <div className="tp-bottom"><Speaker/></div>
      <div className="tp-seam"><small>راز</small><b>موفقیت</b></div>
    </> : style === "talking_3" ? <>
      <div className="tp-top"><div className="tp-pic cine"><Picture cine/></div></div>
      <div className="tp-bottom"><Speaker/></div>
      <div className="tp-fade"/>
      <div className="tp-chapter"><em>فصل اول</em><b>شروع از صفر</b></div>
      <div className="tp-seam plain"><b>هیچ‌وقت دیر نیست</b></div>
      <div className="tp-grain"/><div className="tp-vig"/>
    </> : style === "talking_5" ? <>
      <div className="tp-full"><Speaker/></div>
      <div className="tp-split5">
        <div className="tp-panel"><span className="tp-tag">خبر فوری</span><b>هوش مصنوعی تدوین را عوض کرد</b><i/><i className="s"/></div>
        <div className="tp-speakercard"><Speaker/><span className="tp-name">علی رضایی · مدرس</span></div>
      </div>
      <div className="tp-slam">۱۰ برابر</div>
    </> : style === "premium" ? <>
      <div className="tp-full zoom"><Speaker/></div>
      <div className="tp-ring"/>
      <div className="tp-kinetic"><span>این</span><span>یک</span><b>تغییر</b><span>بزرگ</span><span>است</span></div>
      <div className="tp-vig soft"/>
    </> : <>
      <div className="tp-full cuts"><Speaker/></div>
      <div className="tp-bw"/>
      <div className="tp-caption">هر روز فقط ده دقیقه</div>
      <div className="tp-hook">چطور <mark>عادت</mark> بسازیم؟</div>
      <div className="tp-lower"><b>سارا محمدی</b><small>روان‌شناس</small></div>
    </>}
  </div>;
}
