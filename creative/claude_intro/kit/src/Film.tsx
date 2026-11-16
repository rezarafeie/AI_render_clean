// Intro engine 4 — Film3D (1920x1080, 24 fps): one desk from day to night; the person types one sentence, leaves, and the product finishes the work by
// morning. The plates are Cycles renders of a Blender scene (kit/b3d/scene.py, cached per scene parameters); the product's interface is live on the laptop
// screen through a homography. No narrator: four short subtitles. Shots, subtitles and the end card come from content.json.
import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame} from 'remotion';
import {CONTENT, TIMING, Fonts, useFonts, clamp, lerp, seg, eo5, eio, fit, Mascot} from './lib';
import {ProductUI, UI_W, UI_H} from './ProductUI';
import plates from './plates.json';

const FPS = 24, W = 1920, H = 1080;
const FILM_DUR: number = TIMING.total;
const END: number = TIMING.end;          // the end card starts here
const E: any = CONTENT.end ?? {};

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
const SHOTS: Shot[] = TIMING.shots ?? [];        // each shot shows a span u0..u1 of the interface's narrative clock (see ProductUI)
const SUBS: [number, number, string][] = TIMING.subs ?? [];

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
				<ProductUI u={u} />
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
	const endT = t - END;
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
			{t >= END - 3.4 && t < END && (
				<div style={{position: 'absolute', left: 0, right: 0, bottom: 100, textAlign: 'center', direction: 'rtl', color: '#fffaf0', textShadow: '0 2px 22px rgba(0,0,0,.7)', opacity: Math.min(seg(t, END - 3.4, END - 2.7), 1 - seg(t, END - 0.5, END))}}>
					<div style={{fontFamily: 'Pey', fontWeight: 900, fontSize: 78}}>{CONTENT.brand}</div>
					<div style={{fontFamily: 'Pey', fontWeight: 400, fontSize: 36, marginTop: 4}}>{E.line ?? ''}</div>
				</div>
			)}
			{t >= END && (
				<AbsoluteFill style={{background: '#f2eee5', opacity: seg(t, END, END + 0.5)}}>
					<svg width={W} height={H} style={{position: 'absolute'}}><Mascot x={960} y={420 - Math.abs(Math.sin(clamp((endT - 0.6) / 0.5) * Math.PI)) * 30} s={1.7} happy={endT > 1.1 && endT < 2.2} blink={0} /></svg>
					<div style={{position: 'absolute', left: 0, right: 0, top: 480, textAlign: 'center', direction: 'rtl', color: '#171512'}}>
						<div style={{fontFamily: 'Pey', fontWeight: 400, fontSize: fit(E.moral ?? '', 'Pey', 400, 84, 1700), whiteSpace: 'nowrap', opacity: seg(endT, 0.5, 1.0), transform: `translateY(${(1 - eo5(seg(endT, 0.5, 1.1))) * 24}px)`}}>{E.moral}</div>
						<div style={{fontFamily: 'Vaz', fontWeight: 500, fontSize: 28, color: '#8b8579', marginTop: 40, opacity: seg(endT, 1.3, 1.8)}}>{E.credit ?? ''}</div>
						<div style={{fontFamily: 'VazL', fontWeight: 500, fontSize: 30, color: '#e8590c', marginTop: 24, letterSpacing: 3, opacity: seg(endT, 1.7, 2.2)}}>{CONTENT.url}</div>
					</div>
				</AbsoluteFill>
			)}
			<AbsoluteFill style={{background: '#000', opacity: Math.max(1 - seg(t, 0, 0.8), seg(t, FILM_DUR - 0.6, FILM_DUR))}} />
		</AbsoluteFill>
	);
};
