import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig, Easing} from 'remotion';

export const G = '#17844F';
export const GL = '#2FB574';
export const GD = '#0E5A36';
export const INK = '#1B201E';
export const MUTED = '#59605C';
export const FONT = 'Vazirmatn';

export const clamp = (x: number) => Math.max(0, Math.min(1, x));
export const easeOut = Easing.bezier(0.16, 1, 0.3, 1);
export const easeInOut = Easing.bezier(0.65, 0, 0.35, 1);

export const useT = () => {
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	return f / fps;
};

/** progress 0..1 starting at `at` seconds, eased */
export const prog = (t: number, at: number, dur = 0.5, ease = easeOut) =>
	ease(clamp((t - at) / dur));

export const useSpr = (at: number, damping = 13, mass = 0.8) => {
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	return spring({frame: f - at * fps, fps, config: {damping, mass, stiffness: 120}});
};

type Cue = (s: string, occ?: number, offset?: number) => number;
export const SceneCtx = React.createContext<{dur: number; cue: Cue}>({dur: 1, cue: () => 0});
export const useScene = () => React.useContext(SceneCtx);

/** Text that rises in with blur */
export const Txt: React.FC<{
	at: number;
	size?: number;
	weight?: number;
	color?: string;
	style?: React.CSSProperties;
	children: React.ReactNode;
	from?: 'up' | 'down' | 'scale';
	dur?: number;
}> = ({at, size = 52, weight = 500, color = INK, style, children, from = 'up', dur = 0.55}) => {
	const t = useT();
	const p = prog(t, at, dur);
	const s = useSpr(at, 12, 0.7);
	const tr =
		from === 'scale'
			? `scale(${interpolate(s, [0, 1], [0.6, 1])})`
			: `translateY(${(1 - p) * (from === 'up' ? 40 : -40)}px)`;
	return (
		<div
			style={{
				fontFamily: FONT,
				fontSize: size,
				fontWeight: weight,
				color,
				direction: 'rtl',
				lineHeight: 1.25,
				opacity: p,
				filter: `blur(${(1 - p) * 12}px)`,
				transform: tr,
				whiteSpace: 'nowrap',
				...style,
			}}
		>
			{children}
		</div>
	);
};

/** Big headline that reveals word by word */
export const Words: React.FC<{
	text: string;
	at: number;
	size?: number;
	weight?: number;
	color?: string;
	stagger?: number;
	style?: React.CSSProperties;
	hl?: string[];
}> = ({text, at, size = 150, weight = 900, color = INK, stagger = 0.12, style, hl = []}) => {
	const t = useT();
	const words = text.split(' ');
	return (
		<div
			style={{
				fontFamily: FONT,
				fontSize: size,
				fontWeight: weight,
				color,
				direction: 'rtl',
				lineHeight: 1.12,
				letterSpacing: -2,
				display: 'flex',
				flexWrap: 'nowrap',
				whiteSpace: 'nowrap',
				justifyContent: 'center',
				gap: `0 ${size * 0.22}px`,
				...style,
			}}
		>
			{words.map((w, i) => {
				const p = prog(t, at + i * stagger, 0.6);
				return (
					<span
						key={i}
						style={{
							display: 'inline-block',
							opacity: p,
							transform: `translateY(${(1 - p) * 60}px) scale(${0.85 + 0.15 * p})`,
							filter: `blur(${(1 - p) * 14}px)`,
							color: hl.includes(w) ? G : color,
						}}
					>
						{w}
					</span>
				);
			})}
		</div>
	);
};

/** Dark pill with optional green highlighted part */
export const Pill: React.FC<{at: number; children: React.ReactNode; style?: React.CSSProperties; size?: number; light?: boolean}> = ({
	at,
	children,
	style,
	size = 40,
	light,
}) => {
	const s = useSpr(at, 14, 0.6);
	const t = useT();
	const p = prog(t, at, 0.35);
	return (
		<div
			style={{
				fontFamily: FONT,
				fontWeight: 700,
				fontSize: size,
				direction: 'rtl',
				color: light ? INK : '#fff',
				background: light ? 'rgba(255,255,255,0.85)' : 'linear-gradient(180deg,#26302C,#161B19)',
				border: light ? '2px solid rgba(0,0,0,0.08)' : 'none',
				padding: `${size * 0.32}px ${size * 0.6}px`,
				borderRadius: size * 0.35,
				boxShadow: '0 18px 40px rgba(0,0,0,0.22), inset 0 1px 0 rgba(255,255,255,0.12)',
				whiteSpace: 'nowrap',
				opacity: p,
				transform: `scale(${interpolate(s, [0, 1], [0.5, 1])})`,
				...style,
			}}
		>
			{children}
		</div>
	);
};

export const Hl: React.FC<{children: React.ReactNode}> = ({children}) => <span style={{color: GL}}>{children}</span>;

export const Badge: React.FC<{n: string; at: number; style?: React.CSSProperties; dim?: boolean; active?: boolean; strike?: boolean}> = ({
	n,
	at,
	style,
	dim,
	active,
	strike,
}) => {
	const s = useSpr(at, 12, 0.6);
	return (
		<div
			style={{
				fontFamily: FONT,
				fontWeight: 800,
				fontSize: 40,
				direction: 'rtl',
				color: active ? '#fff' : G,
				background: active ? G : 'rgba(255,255,255,0.55)',
				border: `3px solid ${G}`,
				padding: '8px 34px 12px',
				borderRadius: 100,
				whiteSpace: 'nowrap',
				opacity: s * (dim ? 0.35 : 1),
				transform: `scale(${interpolate(s, [0, 1], [0.4, 1])})`,
				textDecoration: strike ? 'line-through' : 'none',
				boxShadow: active ? '0 12px 30px rgba(23,132,79,0.35)' : 'none',
				...style,
			}}
		>
			مرحله‌ی {n}
		</div>
	);
};

export const Abs: React.FC<{x?: number; y: number; children: React.ReactNode; style?: React.CSSProperties; anchor?: 'center' | 'right' | 'left'}> = ({
	x = 540,
	y,
	children,
	style,
	anchor = 'center',
}) => (
	<div
		style={{
			position: 'absolute',
			left: x,
			top: y,
			transform: anchor === 'center' ? 'translate(-50%,-50%)' : anchor === 'right' ? 'translate(-100%,-50%)' : 'translate(0,-50%)',
			display: 'flex',
			flexDirection: 'column',
			alignItems: anchor === 'center' ? 'center' : anchor === 'right' ? 'flex-end' : 'flex-start',
			...style,
		}}
	>
		{children}
	</div>
);

/** Floating idle motion */
export const useFloat = (amp = 10, speed = 1, phase = 0) => {
	const t = useT();
	return Math.sin(t * speed * 2 + phase) * amp;
};

/** pops an svg/html element in with spring scale */
export const Pop: React.FC<{at: number; children: React.ReactNode; style?: React.CSSProperties; from?: number; origin?: string; damping?: number}> = ({
	at,
	children,
	style,
	from = 0.3,
	origin = '50% 50%',
	damping = 12,
}) => {
	const s = useSpr(at, damping, 0.9);
	const t = useT();
	return (
		<div
			style={{
				transform: `scale(${interpolate(s, [0, 1], [from, 1])})`,
				transformOrigin: origin,
				opacity: prog(t, at, 0.3),
				...style,
			}}
		>
			{children}
		</div>
	);
};

export const fa = (n: number | string) => String(n).replace(/[0-9]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[+d]);
