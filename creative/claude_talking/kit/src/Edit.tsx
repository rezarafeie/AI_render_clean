import React from 'react';
import {AbsoluteFill, OffthreadVideo, Sequence, staticFile, useCurrentFrame, continueRender, delayRender} from 'remotion';
import data from './data.json';
import {coralText, FA, H, INK, MONEY, NASKH, SERIF, SPLIT, W, prog, useSp, useT} from './ui';
import {OVERLAYS, GP} from './overlays';
import {GRAPHICS as WRITTEN} from './graphics';

/* The fixed engine of the talking-head reel: the speaker (face-tracked, punch on every jump cut), three layouts (full / split / graphic), the zoom-blur
   entry of every beat and the word-by-word captions. Everything per video comes from data.json and graphics.tsx. */

type Beat = {w: number; start: number; end: number; layout: 'full' | 'split' | 'graphic'; g: string | null; zoom: number | null; bg?: string; captions?: boolean; capY?: number};
const beats = data.beats as Beat[];
const cuts = data.cuts as number[];
const KW = data.kw as Record<string, number>;
const FPS = data.fps as number;
const SRC_W = data.video.w as number;
const SRC_H = data.video.h as number;
const GRAPHICS: Record<string, React.FC<GP>> = {...OVERLAYS, ...(WRITTEN as Record<string, React.FC<GP>>)};

const faceX = (t: number) => {
	const face = data.face as number[];
	if (!face.length) return SRC_W / 2;
	const i = t / data.faceStep;
	const a = Math.max(0, Math.min(face.length - 1, Math.floor(i)));
	const b = Math.min(face.length - 1, a + 1);
	return face[a] + (face[b] - face[a]) * (i - a);
};
const beatAt = (t: number) => beats.find((b) => t >= b.start && t < b.end) ?? beats[beats.length - 1];

/* -------- speaker video -------- */
const Speaker: React.FC<{b: Beat; mode: 'full' | 'split'}> = ({b, mode}) => {
	const f = useCurrentFrame();
	const abs = b.start + f / FPS;
	const startFrom = Math.round(b.start * FPS);
	const nCuts = cuts.filter((c) => c > b.start + 0.05 && c <= abs).length;      // alternate punch-in on every jump cut hides the jump
	const alt = nCuts % 2 === 1 ? 1.1 : 1;
	const push = 1 + 0.025 * (f / FPS);                                              // a slow live-camera push inside the beat
	const cx = faceX(abs) + (data.faceDx as number);
	const boxW = W;
	const boxH = mode === 'full' ? H : H - SPLIT;
	const base = mode === 'full' ? Math.max(boxW / SRC_W, boxH / SRC_H) : Math.max(boxW / SRC_W, boxH / (SRC_H * 0.74));
	const S = base * (b.zoom ?? (mode === 'full' ? 1.15 : 1)) * alt * push;
	const faceTargetY = mode === 'full' ? 700 : 330;
	const vw = SRC_W * S;
	const vh = SRC_H * S;
	const tx = Math.min(0, Math.max(boxW - vw, boxW / 2 - cx * S));
	const ty = Math.min(0, Math.max(boxH - vh, faceTargetY - (data.faceY as number) * S));
	return (
		<div style={{position: 'absolute', left: 0, top: 0, width: boxW, height: boxH, overflow: 'hidden'}}>
			<OffthreadVideo src={staticFile('cut.mp4')} startFrom={startFrom} muted style={{position: 'absolute', left: tx, top: ty, width: vw, height: vh, maxWidth: 'none'}} />
		</div>
	);
};

/* -------- backgrounds -------- */
const Leaves: React.FC = () => {
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

const isDark = (b: Beat) => b.bg === 'dark';
const Background: React.FC<{b: Beat}> = ({b}) => {
	if (isDark(b)) return <AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 40%, #1d1d20 0%, #0a0a0b 75%)'}} />;
	const color = b.bg === 'beige' ? '#E6DCCF' : b.layout === 'graphic' ? '#F1EEE8' : '#F3F1EC';
	return (
		<AbsoluteFill style={{background: `radial-gradient(ellipse 90% 70% at 50% 35%, #FFFFFF 0%, ${color} 70%)`}}>
			<Leaves />
		</AbsoluteFill>
	);
};

/* -------- beat -------- */
const BeatView: React.FC<{b: Beat; first: boolean}> = ({b, first}) => {
	const t = useT();
	const dur = b.end - b.start;
	const k = (i: number) => (KW[String(i)] ?? b.start) - b.start;
	const G = b.g ? GRAPHICS[b.g] : null;
	const sp = useSp(0, 16, 0.8);
	const e = first ? 1 : prog(t, 0, 0.22);                                           // every beat enters with a quick zoom-blur
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
		return (
			<AbsoluteFill style={wrap}>
				<Background b={b} />
				{G && <G k={k} dur={dur} />}
			</AbsoluteFill>
		);
	}
	return (
		<AbsoluteFill style={wrap}>
			<Background b={b} />
			<div style={{position: 'absolute', left: 0, top: 0, width: W, height: SPLIT}}>{G && <G k={k} dur={dur} />}</div>
			<div
				style={{
					position: 'absolute', left: 0, top: SPLIT, width: W, height: H - SPLIT, borderRadius: '64px 64px 0 0', overflow: 'hidden',
					boxShadow: '0 -20px 60px rgba(0,0,0,0.18)', transform: first ? undefined : `translateY(${(1 - sp) * 60}px)`,
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
	const c = (data.caps as Cap[]).find((x) => t >= x.s && t < x.e);
	if (!c) return null;
	const b = beatAt(t);
	if (b.captions === false) return null;
	const local = t - c.s;
	const s = Math.min(1, local / 0.12);
	const pop = 0.72 + 0.28 * (1 - Math.pow(1 - s, 3)) + (s >= 1 ? 0.04 * Math.exp(-(local - 0.12) * 18) : 0);
	const dark = b.layout === 'full' || isDark(b);
	const y = b.layout === 'full' ? 1500 : b.layout === 'split' ? SPLIT - 70 : b.capY ?? 1500;
	const base = b.layout === 'full' ? 96 : 84;
	return (
		<div style={{position: 'absolute', left: 40, width: W - 80, top: y, transform: `translateY(-50%) scale(${pop})`, display: 'flex', flexWrap: 'wrap', justifyContent: 'center', alignItems: 'baseline', gap: 22, direction: 'rtl', opacity: Math.min(1, local / 0.05)}}>
			{c.words.map((w, i) => {
				const lat = isLatin(w.t);
				const style: React.CSSProperties = w.money
					? {color: MONEY, fontFamily: lat ? SERIF : NASKH, fontWeight: 700, fontSize: base * 1.3, textShadow: '0 0 30px rgba(59,227,122,0.55), 0 6px 18px rgba(0,0,0,0.6), 0 0 3px rgba(0,0,0,0.9)', WebkitTextStroke: dark ? '2px rgba(0,0,0,0.55)' : undefined}
					: w.key
						? dark
							? {color: '#fff', fontFamily: lat ? SERIF : NASKH, fontStyle: lat ? 'italic' : 'normal', fontWeight: lat ? 900 : 700, fontSize: base * 1.25, textShadow: '0 6px 22px rgba(0,0,0,0.6)'}
							: {...coralText, fontFamily: lat ? SERIF : NASKH, fontStyle: lat ? 'italic' : 'normal', fontWeight: lat ? 900 : 700, fontSize: base * 1.25, filter: 'drop-shadow(0 4px 10px rgba(232,112,90,0.25))'}
						: {color: dark ? '#fff' : INK, fontFamily: lat ? SERIF : FA, fontStyle: lat ? 'italic' : 'normal', fontWeight: 900, fontSize: base, textShadow: dark ? '0 4px 18px rgba(0,0,0,0.65), 0 0 2px rgba(0,0,0,0.8)' : 'none'};
				return (
					<span key={i} style={{lineHeight: 1.2, whiteSpace: 'nowrap', ...style}}>
						{w.t}
					</span>
				);
			})}
		</div>
	);
};

const AR = 'unicode-range:U+0600-06FF,U+0750-077F,U+200C-200E,U+FB50-FDFF,U+FE70-FEFF;';
const LA = 'unicode-range:U+0000-00FF,U+2000-206F;';
const face = (family: string, weight: number, file: string, extra = '') =>
	`@font-face{font-family:'${family}';font-weight:${weight};${extra}src:url('${staticFile('fonts/' + file)}') format('woff2');}`;
const FACES = [
	...[600, 700, 800, 900].map((w) => face('Vazirmatn', w, `vazirmatn-arabic-${w}-normal.woff2`, AR)),
	...[600, 700, 800, 900].map((w) => face('Vazirmatn', w, `vazirmatn-latin-${w}-normal.woff2`, LA)),
	face('Noto Naskh Arabic', 700, 'noto-naskh-arabic-arabic-700-normal.woff2'),
	face('Playfair Display', 800, 'playfair-display-latin-800-italic.woff2', 'font-style:italic;'),
	face('Playfair Display', 900, 'playfair-display-latin-900-italic.woff2', 'font-style:italic;'),
].join('\n');

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
			.then(() => continueRender(h))
			.catch(() => continueRender(h));
	}, [h]);
	return (
		<AbsoluteFill style={{background: '#000'}}>
			<style>{FACES}</style>
			{beats.map((b, i) => {
				const from = Math.round(b.start * FPS);
				const d = Math.max(1, Math.round(b.end * FPS) - from);
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
