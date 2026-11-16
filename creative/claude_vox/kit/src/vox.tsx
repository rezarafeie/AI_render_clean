// The Vox kit: paper-collage documentary primitives (the studio's reference film «Zappos & drop shipping», VOX_ENGINE_SPEC.md §7).
// Scenes are written ONLY from these primitives; every `at` is a cue of the narration: c('word') seconds from the scene start.
import React from 'react';
import {AbsoluteFill, Easing, Img, interpolate, random, spring, staticFile, useCurrentFrame} from 'remotion';
import {THEME} from './theme';
import usmap from './usmap.json';

export const W = 1080;
export const H = 1920;
export const FPS = 30;
export const INK = '#1C1B19';
export const RED = THEME.red;
export const MUST = THEME.must;
export const TEAL = THEME.teal;
export const CREAM = '#F3ECDF';
export const DARK = '#2A2724';
export const D = 'Doran';
export const TW = "'Special Elite', 'Courier New', monospace";
export const ANTON = 'Anton';

export const clamp = (x: number) => Math.max(0, Math.min(1, x));
export const eo = Easing.bezier(0.16, 1, 0.3, 1);
export const eio = Easing.bezier(0.65, 0, 0.35, 1);
export const back = Easing.bezier(0.34, 1.56, 0.64, 1);
export const prog = (t: number, at: number, d = 0.4, e: (x: number) => number = eo) => e(clamp((t - at) / Math.max(d, 0.001)));
export const useT = () => useCurrentFrame() / FPS;
export const useSp = (at: number, damping = 13, mass = 0.8, stiffness = 150) => {
	const f = useCurrentFrame();
	return spring({frame: f - Math.round(at * FPS), fps: FPS, config: {damping, mass, stiffness}});
};
export const fa = (n: number | string) => String(n).replace(/[0-9]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[+d]);
/** boil: changes every 3 frames, for hand-drawn jitter */
export const useBoil = () => Math.floor(useCurrentFrame() / 3);

/* ---------------- the scene context: c('word', occurrence) = seconds (from the scene start) at which the word is heard ---------------- */
export type SP = {c: (w: string, occ?: number) => number; dur: number};
export const Ctx = React.createContext<SP>({c: () => 0, dur: 1});
export const useS = () => React.useContext(Ctx);

export const Abs: React.FC<{x: number; y: number; children?: React.ReactNode; style?: React.CSSProperties}> = ({x, y, children, style}) => (
	<div style={{position: 'absolute', left: x, top: y, transform: 'translate(-50%,-50%)', ...style}}>{children}</div>
);

/* ---------------- paper background ---------------- */
export const Paper: React.FC<{tex?: 'paper' | 'grid'; tint?: string; tintOp?: number}> = ({tex = 'paper', tint, tintOp = 1}) => (
	<AbsoluteFill>
		<Img src={staticFile(`img/${tex === 'grid' ? 'grid' : 'paper'}.jpg`)} style={{width: W, height: H}} />
		{tint && <AbsoluteFill style={{background: tint, mixBlendMode: 'multiply', opacity: tintOp}} />}
	</AbsoluteFill>
);

/* ---------------- entering element ---------------- */
type From = 'left' | 'right' | 'up' | 'down' | 'pop' | 'drop' | 'none';
export const Enter: React.FC<{at: number; from?: From; dist?: number; rot?: number; children?: React.ReactNode; x: number; y: number; z?: number; out?: number; boil?: boolean; d?: number}> = ({
	at,
	from = 'pop',
	dist = 1200,
	rot = 0,
	children,
	x,
	y,
	z,
	out,
	boil = true,
	d = 0.5,
}) => {
	const t = useT();
	const b = useBoil();
	const s = useSp(at, from === 'pop' ? 11 : 15, 0.8, from === 'pop' ? 170 : 120);
	const q = useSp(at, 10, 0.7, 200);
	if (t < at - 0.02) return null;
	const p = from === 'pop' ? s : prog(t, at, d, eo);
	let tx = 0,
		ty = 0,
		sc = 1,
		r = rot;
	if (from === 'left') tx = -(1 - p) * dist;
	if (from === 'right') tx = (1 - p) * dist;
	if (from === 'up') ty = -(1 - p) * dist;
	if (from === 'down') ty = (1 - p) * dist;
	if (from === 'pop') sc = interpolate(s, [0, 1], [0.2, 1]);
	if (from === 'drop') sc = interpolate(q, [0, 1], [1.6, 1]);
	if (from === 'left' || from === 'right') r = rot + (1 - p) * (from === 'left' ? -12 : 12);
	const jit = boil ? (random('b' + b + x) - 0.5) * 0.6 : 0;
	const o = out !== undefined ? 1 - prog(t, out, 0.25) : 1;
	const outY = out !== undefined ? prog(t, out, 0.35, eio) * 60 : 0;
	return (
		<div style={{position: 'absolute', left: x, top: y, transform: `translate(-50%,-50%) translate(${tx}px,${ty + outY}px) rotate(${r + jit}deg) scale(${sc})`, zIndex: z, opacity: Math.min(o, from === 'drop' ? prog(t, at, 0.08) : 1)}}>
			{children}
		</div>
	);
};

/** a cut-out picture (public/img/NAME.png, white paper border already in the file) */
export const Cut: React.FC<{src: string; w: number; shadow?: boolean; flip?: boolean}> = ({src, w, shadow = true, flip}) => (
	<Img src={staticFile('img/' + src)} style={{width: w, display: 'block', transform: flip ? 'scaleX(-1)' : undefined, filter: shadow ? 'drop-shadow(0 14px 18px rgba(40,30,15,0.28)) drop-shadow(0 2px 3px rgba(0,0,0,0.2))' : undefined}} />
);

export const Tape: React.FC<{w?: number; rot?: number; style?: React.CSSProperties}> = ({w = 170, rot = 0, style}) => (
	<div
		style={{
			position: 'absolute',
			width: w,
			height: 46,
			background: 'rgba(238,228,200,0.78)',
			transform: `rotate(${rot}deg)`,
			boxShadow: '0 2px 4px rgba(0,0,0,0.12)',
			clipPath: 'polygon(0% 8%, 4% 0%, 8% 10%, 12% 2%, 100% 0%, 96% 12%, 100% 24%, 97% 40%, 100% 58%, 96% 76%, 100% 92%, 94% 100%, 0% 100%, 4% 86%, 0% 70%, 3% 52%, 0% 34%, 4% 20%)',
			...style,
		}}
	/>
);

/** a printed photo (public/img/NAME.jpg) in a paper frame with two strips of tape */
export const Photo: React.FC<{src: string; w: number; tape?: boolean; border?: number; caption?: string}> = ({src, w, tape = true, border = 16, caption}) => (
	<div style={{position: 'relative', background: '#FBF8F1', padding: border, paddingBottom: caption ? border * 4 : border, boxShadow: '0 18px 30px rgba(40,30,15,0.28), 0 2px 4px rgba(0,0,0,0.15)'}}>
		<Img src={staticFile('img/' + src)} style={{width: w, display: 'block', filter: 'contrast(1.05)'}} />
		{caption && <div style={{position: 'absolute', bottom: border, left: 0, right: 0, textAlign: 'center', fontFamily: TW, fontSize: 30, color: INK}}>{caption}</div>}
		{tape && (
			<>
				<Tape w={180} rot={-38} style={{left: -50, top: -8}} />
				<Tape w={180} rot={-38} style={{right: -50, bottom: -8}} />
			</>
		)}
	</div>
);

export const Polaroid: React.FC<{children?: React.ReactNode; w?: number}> = ({children, w = 300}) => (
	<div style={{background: '#FBF8F1', padding: 14, paddingBottom: 54, width: w, boxShadow: '0 14px 22px rgba(40,30,15,0.3)'}}>
		<div style={{width: w, height: w * 0.8, background: '#DDD7CB', overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center'}}>{children}</div>
	</div>
);

/* ---------------- text ---------------- */
/** RTL-friendly wipe reveal for Persian (Persian letters join: never type them letter by letter) */
export const Wipe: React.FC<{at: number; children?: React.ReactNode; d?: number; style?: React.CSSProperties; dir?: 'rtl' | 'ltr'}> = ({at, children, d = 0.45, style, dir = 'rtl'}) => {
	const t = useT();
	const p = prog(t, at, d, eio);
	if (t < at) return null;
	const clip = dir === 'rtl' ? `inset(-20% 0 -20% ${(1 - p) * 100}%)` : `inset(-20% ${(1 - p) * 100}% -20% 0)`;
	return <div style={{clipPath: clip, whiteSpace: 'nowrap', ...style}}>{children}</div>;
};

/** typewriter for Latin text and numbers (Special Elite) with a blinking cursor */
export const Type: React.FC<{at: number; text: string; cps?: number; style?: React.CSSProperties; cursor?: boolean}> = ({at, text, cps = 18, style, cursor = true}) => {
	const t = useT();
	if (t < at) return null;
	const s = String(text ?? '');
	const n = Math.min(s.length, Math.floor((t - at) * cps) + 1);
	const done = n >= s.length;
	return (
		<div style={{fontFamily: TW, whiteSpace: 'pre', direction: 'ltr', ...style}}>
			{s.slice(0, n)}
			{cursor && <span style={{opacity: !done || Math.floor(t * 3) % 2 === 0 ? 1 : 0}}>▌</span>}
		</div>
	);
};

/** highlighter bar behind text, opening from the right */
export const Hl: React.FC<{at: number; color?: string; children?: React.ReactNode; d?: number; pad?: number}> = ({at, color = MUST, children, d = 0.35, pad = 12}) => {
	const t = useT();
	const p = prog(t, at, d, eio);
	return (
		<span style={{position: 'relative', display: 'inline-block'}}>
			<span style={{position: 'absolute', left: -pad, right: -pad, top: '38%', bottom: '2%', background: color, opacity: 0.85, transformOrigin: 'right', transform: `scaleX(${p}) skewX(-8deg)`, borderRadius: 4, zIndex: 0}} />
			<span style={{position: 'relative', zIndex: 1}}>{children}</span>
		</span>
	);
};

/** a line of text (Persian by default: Doran, rtl, never wraps) */
export const T: React.FC<{size?: number; weight?: number; color?: string; children?: React.ReactNode; font?: string; style?: React.CSSProperties}> = ({size = 80, weight = 800, color = INK, children, font = D, style}) => (
	<div style={{fontFamily: font, fontWeight: weight, fontSize: size, color, lineHeight: 1.15, direction: font === D ? 'rtl' : 'ltr', whiteSpace: 'nowrap', ...style}}>{children}</div>
);

/* ---------------- hand-drawn marks (boiling) ---------------- */
const jitterPath = (pts: [number, number][], seed: string, amp: number) => pts.map(([x, y], i) => [x + (random(seed + 'x' + i) - 0.5) * amp, y + (random(seed + 'y' + i) - 0.5) * amp] as [number, number]);
export const smooth = (pts: [number, number][]) => {
	if (!pts || pts.length < 2) return '';
	let d = `M${pts[0][0]},${pts[0][1]}`;
	for (let i = 1; i < pts.length - 1; i++) {
		const [x1, y1] = pts[i];
		const [x2, y2] = pts[i + 1];
		d += ` Q${x1},${y1} ${(x1 + x2) / 2},${(y1 + y2) / 2}`;
	}
	const l = pts[pts.length - 1];
	return d + ` L${l[0]},${l[1]}`;
};

/** an svg path that draws itself (use inside a full-frame <svg>) */
export const Marker: React.FC<{d: string; at: number; dur?: number; color?: string; width?: number; len?: number}> = ({d, at, dur = 0.45, color = RED, width = 9, len = 3000}) => {
	const t = useT();
	const p = prog(t, at, dur, eio);
	if (t < at) return null;
	return <path d={d} fill="none" stroke={color} strokeWidth={width} strokeLinecap="round" strokeLinejoin="round" strokeDasharray={len} strokeDashoffset={len * (1 - p)} />;
};

const Full: React.FC<{children?: React.ReactNode}> = ({children}) => (
	<svg width={W} height={H} style={{position: 'absolute', left: 0, top: 0, pointerEvents: 'none', overflow: 'visible'}}>
		{children}
	</svg>
);

/** a hand-drawn ellipse around something (2.15 turns, boiling) — frame coordinates */
export const CircleMark: React.FC<{cx: number; cy: number; rx: number; ry: number; at: number; color?: string; width?: number}> = ({cx, cy, rx, ry, at, color = RED, width = 9}) => {
	const b = useBoil();
	const pts: [number, number][] = [];
	for (let i = 0; i <= 26; i++) {
		const a = -Math.PI / 2 + (i / 24) * Math.PI * 2.15;
		const k = 1 + (i / 26) * 0.08;
		pts.push([cx + Math.cos(a) * rx * k, cy + Math.sin(a) * ry * k]);
	}
	return (
		<Full>
			<Marker d={smooth(jitterPath(pts, 'c' + b, 5))} at={at} color={color} width={width} len={4000} dur={0.5} />
		</Full>
	);
};

/** a wavy marker underline drawn right to left — frame coordinates */
export const Underline: React.FC<{x1: number; x2: number; y: number; at: number; color?: string; width?: number}> = ({x1, x2, y, at, color = RED, width = 10}) => {
	const b = useBoil();
	const pts: [number, number][] = [
		[x2, y],
		[(x1 + x2 * 2) / 3, y - 6],
		[(x1 * 2 + x2) / 3, y + 4],
		[x1, y - 3],
	];
	return (
		<Full>
			<Marker d={smooth(jitterPath(pts, 'u' + b, 4))} at={at} color={color} width={width} len={1600} dur={0.35} />
		</Full>
	);
};

/** a red marker cross (two strokes) — frame coordinates */
export const XMark: React.FC<{cx: number; cy: number; s?: number; at: number; color?: string}> = ({cx, cy, s = 60, at, color = RED}) => {
	const b = useBoil();
	const j = (k: string) => (random('x' + b + k) - 0.5) * 6;
	return (
		<Full>
			<Marker d={`M${cx - s + j('a')},${cy - s + j('b')} L${cx + s + j('c')},${cy + s + j('d')}`} at={at} color={color} width={12} len={400} dur={0.18} />
			<Marker d={`M${cx + s + j('e')},${cy - s + j('f')} L${cx - s + j('g')},${cy + s + j('h')}`} at={at + 0.12} color={color} width={12} len={400} dur={0.18} />
		</Full>
	);
};

/** a teal tick — frame coordinates */
export const CheckMark: React.FC<{cx: number; cy: number; s?: number; at: number; color?: string}> = ({cx, cy, s = 50, at, color = TEAL}) => {
	const b = useBoil();
	const j = (k: string) => (random('k' + b + k) - 0.5) * 5;
	return (
		<Full>
			<Marker d={`M${cx - s + j('a')},${cy + j('b')} L${cx - s * 0.2},${cy + s * 0.75} L${cx + s * 1.1 + j('c')},${cy - s * 0.9 + j('d')}`} at={at} color={color} width={13} len={500} dur={0.3} />
		</Full>
	);
};

/** a curved marker arrow through points; the head appears when it is drawn — frame coordinates */
export const Arrow: React.FC<{pts: [number, number][]; at: number; color?: string; width?: number; dur?: number}> = ({pts, at, color = INK, width = 7, dur = 0.5}) => {
	const b = useBoil();
	const t = useT();
	if (!pts || pts.length < 2) return null;
	const jp = jitterPath(pts, 'a' + b, 3);
	const d = smooth(jp);
	const p = prog(t, at, dur, eio);
	const [x2, y2] = jp[jp.length - 1];
	const [x1, y1] = jp[jp.length - 2];
	const a = Math.atan2(y2 - y1, x2 - x1);
	const hl = 30;
	return (
		<Full>
			<Marker d={d} at={at} color={color} width={width} len={3000} dur={dur} />
			{p > 0.95 && <path d={`M${x2 - hl * Math.cos(a - 0.45)},${y2 - hl * Math.sin(a - 0.45)} L${x2},${y2} L${x2 - hl * Math.cos(a + 0.45)},${y2 - hl * Math.sin(a + 0.45)}`} fill="none" stroke={color} strokeWidth={width} strokeLinecap="round" strokeLinejoin="round" />}
		</Full>
	);
};

/** a marker heart centred at (cx, cy), size s — frame coordinates */
export const HeartMark: React.FC<{cx: number; cy: number; s?: number; at: number; color?: string}> = ({cx, cy, s = 50, at, color = RED}) => {
	const k = s / 50;
	const d = `M${cx},${cy - 10 * k} C${cx},${cy - 40 * k} ${cx + 50 * k},${cy - 40 * k} ${cx + 50 * k},${cy} C${cx + 50 * k},${cy + 35 * k} ${cx},${cy + 60 * k} ${cx},${cy + 80 * k} C${cx},${cy + 60 * k} ${cx - 50 * k},${cy + 35 * k} ${cx - 50 * k},${cy} C${cx - 50 * k},${cy - 40 * k} ${cx},${cy - 40 * k} ${cx},${cy - 10 * k} Z`;
	return (
		<Full>
			<Marker d={d} at={at} color={color} width={9} len={800} dur={0.45} />
		</Full>
	);
};

/* ---------------- stamps / labels / numbers ---------------- */
/** a rubber stamp that slams down (Persian or Latin text) */
export const Stamp: React.FC<{at: number; children?: React.ReactNode; color?: string; rot?: number; size?: number; x: number; y: number}> = ({at, children, color = RED, rot = -10, size = 70, x, y}) => {
	const t = useT();
	const s = useSp(at, 9, 0.6, 260);
	if (t < at) return null;
	return (
		<div style={{position: 'absolute', left: x, top: y, transform: `translate(-50%,-50%) rotate(${rot}deg) scale(${interpolate(s, [0, 1], [2.2, 1])})`, opacity: prog(t, at, 0.06)}}>
			<div style={{fontFamily: D, fontWeight: 800, fontSize: size, color, border: `7px solid ${color}`, padding: `${size * 0.05}px ${size * 0.35}px ${size * 0.15}px`, borderRadius: 14, direction: 'rtl', whiteSpace: 'nowrap', mixBlendMode: 'multiply', maskImage: 'radial-gradient(circle at 30% 40%, black 60%, rgba(0,0,0,0.75) 100%)'}}>
				{children}
			</div>
		</div>
	);
};

/** a tilted paper label with a shadow */
export const Label: React.FC<{children?: React.ReactNode; bg?: string; color?: string; size?: number; rot?: number; font?: string}> = ({children, bg = '#FBF8F1', color = INK, size = 48, rot = -2, font = D}) => (
	<div style={{background: bg, color, fontFamily: font, fontWeight: font === D ? 700 : 400, fontSize: size, padding: `${size * 0.12}px ${size * 0.45}px ${size * 0.22}px`, transform: `rotate(${rot}deg)`, boxShadow: '0 8px 14px rgba(40,30,15,0.22)', whiteSpace: 'nowrap', direction: font === D ? 'rtl' : 'ltr', display: 'inline-block'}}>{children}</div>
);

/** a counting number in Anton with thousands separators (prefix '$', suffix '%' ...) */
export const Counter: React.FC<{at: number; dur: number; to: number; from?: number; prefix?: string; suffix?: string; decimals?: number; style?: React.CSSProperties}> = ({at, dur, to, from = 0, prefix = '', suffix = '', decimals = 0, style}) => {
	const t = useT();
	if (t < at) return null;
	const p = prog(t, at, Math.max(0.2, dur), Easing.bezier(0.3, 0, 0.2, 1));
	const v = from + (to - from) * p;
	const text = v.toLocaleString('en-US', {minimumFractionDigits: decimals, maximumFractionDigits: decimals});
	return <div style={{fontFamily: ANTON, direction: 'ltr', whiteSpace: 'nowrap', ...style}}>{prefix}{text}{suffix}</div>;
};

/** a big flat accent disc (multiply) behind pictures; `half` = the top half only */
export const Disc: React.FC<{x: number; y: number; r: number; color: string; at: number; half?: boolean; rot?: number}> = ({x, y, r, color, at, half, rot = 0}) => {
	const s = useSp(at, 16, 1, 110);
	return (
		<div style={{position: 'absolute', left: x - r, top: y - r, width: 2 * r, height: 2 * r, borderRadius: '50%', background: color, transform: `scale(${s}) rotate(${rot}deg)`, clipPath: half ? 'inset(0 0 50% 0)' : undefined, mixBlendMode: 'multiply'}} />
	);
};

/** a torn paper strip (children are laid on it) */
export const Torn: React.FC<{w: number; h: number; color?: string; seed?: string; children?: React.ReactNode; style?: React.CSSProperties}> = ({w, h, color = '#FBF8F1', seed = 't', children, style}) => {
	const n = 24;
	const top = Array.from({length: n + 1}).map((_, i) => `${(i / n) * 100}% ${random(seed + 'a' + i) * 6}%`);
	const bot = Array.from({length: n + 1}).map((_, i) => `${100 - (i / n) * 100}% ${94 + random(seed + 'b' + i) * 6}%`);
	return (
		<div style={{position: 'relative', width: w, height: h, filter: 'drop-shadow(0 10px 14px rgba(40,30,15,0.25))', ...style}}>
			<div style={{position: 'absolute', inset: 0, background: color, clipPath: `polygon(${[...top, ...bot].join(',')})`}} />
			<div style={{position: 'absolute', inset: 0}}>{children}</div>
		</div>
	);
};

/** a white camera flash */
export const Flash: React.FC<{at: number; d?: number}> = ({at, d = 0.25}) => {
	const t = useT();
	const k = t < at ? 0 : Math.max(0, 1 - (t - at) / d);
	return k > 0 ? <AbsoluteFill style={{background: '#fff', opacity: k}} /> : null;
};

/* ---------------- data ---------------- */
/** a map pin that drops in (its tip is the bottom centre of a 60x90 box) */
export const Pin: React.FC<{at: number; color?: string}> = ({at, color = RED}) => {
	const t = useT();
	const s = useSp(at, 9, 0.6, 220);
	if (t < at) return null;
	return (
		<svg width={60} height={90} viewBox="0 0 60 90" style={{transform: `translateY(${(1 - s) * -80}px)`, transformOrigin: '50% 100%', overflow: 'visible'}}>
			<path d="M30,88 C30,88 4,52 4,30 A26,26 0 1,1 56,30 C56,52 30,88 30,88 Z" fill={color} stroke={INK} strokeWidth={3} />
			<circle cx={30} cy={30} r={10} fill={CREAM} />
		</svg>
	);
};

export type Slice = {v: number; color?: string; label?: string};
/** a pie drawn by its outline, then its slices; slice `pull` slides out along its middle. Centre of an 800x800 svg (r <= 330). */
export const Pie: React.FC<{slices: Slice[]; p: number; pull?: number; pullP?: number; r?: number; labelSize?: number}> = ({slices = [], p = 1, pull = -1, pullP = 0, r = 300, labelSize = 80}) => {
	const C = 2 * Math.PI * r;
	const total = (slices ?? []).reduce((s, x) => s + Math.max(0, x.v || 0), 0) || 1;
	let a = -Math.PI / 2;
	return (
		<svg width={800} height={800} viewBox="-400 -400 800 800" style={{overflow: 'visible'}}>
			<circle r={r} fill={CREAM} stroke={INK} strokeWidth={8} strokeDasharray={C} strokeDashoffset={C * (1 - clamp(p))} />
			{(slices ?? []).map((sl, i) => {
				const a0 = a;
				const a1 = a + (Math.max(0, sl.v || 0) / total) * Math.PI * 2;
				a = a1;
				const mid = (a0 + a1) / 2;
				const off = i === pull ? pullP * 110 : 0;
				const large = a1 - a0 > Math.PI ? 1 : 0;
				const show = clamp((p - 0.85) / 0.15);
				return (
					<g key={i} transform={`translate(${Math.cos(mid) * off},${Math.sin(mid) * off})`} opacity={show}>
						<path d={`M0,0 L${Math.cos(a0) * r},${Math.sin(a0) * r} A${r},${r} 0 ${large},1 ${Math.cos(a1) * r},${Math.sin(a1) * r} Z`} fill={sl.color || CREAM} stroke={INK} strokeWidth={8} />
						{sl.label ? (
							<text x={Math.cos(mid) * r * 0.58} y={Math.sin(mid) * r * 0.58 + labelSize * 0.33} textAnchor="middle" fontFamily={ANTON} fontSize={labelSize} fill={sl.color && sl.color !== CREAM ? CREAM : INK}>
								{sl.label}
							</text>
						) : null}
					</g>
				);
			})}
		</svg>
	);
};

/** a line chart that draws itself point to point (p 0..1) inside the box x,y,w,h (frame coordinates); log = log10 scale. Labels in Anton above points. */
export const LineChart: React.FC<{pts: [number, number, string?][]; p: number; x: number; y: number; w: number; h: number; log?: boolean; color?: string; ticks?: number[]; tickFmt?: (v: number) => string}> = ({pts = [], p = 1, x, y, w, h, log, color = RED, ticks = [], tickFmt}) => {
	const list = pts ?? [];
	if (list.length < 2) return null;
	const xs = list.map((q) => q[0]);
	const vs = list.map((q) => (log ? Math.log10(Math.max(q[1], 1e-9)) : q[1]));
	const x0 = Math.min(...xs), x1 = Math.max(...xs);
	const v0 = Math.min(0, ...vs), v1 = Math.max(...vs);
	const X = (v: number) => x + ((v - x0) / Math.max(x1 - x0, 1e-9)) * w;
	const Y = (v: number) => y + h - ((v - v0) / Math.max(v1 - v0, 1e-9)) * h;
	const n = list.length;
	const seg = clamp(p) * (n - 1);
	const shown: [number, number][] = list.slice(0, Math.floor(seg) + 1).map((q, i) => [X(q[0]), Y(vs[i])]);
	if (seg < n - 1) {
		const i = Math.floor(seg);
		const f = seg - i;
		shown.push([X(list[i][0]) + (X(list[i + 1][0]) - X(list[i][0])) * f, Y(vs[i]) + (Y(vs[i + 1]) - Y(vs[i])) * f]);
	}
	const d = shown.map((q, i) => `${i ? 'L' : 'M'}${q[0]},${q[1]}`).join(' ');
	return (
		<Full>
			<line x1={x} y1={y + h} x2={x + w} y2={y + h} stroke={INK} strokeWidth={4} />
			<line x1={x} y1={y + h} x2={x} y2={y - 20} stroke={INK} strokeWidth={4} />
			{(ticks ?? []).map((tv) => (
				<text key={tv} x={X(tv)} y={y + h + 60} textAnchor="middle" fontFamily={TW} fontSize={36} fill={INK}>
					{tickFmt ? tickFmt(tv) : String(tv)}
				</text>
			))}
			<path d={d} fill="none" stroke={color} strokeWidth={10} strokeLinecap="round" strokeLinejoin="round" />
			{list.map((q, i) =>
				i <= seg + 0.01 ? (
					<g key={i}>
						<circle cx={X(q[0])} cy={Y(vs[i])} r={12} fill={i === n - 1 ? color : INK} />
						{q[2] ? (
							<text x={X(q[0]) + (i === n - 1 ? -20 : 20)} y={Y(vs[i]) - 28} textAnchor={i === n - 1 ? 'end' : 'start'} fontFamily={ANTON} fontSize={i === n - 1 ? 80 : 50} fill={INK}>
								{q[2]}
							</text>
						) : null}
					</g>
				) : null,
			)}
		</Full>
	);
};

/** a bar chart growing from the baseline (frame coordinates); bars: [label, value, color?] */
export const Bars: React.FC<{bars: [string, number, string?][]; p: number; x: number; y: number; w: number; h: number; fmt?: (v: number) => string}> = ({bars = [], p = 1, x, y, w, h, fmt}) => {
	const list = bars ?? [];
	if (!list.length) return null;
	const max = Math.max(...list.map((b) => b[1]), 1e-9);
	const bw = (w / list.length) * 0.62;
	return (
		<Full>
			<line x1={x} y1={y + h} x2={x + w} y2={y + h} stroke={INK} strokeWidth={4} />
			{list.map(([label, v, color], i) => {
				const k = clamp(p * list.length - i);
				const bh = (v / max) * h * eo(k);
				const cx = x + (w / list.length) * (i + 0.5);
				return (
					<g key={i}>
						<rect x={cx - bw / 2} y={y + h - bh} width={bw} height={bh} fill={color || TEAL} stroke={INK} strokeWidth={4} />
						{k > 0.9 ? (
							<text x={cx} y={y + h - bh - 22} textAnchor="middle" fontFamily={ANTON} fontSize={52} fill={INK}>
								{fmt ? fmt(v) : String(v)}
							</text>
						) : null}
						<text x={cx} y={y + h + 56} textAnchor="middle" fontFamily={D} fontWeight={700} fontSize={40} fill={INK} style={{direction: 'rtl'}}>
							{label}
						</text>
					</g>
				);
			})}
		</Full>
	);
};

/** the contiguous USA (Albers-like flat projection). Width w; `fill` colours states by name ('Kentucky': TEAL) once fillAt has passed. */
export const USMap: React.FC<{at: number; w: number; fill?: Record<string, string>; fillAt?: number}> = ({at, w, fill = {}, fillAt}) => {
	const t = useT();
	const k = w / usmap.w;
	const p = prog(t, at, 0.8, eio);
	const f = prog(t, fillAt ?? at + 0.6, 0.4);
	const paths = usmap.paths as Record<string, string>;
	return (
		<svg width={w} height={usmap.h * k} viewBox={`0 0 ${usmap.w} ${usmap.h}`} style={{overflow: 'visible', filter: 'drop-shadow(0 10px 14px rgba(40,30,15,0.25))'}}>
			{Object.entries(paths).map(([n, d], i) => (
				<path key={n} d={d} fill="#FBF8F1" stroke={INK} strokeWidth={1.4} opacity={clamp(p * 1.6 - (i / 50) * 0.6)} />
			))}
			{Object.entries(fill ?? {}).map(([n, color]) =>
				paths[n] ? <path key={'f' + n} d={paths[n]} fill={color} stroke={INK} strokeWidth={1.4} opacity={f} /> : null,
			)}
		</svg>
	);
};
/** where (lon, lat) falls on a USMap of width w: [x, y] relative to the map's top-left */
export const usPoint = (lon: number, lat: number, w: number): [number, number] => {
	const k0 = 19.0;
	const c = Math.cos((38 * Math.PI) / 180);
	const k = w / usmap.w;
	return [(lon + 125) * c * k0 * k, (50 - lat) * k0 * k];
};
