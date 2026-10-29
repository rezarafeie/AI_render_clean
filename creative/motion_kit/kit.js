/* Motion-graphic kit (global HM). Deterministic: every helper is a function of the timeline position only.
   build() helpers add tweens to the timeline bound by the page; update() helpers are pure functions of t. */
(function () {
  var HM = window.HM = { _tl: null, duration: 0, width: 1080, height: 1920 };
  var DIGITS = "۰۱۲۳۴۵۶۷۸۹";

  HM._bind = function (tl, info) { HM._tl = tl; HM.duration = info.duration; HM.width = info.width; HM.height = info.height; };
  function T() { if (!HM._tl) throw new Error("HM helpers can only be used inside build()"); return HM._tl; }
  function list(targets) {   // a selector, an element, or any (nested) list of them: always a flat array of elements
    if (typeof targets === "string") return Array.prototype.slice.call(document.querySelectorAll(targets));
    if (targets && targets.nodeType) return [targets];
    if (targets && targets.length !== undefined) {
      var out = [];
      Array.prototype.forEach.call(targets, function (t) { out = out.concat(list(t)); });
      return out;
    }
    return [];
  }
  function opt(o, k, d) { return o && o[k] !== undefined ? o[k] : d; }

  HM.fa = function (n) { return String(n).replace(/\d/g, function (d) { return DIGITS[+d]; }); };
  HM.clamp = function (x, a, b) { a = a === undefined ? 0 : a; b = b === undefined ? 1 : b; return Math.min(b, Math.max(a, x)); };
  HM.easeOut = function (p) { p = HM.clamp(p); return 1 - Math.pow(1 - p, 3); };
  HM.easeInOut = function (p) { p = HM.clamp(p); return p < .5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2; };
  HM.random = function (seed) {   // deterministic generator (mulberry32)
    var a = (seed >>> 0) || 1;
    return function () { a |= 0; a = a + 0x6D2B79F5 | 0; var t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
  };

  /* ── entrances / exits ─────────────────────────────────────────── */
  HM.rise = function (targets, at, o) {   // <span class="hm-mask"><span class="hm-rise">text</span></span>
    return T().fromTo(list(targets), { opacity: 0, yPercent: 115 }, { opacity: 1, yPercent: 0, duration: opt(o, "duration", .8), ease: "power3.out", stagger: opt(o, "stagger", .1) }, at);
  };
  HM.sink = function (targets, at, o) {
    return T().to(list(targets), { yPercent: -115, duration: opt(o, "duration", .6), ease: "power3.in", stagger: opt(o, "stagger", .06) }, at);
  };
  HM.fadeUp = function (targets, at, o) {
    var y = opt(o, "y", 60);
    return T().fromTo(list(targets), { opacity: 0, y: y }, { opacity: 1, y: 0, duration: opt(o, "duration", .7), ease: "power3.out", stagger: opt(o, "stagger", .1) }, at);
  };
  HM.fadeOut = function (targets, at, o) {
    return T().to(list(targets), { opacity: 0, duration: opt(o, "duration", .45), ease: "power2.in", stagger: opt(o, "stagger", 0) }, at);
  };
  HM.pop = function (targets, at, o) {    // scale-in with a small overshoot
    var from = opt(o, "from", .6);
    if (typeof from !== "number" || !Number.isFinite(from) || from < 0) throw new Error("HM.pop: from must be a non-negative numeric scale");
    return T().fromTo(list(targets), { opacity: 0, scale: from }, { opacity: 1, scale: 1, duration: opt(o, "duration", .6), ease: "back.out(1.6)", stagger: opt(o, "stagger", .08) }, at);
  };

  // Local scene clock, one master timeline. Legacy absolute-time drafts do not use this adapter.
  // Explicit numeric positions only: a model cannot accidentally add a global scene start twice.
  HM._scene = function (master, start, duration, build) {
    var prior = HM._tl, proxy = {};
    ["to", "from", "fromTo", "set"].forEach(function (method) {
      proxy[method] = function () {
        var args = Array.prototype.slice.call(arguments), posIndex = method === "fromTo" ? 3 : 2;
        var at = args[posIndex];
        if (typeof at !== "number" || !Number.isFinite(at) || at < 0 || at > duration)
          throw new Error("Scene animation position outside local duration: " + at);
        var vars = args[method === "fromTo" ? 2 : 1] || {};
        var seconds = method === "set" ? 0 : (vars.duration === undefined ? .5 : vars.duration);
        var repeats = vars.repeat || 0, delay = vars.delay || 0, repeatDelay = vars.repeatDelay || 0, stagger = vars.stagger || 0;
        var targets = list(args[0]);
        if (![seconds, repeats, delay, repeatDelay].every(function (v) { return typeof v === "number" && Number.isFinite(v) && v >= 0; }) || !Number.isInteger(repeats))
          throw new Error("Scene duration, delay and repeat must be bounded non-negative numbers");
        var tail = typeof stagger === "number" ? Math.abs(stagger) * Math.max(0, targets.length - 1) :
          (stagger && typeof stagger.amount === "number" ? Math.abs(stagger.amount) : NaN);
        if (!Number.isFinite(tail) || at + delay + seconds * (repeats + 1) + repeatDelay * repeats + tail > duration + .001)
          throw new Error("Scene animation extends beyond its scene");
        args[posIndex] = start + at;
        master[method].apply(master, args);
        return proxy;
      };
    });
    HM._tl = proxy;
    try { build(proxy, 0, duration); } finally { HM._tl = prior; }
  };
  HM.slide = function (targets, at, o) {  // horizontal entrance; dir "right" (default, RTL reading side) or "left"
    var x = opt(o, "x", 140) * (opt(o, "dir", "right") === "left" ? -1 : 1);
    return T().fromTo(list(targets), { opacity: 0, x: x }, { opacity: 1, x: 0, duration: opt(o, "duration", .7), ease: "power3.out", stagger: opt(o, "stagger", .1) }, at);
  };

  /* A scene revealed through a growing diamond that starts at (x, y); a coloured band leads the edge. */
  HM.wipe = function (scene, at, o) {
    var el = list(scene)[0], W = HM.width, H = HM.height;
    var cx = opt(o, "x", W / 2), cy = opt(o, "y", H / 2), dur = opt(o, "duration", .9), band = opt(o, "band", null);
    var reach = Math.max(cx, W - cx) + Math.max(cy, H - cy) + 40;
    function poly(r) { return "polygon(" + cx + "px " + (cy - r) + "px," + (cx + r) + "px " + cy + "px," + cx + "px " + (cy + r) + "px," + (cx - r) + "px " + cy + "px)"; }
    var prior = [];       // scenes this one fully covers: hidden once the wipe completes, so they never show through or collide
    for (var sib = el.previousElementSibling; sib; sib = sib.previousElementSibling) if (sib.classList.contains("hm-scene")) prior.push(sib);
    var state = { p: 0 }, strip = null;
    if (band) {
      strip = document.createElement("div"); strip.className = "hm-band";
      el.parentNode.insertBefore(strip, el); strip.style.background = band; strip.style.opacity = "0";
    }
    el.style.clipPath = poly(0);
    var tl = T();
    tl.fromTo(state, { p: 0 }, {
      p: 1, duration: dur, ease: "power2.inOut",
      onUpdate: function () {
        var r = state.p * reach;
        el.style.clipPath = poly(r);
        if (strip) { strip.style.opacity = state.p > 0 && state.p < 1 ? "1" : "0"; strip.style.clipPath = poly(Math.min(reach, r + 90)); }
        for (var i = 0; i < prior.length; i++) prior[i].style.visibility = state.p >= 1 ? "hidden" : "";
      },
      onReverseComplete: function () { el.style.clipPath = poly(0); if (strip) strip.style.opacity = "0"; }
    }, at);
    return tl;
  };

  HM.set = function (targets, vars, at) {   // jump to a state at a time: HM.set(".a", {opacity: 0}, 0)
    return T().set(list(targets), vars || {}, at || 0);
  };

  HM.hide = function (targets, at) {   // hide a layer once something opaque covers it (HM.wipe does this by itself)
    return T().set(list(targets), { visibility: "hidden" }, at);
  };

  /* SVG strokes that draw themselves (stroke-dasharray from the real path length). */
  HM.draw = function (paths, at, o) {
    var items = list(paths), tl = T();
    items.forEach(function (p, i) {
      if (!p.style) return;
      var len = p.getTotalLength ? Math.ceil(p.getTotalLength()) : 1000;
      p.style.strokeDasharray = len + " " + len;
      tl.fromTo(p, { strokeDashoffset: len }, { strokeDashoffset: 0, duration: opt(o, "duration", 1.2), ease: opt(o, "ease", "power2.inOut") }, at + i * opt(o, "stagger", .15));
    });
    return tl;
  };

  /* ── text ──────────────────────────────────────────────────────── */
  HM.words = function (target) {   // wraps whole words (never letters: Persian letters must stay joined)
    var el = list(target)[0], parts = el.textContent.trim().split(/\s+/), out = [];
    el.textContent = "";
    parts.forEach(function (w, i) {
      var s = document.createElement("span"); s.className = "hm-word"; s.textContent = w; el.appendChild(s); out.push(s);
      if (i < parts.length - 1) el.appendChild(document.createTextNode(" "));
    });
    return out;
  };

  /* ── per-frame helpers: call from update(t); they only read t ───── */
  HM.type = function (target, text, start, cps, t) {
    var el = list(target)[0], n = Math.max(0, Math.min(text.length, Math.floor((t - start) * cps)));
    el.textContent = text.slice(0, n);
    return n >= text.length;
  };
  HM.stream = function (spans, start, wps, t) {
    spans.forEach(function (s, i) { s.style.opacity = t >= start + i / wps ? "1" : "0"; });
  };
  HM.counter = function (target, value, start, duration, t, o) {
    var el = list(target)[0], d = opt(o, "decimals", 0), p = HM.easeOut((t - start) / duration), v = value * p;
    var s = d ? v.toFixed(d) : String(Math.round(v));
    s = s.replace(/\B(?=(\d{3})+(?!\d))/g, opt(o, "separator", ","));
    if (opt(o, "persian", true)) s = HM.fa(s).replace(/,/g, "٬").replace(/\./g, "٫");
    el.textContent = (opt(o, "prefix", "")) + s + (opt(o, "suffix", ""));
  };
  HM.progress = function (target, value, start, duration, t) {   // sets width in % of a bar element
    var el = list(target)[0]; el.style.width = (value * HM.easeOut((t - start) / duration)) + "%";
  };

  HM.colors = { ink: "#171717", cream: "#FDF7F3", night: "#0E0E0E" };
})();
