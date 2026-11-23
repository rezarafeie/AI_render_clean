import React from "react";

/* A talking-edit style's own mini-reel for the wizard, drawn from what each renderer really does (engine/talking_styles):
   talking_1 full frame with wide/close cuts, a pinned hook box and a lower third, a black-and-white flash;
   talking_2 educational split: a picture card zooming on a coloured top half, the speaker below, a small white lead word over a big yellow keyword
   on the seam, glassy chips listing things; talking_3 cinematic split: a full-bleed picture pushing in, a soft dark seam, teal-orange grade, grain,
   vignette, an editorial chapter title; talking_5 a style pack: a news panel above a rounded speaker card, hard cuts to full frame, a key-word slam;
   premium: full frame with word-by-word kinetic captions and motion accents. The speaker is a neutral silhouette. */

const Speaker = ({ className = "" }: { className?: string }) => <svg className={`tp-speaker ${className}`} viewBox="0 0 90 100" preserveAspectRatio="xMidYMax slice" aria-hidden>
  <defs><linearGradient id="tp-skin" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#d9b49a"/><stop offset="1" stopColor="#b98d72"/></linearGradient></defs>
  <path d="M8 100 C10 76 26 68 45 68 C64 68 80 76 82 100 Z" fill="#2c3440"/>
  <path d="M38 60 h14 v10 c-4 4 -10 4 -14 0z" fill="#b98d72"/>
  <ellipse cx="45" cy="44" rx="15" ry="18" fill="url(#tp-skin)"/>
  <path d="M30 40 C30 24 60 22 61 40 C58 32 50 30 45 31 C38 31 33 34 30 40Z" fill="#2a211c"/>
  <path d="M33 86 h8 M49 86 h8" stroke="#3a4554" strokeWidth="2"/>
  <circle cx="64" cy="80" r="2.4" fill="#111"/>
</svg>;

export function TalkingPreview({ style, big = false, playing = true }: { style: string; big?: boolean; playing?: boolean }) {
  return <div className="tp" data-s={style} data-big={big || undefined} data-play={playing || undefined}>
    {style === "talking_2" ? <>
      <div className="tp-top"><div className="tp-card"><i className="tp-pic"/></div>
        <div className="tp-chips"><span>۱. ایده</span><span>۲. ساخت</span><span>۳. انتشار</span></div></div>
      <div className="tp-bottom"><Speaker/></div>
      <div className="tp-seam"><small>راز</small><b>موفقیت</b></div>
    </> : style === "talking_3" ? <>
      <div className="tp-top"><i className="tp-pic cine"/></div>
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
