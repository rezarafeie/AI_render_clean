import React from 'react';
import {random} from 'remotion';
import {Coin, Sparkle, prog, useT} from './ui';

export type GP = {k: (i: number) => number; dur: number};

/* Fixed overlays for "full" beats (the speaker stays visible under them). */
/* ---------- coins burst (full overlay) ---------- */
export const GCoins: React.FC<GP & {seed?: string}> = ({seed = 'c'}) => {
	const t = useT();
	const n = 28;
	return (
		<div style={{position: 'absolute', inset: 0, pointerEvents: 'none'}}>
			<div
				style={{
					position: 'absolute',
					inset: 0,
					background: `radial-gradient(circle at 50% 75%, rgba(245,184,61,${0.45 * Math.max(0, 1 - t * 2)}) 0%, rgba(245,184,61,0) 60%)`,
				}}
			/>
			{Array.from({length: n}).map((_, i) => {
				const vx = (random(seed + 'x' + i) - 0.5) * 1300;
				const vy = -1900 - random(seed + 'y' + i) * 1200;
				const d = random(seed + 'd' + i) * 0.18;
				const tt = Math.max(0, t - d);
				if (tt <= 0) return null;
				const x = 540 + vx * tt;
				const y = 1950 + vy * tt + 2600 * tt * tt;
				const s = 60 + random(seed + 's' + i) * 60;
				return (
					<div key={i} style={{position: 'absolute', left: x - s / 2, top: y - s / 2, transform: `rotate(${tt * 400 * (i % 2 ? 1 : -1)}deg)`}}>
						<Coin s={s} spin={Math.cos(tt * 12 + i)} />
					</div>
				);
			})}
		</div>
	);
};

/* ---------- sparkle overlay ---------- */
export const GSparkle: React.FC<GP> = () => {
	const t = useT();
	const pts = [
		[250, 520, 0, 90], [840, 450, 0.08, 70], [190, 900, 0.15, 55], [900, 820, 0.05, 100], [330, 300, 0.2, 50], [760, 1100, 0.12, 60], [560, 260, 0.1, 80],
	];
	return (
		<div style={{position: 'absolute', inset: 0}}>
			{pts.map(([x, y, d, s], i) => {
				const p = prog(t, d, 0.35);
				const tw = 0.7 + 0.3 * Math.sin(t * 9 + i);
				return (
					<div key={i} style={{position: 'absolute', left: x - s / 2, top: y - s / 2, transform: `scale(${p * tw}) rotate(${t * 90}deg)`, opacity: p, filter: 'drop-shadow(0 0 18px rgba(255,255,255,0.9))'}}>
						<Sparkle s={s} color={i % 3 === 0 ? '#FFE7A3' : '#fff'} />
					</div>
				);
			})}
		</div>
	);
};


export const OVERLAYS: Record<string, React.FC<GP>> = {
	coins: GCoins,
	coins2: (p) => <GCoins {...p} seed="z" />,
	sparkle: GSparkle,
};
