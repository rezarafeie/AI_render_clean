import React from 'react';
import {Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';

export const W = 1080;
export const H = 1920;
export const SPLIT = 1010;
export const CORAL = '#E8705A';
export const CORAL2 = '#F5A98B';
export const INK = '#141414';
export const MUTED = '#6A6763';
export const GREEN = '#1FA463';
export const MONEY = '#3BE37A';
export const GOLD = '#F5B83D';
export const FA = 'Doran';            // the studio's Persian face (variable 100-900)
export const NASKH = 'Doran';         // key words: the same face, heavier (the person wants Doran everywhere)
export const SERIF = 'Playfair Display';

export const clamp = (x: number) => Math.max(0, Math.min(1, x));
export const eo = Easing.bezier(0.16, 1, 0.3, 1);
export const eio = Easing.bezier(0.65, 0, 0.35, 1);
export const prog = (t: number, at: number, d = 0.4, e = eo) => e(clamp((t - at) / d));
export const useT = () => {
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	return f / fps;
};
export const useSp = (at: number, damping = 12, mass = 0.7, stiffness = 140) => {
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	return spring({frame: f - Math.round(at * fps), fps, config: {damping, mass, stiffness}});
};
export const fa = (n: number | string) => String(n).replace(/[0-9]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[+d]);

export const coralText: React.CSSProperties = {
	background: `linear-gradient(180deg, #F07F62 0%, ${CORAL} 55%, #D2452F 100%)`,
	WebkitBackgroundClip: 'text',
	backgroundClip: 'text',
	color: 'transparent',
};

/** Pops in with spring scale + rotation */
export const Pop: React.FC<{at: number; children: React.ReactNode; style?: React.CSSProperties; from?: number; rot?: number; damping?: number; y?: number}> = ({
	at,
	children,
	style,
	from = 0.4,
	rot = 0,
	damping = 11,
	y = 0,
}) => {
	const s = useSp(at, damping, 0.8);
	const t = useT();
	return (
		<div
			style={{
				opacity: prog(t, at, 0.12),
				transform: `translateY(${(1 - s) * y}px) scale(${interpolate(s, [0, 1], [from, 1])}) rotate(${(1 - s) * rot}deg)`,
				...style,
			}}
		>
			{children}
		</div>
	);
};

export const Card: React.FC<{w: number; h: number; children?: React.ReactNode; style?: React.CSSProperties; r?: number}> = ({w, h, children, style, r = 44}) => (
	<div
		style={{
			width: w,
			height: h,
			borderRadius: r,
			background: '#fff',
			boxShadow: '0 34px 80px rgba(40,30,20,0.16), 0 6px 18px rgba(40,30,20,0.08)',
			position: 'relative',
			overflow: 'hidden',
			...style,
		}}
	>
		{children}
	</div>
);

export const Tag: React.FC<{children: React.ReactNode; at: number; color?: string; style?: React.CSSProperties}> = ({children, at, color = CORAL, style}) => (
	<Pop at={at} from={0.5} damping={12} style={style}>
		<div
			style={{
				fontFamily: FA,
				fontWeight: 800,
				fontSize: 38,
				direction: 'rtl',
				color,
				border: `3px solid ${color}`,
				background: 'rgba(255,255,255,0.85)',
				borderRadius: 100,
				padding: '8px 30px 12px',
				whiteSpace: 'nowrap',
				boxShadow: '0 10px 24px rgba(0,0,0,0.08)',
			}}
		>
			{children}
		</div>
	</Pop>
);

export const At: React.FC<{x: number; y: number; children: React.ReactNode; z?: number}> = ({x, y, children, z}) => (
	<div style={{position: 'absolute', left: x, top: y, transform: 'translate(-50%,-50%)', zIndex: z}}>{children}</div>
);

export const useFloat = (amp = 10, sp = 1, ph = 0) => Math.sin(useT() * sp * 2 + ph) * amp;

/* ----------------- icons ----------------- */
export const Briefcase: React.FC<{s?: number}> = ({s = 160}) => (
	<svg width={s} height={s} viewBox="0 0 160 160">
		<rect x={52} y={22} width={56} height={34} rx={12} fill="none" stroke="#2a2a2a" strokeWidth={10} />
		<rect x={10} y={46} width={140} height={98} rx={18} fill="#2b2b2b" />
		<rect x={10} y={46} width={140} height={40} rx={18} fill="#3a3a3a" />
		<rect x={66} y={74} width={28} height={24} rx={6} fill={CORAL} />
		<rect x={14} y={50} width={132} height={6} rx={3} fill="rgba(255,255,255,0.12)" />
	</svg>
);

export const BoxIcon: React.FC<{s?: number}> = ({s = 220}) => (
	<svg width={s} height={s} viewBox="0 0 220 220">
		<ellipse cx={110} cy={196} rx={86} ry={12} fill="rgba(0,0,0,0.15)" />
		<path d="M20,70 L110,110 L110,200 L20,160 Z" fill="#C99A62" />
		<path d="M200,70 L110,110 L110,200 L200,160 Z" fill="#A87A45" />
		<path d="M20,70 L110,30 L200,70 L110,110 Z" fill="#E2B67D" />
		<path d="M65,50 L155,90 L155,120 L140,113 L140,94 L50,56 Z" fill="#F3E2C2" opacity={0.9} />
		<rect x={132} y={140} width={46} height={30} rx={6} fill={GREEN} transform="skewY(-24) translate(0,62)" />
	</svg>
);

export const Laptop: React.FC<{s?: number}> = ({s = 230}) => (
	<svg width={s} height={s * 0.8} viewBox="0 0 230 184">
		<rect x={30} y={10} width={170} height={118} rx={12} fill="#1d1f22" />
		<rect x={40} y={20} width={150} height={98} rx={6} fill="url(#lg)" />
		<defs>
			<linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
				<stop offset="0" stopColor="#FFD1C2" />
				<stop offset="1" stopColor={CORAL} />
			</linearGradient>
		</defs>
		<circle cx={115} cy={69} r={26} fill="rgba(255,255,255,0.9)" />
		<path d="M107,56 L130,69 L107,82 Z" fill={CORAL} />
		<path d="M6,136 L224,136 L210,160 L20,160 Z" fill="#2a2c30" />
		<rect x={95} y={138} width={40} height={6} rx={3} fill="#555" />
	</svg>
);

export const Mic: React.FC<{s?: number}> = ({s = 200}) => (
	<svg width={s} height={s * 1.3} viewBox="0 0 200 260">
		<rect x={60} y={10} width={80} height={140} rx={40} fill="#2b2b2b" />
		{Array.from({length: 7}).map((_, i) => (
			<line key={i} x1={68} x2={132} y1={30 + i * 16} y2={30 + i * 16} stroke="#555" strokeWidth={4} />
		))}
		<rect x={60} y={10} width={30} height={140} rx={15} fill="rgba(255,255,255,0.08)" />
		<path d="M38,110 C38,176 162,176 162,110" fill="none" stroke="#2b2b2b" strokeWidth={12} strokeLinecap="round" />
		<rect x={94} y={176} width={12} height={50} fill="#2b2b2b" />
		<rect x={56} y={222} width={88} height={14} rx={7} fill="#2b2b2b" />
	</svg>
);

export const Gear: React.FC<{s?: number; color?: string; rot?: number}> = ({s = 120, color = '#2b2b2b', rot = 0}) => {
	const teeth = 10;
	let d = '';
	for (let i = 0; i < teeth * 2; i++) {
		const a = (i / (teeth * 2)) * Math.PI * 2;
		const r = i % 2 === 0 ? 50 : 40;
		const a2 = ((i + 1) / (teeth * 2)) * Math.PI * 2;
		d += `${i === 0 ? 'M' : 'L'}${60 + Math.cos(a) * r},${60 + Math.sin(a) * r} L${60 + Math.cos(a2 - 0.08) * r},${60 + Math.sin(a2 - 0.08) * r} `;
	}
	return (
		<svg width={s} height={s} viewBox="0 0 120 120" style={{transform: `rotate(${rot}deg)`}}>
			<path d={d + 'Z'} fill={color} />
			<circle cx={60} cy={60} r={16} fill="#fff" />
		</svg>
	);
};

export const Check: React.FC<{s?: number}> = ({s = 90}) => (
	<svg width={s} height={s} viewBox="0 0 90 90">
		<circle cx={45} cy={45} r={42} fill={GREEN} />
		<path d="M25,46 L39,60 L66,31" fill="none" stroke="#fff" strokeWidth={9} strokeLinecap="round" strokeLinejoin="round" />
	</svg>
);

export const StampX: React.FC<{s?: number}> = ({s = 260}) => (
	<svg width={s} height={s} viewBox="0 0 260 260">
		<circle cx={130} cy={130} r={112} fill="rgba(229,57,53,0.08)" stroke="#E53935" strokeWidth={14} />
		<circle cx={130} cy={130} r={92} fill="none" stroke="#E53935" strokeWidth={4} strokeDasharray="10 8" />
		<path d="M85,85 L175,175 M175,85 L85,175" stroke="#E53935" strokeWidth={22} strokeLinecap="round" />
	</svg>
);

export const Coin: React.FC<{s?: number; spin?: number}> = ({s = 80, spin = 1}) => (
	<svg width={s} height={s} viewBox="0 0 80 80" style={{transform: `scaleX(${spin})`}}>
		<circle cx={40} cy={42} r={36} fill="#C98A12" />
		<circle cx={40} cy={38} r={36} fill={GOLD} />
		<circle cx={40} cy={38} r={27} fill="none" stroke="#FFE08A" strokeWidth={4} />
		<path d="M40,22 L44,34 L57,34 L46,42 L50,55 L40,47 L30,55 L34,42 L23,34 L36,34 Z" fill="#FFF1B8" />
	</svg>
);

export const Sparkle: React.FC<{s?: number; color?: string}> = ({s = 60, color = '#fff'}) => (
	<svg width={s} height={s} viewBox="0 0 60 60">
		<path d="M30,0 C33,20 40,27 60,30 C40,33 33,40 30,60 C27,40 20,33 0,30 C20,27 27,20 30,0 Z" fill={color} />
	</svg>
);

export const Play: React.FC<{s?: number; bg?: string; fg?: string}> = ({s = 120, bg = 'rgba(255,255,255,0.92)', fg = INK}) => (
	<svg width={s} height={s} viewBox="0 0 120 120">
		<circle cx={60} cy={60} r={56} fill={bg} />
		<path d="M48,36 L86,60 L48,84 Z" fill={fg} />
	</svg>
);

export const Phone: React.FC<{w?: number; children?: React.ReactNode}> = ({w = 360, children}) => {
	const h = w * 2;
	return (
		<div style={{width: w, height: h, borderRadius: w * 0.16, background: '#141516', padding: w * 0.035, boxShadow: '0 40px 90px rgba(0,0,0,0.3)', position: 'relative'}}>
			<div style={{width: '100%', height: '100%', borderRadius: w * 0.13, background: '#fafafa', overflow: 'hidden', position: 'relative'}}>{children}</div>
			<div style={{position: 'absolute', top: w * 0.07, left: '50%', transform: 'translateX(-50%)', width: w * 0.28, height: w * 0.075, borderRadius: 40, background: '#0b0b0b'}} />
		</div>
	);
};
