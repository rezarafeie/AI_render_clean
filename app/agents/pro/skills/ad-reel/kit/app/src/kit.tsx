import React from 'react';
import {Easing, Img, interpolate, random, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';

export const W = 1080;
export const H = 1920;
export const RED = '#FF2A2A';
export const RED2 = '#C80000';
export const YEL = '#FFD400';
export const ORANGE = '#FF7A1A';
export const FA = 'Vazirmatn';
export const DISPLAY = 'Lalezar';

export const clamp = (x: number) => Math.max(0, Math.min(1, x));
export const eo = Easing.bezier(0.16, 1, 0.3, 1);
export const eio = Easing.bezier(0.65, 0, 0.35, 1);
export const ein = Easing.bezier(0.7, 0, 0.84, 0);
export const prog = (t: number, at: number, d = 0.4, e = eo) => e(clamp((t - at) / d));
export const useT = () => {
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	return f / fps;
};
export const useSp = (at: number, damping = 12, mass = 0.7, stiffness = 160) => {
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	return spring({frame: f - Math.round(at * fps), fps, config: {damping, mass, stiffness}});
};
export const fa = (n: number | string) => String(n).replace(/[0-9]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[+d]);

/** decaying shake offset */
export const shake = (t: number, at: number, amp = 30, decay = 7, freq = 55, seed = 0) => {
	if (t < at) return [0, 0];
	const d = t - at;
	const k = amp * Math.exp(-d * decay);
	return [Math.sin(d * freq + seed) * k, Math.cos(d * freq * 1.3 + seed) * k * 0.7];
};
/** continuous vibration (for tools running) */
export const vib = (t: number, on: boolean, amp = 6) => (on ? [Math.sin(t * 90) * amp, Math.cos(t * 77) * amp * 0.7] : [0, 0]);

export const P: React.FC<{src: string; w: number; style?: React.CSSProperties}> = ({src, w, style}) => (
	<Img src={staticFile('img/' + src)} style={{width: w, display: 'block', ...style}} />
);

export const At: React.FC<{x: number; y: number; children: React.ReactNode; style?: React.CSSProperties}> = ({x, y, children, style}) => (
	<div style={{position: 'absolute', left: x, top: y, transform: 'translate(-50%,-50%)', ...style}}>{children}</div>
);

export const Pop: React.FC<{at: number; children: React.ReactNode; from?: number; rot?: number; damping?: number; x?: number; y?: number; style?: React.CSSProperties}> = ({
	at,
	children,
	from = 0.3,
	rot = 0,
	damping = 11,
	x = 0,
	y = 0,
	style,
}) => {
	const s = useSp(at, damping, 0.8);
	const t = useT();
	return (
		<div
			style={{
				opacity: t < at ? 0 : prog(t, at, 0.1),
				transform: `translate(${(1 - s) * x}px,${(1 - s) * y}px) scale(${interpolate(s, [0, 1], [from, 1])}) rotate(${(1 - s) * rot}deg)`,
				...style,
			}}
		>
			{children}
		</div>
	);
};

/** Big punchy headline: slams in */
export const Slam: React.FC<{at: number; children: React.ReactNode; size?: number; color?: string; stroke?: boolean; skew?: number; style?: React.CSSProperties; font?: string}> = ({
	at,
	children,
	size = 150,
	color = '#fff',
	skew = -6,
	style,
	font = FA,
}) => {
	const t = useT();
	const s = useSp(at, 10, 0.6, 220);
	if (t < at) return null;
	return (
		<div
			style={{
				fontFamily: font,
				fontWeight: 900,
				fontSize: size,
				lineHeight: 1.05,
				color,
				direction: 'rtl',
				whiteSpace: 'nowrap',
				transform: `scale(${interpolate(s, [0, 1], [2.2, 1])}) skewX(${skew}deg)`,
				opacity: prog(t, at, 0.06),
				textShadow: '0 10px 40px rgba(0,0,0,0.6)',
				filter: `blur(${(1 - prog(t, at, 0.12)) * 10}px)`,
				...style,
			}}
		>
			{children}
		</div>
	);
};

/** Label with red block background */
export const Block: React.FC<{at: number; children: React.ReactNode; bg?: string; color?: string; size?: number; rot?: number}> = ({at, children, bg = RED, color = '#fff', size = 64, rot = -3}) => {
	const t = useT();
	const p = prog(t, at, 0.3);
	if (t < at) return null;
	return (
		<div style={{position: 'relative', display: 'inline-block', transform: `rotate(${rot}deg)`}}>
			<div style={{position: 'absolute', inset: 0, background: bg, transformOrigin: '100% 50%', transform: `scaleX(${p})`, borderRadius: 10, boxShadow: `0 14px 40px ${bg}66`}} />
			<div style={{position: 'relative', fontFamily: FA, fontWeight: 900, fontSize: size, color, padding: `${size * 0.12}px ${size * 0.4}px ${size * 0.2}px`, direction: 'rtl', whiteSpace: 'nowrap', opacity: prog(t, at + 0.08, 0.15)}}>
				{children}
			</div>
		</div>
	);
};

/** number tag like 01 / 04 */
export const NumTag: React.FC<{n: number; at: number}> = ({n, at}) => (
	<Pop at={at} from={0.4} rot={-20}>
		<div style={{display: 'flex', alignItems: 'baseline', gap: 10, direction: 'rtl'}}>
			<div style={{fontFamily: FA, fontWeight: 900, fontSize: 120, color: 'transparent', WebkitTextStroke: `4px ${RED}`, lineHeight: 1}}>{fa(String(n).padStart(2, '0'))}</div>
			<div style={{fontFamily: FA, fontWeight: 800, fontSize: 36, color: 'rgba(255,255,255,0.6)'}}>از ۴</div>
		</div>
	</Pop>
);

/** radial speed lines */
export const SpeedLines: React.FC<{cx: number; cy: number; o: number; seed?: string; n?: number; color?: string}> = ({cx, cy, o, seed = 's', n = 46, color = '#fff'}) => {
	const t = useT();
	return (
		<svg width={W} height={H} style={{position: 'absolute', left: 0, top: 0, opacity: o, mixBlendMode: 'screen'}}>
			{Array.from({length: n}).map((_, i) => {
				const a = (i / n) * Math.PI * 2 + random(seed + i) * 0.1;
				const ph = (t * 3 + random(seed + 'p' + i)) % 1;
				const r1 = 260 + ph * 900;
				const r2 = r1 + 120 + random(seed + 'l' + i) * 260;
				return <line key={i} x1={cx + Math.cos(a) * r1} y1={cy + Math.sin(a) * r1} x2={cx + Math.cos(a) * r2} y2={cy + Math.sin(a) * r2} stroke={color} strokeWidth={3 + random(seed + 'w' + i) * 5} opacity={0.35 * (1 - ph)} strokeLinecap="round" />;
			})}
		</svg>
	);
};

/** spark particle emitter */
export const Sparks: React.FC<{x: number; y: number; from: number; to: number; dir?: number; spread?: number; n?: number; seed?: string; speed?: number}> = ({
	x,
	y,
	from,
	to,
	dir = -90,
	spread = 70,
	n = 120,
	seed = 'k',
	speed = 1400,
}) => {
	const t = useT();
	const life = 0.55;
	return (
		<svg width={W} height={H} style={{position: 'absolute', left: 0, top: 0, mixBlendMode: 'screen', pointerEvents: 'none'}}>
			{Array.from({length: n}).map((_, i) => {
				const born = from + (i / n) * Math.max(0.01, to - from);
				const age = t - born;
				if (age < 0 || age > life) return null;
				const a = ((dir + (random(seed + i) - 0.5) * spread) * Math.PI) / 180;
				const v = speed * (0.5 + random(seed + 'v' + i));
				const px = x + Math.cos(a) * v * age;
				const py = y + Math.sin(a) * v * age + 1800 * age * age;
				const tail = 0.03;
				const qx = x + Math.cos(a) * v * (age - tail);
				const qy = y + Math.sin(a) * v * (age - tail) + 1800 * (age - tail) * (age - tail);
				const k = 1 - age / life;
				return <line key={i} x1={qx} y1={qy} x2={px} y2={py} stroke={k > 0.5 ? '#FFE9A8' : ORANGE} strokeWidth={2 + 4 * k} strokeLinecap="round" opacity={k} />;
			})}
		</svg>
	);
};

/** shiny light sweep over an element */
export const Sweep: React.FC<{at: number; dur?: number}> = ({at, dur = 0.7}) => {
	const t = useT();
	const p = (t - at) / dur;
	if (p < 0 || p > 1) return null;
	return (
		<div style={{position: 'absolute', inset: 0, overflow: 'hidden', pointerEvents: 'none', mixBlendMode: 'screen'}}>
			<div style={{position: 'absolute', top: '-50%', left: `${-60 + p * 200}%`, width: '35%', height: '200%', transform: 'rotate(20deg)', background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.55), transparent)'}} />
		</div>
	);
};

export const Glow: React.FC<{x: number; y: number; r: number; color?: string; o?: number}> = ({x, y, r, color = RED, o = 0.5}) => (
	<div style={{position: 'absolute', left: x - r, top: y - r, width: r * 2, height: r * 2, borderRadius: '50%', background: `radial-gradient(circle, ${color} 0%, transparent 65%)`, opacity: o, filter: 'blur(10px)'}} />
);

export const Check: React.FC<{s?: number; color?: string}> = ({s = 70, color = '#22C55E'}) => (
	<svg width={s} height={s} viewBox="0 0 90 90">
		<circle cx={45} cy={45} r={42} fill={color} />
		<path d="M25,46 L39,60 L66,31" fill="none" stroke="#fff" strokeWidth={10} strokeLinecap="round" strokeLinejoin="round" />
	</svg>
);
