import React from 'react';
import {AbsoluteFill, Easing, OffthreadVideo, Sequence, continueRender, delayRender, interpolate, spring, staticFile, useCurrentFrame} from 'remotion';
import data from './data.json';

/* The fixed engine of the premium full-frame talking edit («تدوین صحبتی پریمیوم»): ONE full 1080x1920 frame, a virtual camera on the speaker,
   two-tier motion captions, glass cards, text that passes BEHIND the speaker, a graded look. Everything per video comes from data.json
   (the plan's moments); nothing here is written per video. Time is OUTPUT time, hooked to spoken words by the planner. */

const W = 1080;
const H = 1920;
const FPS = (data as any).fps as number;
const SRC_W = (data as any).video.w as number;
const SRC_H = (data as any).video.h as number;
const D = 'Doran';
const SERIF = 'Playfair Display';

const PALETTES: Record<string, any> = {
	'cream-gold-espresso': {cream: '#F7EEDF', gold: '#E9C27A', goldGrad: 'linear-gradient(180deg, #FFF6DF 0%, #F1D79C 45%, #D4A24E 100%)', darkGrad: 'linear-gradient(180deg, #4A331A 0%, #22170C 55%, #0F0A05 100%)', ink: '#2E2114', glow: '255,240,215', leak1: '255,150,60', leak2: '255,205,120', vig: '20,10,0', glass: ['rgba(40,30,20,0.55)', 'rgba(15,12,10,0.45)'], glassBorder: 'rgba(255,235,200,0.28)', pill: 'rgba(18,14,10,0.42)', rule: 'rgba(255,235,200,0.35)'},
	'ice-blue-silver': {cream: '#EEF4FA', gold: '#9CC8F0', goldGrad: 'linear-gradient(180deg, #FFFFFF 0%, #CFE3F5 45%, #8FB4D9 100%)', darkGrad: 'linear-gradient(180deg, #27425E 0%, #142234 55%, #08111C 100%)', ink: '#142234', glow: '220,236,255', leak1: '90,150,255', leak2: '160,210,255', vig: '0,8,20', glass: ['rgba(20,32,48,0.55)', 'rgba(8,14,22,0.45)'], glassBorder: 'rgba(200,225,255,0.28)', pill: 'rgba(8,14,22,0.42)', rule: 'rgba(200,225,255,0.35)'},
	'mono-red': {cream: '#FFFFFF', gold: '#FF5A47', goldGrad: 'linear-gradient(180deg, #FF9C8E 0%, #FF5A47 50%, #C41E12 100%)', darkGrad: 'linear-gradient(180deg, #3A0E0A 0%, #1A0605 55%, #0A0202 100%)', ink: '#1A0605', glow: '255,225,220', leak1: '255,70,50', leak2: '255,140,110', vig: '20,0,0', glass: ['rgba(40,14,12,0.6)', 'rgba(14,6,5,0.5)'], glassBorder: 'rgba(255,200,190,0.28)', pill: 'rgba(20,6,5,0.5)', rule: 'rgba(255,200,190,0.35)'},
	'black-neon-green': {cream: '#F2FFF6', gold: '#3BE37A', goldGrad: 'linear-gradient(180deg, #D8FFE6 0%, #6EF0A0 50%, #1FA463 100%)', darkGrad: 'linear-gradient(180deg, #123A22 0%, #08170E 55%, #020805 100%)', ink: '#08170E', glow: '200,255,220', leak1: '40,220,120', leak2: '120,255,180', vig: '0,10,4', glass: ['rgba(10,30,18,0.6)', 'rgba(4,12,8,0.5)'], glassBorder: 'rgba(160,255,200,0.28)', pill: 'rgba(4,14,8,0.5)', rule: 'rgba(160,255,200,0.35)'},
	'coral-beige': {cream: '#FFF8F0', gold: '#F08A6C', goldGrad: 'linear-gradient(180deg, #FFE2D4 0%, #F5A98B 50%, #E8705A 100%)', darkGrad: 'linear-gradient(180deg, #5A3A2E 0%, #2E1C16 55%, #140A07 100%)', ink: '#3A2218', glow: '255,236,225', leak1: '255,140,100', leak2: '255,200,160', vig: '25,8,0', glass: ['rgba(60,34,26,0.55)', 'rgba(24,12,9,0.45)'], glassBorder: 'rgba(255,225,210,0.3)', pill: 'rgba(30,14,10,0.45)', rule: 'rgba(255,225,210,0.35)'},
};
const STYLE = ((data as any).style ?? {}) as any;
const P = PALETTES[STYLE.palette] ?? PALETTES['cream-gold-espresso'];
const CREAM = P.cream as string;
const GOLD = P.gold as string;
const goldText: React.CSSProperties = {background: P.goldGrad, WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent'};
const darkText: React.CSSProperties = {background: P.darkGrad, WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent'};
const behindStyle: React.CSSProperties = STYLE.behindInk === 'light' ? goldText : darkText;
const behindGlow = STYLE.behindInk === 'light' ? 'drop-shadow(0 6px 18px rgba(0,0,0,0.55))' : `drop-shadow(0 6px 18px rgba(${P.glow},0.5))`;
const behindSub = STYLE.behindInk === 'light' ? CREAM : (P.ink as string);
const CAP_Y = (STYLE.capY as number) ?? 1180;
const FACE_TARGET_Y = (STYLE.faceTargetY as number) ?? 740;
const BASE_Z = ((STYLE.baseZoom as number[]) ?? [1.0, 1.12, 1.04, 1.16, 1.0, 1.1]) as number[];

const clamp = (x: number) => Math.max(0, Math.min(1, x));
const eo = Easing.bezier(0.16, 1, 0.3, 1);
const eio = Easing.bezier(0.65, 0, 0.35, 1);
const prog = (t: number, at: number, d = 0.4, e = eo) => e(clamp((t - at) / d));
const fa = (n: number | string) => String(n).replace(/[0-9]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[+d]);
/** a font size that keeps `chars` letters of Persian inside `maxW` px */
const fit = (size: number, chars: number, maxW: number, k = 0.56) => Math.min(size, Math.floor(maxW / Math.max(1, chars * k)));

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
const zoomAt = (t: number) => {
	const seg = cuts.filter((c) => c <= t).length;
	let z = BASE_Z[seg % BASE_Z.length];
	for (const e of zooms) {
		const ramp = e.ramp ?? 0.5;
		z *= 1 + e.amount * prog(t, e.s - 0.1, ramp, eio) * (1 - prog(t, e.e - 0.2, 0.4, eio));
	}
	z *= 1 + 0.006 * (t % 6);
	return z;
};
const camAt = (t: number) => {
	const base = Math.max(W / SRC_W, H / SRC_H);
	const S = base * zoomAt(t);
	const cx = faceX(t) + ((D_.faceDx as number) ?? 0);
	const tx = Math.min(0, Math.max(W - SRC_W * S, W / 2 - cx * S));
	const ty = Math.min(0, Math.max(H - SRC_H * S, FACE_TARGET_Y - (D_.faceY as number) * S));
	return {S, tx, ty};
};
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

const BehindText: React.FC<{b: Behind}> = ({b}) => {
	const f = useCurrentFrame();
	const t = f / FPS; // local
	const dur = b.e - b.s;
	const out = 1 - prog(t, dur - 0.25, 0.25);
	const wrap: React.CSSProperties = {position: 'absolute', left: 0, width: W, display: 'flex', flexDirection: 'column', alignItems: 'center', opacity: out};
	const latin = b.kind === 'latin';
	const slamAt = b.kind === 'stepped' ? (b.strike ?? 1.15) : 0.15;
	const s = useSpAt(b.s + slamAt, b.kind === 'stepped' ? 12 : 14, b.kind === 'stepped' ? 0.8 : 1, b.kind === 'stepped' ? 180 : 140);
	let size = latin ? fit(210, b.word.length, 1000, 0.62) : fit(b.kind === 'stepped' ? 300 : 225, b.word.length, 980, 0.6);
	// Placed against the speaker's head: ~62% of the block above the head, the rest passes behind it (playbook A4), wherever the camera has put the head.
	// the highest the head gets while the text is up (a slow push-in lifts it): the word is placed against THAT, so it is never buried at the peak
	const headAt = (t: number) => {
		const c = camAt(t);
		return c.ty + (b.top as number) * c.S;
	};
	const headTop = b.top != null ? Math.min(headAt(b.s), headAt(b.s + (b.e - b.s) / 2), headAt(b.e - 0.3)) : b.kind === 'stepped' ? 410 : 430;
	const lh = latin ? 1.0 : b.kind === 'stepped' ? 0.95 : 1.05;
	const extra = b.kind === 'stepped' ? 105 : b.kicker ? 64 : 0;
	const room = Math.max(0.55, Math.min(1, (headTop - 70) / ((extra + size * lh) * 0.62)));   // little room above a high head: the word gets smaller, never buried
	size = Math.floor(size * room);
	const blockH = extra * room + size * lh;
	const top = Math.max(70, Math.min(headTop - blockH * 0.62, 520));
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
const Glass: React.FC<{children: React.ReactNode; style?: React.CSSProperties}> = ({children, style}) => (
	<div style={{background: `linear-gradient(160deg, ${P.glass[0]}, ${P.glass[1]})`, border: `1.5px solid ${P.glassBorder}`, borderRadius: 40, backdropFilter: 'blur(18px) saturate(1.3)', boxShadow: '0 30px 80px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.18)', ...style}}>{children}</div>
);

const InOut: React.FC<{s: number; e: number; children: React.ReactNode; y?: number}> = ({s, e, children, y = -60}) => {
	const t = useTime();
	const pin = useSpAt(s, 15, 0.8);
	const po = prog(t, e - 0.22, 0.22, eio);
	if (t < s - 0.05 || t > e + 0.05) return null;
	return (
		<div style={{opacity: Math.min(prog(t, s, 0.15), 1 - po), transform: `translateY(${(1 - pin) * y + po * -30}px) scale(${0.9 + 0.1 * pin})`, filter: po > 0 ? `blur(${po * 12}px)` : undefined}}>{children}</div>
	);
};

const Icon: React.FC<{k: string; s?: number}> = ({k: kind, s = 80}) => {
	const st = {fill: 'none', stroke: GOLD, strokeWidth: 5, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const};
	return (
		<svg width={s} height={s} viewBox="0 0 80 80">
			{kind === 'spark' && <path d="M40,8 C43,28 52,37 72,40 C52,43 43,52 40,72 C37,52 28,43 8,40 C28,37 37,28 40,8 Z" {...st} />}
			{kind === 'fork' && <path d="M40,74 L40,42 M40,42 L18,18 M40,42 L62,18 M18,18 L18,30 M18,18 L30,18 M62,18 L50,18 M62,18 L62,30" {...st} />}
			{kind === 'compass' && (
				<g {...st}>
					<circle cx={40} cy={40} r={30} />
					<path d="M52,28 L44,44 L28,52 L36,36 Z" fill={GOLD} />
				</g>
			)}
			{kind === 'tools' && <path d="M50,12 a14,14 0 0,0 -6,22 L14,64 a5,5 0 0,0 7,7 L51,41 a14,14 0 0,0 22,-6 l-9,-2 -3,-9 Z" {...st} />}
			{kind === 'user' && (
				<g {...st}>
					<circle cx={40} cy={28} r={13} />
					<path d="M14,70 C16,52 64,52 66,70" />
				</g>
			)}
			{kind === 'group' && (
				<g {...st}>
					<circle cx={40} cy={26} r={11} />
					<path d="M20,66 C22,50 58,50 60,66" />
					<circle cx={16} cy={34} r={8} />
					<circle cx={64} cy={34} r={8} />
					<path d="M2,64 C3,54 14,50 22,52 M78,64 C77,54 66,50 58,52" />
				</g>
			)}
			{kind === 'list' && <path d="M26,22 L66,22 M26,40 L66,40 M26,58 L66,58 M12,22 L14,22 M12,40 L14,40 M12,58 L14,58" {...st} strokeWidth={6} />}
			{kind === 'bulb' && (
				<g {...st}>
					<path d="M28,50 C18,42 18,18 40,14 C62,18 62,42 52,50 L52,58 L28,58 Z" />
					<path d="M30,66 L50,66 M34,73 L46,73" />
				</g>
			)}
			{kind === 'arrow' && <path d="M60,40 L20,40 M34,26 L20,40 L34,54" {...st} strokeWidth={6} />}
			{kind === 'heart' && <path d="M40,68 C10,46 12,18 30,16 C36,16 40,20 40,24 C40,20 44,16 50,16 C68,18 70,46 40,68 Z" {...st} />}
			{kind === 'star' && <path d="M40,8 L49,30 L72,31 L54,46 L60,70 L40,57 L20,70 L26,46 L8,31 L31,30 Z" {...st} />}
			{kind === 'check' && (
				<g {...st}>
					<circle cx={40} cy={40} r={30} />
					<path d="M26,41 L36,51 L56,29" />
				</g>
			)}
			{kind === 'chart' && <path d="M12,66 L12,14 M12,66 L70,66 M22,54 L34,38 L46,46 L64,22 M54,22 L64,22 L64,32" {...st} />}
			{kind === 'coin' && (
				<g {...st}>
					<circle cx={40} cy={40} r={28} />
					<path d="M40,22 L40,58 M30,31 C30,25 50,25 50,32 C50,40 30,38 30,47 C30,55 50,55 50,49" />
				</g>
			)}
			{kind === 'clock' && (
				<g {...st}>
					<circle cx={40} cy={40} r={30} />
					<path d="M40,22 L40,40 L54,48" />
				</g>
			)}
			{kind === 'target' && (
				<g {...st}>
					<circle cx={40} cy={40} r={30} />
					<circle cx={40} cy={40} r={17} />
					<circle cx={40} cy={40} r={4} fill={GOLD} />
				</g>
			)}
			{kind === 'rocket' && <path d="M40,8 C56,18 58,40 50,58 L30,58 C22,40 24,18 40,8 Z M30,58 L22,72 L34,66 M50,58 L58,72 L46,66 M40,34 a6,6 0 1,0 0.1,0" {...st} />}
			{kind === 'lock' && (
				<g {...st}>
					<rect x={18} y={36} width={44} height={34} rx={6} />
					<path d="M28,36 L28,26 C28,12 52,12 52,26 L52,36" />
				</g>
			)}
			{kind === 'play' && (
				<g {...st}>
					<circle cx={40} cy={40} r={30} />
					<path d="M33,26 L58,40 L33,54 Z" fill={GOLD} />
				</g>
			)}
		</svg>
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
			<div style={{position: 'absolute', left: 0, width: W, top: CAP_Y, display: 'flex', flexDirection: 'column', alignItems: 'center', direction: 'rtl', opacity: 1 - out, transform: `translateY(${-out * 30}px)`, filter: out > 0 ? `blur(${out * 10}px)` : undefined}}>
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
		<div style={{position: 'absolute', left: 0, width: W, top: CAP_Y + 70, display: 'flex', justifyContent: 'center', opacity: Math.min(prog(t, c.s, 0.12), 1 - out), transform: `translateY(${(1 - pin) * 30 - out * 20}px) scale(${0.94 + 0.06 * pin})`}}>
			<div style={{display: 'flex', gap: 18, direction: 'rtl', padding: '16px 38px 22px', borderRadius: 30, background: P.pill, border: `1px solid ${P.glassBorder}`, backdropFilter: 'blur(14px)', boxShadow: '0 20px 50px rgba(0,0,0,0.3)'}}>
				{c.words.map((w, i) => (
					<span key={i} style={{fontFamily: D, fontWeight: 700, fontSize: size, lineHeight: 1.2, whiteSpace: 'nowrap', color: i === cur ? GOLD : CREAM, opacity: t >= w.s - 0.08 ? 1 : 0.28, transform: i === cur ? 'translateY(-3px)' : 'none', display: 'inline-block', textShadow: '0 3px 12px rgba(0,0,0,0.5)'}}>{w.t}</span>
				))}
			</div>
		</div>
	);
};

const Captions: React.FC = () => {
	const t = useTime();
	const c = caps.find((x) => t >= x.s && t < x.e);
	if (!c || c.hide) return null;
	return <Caption key={c.s} c={c} />;
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
				{behinds.filter((b) => b.seg).map((b, i) => (
					<Sequence key={'f' + i} from={Math.round(b.s * FPS)} durationInFrames={Math.max(1, Math.round((b.e - b.s) * FPS))}>
						<FG b={b} />
					</Sequence>
				))}
			</AbsoluteFill>
			<Look />
			<Graphics />
			<Captions />
		</AbsoluteFill>
	);
};
