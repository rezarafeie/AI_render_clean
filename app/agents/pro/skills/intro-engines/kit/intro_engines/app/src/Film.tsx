import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame} from 'remotion';
import {Fonts, useFonts, clamp, lerp, seg, eo5, eio, Jaraqe} from './lib';
import {EditorUI, UI_W, UI_H} from './EditorUI';
import plates from './plates.json';

const FPS = 24, W = 1920, H = 1080;
export const FILM_DUR = 47;

// homography: map (0,0)-(w,h) rect to quad TL,TR,BR,BL → css matrix3d
const homography = (w: number, h: number, q: number[][]) => {
	const src = [[0, 0], [w, 0], [w, h], [0, h]];
	const A: number[][] = [], b: number[] = [];
	for (let i = 0; i < 4; i++) {
		const [x, y] = src[i], [X, Y] = q[i];
		A.push([x, y, 1, 0, 0, 0, -x * X, -y * X]); b.push(X);
		A.push([0, 0, 0, x, y, 1, -x * Y, -y * Y]); b.push(Y);
	}
	// gaussian elimination
	const n = 8, M = A.map((r, i) => [...r, b[i]]);
	for (let c = 0; c < n; c++) {
		let p = c;
		for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
		[M[c], M[p]] = [M[p], M[c]];
		for (let r = 0; r < n; r++) if (r !== c) { const f = M[r][c] / M[c][c]; for (let k = c; k <= n; k++) M[r][k] -= f * M[c][k]; }
	}
	const hh = M.map((r, i) => r[n] / r[i]);
	return `matrix3d(${hh[0]},${hh[3]},0,${hh[6]},${hh[1]},${hh[4]},0,${hh[7]},0,0,1,0,${hh[2]},${hh[5]},0,1)`;
};

type Plate = {screen: number[][]};
const P = plates as Record<string, Plate>;

type Shot = {a: number; b: number; plate: string; plate2?: [string, number, number][]; s0: number; s1: number; dx?: number; dy?: number; ox?: number; oy?: number; u0: number; u1: number; blur?: number; uiDim?: number; fg?: string};
// narrative clock for the UI: see EditorUI
const SHOTS: Shot[] = [
	{a: 0, b: 4.6, plate: 'wide_day', s0: 1.0, s1: 1.07, ox: 0.52, oy: 0.62, u0: 0, u1: 0.5, uiDim: 0.85},
	{a: 4.6, b: 10.0, plate: 'screen_day', s0: 1.02, s1: 1.07, dx: -18, ox: 0.5, oy: 0.4, u0: 0.4, u1: 5.6, uiDim: 0.92},
	{a: 10.0, b: 13.2, plate: 'mascot_dusk', s0: 1.03, s1: 1.09, dx: 14, ox: 0.4, oy: 0.55, u0: 6, u1: 8, blur: 15, fg: 'mascot_dusk_fg'},
	{a: 13.2, b: 18.2, plate: 'med_day', s0: 1.02, s1: 1.08, ox: 0.6, oy: 0.4, u0: 7.4, u1: 12.6, uiDim: 0.92},
	{a: 18.2, b: 25.2, plate: 'wide_day', plate2: [['wide_dusk', 19.2, 21.0], ['wide_night', 22.0, 23.8]], s0: 1.07, s1: 1.16, ox: 0.52, oy: 0.62, u0: 12, u1: 16},
	{a: 25.2, b: 30.2, plate: 'screen_night', s0: 1.07, s1: 1.02, dx: 16, ox: 0.5, oy: 0.4, u0: 15.5, u1: 21},
	{a: 30.2, b: 34.4, plate: 'low_night', s0: 1.02, s1: 1.09, dx: -12, ox: 0.7, oy: 0.4, u0: 20.6, u1: 24.9},
	{a: 34.4, b: 38.6, plate: 'med_night', s0: 1.08, s1: 1.02, ox: 0.6, oy: 0.4, u0: 24.3, u1: 28},
	{a: 38.6, b: 43.0, plate: 'wide_morning', s0: 1.1, s1: 1.02, ox: 0.52, oy: 0.62, u0: 28, u1: 30, uiDim: 0.85},
];
export const FILM_EV: {t: number; k: string; g?: number}[] = [
	{t: 0.2, k: 'room', g: 0.35}, {t: 5.3, k: 'keys', g: 0.5}, {t: 8.2, k: 'keys', g: 0.4}, {t: 9.55, k: 'key', g: 0.7}, {t: 10.0, k: 'swell', g: 0.35},
	{t: 13.2, k: 'tick', g: 0.3}, {t: 18.2, k: 'room', g: 0.4}, {t: 22.0, k: 'key', g: 0.5}, {t: 25.2, k: 'room', g: 0.35}, {t: 30.2, k: 'swell', g: 0.3},
	{t: 34.0, k: 'ding', g: 0.5}, {t: 38.6, k: 'swell', g: 0.5}, {t: 43.0, k: 'pop', g: 0.4},
];
const SUBS: [number, number, string][] = [
	[1.3, 4.3, 'با یک جمله شروع شد.'],
	[19.0, 22.6, 'بعد، خودش کار کرد.'],
	[30.8, 33.8, 'تو خواب بودی.'],
	[35.4, 38.2, 'تا صبح، آماده بود.'],
];

const Layer: React.FC<{sh: Shot; t: number}> = ({sh, t}) => {
	const p = (t - sh.a) / (sh.b - sh.a);
	const s = lerp(sh.s0, sh.s1, p);
	const sway = `translate(${Math.sin(t * 0.7) * 2.2 + (sh.dx ?? 0) * (p - 0.5)}px, ${Math.cos(t * 0.53) * 1.6 + (sh.dy ?? 0) * (p - 0.5)}px)`;
	const u = lerp(sh.u0, sh.u1, p);
	const q = P[sh.plate].screen;
	return (
		<AbsoluteFill style={{transform: `${sway} scale(${s})`, transformOrigin: `${(sh.ox ?? 0.5) * 100}% ${(sh.oy ?? 0.5) * 100}%`}}>
			<Img src={staticFile(`film/${sh.plate}.jpg`)} style={{position: 'absolute', width: W, height: H}} />
			{(sh.plate2 ?? []).map(([n, a, b]) => <Img key={n} src={staticFile(`film/${n}.jpg`)} style={{position: 'absolute', width: W, height: H, opacity: eio(seg(t, a, b))}} />)}
			<div style={{position: 'absolute', left: 0, top: 0, width: UI_W, height: UI_H, transformOrigin: '0 0', transform: homography(UI_W, UI_H, q), filter: `blur(${sh.blur ?? 0}px) brightness(${sh.uiDim ?? 1})`, overflow: 'hidden'}}>
				<EditorUI u={u} />
				<div style={{position: 'absolute', inset: 0, background: 'linear-gradient(115deg, rgba(255,255,255,.07) 0%, rgba(255,255,255,0) 38%)'}} />
			</div>
			{sh.fg && <Img src={staticFile(`film/${sh.fg}.png`)} style={{position: 'absolute', width: W, height: H}} />}
		</AbsoluteFill>
	);
};

export const Film: React.FC = () => {
	useFonts();
	const f = useCurrentFrame();
	const t = f / FPS;
	const i = SHOTS.findIndex((s) => t >= s.a && t < s.b);
	const sh = SHOTS[i];
	const X = 0.5; // cross-dissolve
	const prev = i > 0 && t - sh.a < X ? SHOTS[i - 1] : null;
	const sub = SUBS.find(([a, b]) => t >= a && t < b);
	const endT = t - 43;
	return (
		<AbsoluteFill style={{background: '#000'}}>
			<Fonts />
			{sh && (
				<>
					{prev && <Layer sh={prev} t={t} />}
					<AbsoluteFill style={{opacity: prev ? eio((t - sh.a) / X) : 1}}><Layer sh={sh} t={t} /></AbsoluteFill>
					<AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 45%, rgba(0,0,0,0) 55%, rgba(0,0,0,.38) 100%)'}} />
				</>
			)}
			{sub && (
				<div style={{position: 'absolute', left: 0, right: 0, bottom: 118, textAlign: 'center', fontFamily: 'Pey', fontWeight: 400, fontSize: 50, color: '#f4efe6', direction: 'rtl', textShadow: '0 2px 18px rgba(0,0,0,.65)', opacity: Math.min(seg(t, sub[0], sub[0] + 0.5), 1 - seg(t, sub[1] - 0.5, sub[1]))}}>{sub[2]}</div>
			)}
			{t >= 39.6 && t < 43 && (
				<div style={{position: 'absolute', left: 0, right: 0, bottom: 100, textAlign: 'center', direction: 'rtl', color: '#fffaf0', textShadow: '0 2px 22px rgba(0,0,0,.7)', opacity: Math.min(seg(t, 39.6, 40.3), 1 - seg(t, 42.5, 43))}}>
					<div style={{fontFamily: 'Pey', fontWeight: 900, fontSize: 78}}>ادیتور جی‌پی‌تی</div>
					<div style={{fontFamily: 'Pey', fontWeight: 400, fontSize: 36, marginTop: 4}}>از یک جمله، تا ویدیوی آماده.</div>
				</div>
			)}
			{t >= 43 && (
				<AbsoluteFill style={{background: '#f2eee5', opacity: seg(t, 43, 43.5)}}>
					<svg width={W} height={H} style={{position: 'absolute'}}><Jaraqe x={960} y={420 - Math.abs(Math.sin(clamp((endT - 0.6) / 0.5) * Math.PI)) * 30} s={1.7} col="#f7a600" happy={endT > 1.1 && endT < 2.2} blink={0} /></svg>
					<div style={{position: 'absolute', left: 0, right: 0, top: 480, textAlign: 'center', direction: 'rtl', color: '#171512'}}>
						<div style={{fontFamily: 'Pey', fontWeight: 400, fontSize: 84, opacity: seg(endT, 0.5, 1.0), transform: `translateY(${(1 - eo5(seg(endT, 0.5, 1.1))) * 24}px)`}}>همه‌چیز با یک پیام شروع می‌شود.</div>
						<div style={{fontFamily: 'Vaz', fontWeight: 500, fontSize: 28, color: '#8b8579', marginTop: 40, opacity: seg(endT, 1.3, 1.8)}}>اتاق، نور، صفحه‌نمایش و تدوینِ این فیلم با کد ساخته شده است.</div>
						<div style={{fontFamily: 'VazL', fontWeight: 500, fontSize: 30, color: '#e8590c', marginTop: 24, letterSpacing: 3, opacity: seg(endT, 1.7, 2.2)}}>editor.rafiei.co</div>
					</div>
				</AbsoluteFill>
			)}
			<AbsoluteFill style={{background: '#000', opacity: Math.max(1 - seg(t, 0, 0.8), seg(t, FILM_DUR - 0.6, FILM_DUR))}} />
		</AbsoluteFill>
	);
};
