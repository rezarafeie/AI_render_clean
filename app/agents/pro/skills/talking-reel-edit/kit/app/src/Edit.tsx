import React from 'react';
import {AbsoluteFill, OffthreadVideo, Sequence, staticFile, useCurrentFrame, useVideoConfig, continueRender, delayRender, interpolate} from 'remotion';
import '@fontsource/vazirmatn/600.css';
import '@fontsource/vazirmatn/700.css';
import '@fontsource/vazirmatn/800.css';
import '@fontsource/vazirmatn/900.css';
import '@fontsource/noto-naskh-arabic/700.css';
import '@fontsource/playfair-display/800-italic.css';
import '@fontsource/playfair-display/900-italic.css';
import data from './data.json';
import {CORAL, coralText, FA, H, INK, MONEY, NASKH, SERIF, SPLIT, W, clamp, prog, useSp, useT} from './ui';
import {GRAPHICS} from './graphics';

type Beat = {w: number; start: number; end: number; layout: 'full' | 'split' | 'graphic'; g: string | null; zoom: number | null};
const beats = data.beats as Beat[];
const cuts = data.cuts as number[];
const KW = data.kw as Record<string, number>;
const FPS = 30;

const faceX = (t: number) => {
	const i = t / data.faceStep;
	const a = Math.max(0, Math.min(data.face.length - 1, Math.floor(i)));
	const b = Math.min(data.face.length - 1, a + 1);
	return data.face[a] + (data.face[b] - data.face[a]) * (i - a);
};
const layoutAt = (t: number) => (beats.find((b) => t >= b.start && t < b.end) ?? beats[beats.length - 1]).layout;
const beatAt = (t: number) => beats.find((b) => t >= b.start && t < b.end) ?? beats[beats.length - 1];

/* -------- speaker video -------- */
const Speaker: React.FC<{b: Beat; mode: 'full' | 'split'}> = ({b, mode}) => {
	const f = useCurrentFrame();
	const abs = b.start + f / FPS;
	const startFrom = Math.round(b.start * FPS);
	// alternate punch on every jump cut for energy
	const nCuts = cuts.filter((c) => c > b.start + 0.05 && c <= abs).length;
	const alt = nCuts % 2 === 1 ? 1.1 : 1;
	const push = 1 + 0.025 * (f / FPS);
	const cx = faceX(abs) + 55;
	let S: number, boxW: number, boxH: number, faceTargetY: number;
	if (mode === 'full') {
		boxW = W;
		boxH = H;
		S = (H / 1080) * (b.zoom ?? 1.15) * alt * push;
		faceTargetY = 700;
	} else {
		boxW = W;
		boxH = H - SPLIT;
		S = (boxH / 800) * (b.zoom ?? 1) * alt * push;
		faceTargetY = 330;
	}
	const vw = 1920 * S;
	const vh = 1080 * S;
	const tx = Math.min(0, Math.max(boxW - vw, boxW / 2 - cx * S));
	const ty = Math.min(0, Math.max(boxH - vh, faceTargetY - data.faceY * S));
	return (
		<div style={{position: 'absolute', left: 0, top: 0, width: boxW, height: boxH, overflow: 'hidden'}}>
			<OffthreadVideo src={staticFile('cut.mp4')} startFrom={startFrom} muted style={{position: 'absolute', left: tx, top: ty, width: vw, height: vh, maxWidth: 'none'}} />
		</div>
	);
};

/* -------- backgrounds -------- */
const Leaves: React.FC<{dark?: boolean}> = () => {
	const t = useT();
	return (
		<svg width={W} height={1100} style={{position: 'absolute', left: 0, top: 0, opacity: 0.08, filter: 'blur(14px)'}}>
			<g transform={`translate(${880 + Math.sin(t * 0.7) * 10},-60) rotate(${20 + Math.sin(t * 0.9) * 3})`} fill="#2d3a2a">
				{Array.from({length: 7}).map((_, i) => (
					<path key={i} d="M0,0 C60,80 70,220 0,330 C-70,220 -60,80 0,0 Z" transform={`rotate(${-70 + i * 22}) translate(0,40)`} />
				))}
			</g>
			<g transform={`translate(${60 + Math.sin(t * 0.5) * 8},120) rotate(${-30 + Math.sin(t * 0.8) * 2})`} fill="#2d3a2a">
				{Array.from({length: 5}).map((_, i) => (
					<path key={i} d="M0,0 C40,60 50,160 0,240 C-50,160 -40,60 0,0 Z" transform={`rotate(${-50 + i * 25}) translate(0,30)`} />
				))}
			</g>
		</svg>
	);
};

const LightBg: React.FC<{color?: string}> = ({color = '#F3F1EC'}) => (
	<AbsoluteFill style={{background: `radial-gradient(ellipse 90% 70% at 50% 35%, #FFFFFF 0%, ${color} 70%)`}}>
		<Leaves />
	</AbsoluteFill>
);

/* -------- beat -------- */
const BeatView: React.FC<{b: Beat; first: boolean}> = ({b, first}) => {
	const t = useT();
	const dur = b.end - b.start;
	const k = (i: number) => (KW[String(i)] ?? b.start) - b.start;
	const G = b.g ? GRAPHICS[b.g] : null;
	const sp = useSp(0, 16, 0.8);
	// entry: quick zoom-blur in
	const e = first ? 1 : prog(t, 0, 0.22);
	const wrap: React.CSSProperties = {transform: `scale(${1 + (1 - e) * 0.09})`, filter: e < 1 ? `blur(${(1 - e) * 14}px)` : undefined};
	if (b.layout === 'full') {
		return (
			<AbsoluteFill style={wrap}>
				<Speaker b={b} mode="full" />
				<AbsoluteFill style={{background: 'linear-gradient(180deg, rgba(0,0,0,0) 55%, rgba(0,0,0,0.45) 100%)'}} />
				{G && <G k={k} dur={dur} />}
			</AbsoluteFill>
		);
	}
	if (b.layout === 'graphic') {
		const dark = b.g === 'saas';
		return (
			<AbsoluteFill style={wrap}>
				{dark ? (
					<AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 40%, #1d1d20 0%, #0a0a0b 75%)'}} />
				) : (
					<LightBg color={b.g === 'product' ? '#E6DCCF' : '#F1EEE8'} />
				)}
				{G && <G k={k} dur={dur} />}
			</AbsoluteFill>
		);
	}
	// split
	return (
		<AbsoluteFill style={wrap}>
			<LightBg />
			<div style={{position: 'absolute', left: 0, top: 0, width: W, height: SPLIT}}>{G && <G k={k} dur={dur} />}</div>
			<div
				style={{
					position: 'absolute',
					left: 0,
					top: SPLIT,
					width: W,
					height: H - SPLIT,
					borderRadius: '64px 64px 0 0',
					overflow: 'hidden',
					boxShadow: '0 -20px 60px rgba(0,0,0,0.18)',
					transform: first ? undefined : `translateY(${(1 - sp) * 60}px)`,
				}}
			>
				<Speaker b={b} mode="split" />
			</div>
		</AbsoluteFill>
	);
};

/* -------- captions -------- */
type Cap = {s: number; e: number; words: {t: string; key: boolean; money: boolean}[]};
const isLatin = (s: string) => /[A-Za-z]/.test(s);

const Captions: React.FC = () => {
	const f = useCurrentFrame();
	const t = f / FPS;
	const caps = data.caps as Cap[];
	const c = caps.find((x) => t >= x.s && t < x.e);
	if (!c) return null;
	if (beatAt(t).g === 'saas') return null;
	const lay = layoutAt(t);
	const b = beatAt(t);
	const local = t - c.s;
	const s = Math.min(1, local / 0.12);
	const pop = 0.72 + 0.28 * (1 - Math.pow(1 - s, 3)) + (s >= 1 ? 0.04 * Math.exp(-(local - 0.12) * 18) : 0);
	const dark = lay === 'full' || b.g === 'saas';
	const y = lay === 'full' ? 1500 : lay === 'split' ? SPLIT - 70 : b.g === 'saas' ? 1500 : b.g === 'two' ? 1450 : 1500;
	const base = lay === 'full' ? 96 : 84;
	return (
		<div style={{position: 'absolute', left: 0, width: W, top: y, transform: `translateY(-50%) scale(${pop})`, display: 'flex', justifyContent: 'center', alignItems: 'baseline', gap: 22, direction: 'rtl', opacity: Math.min(1, local / 0.05)}}>
			{c.words.map((w, i) => {
				const lat = isLatin(w.t);
				const keyStyle: React.CSSProperties = w.money
					? {color: MONEY, fontFamily: lat ? SERIF : NASKH, fontWeight: 700, fontSize: base * 1.3, textShadow: '0 0 30px rgba(59,227,122,0.55), 0 6px 18px rgba(0,0,0,0.6), 0 0 3px rgba(0,0,0,0.9)', WebkitTextStroke: dark ? '2px rgba(0,0,0,0.55)' : undefined}
					: w.key
						? dark
							? {color: '#fff', fontFamily: lat ? SERIF : NASKH, fontStyle: lat ? 'italic' : 'normal', fontWeight: lat ? 900 : 700, fontSize: base * 1.25, textShadow: '0 6px 22px rgba(0,0,0,0.6)'}
							: {...coralText, fontFamily: lat ? SERIF : NASKH, fontStyle: lat ? 'italic' : 'normal', fontWeight: lat ? 900 : 700, fontSize: base * 1.25, filter: 'drop-shadow(0 4px 10px rgba(232,112,90,0.25))'}
						: {color: dark ? '#fff' : INK, fontFamily: lat ? SERIF : FA, fontStyle: lat ? 'italic' : 'normal', fontWeight: 900, fontSize: base, textShadow: dark ? '0 4px 18px rgba(0,0,0,0.65), 0 0 2px rgba(0,0,0,0.8)' : 'none'};
				return (
					<span key={i} style={{lineHeight: 1.2, whiteSpace: 'nowrap', ...keyStyle}}>
						{w.t}
					</span>
				);
			})}
		</div>
	);
};

export const Edit: React.FC = () => {
	const [h] = React.useState(() => delayRender('fonts'));
	React.useEffect(() => {
		Promise.all([
			document.fonts.load('900 40px Vazirmatn', 'سلام'),
			document.fonts.load('700 40px Vazirmatn', 'سلام'),
			document.fonts.load('700 40px "Noto Naskh Arabic"', 'سلام'),
			document.fonts.load('italic 900 40px "Playfair Display"', 'SaaS'),
			document.fonts.load('italic 800 40px "Playfair Display"', 'SaaS'),
		])
			.then(() => document.fonts.ready)
			.then(() => continueRender(h));
	}, [h]);
	return (
		<AbsoluteFill style={{background: '#000'}}>
			{beats.map((b, i) => {
				const from = Math.round(b.start * FPS);
				const d = Math.round(b.end * FPS) - from;
				return (
					<Sequence key={i} from={from} durationInFrames={d} name={`${b.layout}:${b.g ?? ''}`}>
						<BeatView b={b} first={i === 0} />
					</Sequence>
				);
			})}
			<Captions />
		</AbsoluteFill>
	);
};
