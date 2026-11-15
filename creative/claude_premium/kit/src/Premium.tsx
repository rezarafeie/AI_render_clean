import React from 'react';
import {AbsoluteFill, Easing, OffthreadVideo, Sequence, continueRender, delayRender, interpolate, spring, staticFile, useCurrentFrame} from 'remotion';
import data from './data.json';
import {CAP_Y, CREAM, D, FACE_TARGET_Y, FPS, GOLD, H, P, SERIF, SRC_H, SRC_W, STYLE, W, BASE_Z, behindGlow, behindStyle, behindSub, clamp, eio, eo, fa, fit, goldText, prog} from './tokens';
import {Glass, Icon} from './gfx';
import {GRAPHICS as WRITTEN} from './graphics';

/* The fixed engine of the premium full-frame talking edit («تدوین صحبتی پریمیوم»): ONE full 1080x1920 frame, a virtual camera on the speaker,
   two-tier motion captions, glass cards, text that passes BEHIND the speaker, a graded look. Everything per video comes from data.json
   (the plan's moments); nothing here is written per video. Time is OUTPUT time, hooked to spoken words by the planner. */

type Word = {t: string; s: number; key: boolean};
type Cap = {s: number; e: number; words: Word[]; hide: boolean; big: boolean};
type Behind = {s: number; e: number; kind: 'word' | 'latin' | 'stepped'; kicker?: string; word: string; sphere?: boolean; repeat?: {t: string; at: number}[]; strike?: number; crop: {x: number; w: number}; seg: string | null; top?: number | null};
type CardT = {s: number; e: number; number?: string; icon?: string; latin?: string; sub?: string; title: string; arrow?: boolean; dots?: number; glow?: boolean};
type Topic = {s: number; e: number; title: string; icon: string};
type Zoom = {s: number; e: number; amount: number; ramp?: number};
const D_ = data as any;
const caps = D_.caps as Cap[];
const behinds = (D_.behind ?? []) as Behind[];
const cards = (D_.cards ?? []) as CardT[];
const topics = (D_.topics ?? []) as Topic[];
const zooms = (D_.zooms ?? []) as Zoom[];
const cuts = D_.cuts as number[];
const events = (D_.events ?? []) as number[];
const end = D_.end as {s: number; name: string; tag: string} | null;
const TOTAL = D_.total as number;
const props = (D_.props ?? []) as {s: number; e: number; name: string; zone: string}[];
const GRAPHICS = WRITTEN as Record<string, React.FC<any>>;
const KW = D_.kw as Record<string, number>;
const FACE_H = (D_.faceH as number) ?? SRC_H * 0.18;
const S0 = Math.max(W / SRC_W, H / SRC_H);
const CAPY = Math.max(1040, Math.min(1250, FACE_TARGET_Y + FACE_H * S0 * 0.62 + 120));

const useTime = () => useCurrentFrame() / FPS;
const useSpAt = (at: number, damping = 14, mass = 0.8, stiffness = 140) => {
	const f = useCurrentFrame();
	return spring({frame: f - Math.round(at * FPS), fps: FPS, config: {damping, mass, stiffness}});
};

/* ========== font faces ========== */
const face = (weight: number, file: string) => `@font-face{font-family:'Playfair Display';font-weight:${weight};font-style:italic;font-display:block;src:url('${staticFile('fonts/' + file)}') format('woff2');}`;
const Fonts: React.FC = () => (
	<style>
		{[`@font-face{font-family:'Doran';src:url('${staticFile('fonts/doran.ttf')}') format('truetype');font-weight:100 900;font-display:block;}`, face(800, 'playfair-display-latin-800-italic.woff2'), face(900, 'playfair-display-latin-900-italic.woff2')].join('\n')}
	</style>
);

/* ========== section transitions ========== */
const evAmt = (t: number, d = 0.28) => {
	let m = 0;
	for (const e of events) {
		const x = (t - e) / d;
		if (x >= -0.5 && x <= 1) m = Math.max(m, x < 0 ? 1 + x * 2 : 1 - x);
	}
	return clamp(m);
};

/* ========== camera ========== */
const faceX = (t: number) => {
	const face = D_.face as number[];
	if (!face.length) return SRC_W / 2;
	const i = t / D_.faceStep;
	const a = Math.max(0, Math.min(face.length - 1, Math.floor(i)));
	const b = Math.min(face.length - 1, a + 1);
	return face[a] + (face[b] - face[a]) * (i - a);
};
const emphasisAt = (t: number) => {
	let m = 1;
	for (const e of zooms) {
		const ramp = e.ramp ?? 0.5;
		m *= 1 + e.amount * prog(t, e.s - 0.1, ramp, eio) * (1 - prog(t, e.e - 0.2, 0.4, eio));
	}
	return m;
};
const zoomAt = (t: number) => {
	const seg = cuts.filter((c) => c <= t).length;
	return BASE_Z[seg % BASE_Z.length] * emphasisAt(t) * (1 + 0.006 * (t % 6));
};
const camAt = (t: number) => {
	const base = Math.max(W / SRC_W, H / SRC_H);
	const S = base * zoomAt(t);
	const cx = faceX(t) + ((D_.faceDx as number) ?? 0);
	// a push-in lifts the head toward the top edge: the face target sinks a little with the emphasis so the head keeps room for the text passing behind it
	const target = FACE_TARGET_Y + (emphasisAt(t) - 1) * 700;
	const tx = Math.min(0, Math.max(W - SRC_W * S, W / 2 - cx * S));
	const ty = Math.min(0, Math.max(H - SRC_H * S, target - (D_.faceY as number) * S));
	return {S, tx, ty};
};
/** where the speaker's head is on screen at time t (from the camera and the tracked face): graphics are placed against it, never on it */
const headAt = (t: number) => {
	const c = camAt(t);
	const fh = FACE_H * c.S;
	const cy = c.ty + (D_.faceY as number) * c.S;
	const cx = c.tx + faceX(t) * c.S;
	return {fh, cy, cx, top: cy - fh * 0.95, chin: cy + fh * 0.62, half: fh * 0.66};
};
type Rect = {x: number; y: number; w: number; h: number};
const zoneRect = (zone: string, t: number): Rect => {
	const h = headAt(t);
	if (zone === 'top') return {x: 70, y: 70, w: 940, h: Math.max(0, h.top - 40 - 70)};
	if (zone === 'left') return {x: 24, y: Math.max(70, h.cy - h.fh * 1.0), w: Math.max(0, h.cx - h.half - 48), h: 560};
	if (zone === 'right') {
		const x = h.cx + h.half + 24;
		return {x, y: Math.max(70, h.cy - h.fh * 1.0), w: Math.max(0, W - 24 - x), h: 560};
	}
	const y = CAPY + 190;
	return {x: 60, y, w: 960, h: Math.max(0, Math.min(500, 1850 - y))};   // lower: under the captions, over the lap
};
const usable = (r: Rect) => r.w >= 200 && r.h >= 150;

const Cam: React.FC = () => {
	const t = useTime();
	const {S, tx, ty} = camAt(t);
	return <OffthreadVideo src={staticFile('graded.mp4')} muted style={{position: 'absolute', left: tx, top: ty, width: SRC_W * S, height: SRC_H * S, maxWidth: 'none'}} />;
};
/** the speaker cut out (alpha webm), locked to the camera while a text passes behind */
const FG: React.FC<{b: Behind}> = ({b}) => {
	const f = useCurrentFrame();
	const t = b.s + f / FPS;
	const {S, tx, ty} = camAt(t);
	return <OffthreadVideo src={staticFile(b.seg as string)} transparent muted style={{position: 'absolute', left: tx + b.crop.x * S, top: ty, width: b.crop.w * S, height: SRC_H * S, maxWidth: 'none'}} />;
};

/* ========== look: vignette, light leaks, grade, grain ========== */
const Look: React.FC = () => {
	const f = useCurrentFrame();
	const t = f / FPS;
	const burst = evAmt(t, 0.6);
	const a = 0.18 + 0.35 * burst;
	return (
		<>
			<AbsoluteFill style={{background: `radial-gradient(ellipse 75% 60% at 50% 42%, rgba(0,0,0,0) 50%, rgba(${P.vig},0.45) 100%)`}} />
			{STYLE.leaks !== false && (
				<AbsoluteFill style={{mixBlendMode: 'screen', opacity: a}}>
					<div style={{position: 'absolute', left: -300 + Math.sin(t * 0.4) * 120, top: -200 + Math.cos(t * 0.3) * 100, width: 900, height: 900, borderRadius: '50%', background: `radial-gradient(circle, rgba(${P.leak1},0.9), rgba(${P.leak1},0) 65%)`, filter: 'blur(30px)'}} />
					<div style={{position: 'absolute', right: -350 + Math.cos(t * 0.5) * 120, bottom: 200 + Math.sin(t * 0.35) * 160, width: 1000, height: 1000, borderRadius: '50%', background: `radial-gradient(circle, rgba(${P.leak2},0.8), rgba(${P.leak2},0) 65%)`, filter: 'blur(40px)'}} />
				</AbsoluteFill>
			)}
			<AbsoluteFill style={{background: 'linear-gradient(180deg, rgba(0,0,0,0.12) 0%, rgba(0,0,0,0) 15%, rgba(0,0,0,0) 55%, rgba(0,0,0,0.45) 100%)'}} />
			{STYLE.grain !== false && (
				<svg width={W} height={H} style={{position: 'absolute', opacity: 0.08, mixBlendMode: 'overlay'}}>
					<filter id="gr">
						<feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves={2} seed={f % 10} />
					</filter>
					<rect width={W} height={H} filter="url(#gr)" />
				</svg>
			)}
		</>
	);
};

/* ========== text behind the speaker ========== */
const Rise: React.FC<{at: number; children: React.ReactNode; d?: number; y?: number; style?: React.CSSProperties}> = ({at, children, d = 0.5, y = 80, style}) => {
	const t = useTime();
	const p = prog(t, at, d);
	return <div style={{opacity: p, transform: `translateY(${(1 - p) * y}px) scale(${0.92 + 0.08 * p})`, filter: `blur(${(1 - p) * 16}px)`, ...style}}>{children}</div>;
};

const Sphere: React.FC<{t: number}> = ({t}) => (
	<svg width={900} height={900} style={{position: 'absolute', top: -150, opacity: 0.22 * prog(t, 0, 0.5)}}>
		<g transform={`translate(450,450) rotate(${t * 18})`} fill="none" stroke={behindSub} strokeWidth={2.5}>
			<circle r={400} />
			{[-0.7, -0.35, 0, 0.35, 0.7].map((y, i) => (
				<ellipse key={i} rx={400 * Math.sqrt(1 - y * y)} ry={26} cy={y * 400} />
			))}
			{[0.3, 0.62, 0.9].map((x, i) => (
				<ellipse key={'m' + i} rx={400 * x} ry={400} />
			))}
		</g>
	</svg>
);

/** where a behind-text sits against the head, or {ok: false} when the head leaves no room above it (then there is no behind-text: a hidden word is never shown) */
const behindLayout = (b: Behind) => {
	const latin = b.kind === 'latin';
	let size = latin ? fit(210, b.word.length, 1000, 0.62) : fit(b.kind === 'stepped' ? 300 : 225, b.word.length, 980, 0.6);
	const lh = latin ? 1.0 : b.kind === 'stepped' ? 0.95 : 1.05;
	const extra = b.kind === 'stepped' ? 105 : b.kicker ? 64 : 0;
	const headTop = b.top != null
		? Math.min(...[b.s, b.s + (b.e - b.s) / 2, b.e - 0.3].map((t) => {
			const c = camAt(t);
			return c.ty + (b.top as number) * c.S;
		}))
		: headAt(b.s + (b.e - b.s) / 2).top;
	const room = Math.min(1, (headTop - 70) / ((extra + size * lh) * 0.8));       // ~80% of the block above the head, the rest passes behind it
	size = Math.floor(size * Math.max(0.5, room));
	const blockH = extra * Math.max(0.5, room) + size * lh;
	return {ok: b.seg != null && room >= 0.55, size, blockH, top: Math.max(70, Math.min(headTop - blockH * 0.8, 520))};
};

const BehindText: React.FC<{b: Behind}> = ({b}) => {
	const f = useCurrentFrame();
	const t = f / FPS; // local
	const dur = b.e - b.s;
	const out = 1 - prog(t, dur - 0.25, 0.25);
	const wrap: React.CSSProperties = {position: 'absolute', left: 0, width: W, display: 'flex', flexDirection: 'column', alignItems: 'center', opacity: out};
	const latin = b.kind === 'latin';
	const slamAt = b.kind === 'stepped' ? (b.strike ?? 1.15) : 0.15;
	const s = useSpAt(b.s + slamAt, b.kind === 'stepped' ? 12 : 14, b.kind === 'stepped' ? 0.8 : 1, b.kind === 'stepped' ? 180 : 140);
	const L = behindLayout(b);
	const size = L.size;
	const top = L.top;
	if (!L.ok) return null;
	return (
		<div style={{...wrap, top}}>
			{b.sphere && <Sphere t={t} />}
			{b.kind === 'stepped' && (
				<div style={{display: 'flex', gap: 30, direction: 'rtl'}}>
					{(b.repeat ?? []).map((r, i) => (
						<Rise key={i} at={r.at} y={40}>
							<div style={{fontFamily: D, fontWeight: 300, fontSize: 86, color: behindSub}}>{r.t}</div>
						</Rise>
					))}
				</div>
			)}
			{b.kind !== 'stepped' && b.kicker && (
				<Rise at={latin ? 0.05 : 0.02} y={30}>
					<div style={{fontFamily: D, fontWeight: 500, fontSize: fit(54, b.kicker.length, 900, 0.5), color: behindSub, direction: 'rtl', letterSpacing: 2}}>{b.kicker}</div>
				</Rise>
			)}
			{latin ? (
				<div style={{display: 'flex', direction: 'ltr', marginTop: -10}}>
					{b.word.split('').map((c, i) => {
						const p = prog(t, 0.12 + i * 0.05, 0.5);
						return (
							<span key={i} style={{fontFamily: SERIF, fontStyle: 'italic', fontWeight: 900, fontSize: size, lineHeight: 1, ...behindStyle, display: 'inline-block', opacity: p, transform: `translateY(${(1 - p) * 120}px)`, filter: behindGlow}}>
								{c}
							</span>
						);
					})}
				</div>
			) : b.kind === 'stepped' ? (
				<div style={{fontFamily: D, fontWeight: 800, fontSize: size, lineHeight: 0.95, ...behindStyle, direction: 'rtl', transform: `scale(${interpolate(s, [0, 1], [1.6, 1])})`, opacity: prog(t, slamAt, 0.15), filter: behindGlow}}>{b.word}</div>
			) : (
				<div style={{fontFamily: D, fontWeight: 800, fontSize: size, lineHeight: 1.05, ...behindStyle, direction: 'rtl', whiteSpace: 'nowrap', transform: `scale(${interpolate(s, [0, 1], [1.35, 1]) * (1 + 0.03 * t)})`, opacity: prog(t, 0.1, 0.25), filter: `blur(${(1 - prog(t, 0.1, 0.35)) * 20}px) ${behindGlow}`}}>{b.word}</div>
			)}
		</div>
	);
};

/* ========== glass cards ========== */
const InOut: React.FC<{s: number; e: number; children: React.ReactNode; y?: number}> = ({s, e, children, y = -60}) => {
	const t = useTime();
	const pin = useSpAt(s, 15, 0.8);
	const po = prog(t, e - 0.22, 0.22, eio);
	if (t < s - 0.05 || t > e + 0.05) return null;
	return (
		<div style={{opacity: Math.min(prog(t, s, 0.15), 1 - po), transform: `translateY(${(1 - pin) * y + po * -30}px) scale(${0.9 + 0.1 * pin})`, filter: po > 0 ? `blur(${po * 12}px)` : undefined}}>{children}</div>
	);
};

const InfoCard: React.FC<{c: CardT}> = ({c}) => {
	const t = useTime();
	const hasNum = !!c.number;
	const titleSize = fit(60, c.title.length, 640, 0.5);
	return (
		<InOut s={c.s} e={c.e}>
			<Glass style={{display: 'flex', alignItems: 'center', gap: 30, padding: '22px 46px 26px', direction: 'rtl', maxWidth: 960}}>
				{hasNum && <div style={{fontFamily: D, fontWeight: 800, fontSize: 112, lineHeight: 1, ...goldText}}>{fa(c.number as string)}</div>}
				{hasNum && c.icon === undefined && <div style={{width: 2, height: 100, background: P.rule}} />}
				{!hasNum && c.icon && (
					<div style={{filter: c.glow ? `drop-shadow(0 0 ${14 + 8 * Math.sin(t * 6)}px rgba(${P.leak2},0.9))` : undefined}}>
						<Icon k={c.icon} s={c.sub ? 90 : 74} />
					</div>
				)}
				<div>
					{c.latin && <div style={{fontFamily: SERIF, fontStyle: 'italic', fontWeight: 800, fontSize: 38, color: GOLD, direction: 'ltr', letterSpacing: 3}}>{c.latin}</div>}
					{c.sub && <div style={{fontFamily: D, fontWeight: 500, fontSize: 40, color: 'rgba(247,238,223,0.8)'}}>{c.sub}</div>}
					<div style={{fontFamily: D, fontWeight: 800, fontSize: titleSize, color: CREAM}}>{c.title}</div>
					{!!c.dots && (
						<div style={{display: 'flex', gap: 12, marginTop: 8}}>
							{Array.from({length: c.dots}).map((_, i) => (
								<div key={i} style={{width: 18, height: 18, borderRadius: 9, background: GOLD, opacity: prog(t, c.s + 0.5 + i * 0.12, 0.3) * 0.8}} />
							))}
						</div>
					)}
				</div>
				{c.arrow && (
					<div style={{transform: `translateX(${Math.sin(t * 6) * 8}px)`}}>
						<Icon k="arrow" s={70} />
					</div>
				)}
			</Glass>
		</InOut>
	);
};

const TopicCard: React.FC<{i: number}> = ({i}) => {
	const t = useTime();
	const tp = topics[i];
	const p = useSpAt(tp.s, 15, 0.8);
	const first = i === 0;
	const last = i === topics.length - 1;
	const out = last ? prog(t, tp.e - 0.22, 0.22, eio) : 0;
	const enter = first ? prog(t, tp.s, 0.3) : 1;
	return (
		<div style={{opacity: enter * (1 - out), transform: `translateY(${first ? (1 - p) * -60 : 0}px)`, filter: out > 0 ? `blur(${out * 12}px)` : undefined}}>
			<Glass style={{width: 900, padding: '26px 40px 30px', direction: 'rtl', position: 'relative', overflow: 'hidden'}}>
				<div style={{display: 'flex', alignItems: 'center', gap: 28, transform: `translateX(${(1 - p) * -120}px)`, opacity: prog(t, tp.s, 0.2)}}>
					<div style={{fontFamily: D, fontWeight: 800, fontSize: 104, lineHeight: 1, ...goldText, minWidth: 120, textAlign: 'center'}}>{fa(String(i + 1).padStart(2, '0'))}</div>
					<div style={{width: 96, height: 96, borderRadius: 48, border: `2px solid ${P.glassBorder}`, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(255,255,255,0.06)'}}>
						<Icon k={tp.icon} s={62} />
					</div>
					<div style={{fontFamily: D, fontWeight: 700, fontSize: fit(46, tp.title.length, 560, 0.5), color: CREAM, flex: 1, lineHeight: 1.3, whiteSpace: 'nowrap'}}>{tp.title}</div>
				</div>
				<div style={{display: 'flex', gap: 10, marginTop: 18, justifyContent: 'flex-start'}}>
					{topics.map((_, j) => (
						<div key={j} style={{height: 8, flex: j === i ? 3 : 1, borderRadius: 4, background: j <= i ? GOLD : 'rgba(255,255,255,0.2)'}} />
					))}
				</div>
			</Glass>
		</div>
	);
};

const Graphics: React.FC = () => {
	const t = useTime();
	const ti = topics.findIndex((x) => t >= x.s && t < x.e);
	return (
		<>
			{cards.map((c, i) => (
				<div key={i} style={{position: 'absolute', top: 150, width: W, display: 'flex', justifyContent: 'center'}}>
					<InfoCard c={c} />
				</div>
			))}
			{ti >= 0 && (
				<div style={{position: 'absolute', top: 140, width: W, display: 'flex', justifyContent: 'center'}}>
					<TopicCard i={ti} />
				</div>
			)}
			{end && (
				<div style={{position: 'absolute', top: 1580, width: W, display: 'flex', justifyContent: 'center'}}>
					<InOut s={end.s} e={TOTAL + 1} y={40}>
						<div style={{display: 'flex', alignItems: 'center', gap: 18, direction: 'rtl'}}>
							<div style={{fontFamily: D, fontWeight: 800, fontSize: fit(56, end.name.length, 460, 0.55), ...goldText}}>{end.name}</div>
							{end.tag && <div style={{width: 2, height: 50, background: P.rule}} />}
							{end.tag && <div style={{fontFamily: D, fontWeight: 500, fontSize: fit(44, end.tag.length, 360, 0.5), color: CREAM}}>{end.tag}</div>}
						</div>
					</InOut>
				</div>
			)}
		</>
	);
};

/* ========== captions: two-tier (small + big key word) or a karaoke glass pill ========== */
const Caption: React.FC<{c: Cap}> = ({c}) => {
	const t = useTime();
	const out = prog(t, c.e - 0.16, 0.16, eio);
	const pin = useSpAt(c.s, 15, 0.7);
	const keys = c.words.filter((w) => w.key);
	const small = c.words.filter((w) => !w.key);
	const Word: React.FC<{w: Word; size: number; weight: number; gold?: boolean}> = ({w, size, weight, gold}) => {
		const p = prog(t, w.s - 0.06, 0.32);
		const clip = gold ? `inset(0 0 0 ${(1 - prog(t, w.s - 0.06, 0.4, eio)) * 100}%)` : undefined;
		return (
			<span style={{fontFamily: D, fontWeight: weight, fontSize: size, lineHeight: 1.15, display: 'inline-block', whiteSpace: 'nowrap', opacity: gold ? (t >= w.s - 0.06 ? 1 : 0) : p, transform: `translateY(${(1 - p) * 28}px)`, filter: gold ? 'drop-shadow(0 8px 24px rgba(0,0,0,0.55))' : `blur(${(1 - p) * 8}px)`, textShadow: gold ? undefined : '0 4px 18px rgba(0,0,0,0.7), 0 0 2px rgba(0,0,0,0.6)', clipPath: clip, ...(gold ? goldText : {color: CREAM})}}>{w.t}</span>
		);
	};
	if (c.big && keys.length) {
		const chars = keys.reduce((n, w) => n + w.t.length, 0) + keys.length * 2;
		const keySize = Math.min(keys.length > 1 || keys[0].t.length > 8 ? 118 : 140, fit(140, chars, 980, 0.62));
		const smallChars = small.reduce((n, w) => n + w.t.length, 0) + small.length * 2;
		const smallSize = Math.min(58, fit(58, smallChars, 980, 0.5));
		const ul = prog(t, keys[0].s + 0.1, 0.5, eio);
		return (
			<div style={{position: 'absolute', left: 0, width: W, top: CAPY, display: 'flex', flexDirection: 'column', alignItems: 'center', direction: 'rtl', opacity: 1 - out, transform: `translateY(${-out * 30}px)`, filter: out > 0 ? `blur(${out * 10}px)` : undefined}}>
				{small.length > 0 && (
					<div style={{display: 'flex', gap: 16, direction: 'rtl'}}>
						{small.map((w, i) => (
							<Word key={i} w={w} size={smallSize} weight={500} />
						))}
					</div>
				)}
				<div style={{display: 'flex', gap: 26, direction: 'rtl', marginTop: -8}}>
					{keys.map((w, i) => (
						<Word key={i} w={w} size={keySize} weight={800} gold />
					))}
				</div>
				<svg width={420} height={24} style={{marginTop: -6, opacity: 0.9}}>
					<path d="M410,14 C300,4 120,4 10,16" stroke={GOLD} strokeWidth={4} fill="none" strokeLinecap="round" strokeDasharray={420} strokeDashoffset={420 * (1 - ul)} />
				</svg>
			</div>
		);
	}
	const cur = c.words.findIndex((w, i) => t >= w.s - 0.05 && (i + 1 >= c.words.length || t < c.words[i + 1].s - 0.05));
	const chars = c.words.reduce((n, w) => n + w.t.length, 0) + c.words.length * 2;
	const size = fit(64, chars, 860, 0.56);
	return (
		<div style={{position: 'absolute', left: 0, width: W, top: CAPY + 70, display: 'flex', justifyContent: 'center', opacity: Math.min(prog(t, c.s, 0.12), 1 - out), transform: `translateY(${(1 - pin) * 30 - out * 20}px) scale(${0.94 + 0.06 * pin})`}}>
			<div style={{display: 'flex', gap: 18, direction: 'rtl', padding: '16px 38px 22px', borderRadius: 30, background: P.pill, border: `1px solid ${P.glassBorder}`, backdropFilter: 'blur(14px)', boxShadow: '0 20px 50px rgba(0,0,0,0.3)'}}>
				{c.words.map((w, i) => (
					<span key={i} style={{fontFamily: D, fontWeight: 700, fontSize: size, lineHeight: 1.2, whiteSpace: 'nowrap', color: i === cur ? GOLD : CREAM, opacity: t >= w.s - 0.08 ? 1 : 0.28, transform: i === cur ? 'translateY(-3px)' : 'none', display: 'inline-block', textShadow: '0 3px 12px rgba(0,0,0,0.5)'}}>{w.t}</span>
				))}
			</div>
		</div>
	);
};

const behindShows = (t: number) => behinds.some((b) => t >= b.s - 0.2 && t < b.e && behindLayout(b).ok);

/** the reference's caption: small white words with a soft shadow; the words that carry the idea are bigger and warm-coloured, in the same line */
const CleanCaption: React.FC<{c: Cap}> = ({c}) => {
	const t = useTime();
	const out = prog(t, c.e - 0.16, 0.16, eio);
	const chars = c.words.reduce((n, w) => n + w.t.length * (w.key ? 1.55 : 1), 0) + c.words.length * 2;
	const k = Math.min(1, 900 / Math.max(1, chars * 0.54 * 56));
	return (
		<div style={{position: 'absolute', left: 90, width: W - 180, top: CAPY, display: 'flex', flexWrap: 'wrap', justifyContent: 'center', alignItems: 'baseline', gap: `0 ${Math.round(16 * k + 4)}px`, direction: 'rtl', opacity: 1 - out, transform: `translateY(${-out * 18}px)`, filter: out > 0 ? `blur(${out * 8}px)` : undefined}}>
			{c.words.map((w, i) => {
				const p = prog(t, w.s - 0.06, 0.3);
				return (
					<span key={i} style={{fontFamily: D, fontWeight: w.key ? 800 : 600, fontSize: Math.round((w.key ? 86 : 56) * k), lineHeight: 1.25, whiteSpace: 'nowrap', display: 'inline-block', opacity: p, transform: `translateY(${(1 - p) * 22}px)`, filter: p < 1 ? `blur(${(1 - p) * 6}px)` : 'drop-shadow(0 5px 14px rgba(0,0,0,0.65))', ...(w.key ? goldText : {color: CREAM})}}>
						{w.t}
					</span>
				);
			})}
		</div>
	);
};

const Captions: React.FC = () => {
	const t = useTime();
	const c = caps.find((x) => t >= x.s && t < x.e);
	if (!c || (c.hide && behindShows(t))) return null;
	return STYLE.captions === 'two-tier' || STYLE.captions === 'pill' ? <Caption key={c.s} c={c} /> : <CleanCaption key={c.s} c={c} />;
};

/** a graphic written for this video, drawn inside its zone (never on the head) */
const PropView: React.FC<{p: {s: number; e: number; name: string; zone: string}}> = ({p}) => {
	const G = GRAPHICS[p.name];
	const mid = p.s + (p.e - p.s) / 2;
	let rect = zoneRect(p.zone, mid);
	if (!usable(rect)) rect = zoneRect('lower', mid);
	const t = useTime();
	const fade = Math.min(prog(t, 0, 0.18), 1 - prog(t, p.e - p.s - 0.25, 0.25, eio));
	if (!G || !usable(rect)) return null;
	const k = (i: number) => (KW[String(i)] ?? p.s) - p.s;
	return (
		<div style={{position: 'absolute', left: rect.x, top: rect.y, width: rect.w, height: rect.h, opacity: fade}}>
			<G k={k} dur={p.e - p.s} w={rect.w} h={rect.h} />
		</div>
	);
};

/* ========== main ========== */
export const Premium: React.FC = () => {
	const f = useCurrentFrame();
	const t = f / FPS;
	const [h] = React.useState(() => delayRender('fonts'));
	React.useEffect(() => {
		const id = setTimeout(() => {
			Promise.all([800, 700, 500, 300].map((w) => document.fonts.load(`${w} 60px Doran`, 'سلام')))
				.then(() => document.fonts.load('italic 900 60px "Playfair Display"', 'OVERVIEW'))
				.then(() => document.fonts.ready)
				.then(() => continueRender(h));
		}, 50);
		return () => clearTimeout(id);
	}, [h]);
	const ev = evAmt(t, 0.25);
	return (
		<AbsoluteFill style={{background: '#000'}}>
			<Fonts />
			<AbsoluteFill style={{transform: `scale(${1 + ev * 0.05})`, filter: ev > 0.02 ? `blur(${ev * 10}px) brightness(${1 + ev * 0.25})` : undefined}}>
				<Cam />
				{behinds.map((b, i) => (
					<Sequence key={'b' + i} from={Math.round(b.s * FPS)} durationInFrames={Math.max(1, Math.round((b.e - b.s) * FPS))}>
						<BehindText b={b} />
					</Sequence>
				))}
				{behinds.filter((b) => b.seg && behindLayout(b).ok).map((b, i) => (
					<Sequence key={'f' + i} from={Math.round(b.s * FPS)} durationInFrames={Math.max(1, Math.round((b.e - b.s) * FPS))}>
						<FG b={b} />
					</Sequence>
				))}
			</AbsoluteFill>
			<Look />
			<Graphics />
			{props.map((p, i) => (
				<Sequence key={'p' + i} from={Math.round(p.s * FPS)} durationInFrames={Math.max(1, Math.round((p.e - p.s) * FPS))}>
					<PropView p={p} />
				</Sequence>
			))}
			<Captions />
		</AbsoluteFill>
	);
};
