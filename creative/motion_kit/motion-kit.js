// Vendored into EditorGPT from https://github.com/hughminhphan/motion-kit (skills/motion-designer/motion-kit.js), MIT, (c) 2026 Hugh Phan; see
// vendor/motion-skills/_licenses/motionkit/motion-kit.LICENSE. Local change: typeOn uncovers right-to-left text from the right (marked "EditorGPT" below).
// motion-kit.js - designer motion for GSAP timelines, as an alternative to named presets.
//
// Fixes three causes of the "Claude-made" motion feel:
//   1. Curves are hand-shaped beziers (After Effects speed-graph influence 70-90%), one per
//      property, instead of power1-4 picked from a list.
//   2. Duration comes from distance and weight, not a 0.3-0.6s habit.
//   3. Moves have a lead and reactions (anticipation, overlap, drag, arcs), not even staggers.
//
// Seek-safe: everything is fromTo on a paused timeline, no state read from the previous frame.
// Reference: LIBRARY.md beside this file. Vendor a copy into each composition's assets folder and
// load it with a script tag right after GSAP. MIT, Hugh Phan.

(function () {
  const FPS = 60;
  const F = (n) => n / FPS;

  // Cubic bezier ease, the same curve as CSS cubic-bezier / an AE speed graph.
  function bez(x1, y1, x2, y2) {
    const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
    const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
    const sx = (t) => ((ax * t + bx) * t + cx) * t;
    const sy = (t) => ((ay * t + by) * t + cy) * t;
    const dx = (t) => (3 * ax * t + 2 * bx) * t + cx;
    const solve = (x) => {
      let t = x;
      for (let i = 0; i < 8; i++) {
        const e = sx(t) - x, d = dx(t);
        if (Math.abs(e) < 1e-6) return t;
        if (Math.abs(d) < 1e-6) break;
        t -= e / d;
      }
      let lo = 0, hi = 1;
      t = x;
      for (let i = 0; i < 30; i++) {
        const v = sx(t);
        if (Math.abs(v - x) < 1e-6) break;
        if (v < x) lo = t; else hi = t;
        t = (lo + hi) / 2;
      }
      return t;
    };
    const fn = (p) => (p <= 0 ? 0 : p >= 1 ? 1 : sy(solve(p)));
    fn.points = [x1, y1, x2, y2];
    return fn;
  }

  // Curve library. Each is a character, not a strength. Seeded from AE practice (Easy Ease with
  // influence dragged to 70-90%); replace or extend with curves measured from reference reels.
  const C = {
    land: bez(0.1, 0.75, 0.15, 1),    // arrives at speed, long confident settle (entrances from off-frame)
    heavy: bez(0.75, 0, 0.18, 1),     // slow push-off, decisive arrival (big objects, camera)
    whip: bez(0.85, 0, 0.15, 1),      // AE easy ease at 85% influence: hang, snap, hang
    reveal: bez(0.22, 1, 0.36, 1),    // masked type: almost all travel in the first third
    leave: bez(0.55, 0, 0.9, 0.35),   // accelerates out of frame, never settles
    wind: bez(0.45, 0, 0.55, 1),      // anticipation counter-move
    drift: bez(0.4, 0, 0.6, 1),       // continuous camera breath
  };

  // Duration from distance and weight. Light things over short distances are quick; heavy things
  // over long distances take longer, but sub-linearly (sqrt), which is how a hand-timed reel reads.
  // weight: 0.7 light (chips, labels), 1 normal, 1.35 heavy (panels, camera).
  function dur(distancePx, weight = 1) {
    const frames = (9 + 1.15 * Math.sqrt(Math.max(0, distancePx))) * weight;
    return F(Math.round(frames));
  }

  // Irregular reaction offsets in frames: followers answer the lead, quickly then less so.
  // An even stagger (0.08, 0.16, 0.24) reads as a loop; this reads as a chain of causes.
  const REACT = [0, 4, 9, 15, 22, 30];
  const react = (i, scale = 1) => F(Math.round((REACT[i] ?? REACT[REACT.length - 1] + 8 * (i - REACT.length + 1)) * scale));

  // Move along an arc: x and y get different curves and slightly different durations, so the
  // path bends the way a thrown object's does instead of travelling a straight line.
  function arc(tl, el, from, to, at, opts = {}) {
    const d = Math.hypot((to.x ?? 0) - (from.x ?? 0), (to.y ?? 0) - (from.y ?? 0));
    const w = opts.weight ?? 1;
    const base = opts.duration ?? dur(d, w);
    const xe = opts.xEase ?? C.land, ye = opts.yEase ?? C.heavy;
    if (from.x !== undefined) tl.fromTo(el, { x: from.x }, { x: to.x, duration: base, ease: xe }, at);
    if (from.y !== undefined) tl.fromTo(el, { y: from.y }, { y: to.y, duration: base * 1.12, ease: ye }, at);
    return base;
  }

  // Anticipation: a small counter-move before the main one (about 5% of the travel).
  function anticipate(tl, el, prop, from, to, at, opts = {}) {
    const travel = to - from;
    const back = from - travel * (opts.amount ?? 0.05);
    const windT = F(opts.windFrames ?? 9);
    const d = opts.duration ?? dur(Math.abs(travel), opts.weight ?? 1);
    tl.fromTo(el, { [prop]: from }, { [prop]: back, duration: windT, ease: C.wind }, at);
    tl.to(el, { [prop]: to, duration: d, ease: opts.ease ?? C.whip }, at + windT);
    return windT + d;
  }

  // Drag / follow-through: a child lags its parent's move, then catches up and settles last.
  // Put it on the parent's move with the same direction as the parent's travel.
  function drag(tl, child, prop, lagPx, at, parentDur, opts = {}) {
    const delay = F(opts.delayFrames ?? 3);
    tl.fromTo(child, { [prop]: lagPx }, { [prop]: 0, duration: parentDur + F(opts.extraFrames ?? 8), ease: opts.ease ?? C.land }, at + delay);
  }

  // Masked line reveal: the line rises from behind its own baseline. No opacity fade.
  function revealLines(tl, lines, at, opts = {}) {
    lines.forEach((line, i) => {
      const inner = line.querySelector('.inner') || line;
      tl.fromTo(inner, { yPercent: 108 }, { yPercent: 0, duration: opts.duration ?? F(34), ease: C.reveal }, at + react(i, 1.2));
    });
  }

  // Exit: faster than the entrance and accelerating. Things leave with intent.
  function exitTo(tl, el, to, at, opts = {}) {
    const d = Math.hypot(to.x ?? 0, to.y ?? 0);
    tl.to(el, { ...to, duration: dur(d, (opts.weight ?? 1) * 0.65), ease: C.leave }, at);
  }

  // Physical spring: a damped oscillator, normalised to land exactly on 1. Returns the ease and
  // its natural settle time (the settle IS the physics, so use both). damping 1 = no overshoot,
  // 0.75-0.85 = "felt, not seen". Transforms only: it passes 1, so never on opacity.
  function spring({ response = 0.45, damping = 0.8 } = {}) {
    const w = (2 * Math.PI) / response;
    const pos = (t) => {
      if (damping >= 1) return 1 - Math.exp(-w * t) * (1 + w * t);
      const wd = w * Math.sqrt(1 - damping * damping);
      return 1 - Math.exp(-damping * w * t) * (Math.cos(wd * t) + ((damping * w) / wd) * Math.sin(wd * t));
    };
    let T = 4 * response;
    for (let i = 400; i >= 0; i--) {
      const t = (i / 400) * 4 * response;
      if (Math.abs(1 - pos(t)) > 0.002) { T = ((i + 1) / 400) * 4 * response; break; }
    }
    const end = pos(T);
    const ease = (p) => (p <= 0 ? 0 : p >= 1 ? 1 : pos(p * T) + p * (1 - end));
    return { ease, duration: T };
  }

  // Tempo grid: phrases start on beats so the piece has a pulse (and music can be cut to it later);
  // reactions inside a phrase stay off-grid.
  const grid = (bpm, offset = 0) => (n) => offset + (n * 60) / bpm;

  // Type-on for mono labels: the text uncovers in character steps, like a terminal.
  function typeOn(tl, el, at, opts = {}) {
    const n = opts.chars ?? el.textContent.trim().length;
    // EditorGPT: right-to-left text uncovers from the right edge (the original always uncovered from the left).
    const rtl = (opts.rtl ?? getComputedStyle(el).direction === 'rtl');
    tl.fromTo(el, { clipPath: rtl ? 'inset(0% 0% 0% 100%)' : 'inset(0% 100% 0% 0%)' }, { clipPath: 'inset(0% 0% 0% 0%)', duration: F(opts.frames ?? n * 1.6), ease: `steps(${n})` }, at);
  }

  // ---- Text treatments (LIBRARY.md section 6). Decide what the move is before how it eases.

  // Split an element's text into masked words or characters, once, at build time. Returns the
  // inner spans to animate; each sits in an overflow-hidden wrapper so it can rise out of its line.
  function splitText(el, by = 'words', opts = {}) {
    const masked = opts.mask ?? true;
    if (el._mkSplit && el._mkSplit.by === by) return el._mkSplit.inners;
    const text = el.textContent;
    el.textContent = '';
    const parts = by === 'chars' ? [...text] : text.split(/(\s+)/);
    const inners = [];
    parts.forEach((part) => {
      if (/^\s+$/.test(part)) { el.appendChild(document.createTextNode(part)); return; }
      const mask = document.createElement('span');
      mask.style.cssText = masked ? 'display:inline-block;overflow:hidden;vertical-align:top;padding-bottom:0.08em;margin-bottom:-0.08em' : 'display:inline-block';
      const inner = document.createElement('span');
      inner.style.cssText = 'display:inline-block;will-change:transform';
      inner.textContent = part;
      mask.appendChild(inner); el.appendChild(mask); inners.push(inner);
    });
    el._mkSplit = { by, inners };
    return inners;
  }

  // Hard cut: the element is simply there from this frame (or gone, with on = false).
  function cut(tl, el, at, on = true) {
    tl.set(el, { autoAlpha: on ? 1 : 0 }, at);
  }

  // Words (or chars) rise through their masks, answering each other at uneven offsets.
  function revealWords(tl, el, at, opts = {}) {
    const inners = splitText(el, opts.by ?? 'words');
    tl.set(el, { autoAlpha: 1 }, at);
    inners.forEach((w, i) => tl.fromTo(w, { yPercent: 112 }, { yPercent: 0, duration: opts.duration ?? F(30), ease: opts.ease ?? C.reveal }, at + react(i, opts.spread ?? 1)));
    return inners;
  }

  // Tracking settle: letter-spacing eases from wide (or tight) to its set value. No fade.
  function trackIn(tl, el, at, opts = {}) {
    const to = opts.to ?? getComputedStyle(el).letterSpacing;
    tl.set(el, { autoAlpha: 1 }, at);
    tl.fromTo(el, { letterSpacing: opts.from ?? '0.4em' }, { letterSpacing: to === 'normal' ? '0em' : to, duration: opts.duration ?? F(48), ease: opts.ease ?? C.heavy }, at);
  }

  // Scramble / decode: characters resolve left to right; unresolved ones cycle through glyphs.
  // Deterministic (glyph depends on index and frame), so any seek renders the same frame.
  function scramble(tl, el, at, seconds = 0.8, opts = {}) {
    const target = opts.text ?? el.textContent;
    const glyphs = opts.glyphs ?? 'ABCDEFGHJKLMNPQRSTUVWXYZ0123456789#%&*+=/<>';
    const p = { v: 0 };
    tl.set(el, { autoAlpha: 1 }, at);
    tl.fromTo(p, { v: 0 }, {
      v: 1, duration: seconds, ease: opts.ease ?? 'none',
      onUpdate: () => {
        const frame = Math.round((at + p.v * seconds) * FPS / 2);
        const done = Math.floor(p.v * target.length);
        el.textContent = [...target].map((ch, i) => (i < done || ch === ' ' ? ch : glyphs[(i * 7 + frame * 13) % glyphs.length])).join('');
      },
    }, at);
  }

  // Highlight or underline wipe: a bar grows from one side under or behind a word on screen.
  function wipe(tl, bar, at, opts = {}) {
    tl.fromTo(bar, { scaleX: 0, transformOrigin: opts.from === 'right' ? '100% 50%' : '0% 50%' }, { scaleX: 1, duration: opts.duration ?? F(18), ease: opts.ease ?? C.whip }, at);
  }

  // ---- From After Effects (LIBRARY.md section 6, "Time and procedural tools").

  const rootDuration = (tl) => Number(document.querySelector('[data-composition-id]')?.dataset.duration) || tl.duration();
  const asEase = (e, fallback) => (typeof e === 'function' ? e : typeof e === 'string' ? (LIB[e] ?? gsap.parseEase(e)) : fallback);

  // Text range selector: one move swept across a line's characters (or words), like an AE text
  // animator. `from` is each unit's offset before the sweep reaches it (y, x, yPercent, rotation,
  // scale, opacity); it settles to rest as the selection passes. `width` is how soft the leading
  // edge is (share of the line); `shape` is the falloff ('smooth', 'ramp', 'square' or any curve
  // name); `direction` is 'left', 'right', 'center' (outward) or 'edges' (inward).
  function textRange(tl, el, at, seconds, opts = {}) {
    const units = opts.units ?? splitText(el, opts.by ?? 'chars', { mask: opts.mask ?? true });
    const from = opts.from ?? { yPercent: 110 };
    const n = units.length, width = Math.max(0.01, opts.width ?? 0.35);
    const pos = (i) => {
      const t = i / Math.max(1, n - 1), d = opts.direction ?? 'left';
      return d === 'right' ? 1 - t : d === 'center' ? Math.abs(t - 0.5) * 2 : d === 'edges' ? 1 - Math.abs(t - 0.5) * 2 : t;
    };
    const SH = { smooth: (u) => u * u * (3 - 2 * u), ramp: (u) => u, square: (u) => (u > 0 ? 1 : 0) };
    const shape = typeof opts.shape === 'function' ? opts.shape : SH[opts.shape ?? 'smooth'] ?? curve(opts.shape);
    const rest = (k) => (/^(scale|scaleX|scaleY|opacity)$/.test(k) ? 1 : 0);
    const p = { v: 0 };
    const apply = () => {
      const sweep = p.v * (1 + width);
      units.forEach((u, i) => {
        const s = shape(Math.min(1, Math.max(0, (sweep - pos(i)) / width)));
        const vals = {};
        for (const k in from) vals[k] = from[k] + (rest(k) - from[k]) * s;
        gsap.set(u, vals);
      });
    };
    tl.set(el, { autoAlpha: 1 }, at);
    tl.fromTo(p, { v: 0 }, { v: 1, duration: seconds, ease: asEase(opts.ease, 'none'), onUpdate: apply }, at);
    apply();
    return units;
  }

  // Wiggle: AE's wiggle(freq, amp) as seeded smooth noise, so a frame always renders the same.
  // amps per property, e.g. { x: 6, y: 4, rotation: 0.5, scale: 0.01 }. GSAP is not additive:
  // put the wiggle on a wrapper (camera rig, logo holder), never on an element other tweens move.
  function noise1(x, seed) {
    const h = (n) => { const s = Math.sin((n + seed * 101.3) * 127.1) * 43758.5453; return (s - Math.floor(s)) * 2 - 1; };
    const i = Math.floor(x), f = x - i, u = f * f * (3 - 2 * f);
    return h(i) * (1 - u) + h(i + 1) * u;
  }
  function wiggle(tl, el, amps, opts = {}) {
    const at = opts.at ?? 0, until = opts.until ?? rootDuration(tl), freq = opts.freq ?? 1, seed = opts.seed ?? 1;
    const fadeIn = opts.fadeIn ?? 0.4;
    const rest01 = (prop) => (/^scale/.test(prop) ? 1 : 0);
    const p = { t: 0 };
    const apply = () => {
      const t = at + p.t, k = Math.min(1, p.t / Math.max(1e-6, fadeIn)), vals = {};
      Object.entries(amps).forEach(([prop, a], j) => {
        const n = noise1(t * freq, seed + j * 13) * 0.7 + noise1(t * freq * 2.1, seed + j * 13 + 7) * 0.3;
        vals[prop] = rest01(prop) + k * a * n;
      });
      gsap.set(el, vals);
    };
    tl.fromTo(p, { t: 0 }, { t: until - at, duration: until - at, ease: 'none', onUpdate: apply }, at);
  }

  // Inertial bounce (the classic AE expression): the move keeps its arrival speed and rings out
  // past the target, decaying. Wrap an ease that ends moving (linear, an ease-in, kit.leave).
  // `seconds` is the tween's duration, so freq (Hz) and decay are physical. Transforms only.
  function withBounce(ease, seconds, opts = {}) {
    const base = asEase(ease, (q) => q), share = opts.share ?? 0.45, freq = opts.freq ?? 2.4, decay = opts.decay ?? 6;
    const T = 1 - share, w = 2 * Math.PI * freq, h = 1e-3;
    const v = (base(1) - base(1 - h)) / h / (T * seconds);
    return (p) => {
      if (p <= 0) return 0;
      if (p >= 1) return 1;
      if (p < T) return base(p / T);
      const tau = (p - T) * seconds, s = (p - T) / share;
      return 1 + (v * Math.sin(w * tau) / w) * Math.exp(-decay * tau) * (1 - s * s * s);
    };
  }

  // loopOut: repeat a move until a time. mode 'cycle' restarts each period; 'pingpong' goes there
  // and back. Seek-safe (GSAP repeats on a paused timeline).
  function loop(tl, el, fromVars, toVars, opts = {}) {
    const at = opts.at ?? 0, until = opts.until ?? rootDuration(tl), period = opts.period ?? 1;
    const reps = Math.max(1, Math.floor((until - at) / period));
    const pingpong = opts.mode === 'pingpong';
    tl.fromTo(el, fromVars, { ...toVars, duration: period, ease: asEase(opts.ease, pingpong ? C.drift : 'none'), repeat: reps - 1, yoyo: pingpong }, at);
  }

  // Speed ramp (AE time remapping): author a section on its own paused timeline at normal speed,
  // then play it through a ramp curve. The curve maps output time to the section's time: where it
  // is flat the action is in slow motion, where it is steep it races. Ramps: 'ramp.slowMid'
  // (fast, slow-mo through the hit, fast), 'ramp.speedUp', 'ramp.slowDown', or any curve.
  function ramp(tl, section, at, seconds, rampCurve = 'ramp.slowMid') {
    section.pause(0);
    tl.fromTo(section, { progress: 0 }, { progress: 1, duration: seconds, ease: asEase(rampCurve, curve('ramp.slowMid')) }, at);
  }

  // Null + pick-whip: one controller value drives many properties through mapping functions.
  // The controller is a pure function of time, so links never read the previous frame.
  //   const ctl = MotionKit.controller({ from: 0, to: 1, at: 5, duration: 1.6, ease: 'kit.heavy' });
  //   MotionKit.link(tl, ctl, countEl, (v) => ({ textContent: Math.round(v * 38400).toLocaleString() }));
  //   MotionKit.link(tl, ctl, barEl, (v) => ({ scaleX: v }));
  function controller({ from = 0, to = 1, at = 0, duration = 1, ease = C.heavy } = {}) {
    const e = asEase(ease, C.heavy);
    return { at, duration, value: (t) => from + (to - from) * e(Math.min(1, Math.max(0, (t - at) / duration))) };
  }
  function link(tl, ctl, target, map, opts = {}) {
    const start = opts.at ?? 0, end = opts.until ?? rootDuration(tl);
    const els = target instanceof Element ? [target] : Array.from(target);
    const span = { t: 0 };
    const apply = () => {
      const out = { ...map(ctl.value(start + span.t)) };
      if ('textContent' in out) { els.forEach((e) => { e.textContent = out.textContent; }); delete out.textContent; }
      if (Object.keys(out).length) gsap.set(els, out);
    };
    tl.fromTo(span, { t: 0 }, { t: end - start, duration: end - start, ease: 'none', onUpdate: apply }, start);
    apply();
  }

  // Library: published curves by name, so a piece can borrow a known system's character.
  // Values from source: easings.net src/easings.yml; Material 3 material-web
  // tokens/versions/latest/sass/_md-sys-motion.scss; IBM Carbon motion overview page.
  // See LIBRARY.md for what each one is for. Use with MotionKit.curve('m3.emphasizedDecelerate').
  const B = (x1, y1, x2, y2) => bez(x1, y1, x2, y2);
  const LIB = {
    // easings.net (Penner families as CSS cubic-beziers)
    'easings.inSine': B(0.12, 0, 0.39, 0), 'easings.outSine': B(0.61, 1, 0.88, 1), 'easings.inOutSine': B(0.37, 0, 0.63, 1),
    'easings.inQuad': B(0.11, 0, 0.5, 0), 'easings.outQuad': B(0.5, 1, 0.89, 1), 'easings.inOutQuad': B(0.45, 0, 0.55, 1),
    'easings.inCubic': B(0.32, 0, 0.67, 0), 'easings.outCubic': B(0.33, 1, 0.68, 1), 'easings.inOutCubic': B(0.65, 0, 0.35, 1),
    'easings.inQuart': B(0.5, 0, 0.75, 0), 'easings.outQuart': B(0.25, 1, 0.5, 1), 'easings.inOutQuart': B(0.76, 0, 0.24, 1),
    'easings.inQuint': B(0.64, 0, 0.78, 0), 'easings.outQuint': B(0.22, 1, 0.36, 1), 'easings.inOutQuint': B(0.83, 0, 0.17, 1),
    'easings.inExpo': B(0.7, 0, 0.84, 0), 'easings.outExpo': B(0.16, 1, 0.3, 1), 'easings.inOutExpo': B(0.87, 0, 0.13, 1),
    'easings.inCirc': B(0.55, 0, 1, 0.45), 'easings.outCirc': B(0, 0.55, 0.45, 1), 'easings.inOutCirc': B(0.85, 0, 0.15, 1),
    'easings.inBack': B(0.36, 0, 0.66, -0.56), 'easings.outBack': B(0.34, 1.56, 0.64, 1), 'easings.inOutBack': B(0.68, -0.6, 0.32, 1.6),
    // Material 3 (Google)
    'm3.standard': B(0.2, 0, 0, 1), 'm3.standardDecelerate': B(0, 0, 0, 1), 'm3.standardAccelerate': B(0.3, 0, 1, 1),
    'm3.emphasizedDecelerate': B(0.05, 0.7, 0.1, 1), 'm3.emphasizedAccelerate': B(0.3, 0, 0.8, 0.15),
    'm3.legacy': B(0.4, 0, 0.2, 1), 'm3.legacyDecelerate': B(0, 0, 0.2, 1), 'm3.legacyAccelerate': B(0.4, 0, 1, 1),
    // IBM Carbon: productive = efficient, task UI; expressive = moments that should be noticed
    'carbon.productive.standard': B(0.2, 0, 0.38, 0.9), 'carbon.productive.entrance': B(0, 0, 0.38, 0.9), 'carbon.productive.exit': B(0.2, 0, 1, 0.9),
    'carbon.expressive.standard': B(0.4, 0.14, 0.3, 1), 'carbon.expressive.entrance': B(0, 0, 0.3, 1), 'carbon.expressive.exit': B(0.4, 0.14, 1, 1),
    // Speed ramps for MotionKit.ramp (output time -> section time; flat = slow motion)
    'ramp.slowMid': B(0.1, 0.6, 0.9, 0.4), 'ramp.speedUp': B(0.6, 0, 0.9, 0.55), 'ramp.slowDown': B(0.1, 0.45, 0.4, 1),
  };
  Object.entries(C).forEach(([k, fn]) => { LIB[`kit.${k}`] = fn; });
  const curve = (name) => {
    if (!LIB[name]) throw new Error(`MotionKit: no curve "${name}"`);
    return LIB[name];
  };

  window.MotionKit = { FPS, F, bez, C, LIB, curve, dur, react, arc, anticipate, drag, revealLines, exitTo, spring, grid, typeOn, splitText, cut, revealWords, trackIn, scramble, wipe, textRange, wiggle, withBounce, loop, ramp, controller, link };
})();
