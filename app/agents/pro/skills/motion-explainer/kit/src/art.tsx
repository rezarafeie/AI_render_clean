import React from 'react';
import {interpolate} from 'remotion';
import {G, GD, GL, useT, prog, clamp, easeInOut} from './lib';

/* ---------- shared defs ---------- */
export const Shadow: React.FC<{w: number; y: number; cx: number; o?: number}> = ({w, y, cx, o = 0.25}) => (
	<ellipse cx={cx} cy={y} rx={w / 2} ry={w * 0.09} fill={`rgba(0,0,0,${o})`} filter="url(#blur20)" />
);

export const Defs: React.FC = () => (
	<defs>
		<filter id="blur20" x="-50%" y="-50%" width="200%" height="200%">
			<feGaussianBlur stdDeviation="18" />
		</filter>
		<filter id="blur6">
			<feGaussianBlur stdDeviation="6" />
		</filter>
		<filter id="glow" x="-80%" y="-80%" width="260%" height="260%">
			<feGaussianBlur stdDeviation="22" result="b" />
			<feMerge>
				<feMergeNode in="b" />
				<feMergeNode in="SourceGraphic" />
			</feMerge>
		</filter>
		<linearGradient id="metal" x1="0" x2="1">
			<stop offset="0" stopColor="#7d7a72" />
			<stop offset="0.35" stopColor="#d9d6cc" />
			<stop offset="0.6" stopColor="#a9a59a" />
			<stop offset="1" stopColor="#5d5a53" />
		</linearGradient>
		<linearGradient id="dark" x1="0" x2="1">
			<stop offset="0" stopColor="#2a2e2c" />
			<stop offset="0.5" stopColor="#4a4f4c" />
			<stop offset="1" stopColor="#1b1e1d" />
		</linearGradient>
		<linearGradient id="greenL" x1="0" y1="0" x2="1" y2="1">
			<stop offset="0" stopColor="#2fae6c" />
			<stop offset="1" stopColor="#127043" />
		</linearGradient>
		<linearGradient id="greenR" x1="0" y1="0" x2="1" y2="1">
			<stop offset="0" stopColor="#13703f" />
			<stop offset="1" stopColor="#0a4a2b" />
		</linearGradient>
		<linearGradient id="greenT" x1="0" y1="0" x2="1" y2="0">
			<stop offset="0" stopColor="#4cc98a" />
			<stop offset="1" stopColor="#23955b" />
		</linearGradient>
		<linearGradient id="screen" x1="0" y1="0" x2="0" y2="1">
			<stop offset="0" stopColor="#f6f7f3" />
			<stop offset="1" stopColor="#e3e6df" />
		</linearGradient>
		<linearGradient id="stone" x1="0" y1="0" x2="1" y2="1">
			<stop offset="0" stopColor="#d8d5cd" />
			<stop offset="1" stopColor="#8f8b82" />
		</linearGradient>
		<linearGradient id="wood" x1="0" x2="0" y1="0" y2="1">
			<stop offset="0" stopColor="#3b3d3a" />
			<stop offset="1" stopColor="#1a1b1a" />
		</linearGradient>
		<radialGradient id="light" cx="0.5" cy="0.5" r="0.5">
			<stop offset="0" stopColor="#fff" stopOpacity="1" />
			<stop offset="0.5" stopColor="#d8f5e4" stopOpacity="0.8" />
			<stop offset="1" stopColor="#bdebd1" stopOpacity="0" />
		</radialGradient>
	</defs>
);

export const Svg: React.FC<{w: number; h: number; children: React.ReactNode; style?: React.CSSProperties}> = ({w, h, children, style}) => (
	<svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{overflow: 'visible', ...style}}>
		<Defs />
		{children}
	</svg>
);

/* ---------- Phone ---------- */
export const Phone: React.FC<{w?: number; h?: number; children?: React.ReactNode; id: string}> = ({w = 420, h = 860, children, id}) => {
	const r = w * 0.14;
	const b = w * 0.035;
	return (
		<g>
			<rect x={-8} y={-6} width={w + 16} height={h + 12} rx={r + 6} fill="#0f3d27" />
			<rect x={0} y={0} width={w} height={h} rx={r} fill="#111413" />
			<clipPath id={`clip-${id}`}>
				<rect x={b} y={b} width={w - 2 * b} height={h - 2 * b} rx={r - b} />
			</clipPath>
			<g clipPath={`url(#clip-${id})`}>
				<rect x={b} y={b} width={w - 2 * b} height={h - 2 * b} fill="url(#screen)" />
				{children}
			</g>
			<rect x={w / 2 - w * 0.13} y={b + 14} width={w * 0.26} height={w * 0.07} rx={w * 0.035} fill="#0b0c0c" />
			<rect x={-8} y={-6} width={w + 16} height={h + 12} rx={r + 6} fill="none" stroke="rgba(255,255,255,0.18)" strokeWidth={2} />
		</g>
	);
};

/* ---------- Generic camera glyph (no brand) ---------- */
export const CameraGlyph: React.FC<{s?: number; color?: string}> = ({s = 120, color = G}) => (
	<g>
		<rect x={-s * 0.62} y={-s * 0.36} width={s * 1.24} height={s * 0.82} rx={s * 0.12} fill={color} />
		<path d={`M${-s * 0.2},${-s * 0.36} L${-s * 0.13},${-s * 0.5} L${s * 0.13},${-s * 0.5} L${s * 0.2},${-s * 0.36} Z`} fill={color} />
		<circle cx={0} cy={s * 0.05} r={s * 0.27} fill="#f1f3ee" />
		<circle cx={0} cy={s * 0.05} r={s * 0.18} fill={color} />
		<circle cx={-s * 0.05} cy={0} r={s * 0.05} fill="rgba(255,255,255,0.6)" />
		<rect x={s * 0.36} y={-s * 0.26} width={s * 0.14} height={s * 0.08} rx={s * 0.03} fill="#f1f3ee" />
	</g>
);

/* ---------- Hourglass ---------- */
export const Hourglass: React.FC<{p: number}> = ({p}) => {
	// p: 0..1 sand progress
	const t = useT();
	const W = 440;
	const top = 40;
	const bot = 640;
	const mid = (top + bot) / 2;
	const glass = `M70,${top + 40} C70,${mid - 90} ${W / 2 - 16},${mid - 40} ${W / 2 - 14},${mid} C${W / 2 - 16},${mid + 40} 70,${mid + 90} 70,${bot - 40} L${W - 70},${bot - 40} C${W - 70},${mid + 90} ${W / 2 + 16},${mid + 40} ${W / 2 + 14},${mid} C${W / 2 + 16},${mid - 40} ${W - 70},${mid - 90} ${W - 70},${top + 40} Z`;
	const topLevel = interpolate(p, [0, 1], [top + 110, mid - 10]);
	const moundH = interpolate(p, [0, 1], [10, 150]);
	return (
		<g>
			<Shadow cx={W / 2} y={bot + 30} w={420} />
			<clipPath id="hg">
				<path d={glass} />
			</clipPath>
			<path d={glass} fill="rgba(215,228,220,0.55)" />
			{/* sand */}
			<g clipPath="url(#hg)">
				<rect x={0} y={topLevel} width={W} height={mid - topLevel} fill="url(#greenT)" />
				<path
					d={`M60,${bot - 40} L60,${bot - 40 - moundH * 0.55} Q${W / 2},${bot - 40 - moundH * 1.3} ${W - 60},${bot - 40 - moundH * 0.55} L${W - 60},${bot - 40} Z`}
					fill="url(#greenL)"
				/>
				{p < 0.995 && (
					<rect x={W / 2 - 3} y={mid - 4} width={6} height={bot - 40 - mid - moundH * 0.9} fill={GL} opacity={0.8 + 0.2 * Math.sin(t * 40)} />
				)}
			</g>
			<path d={glass} fill="rgba(200,215,205,0.22)" stroke="#8f9a93" strokeWidth={5} />
			<path d={`M100,${top + 70} C100,${mid - 110} 170,${mid - 60} 190,${mid - 30}`} stroke="rgba(255,255,255,0.7)" strokeWidth={8} fill="none" strokeLinecap="round" />
			{/* frame */}
			{[24, W / 2, W - 24].map((x, i) => (
				<rect key={i} x={x - 11} y={top} width={22} height={bot - top} rx={10} fill="url(#dark)" opacity={i === 1 ? 0 : 1} />
			))}
			<rect x={0} y={top - 40} width={W} height={46} rx={14} fill="url(#wood)" />
			<rect x={0} y={bot - 6} width={W} height={46} rx={14} fill="url(#wood)" />
			<rect x={10} y={top - 36} width={W - 20} height={8} rx={4} fill="rgba(255,255,255,0.12)" />
		</g>
	);
};

/* ---------- Coin stack on green cube ---------- */
export const Cube: React.FC<{x: number; y: number; s: number}> = ({x, y, s}) => {
	// isometric-ish cube: top face center at (x,y)
	const h = s * 0.62;
	const dx = s * 0.5;
	const dy = s * 0.22;
	return (
		<g>
			<path d={`M${x - dx},${y} L${x},${y + dy} L${x},${y + dy + h} L${x - dx},${y + h} Z`} fill="url(#greenL)" />
			<path d={`M${x},${y + dy} L${x + dx},${y} L${x + dx},${y + h} L${x},${y + dy + h} Z`} fill="url(#greenR)" />
			<path d={`M${x - dx},${y} L${x},${y - dy} L${x + dx},${y} L${x},${y + dy} Z`} fill="url(#greenT)" />
			<path d={`M${x - dx * 0.8},${y + h * 0.3} q${dx * 0.3},${h * 0.1} ${dx * 0.6},${h * 0.35}`} stroke="rgba(255,255,255,0.18)" strokeWidth={3} fill="none" />
			<path d={`M${x + dx * 0.2},${y + h * 0.5} q${dx * 0.3},-${h * 0.2} ${dx * 0.6},-${h * 0.1}`} stroke="rgba(255,255,255,0.12)" strokeWidth={3} fill="none" />
		</g>
	);
};

export const Coins: React.FC<{x: number; y: number; n: number; r?: number; at?: number}> = ({x, y, n, r = 82, at = 0}) => {
	const t = useT();
	const th = 15;
	return (
		<g>
			{Array.from({length: n}).map((_, i) => {
				const p = prog(t, at + i * 0.045, 0.35);
				const cy = y - i * th - (1 - p) * 160;
				if (p <= 0) return null;
				return (
					<g key={i} opacity={p}>
						<path d={`M${x - r},${cy} L${x - r},${cy + th} A${r},${r * 0.32} 0 0 0 ${x + r},${cy + th} L${x + r},${cy} Z`} fill="url(#metal)" />
						{Array.from({length: 14}).map((__, k) => (
							<line key={k} x1={x - r + (k + 0.5) * ((2 * r) / 14)} x2={x - r + (k + 0.5) * ((2 * r) / 14)} y1={cy + 3} y2={cy + th + 2} stroke="rgba(0,0,0,0.18)" strokeWidth={2} />
						))}
						<ellipse cx={x} cy={cy} rx={r} ry={r * 0.32} fill="#c9c5ba" stroke="#9c988e" strokeWidth={2} />
					</g>
				);
			})}
		</g>
	);
};

/* ---------- Plate with food ---------- */
export const Plate: React.FC<{cx: number; cy: number; r: number}> = ({cx, cy, r}) => (
	<g>
		<ellipse cx={cx + 10} cy={cy + 24} rx={r} ry={r} fill="rgba(0,0,0,0.22)" filter="url(#blur20)" />
		<circle cx={cx} cy={cy} r={r} fill="#f8f5ee" stroke="#d6cfc0" strokeWidth={4} />
		<circle cx={cx} cy={cy} r={r * 0.78} fill="#fbf9f4" stroke="#ebe5d8" strokeWidth={3} />
		{/* chicken */}
		<g transform={`translate(${cx - r * 0.18},${cy + r * 0.1}) rotate(-28)`}>
			<ellipse rx={r * 0.48} ry={r * 0.27} fill="#d39b52" />
			<ellipse rx={r * 0.42} ry={r * 0.21} fill="#e3b06a" />
			{[-2, -1, 0, 1, 2].map((k) => (
				<line key={k} x1={k * r * 0.12 - r * 0.08} y1={-r * 0.2} x2={k * r * 0.12 + r * 0.06} y2={r * 0.2} stroke="#8b5a22" strokeWidth={6} strokeLinecap="round" opacity={0.7} />
			))}
			<path d={`M${-r * 0.05},${-r * 0.06} q${r * 0.12},${-r * 0.16} ${r * 0.24},0 q${-r * 0.12},${r * 0.12} ${-r * 0.24},0`} fill="#2f8f3e" />
		</g>
		{/* tomatoes */}
		{[
			[0.38, 0.12],
			[0.5, -0.06],
			[0.3, 0.3],
			[0.46, 0.3],
			[0.6, 0.13],
		].map(([dx, dy], i) => (
			<g key={i}>
				<circle cx={cx + dx * r} cy={cy + dy * r} r={r * 0.105} fill="#c8321f" />
				<circle cx={cx + dx * r - r * 0.03} cy={cy + dy * r - r * 0.035} r={r * 0.03} fill="rgba(255,255,255,0.6)" />
			</g>
		))}
		{/* zucchini */}
		{[
			[-0.3, -0.42],
			[-0.08, -0.5],
			[0.14, -0.46],
			[0.32, -0.32],
		].map(([dx, dy], i) => (
			<g key={i}>
				<circle cx={cx + dx * r} cy={cy + dy * r} r={r * 0.13} fill="#2f6b2a" />
				<circle cx={cx + dx * r} cy={cy + dy * r} r={r * 0.1} fill="#cfd98a" />
				<circle cx={cx + dx * r} cy={cy + dy * r} r={r * 0.05} fill="#b9c56c" />
			</g>
		))}
	</g>
);

/* ---------- Sprout ---------- */
export const Sprout: React.FC<{p: number; x: number; y: number; s?: number}> = ({p, x, y, s = 1}) => {
	const stem = clamp(p / 0.6);
	const leaf = clamp((p - 0.4) / 0.6);
	return (
		<g transform={`translate(${x},${y}) scale(${s})`}>
			<path d={`M0,0 C-6,-60 6,-110 0,-${170 * stem}`} stroke="#2b8a3e" strokeWidth={12} fill="none" strokeLinecap="round" />
			<g transform={`translate(0,-${165 * stem}) scale(${leaf})`}>
				<path d="M0,0 C-30,-70 -120,-70 -140,-30 C-100,10 -40,10 0,0 Z" fill="#3fae4f" />
				<path d="M0,0 C-40,-30 -90,-40 -130,-32" stroke="#2a7f36" strokeWidth={3} fill="none" />
				<path d="M0,0 C30,-80 120,-90 150,-50 C110,0 40,10 0,0 Z" fill="#4cc25c" />
				<path d="M0,0 C40,-40 100,-55 140,-50" stroke="#2a7f36" strokeWidth={3} fill="none" />
			</g>
		</g>
	);
};

/* ---------- Shopping bag ---------- */
export const Bag: React.FC<{x: number; y: number; s?: number; o?: number}> = ({x, y, s = 1, o = 1}) => (
	<g transform={`translate(${x},${y}) scale(${s})`} opacity={o}>
		<Shadow cx={0} y={300} w={360} />
		<path d="M-120,-60 Q-120,-190 0,-190 Q120,-190 120,-60" stroke="#9a968c" strokeWidth={10} fill="none" />
		<path d="M-150,-60 L150,-60 L175,290 L-175,290 Z" fill="url(#dark)" />
		<path d="M150,-60 L175,290 L120,290 L110,-60 Z" fill="rgba(0,0,0,0.25)" />
		<path d="M-150,-60 L150,-60 L148,-30 L-148,-30 Z" fill="rgba(255,255,255,0.08)" />
		<path d="M-90,-60 Q-90,-150 0,-150 Q90,-150 90,-60" stroke="#c8c3b6" strokeWidth={12} fill="none" />
		<g transform="translate(90,60) rotate(14)">
			<line x1={0} y1={-60} x2={0} y2={0} stroke="#c8c3b6" strokeWidth={3} />
			<rect x={-40} y={0} width={80} height={120} rx={10} fill="url(#greenL)" />
			<circle cx={0} cy={18} r={7} fill="#0d4a2c" />
		</g>
	</g>
);

/* ---------- Pawn person ---------- */
export const Pawn: React.FC<{x: number; y: number; s?: number; c?: string}> = ({x, y, s = 1, c = '#9a8a74'}) => (
	<g transform={`translate(${x},${y}) scale(${s})`}>
		<path d="M-26,0 C-26,-40 -16,-60 0,-60 C16,-60 26,-40 26,0 Z" fill={c} />
		<circle cx={0} cy={-74} r={18} fill={c} />
		<circle cx={-5} cy={-80} r={6} fill="rgba(255,255,255,0.25)" />
		<path d="M-26,0 C-26,-40 -16,-60 0,-60 L0,0 Z" fill="rgba(255,255,255,0.12)" />
	</g>
);

/* ---------- Door frame ---------- */
export const Door: React.FC<{x: number; y: number; w: number; h: number}> = ({x, y, w, h}) => (
	<g>
		<rect x={x - w / 2} y={y - h} width={w} height={h} fill="#f5fbf7" />
		<path d={`M${x - w / 2 - 34},${y} L${x - w / 2 - 34},${y - h - 34} L${x + w / 2 + 34},${y - h - 34} L${x + w / 2 + 34},${y} L${x + w / 2},${y} L${x + w / 2},${y - h} L${x - w / 2},${y - h} L${x - w / 2},${y} Z`} fill="url(#greenL)" />
		<path d={`M${x + w / 2 + 34},${y} L${x + w / 2 + 60},${y - 18} L${x + w / 2 + 60},${y - h - 52} L${x + w / 2 + 34},${y - h - 34} Z`} fill="url(#greenR)" />
		<path d={`M${x - w / 2 - 34},${y - h - 34} L${x - w / 2 - 8},${y - h - 52} L${x + w / 2 + 60},${y - h - 52} L${x + w / 2 + 34},${y - h - 34} Z`} fill="url(#greenT)" />
	</g>
);

/* ---------- Feed card (for phones) ---------- */
export const FeedCard: React.FC<{x: number; y: number; w: number; seed: number}> = ({x, y, w, seed}) => {
	const hues = ['#9cc9b1', '#c7d6c8', '#b3c7d6', '#d6cdb3', '#a8d1b9'];
	return (
		<g>
			<circle cx={x + w - 26} cy={y + 24} r={18} fill="#cfd5d0" />
			<rect x={x + w - 170} y={y + 14} width={120} height={14} rx={7} fill="#c5cbc6" />
			<rect x={x} y={y + 54} width={w} height={w * 0.72} rx={18} fill={hues[seed % hues.length]} />
			<path d={`M${x},${y + 54 + w * 0.6} L${x + w * 0.3},${y + 54 + w * 0.35} L${x + w * 0.55},${y + 54 + w * 0.55} L${x + w * 0.75},${y + 54 + w * 0.42} L${x + w},${y + 54 + w * 0.6} L${x + w},${y + 54 + w * 0.72} L${x},${y + 54 + w * 0.72} Z`} fill="rgba(0,0,0,0.12)" />
			<circle cx={x + w * 0.75} cy={y + 54 + w * 0.2} r={w * 0.07} fill="rgba(255,255,255,0.7)" />
			<rect x={x + w - 220} y={y + 70 + w * 0.72} width={220} height={14} rx={7} fill="#c5cbc6" />
		</g>
	);
};

/* ---------- AI chip ---------- */
export const Chip: React.FC<{cx: number; cy: number; s: number; glow: number}> = ({cx, cy, s, glow}) => {
	const t = useT();
	const lines = Array.from({length: 16}).map((_, i) => {
		const side = i % 4;
		const k = Math.floor(i / 4);
		const off = (k - 1.5) * s * 0.18;
		const len = s * (0.55 + ((i * 37) % 5) * 0.12);
		let d = '';
		if (side === 0) d = `M${cx + off},${cy - s / 2} L${cx + off},${cy - s / 2 - len * 0.5} L${cx + off * 1.8},${cy - s / 2 - len}`;
		if (side === 1) d = `M${cx + s / 2},${cy + off} L${cx + s / 2 + len * 0.5},${cy + off} L${cx + s / 2 + len},${cy + off * 1.8}`;
		if (side === 2) d = `M${cx + off},${cy + s / 2} L${cx + off},${cy + s / 2 + len * 0.5} L${cx + off * 1.8},${cy + s / 2 + len}`;
		if (side === 3) d = `M${cx - s / 2},${cy + off} L${cx - s / 2 - len * 0.5},${cy + off} L${cx - s / 2 - len},${cy + off * 1.8}`;
		return d;
	});
	return (
		<g>
			{lines.map((d, i) => (
				<g key={i}>
					<path d={d} stroke="#c9ccc6" strokeWidth={5} fill="none" strokeLinecap="round" />
					<path d={d} stroke={GL} strokeWidth={5} fill="none" strokeLinecap="round" strokeDasharray="40 400" strokeDashoffset={-((t * 260 + i * 53) % 440)} opacity={glow} />
				</g>
			))}
			<rect x={cx - s / 2 - 10} y={cy - s / 2 - 10} width={s + 20} height={s + 20} rx={20} fill="#1d2120" />
			{Array.from({length: 7}).map((_, i) => {
				const o = (i - 3) * s * 0.13;
				return (
					<g key={i} fill="#9fa39d">
						<rect x={cx + o - 5} y={cy - s / 2 - 30} width={10} height={20} rx={3} />
						<rect x={cx + o - 5} y={cy + s / 2 + 10} width={10} height={20} rx={3} />
						<rect x={cx - s / 2 - 30} y={cy + o - 5} width={20} height={10} rx={3} />
						<rect x={cx + s / 2 + 10} y={cy + o - 5} width={20} height={10} rx={3} />
					</g>
				);
			})}
			<rect x={cx - s * 0.3} y={cy - s * 0.3} width={s * 0.6} height={s * 0.6} rx={14} fill={G} filter="url(#glow)" opacity={0.4 + 0.6 * glow} />
			<rect x={cx - s * 0.3} y={cy - s * 0.3} width={s * 0.6} height={s * 0.6} rx={14} fill="url(#greenT)" opacity={0.5 + 0.5 * glow} />
			<rect x={cx - s * 0.18} y={cy - s * 0.18} width={s * 0.36} height={s * 0.36} rx={8} fill="none" stroke="rgba(255,255,255,0.6)" strokeWidth={3} />
		</g>
	);
};

/* ---------- Window ---------- */
export const Window: React.FC<{open: number; cx: number; cy: number; w: number; h: number}> = ({open, cx, cy, w, h}) => {
	const sh = w / 2;
	return (
		<g>
			<rect x={cx - w / 2 - 40} y={cy - h / 2 - 40} width={w + 80} height={h + 80} rx={24} fill="url(#wood)" />
			<rect x={cx - w / 2} y={cy - h / 2} width={w} height={h} fill="#1a1d1b" />
			<g opacity={open}>
				<rect x={cx - w / 2} y={cy - h / 2} width={w} height={h} fill="#e9fbf0" />
				<ellipse cx={cx} cy={cy} rx={w * 0.6 * open} ry={h * 0.6} fill="url(#light)" />
			</g>
			{/* shutters rotate open (scaleX) */}
			<g transform={`translate(${cx - w / 2},0) scale(${1 - 0.85 * open},1) translate(${-(cx - w / 2)},0)`}>
				<rect x={cx - w / 2} y={cy - h / 2} width={sh} height={h} fill="#3a3d3b" stroke="#252826" strokeWidth={6} />
				<rect x={cx - w / 2 + 24} y={cy - h / 2 + 24} width={sh - 48} height={h - 48} fill="#2f3230" />
			</g>
			<g transform={`translate(${cx + w / 2},0) scale(${1 - 0.85 * open},1) translate(${-(cx + w / 2)},0)`}>
				<rect x={cx} y={cy - h / 2} width={sh} height={h} fill="#3a3d3b" stroke="#252826" strokeWidth={6} />
				<rect x={cx + 24} y={cy - h / 2 + 24} width={sh - 48} height={h - 48} fill="#2f3230" />
			</g>
		</g>
	);
};

/* ---------- House of blocks ---------- */
export const BlockHouse: React.FC<{x: number; y: number; at: number; bs?: number}> = ({x, y, at, bs = 70}) => {
	const t = useT();
	const blocks: [number, number][] = [];
	for (let r = 0; r < 3; r++) for (let c = 0; c < 4; c++) blocks.push([c, r]);
	const all = blocks;
	const roofP = prog(t, at + blocks.length * 0.06, 0.5);
	return (
		<g>
			<Shadow cx={x + bs * 2} y={y + 10} w={bs * 5.5} />
			{all.map(([c, r], i) => {
				const p = prog(t, at + i * 0.06, 0.4);
				if (p <= 0) return null;
				const bx = x + c * bs;
				const by = y - (r + 1) * bs - (1 - p) * 220;
				const isDoor = r === 0 && (c === 1 || c === 2);
				return (
					<g key={i} opacity={p}>
						<rect x={bx + 2} y={by + 2} width={bs - 4} height={bs - 4} rx={8} fill={isDoor ? '#0d4d2e' : 'url(#greenL)'} />
						<rect x={bx + 2} y={by + 2} width={bs - 4} height={12} rx={6} fill="rgba(255,255,255,0.22)" />
						{!isDoor && <circle cx={bx + bs / 2} cy={by + bs / 2} r={bs * 0.14} fill="rgba(255,255,255,0.18)" />}
					</g>
				);
			})}
			{roofP > 0 && (
				<g opacity={roofP} transform={`translate(0,${-(1 - roofP) * 200})`}>
					<path d={`M${x - 30},${y - 3 * bs} L${x + 2 * bs},${y - 3 * bs - bs * 1.9} L${x + 4 * bs + 30},${y - 3 * bs} Z`} fill="url(#greenR)" />
					<path d={`M${x - 30},${y - 3 * bs} L${x + 2 * bs},${y - 3 * bs - bs * 1.9} L${x + 2 * bs},${y - 3 * bs} Z`} fill="url(#greenL)" />
					<rect x={x + 2.9 * bs} y={y - 3 * bs - bs * 1.5} width={bs * 0.45} height={bs * 0.9} fill="#0d4d2e" />
				</g>
			)}
		</g>
	);
};

/* ---------- Paper plane ---------- */
export const Plane: React.FC<{x: number; y: number; rot: number; s?: number}> = ({x, y, rot, s = 1}) => (
	<g transform={`translate(${x},${y}) rotate(${rot}) scale(${s})`}>
		<path d="M-60,0 L70,-40 L-10,30 Z" fill="#2a2f2d" />
		<path d="M-10,30 L70,-40 L5,10 Z" fill="#111" />
		<path d="M-60,0 L5,10 L-10,30 Z" fill="#4a504d" />
	</g>
);

export {easeInOut};
