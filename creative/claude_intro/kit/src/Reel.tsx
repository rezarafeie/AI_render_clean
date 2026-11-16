// Intro engine 2 — Reel (1920x1080, 60 fps): a fifteen-second motion showreel; one giant word or one animation principle per scene, every cut on the
// music's beat grid B(n) (measured from the bed by creative/claude_intro: TIMING.grid). All words come from content.json.
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {CONTENT, TIMING, Fonts, useFonts, clamp, lerp, seg, eo, eo5, ei, eio, back, spring, rnd, fa, fit, markPath, markScale} from './lib';

const FPS = 60, W = 1920, H = 1080;
const C = {navy: '#100e24', orange: '#ff5a1f', blue: '#2b3bff', lime: '#d9ff3d', lilac: '#b9a8ff', cream: '#efe9dc'};
const G = (TIMING.grid ?? {first: 0.48, period: 0.469}) as {first: number; period: number};        // (defaults only so the module loads in the other intro kinds)
const PER = G.period, END = (TIMING.total ?? 15) as number;
const K: any = CONTENT;
const LABELS: string[] = K.labels ?? ['پیش‌بینی', 'تایپ', 'شکل', 'زمان‌بندی', 'عمق', 'سرعت', 'دامنه', 'امضا'];

// scene table
const B = (n: number) => G.first + PER * (n - 1); // the music's beat grid
const SC = [
	{id: 'count', a: 0, b: B(4), n: 1, label: LABELS[0]},
	{id: 'w1', a: B(4), b: B(5), n: 2, label: LABELS[1]},
	{id: 'w2', a: B(5), b: B(6), n: 2, label: LABELS[1]},
	{id: 'w3', a: B(6), b: B(7), n: 2, label: LABELS[1]},
	{id: 'shape', a: B(7), b: B(13), n: 3, label: LABELS[2]},
	{id: 'ease', a: B(13), b: B(17), n: 4, label: LABELS[3]},
	{id: 'depth', a: B(17), b: B(20), n: 5, label: LABELS[4]},
	{id: 'tunnel', a: B(20), b: B(25), n: 6, label: LABELS[5]},
	{id: 'curve', a: B(25), b: B(26), n: 7, label: LABELS[6]},
	{id: 'speed', a: B(26), b: B(27), n: 7, label: LABELS[6]},
	{id: 'taste', a: B(27), b: B(29), n: 7, label: LABELS[6]},
	{id: 'sign', a: B(29), b: END, n: 8, label: LABELS[7]},
];
const Big: React.FC<{children: string; col: string; size?: number; y?: number; style?: React.CSSProperties; dot?: string}> = ({children, col, size = 560, y = 0, style, dot}) => (
	<div style={{position: 'absolute', left: 0, right: 0, top: '50%', transform: `translateY(-50%) translateY(${y}px)`, textAlign: 'center', fontFamily: 'Rokh', fontWeight: 900, fontSize: fit(children + (dot ? '.' : ''), 'Rokh', 900, size, 1640), lineHeight: 1.25, color: col, direction: 'rtl', whiteSpace: 'nowrap', ...style}}>{children}{dot ? <span style={{color: dot}}>.</span> : null}</div>
);

const Hud: React.FC<{t: number; dark: boolean; sc: (typeof SC)[number]}> = ({t, dark, sc}) => {
	const col = dark ? 'rgba(239,233,220,.72)' : 'rgba(16,14,36,.72)';
	const f = Math.floor(t * FPS);
	const tc = `00:00:${String(Math.floor(f / FPS)).padStart(2, '0')}:${String(f % FPS).padStart(2, '0')}`;
	const st: React.CSSProperties = {position: 'absolute', fontFamily: 'Vaz, VazL', fontWeight: 500, fontSize: 17, color: col, letterSpacing: 1};
	return (
		<>
			<div style={{...st, right: 56, top: 44, direction: 'rtl'}}>{K.hud ?? K.brand}</div>
			<div style={{...st, left: 56, top: 44, fontFamily: 'VazL', fontVariantNumeric: 'tabular-nums'}}>{tc}</div>
			<div style={{...st, right: 56, bottom: 44, direction: 'rtl'}}>{fa(String(sc.n).padStart(2, '0'))} / ۰۸ &nbsp;&nbsp; {sc.label}</div>
			<div style={{position: 'absolute', left: 56, bottom: 52, display: 'flex', gap: 8}}>
				{Array.from({length: 8}).map((_, i) => (
					<div key={i} style={{width: 34, height: 3, background: col, opacity: i < sc.n ? 1 : 0.25}} />
				))}
			</div>
		</>
	);
};

// ---------- scenes ----------
const Count: React.FC<{t: number}> = ({t}) => {
	const P = PER, T0 = G.first - PER;
	const k = (t - T0) / P, ph = k - Math.floor(k); // 0..1 each bounce, impact at ph=0
	const h = 4 * ph * (1 - ph); // 0..1 parabola
	const gy = 760, top = 250;
	const y = gy - 46 - h * (gy - top - 46);
	const sq = ph < 0.08 ? 1 - ph / 0.08 : ph > 0.94 ? (ph - 0.94) / 0.06 : 0;
	const n = 3 - Math.floor(clamp((t - G.first) / P + 1, 0, 3));
	const num = t < G.first ? null : Math.max(1, n);
	const since = t < G.first ? 9 : (t - G.first) % P;
	const cx = 960;
	return (
		<AbsoluteFill style={{background: C.navy}}>
			<svg width={W} height={H}>
				<circle cx={cx} cy={470} r={250} fill="none" stroke={C.lilac} strokeOpacity={0.35} strokeWidth={2} />
				<circle cx={cx} cy={470} r={250} fill="none" stroke={C.lilac} strokeWidth={3} strokeDasharray={`${1571 * clamp(t / (G.first + 3 * P))} 1571`} transform={`rotate(-90 ${cx} 470)`} />
				{num && (
					<text x={cx} y={600} textAnchor="middle" fontFamily="Rokh" fontWeight={900} fontSize={360} fill="#2a2466" transform={`translate(${cx},470) scale(${1 + 0.25 * Math.exp(-since * 14)}) translate(${-cx},-470)`}>
						{fa(num)}
					</text>
				)}
				<line x1={420} x2={1500} y1={gy} y2={gy} stroke={C.cream} strokeOpacity={0.3} strokeWidth={2} />
				<ellipse cx={cx} cy={gy} rx={70 - h * 40} ry={9 - h * 5} fill="none" stroke={C.cream} strokeOpacity={0.5 * (1 - h)} strokeWidth={3} />
				{[6, 5, 4, 3, 2, 1].map((i) => {
					const kk = (t - i * 0.016 - T0) / P, p2 = kk - Math.floor(kk), h2 = 4 * p2 * (1 - p2);
					return <circle key={i} cx={cx} cy={gy - 46 - h2 * (gy - top - 46)} r={46 - i * 3} fill={C.orange} opacity={0.5 - i * 0.07} />;
				})}
				<ellipse cx={cx} cy={y + sq * 22} rx={46 * (1 + sq * 0.5)} ry={46 * (1 - sq * 0.45) * (1 + (1 - h) * 0.0 + Math.abs(0.5 - ph) * 0.24)} fill={C.orange} />
			</svg>
			<div style={{position: 'absolute', right: 420, top: 790, fontFamily: 'Vaz', fontWeight: 500, fontSize: 18, color: 'rgba(239,233,220,.6)', direction: 'rtl', letterSpacing: 1}}>{K.count_note ?? ''} {num ? fa(num) : '…'}</div>
		</AbsoluteFill>
	);
};

const Word: React.FC<{t: number; d: number; word: string; bg: string; col: string; mode: 'slam' | 'rise' | 'smear'; note?: string; underline?: string}> = ({t, d, word, bg, col, mode, note, underline}) => {
	const u = clamp(t / 0.22);
	const out = seg(t, d - 0.1, d);
	let tr = '';
	if (mode === 'slam') tr = `scale(${lerp(1.5, 1, eo5(u)) + out * 0.04})`;
	if (mode === 'rise') tr = `translateY(${(1 - eo5(u)) * 320}px)`;
	if (mode === 'smear') tr = `translateX(${(1 - eo5(u)) * 900}px) skewX(${(1 - eo5(u)) * 18}deg)`;
	const ghosts = mode === 'smear' ? [1, 2, 3, 4, 5] : [];
	return (
		<AbsoluteFill style={{background: bg, overflow: 'hidden'}}>
			{ghosts.map((g) => {
				const ug = clamp((t - g * 0.018) / 0.22);
				return <Big key={g} col={col} style={{transform: `translateY(-50%) translateX(${(1 - eo5(ug)) * 900 + g * 26 * (1 - u)}px)`, opacity: 0.16 * (1 - u * 0.4), color: C.cream}}>{word}</Big>;
			})}
			<div style={{position: 'absolute', inset: 0, transform: tr, transformOrigin: '50% 50%'}}>
				<Big col={col}>{word}</Big>
			</div>
			{underline && <div style={{position: 'absolute', left: W / 2 - 250, top: 800, height: 16, width: 500 * eo5(seg(t, 0.1, 0.4)), background: underline}} />}
			{note && <div style={{position: 'absolute', left: 0, right: 0, top: 905, textAlign: 'center', fontFamily: 'Vaz', fontWeight: 500, fontSize: 21, color: col, opacity: seg(t, 0.2, 0.35), direction: 'rtl', letterSpacing: 0.5}}>{note}</div>}
		</AbsoluteFill>
	);
};

const Shape: React.FC<{t: number}> = ({t}) => {
	const i = t < 2 * PER ? 0 : t < 4 * PER ? 1 : 2;
	const lt = t - [0, 2 * PER, 4 * PER][i];
	const s = back(clamp(lt / 0.3), 2.2);
	const rot = t * 40;
	const names: string[] = K.shapes ?? ['', '', ''];
	const arcs = [
		{r: 330, a: 80, w: 5, c: C.lime, sp: 1.6},
		{r: 395, a: 50, w: 4, c: C.lilac, sp: -1.1},
		{r: 270, a: 110, w: 3, c: '#fff', sp: 0.7},
	];
	return (
		<AbsoluteFill style={{background: C.blue}}>
			<svg width={W} height={H}>
				<defs>
					<pattern id="plus" width={64} height={64} patternUnits="userSpaceOnUse">
						<path d="M32,24 v16 M24,32 h16" stroke="#fff" strokeOpacity={0.22} strokeWidth={2} transform={i === 1 ? 'rotate(45 32 32)' : ''} />
					</pattern>
				</defs>
				<rect width={W} height={H} fill="url(#plus)" />
				<g transform={`translate(960,540)`}>
					{arcs.map((a, k) => {
						const c = 2 * Math.PI * a.r;
						return <circle key={k} r={a.r} fill="none" stroke={a.c} strokeWidth={a.w} strokeLinecap="round" strokeDasharray={`${(c * a.a) / 360} ${(c * (180 - a.a)) / 360}`} transform={`rotate(${rot * a.sp + k * 70})`} opacity={0.9} />;
					})}
					{Array.from({length: 24}).map((_, k) => (
						<line key={k} x1={0} y1={-445} x2={0} y2={-470 - (k % 6 === 0 ? 14 : 0)} stroke="#fff" strokeOpacity={0.5} strokeWidth={2} transform={`rotate(${k * 15 + rot * 0.3})`} />
					))}
					<g transform={`scale(${s}) rotate(${(1 - eo(clamp(lt / 0.5))) * -50 + (i === 1 ? 6 : 0)})`}>
						<g transform="translate(12,16)" opacity={0.25}>
							{i === 0 && <circle r={165} fill="#000" />}
							{i === 1 && <rect x={-150} y={-150} width={300} height={300} rx={10} fill="#000" />}
							{i === 2 && <path d="M0,-180 L175,135 L-175,135 Z" fill="#000" />}
						</g>
						{i === 0 && <circle r={165} fill={C.lime} />}
						{i === 1 && <rect x={-150} y={-150} width={300} height={300} rx={10} fill={C.orange} />}
						{i === 2 && <path d="M0,-180 L175,135 L-175,135 Z" fill={C.lilac} />}
					</g>
				</g>
			</svg>
			<div style={{position: 'absolute', right: 150, top: 470, fontFamily: 'Rokh', fontWeight: 900, fontSize: fit(names[i] ?? '', 'Rokh', 900, 120, 420), color: '#fff', direction: 'rtl', whiteSpace: 'nowrap', transform: `translateY(${(1 - eo5(clamp(lt / 0.3))) * 60}px)`, opacity: clamp(lt / 0.12)}}>{names[i]}</div>
			<div style={{position: 'absolute', left: 150, top: 520, fontFamily: 'Vaz', fontWeight: 500, fontSize: 22, color: 'rgba(255,255,255,.8)', direction: 'rtl'}}>{fa(i + 1)} / ۳{K.shapes_caption ? ` — ${K.shapes_caption}` : ''}</div>
		</AbsoluteFill>
	);
};

const Ease: React.FC<{t: number}> = ({t}) => {
	const m = eio(seg(t, 0.35, 1.0)); // morph linear → S
	const gx = 180, gy = 300, gw = 560, gh = 560;
	const p1 = [lerp(0.33, 0.85, m), lerp(0.33, 0.0, m)], p2 = [lerp(0.66, 0.15, m), lerp(0.66, 1.0, m)];
	const X = (u: number) => gx + u * gw, Y = (v: number) => gy + gh - v * gh;
	const d = `M${X(0)},${Y(0)} C${X(p1[0])},${Y(p1[1])} ${X(p2[0])},${Y(p2[1])} ${X(1)},${Y(1)}`;
	const play = (t * 0.9) % 1;
	const bez = (u: number, a: number, b: number) => 3 * (1 - u) * (1 - u) * u * a + 3 * (1 - u) * u * u * b + u * u * u;
	// solve x(u)=play
	let u = play;
	for (let k = 0; k < 6; k++) u -= (bez(u, p1[0], p2[0]) - play) / Math.max(0.05, 3 * (1 - u) * (1 - u) * p1[0] + 6 * (1 - u) * u * (p2[0] - p1[0]) + 3 * u * u * (1 - p2[0]));
	u = clamp(u);
	const ease = bez(u, p1[1], p2[1]);
	const rows = [
		{n: (K.ease_rows ?? ['خطی', 'نرم', 'فنری'])[0], v: play, c: C.navy},
		{n: (K.ease_rows ?? ['خطی', 'نرم', 'فنری'])[1], v: ease, c: C.orange},
		{n: (K.ease_rows ?? ['خطی', 'نرم', 'فنری'])[2], v: spring(play * 1.6, 11, 5), c: C.blue},
	];
	const tl = eo5(clamp(t / 0.35));
	return (
		<AbsoluteFill style={{background: C.cream}}>
			<div style={{position: 'absolute', right: 180, top: 130, fontFamily: 'Rokh', fontWeight: 700, fontSize: fit(K.claim_1 ?? '', 'Rokh', 700, 84, 1500), color: C.navy, direction: 'rtl', whiteSpace: 'nowrap', clipPath: `inset(-20% 0 -30% ${(1 - tl) * 100}%)`}}>{K.claim_1}</div>
			<svg width={W} height={H} style={{position: 'absolute'}}>
				<rect x={gx} y={gy} width={gw} height={gh} fill="none" stroke={C.navy} strokeOpacity={0.5} strokeWidth={2} />
				{[1, 2, 3, 4, 5].map((k) => (
					<g key={k} stroke={C.navy} strokeOpacity={0.1}>
						<line x1={gx + (gw * k) / 6} x2={gx + (gw * k) / 6} y1={gy} y2={gy + gh} />
						<line y1={gy + (gh * k) / 6} y2={gy + (gh * k) / 6} x1={gx} x2={gx + gw} />
					</g>
				))}
				<line x1={X(0)} y1={Y(0)} x2={X(p1[0])} y2={Y(p1[1])} stroke={C.orange} strokeWidth={2} />
				<line x1={X(1)} y1={Y(1)} x2={X(p2[0])} y2={Y(p2[1])} stroke={C.orange} strokeWidth={2} />
				<path d={d} fill="none" stroke={C.navy} strokeWidth={6} strokeLinecap="round" />
				<circle cx={X(p1[0])} cy={Y(p1[1])} r={10} fill={C.orange} />
				<circle cx={X(p2[0])} cy={Y(p2[1])} r={10} fill={C.orange} />
				<circle cx={X(0)} cy={Y(0)} r={8} fill={C.navy} />
				<circle cx={X(1)} cy={Y(1)} r={8} fill={C.navy} />
				<line x1={X(play)} x2={X(play)} y1={gy} y2={gy + gh} stroke={C.blue} strokeWidth={2} />
				<circle cx={X(play)} cy={Y(ease)} r={9} fill={C.blue} />
				{rows.map((r, k) => {
					const y0 = 380 + k * 170, x0 = 960, x1 = 1640;
					return (
						<g key={k}>
							<line x1={x0} x2={x1 + 90} y1={y0 + 100} y2={y0 + 100} stroke={C.navy} strokeOpacity={0.25} strokeWidth={2} />
							{k > 0 && [1, 2, 3].map((g) => <rect key={g} x={lerp(x0, x1, clamp(k === 1 ? ease : r.v)) - g * 14 * Math.abs(k === 1 ? Math.sin(play * Math.PI) : 0.4)} y={y0 + 6} width={84} height={84} rx={10} fill={r.c} opacity={0.12} />)}
							<rect x={lerp(x0, x1, r.v)} y={y0 + 6} width={84} height={84} rx={10} fill={r.c} />
						</g>
					);
				})}
			</svg>
			{rows.map((r, k) => (
				<div key={k} style={{position: 'absolute', right: 190, top: 345 + k * 170, fontFamily: 'Vaz', fontWeight: 500, fontSize: 20, color: C.navy, opacity: 0.7, direction: 'rtl'}}>{r.n}</div>
			))}
			<div style={{position: 'absolute', left: 180, top: 880, fontFamily: 'VazL', fontWeight: 500, fontSize: 18, color: C.navy, opacity: 0.6}}>cubic-bezier({p1[0].toFixed(2)}, {p1[1].toFixed(2)}, {p2[0].toFixed(2)}, {p2[1].toFixed(2)})</div>
			<div style={{position: 'absolute', right: 1200, top: 880, fontFamily: 'Vaz', fontWeight: 500, fontSize: 18, color: C.navy, opacity: 0.6, direction: 'rtl'}}>{K.claim_1_note ?? ''}</div>
		</AbsoluteFill>
	);
};

const NX = 56, NY = 20;
const PAL = [C.orange, C.lime, C.lilac, C.cream, '#5b6bff'];
const Depth: React.FC<{t: number}> = ({t}) => {
	const m = eio(seg(t, 0.15, 0.95));
	const cam = t * 0.5;
	return (
		<AbsoluteFill style={{background: C.navy}}>
			<svg width={W} height={H}>
				{Array.from({length: NX * NY}).map((_, i) => {
					const ix = i % NX, iy = Math.floor(i / NX);
					const gx = (ix / (NX - 1) - 0.5) * 2, gz = iy / (NY - 1);
					const wave = Math.sin(gx * 4.2 + t * 3.2 + gz * 3) * 0.16 + Math.sin(gx * 9 - t * 2 + gz * 7) * 0.05;
					const z = 0.5 + gz * 1.5;
					const px = 960 + ((gx + Math.sin(cam) * 0.1) / z) * 1250;
					const py = 560 + ((0.38 + wave) / z) * 620 - 150;
					const sx = 960 + (rnd(i) - 0.5) * 2600 * (1 + rnd(i + 7)), sy = 540 + (rnd(i + 3) - 0.5) * 1600 * (1 + rnd(i + 9));
					const x = lerp(sx, px, m), y = lerp(sy, py, m);
					const r = lerp(2 + rnd(i + 5) * 3, 7.5 / z, m);
					return <circle key={i} cx={x} cy={y} r={r} fill={PAL[(ix + iy * 2) % 5]} opacity={lerp(0.5, clamp(1.25 - gz * 0.6), m) * clamp(t / 0.2)} />;
				})}
			</svg>
			<div style={{position: 'absolute', left: 0, right: 0, top: 44, textAlign: 'center', fontFamily: 'Vaz', fontWeight: 500, fontSize: 17, color: 'rgba(239,233,220,.6)', direction: 'rtl', letterSpacing: 1}}>{K.field_label ?? ''} {fa(NX)} × {fa(NY)}</div>
			<div style={{position: 'absolute', right: 150, top: 150, fontFamily: 'Rokh', fontWeight: 700, fontSize: fit(K.claim_2 ?? '', 'Rokh', 700, 84, 1500), color: C.cream, direction: 'rtl', whiteSpace: 'nowrap', clipPath: `inset(-20% 0 -30% ${(1 - eo5(seg(t, 0.7, 1.1))) * 100}%)`}}>{K.claim_2}</div>
		</AbsoluteFill>
	);
};

const Tunnel: React.FC<{t: number}> = ({t}) => {
	const cols = [C.lime, C.blue, C.lilac, C.navy, C.orange, C.cream];
	const N = 13;
	const sp = t * 2.3 + t * t * 0.5;
	const bl: string[] = K.blink ?? ['', ''];
	const word = t < PER ? null : t < 3 * PER ? bl[0] : bl[1];
	const lt = t < 3 * PER ? t - PER : t - 3 * PER;
	return (
		<AbsoluteFill style={{background: C.lime, overflow: 'hidden'}}>
			<svg width={W} height={H}>
				<g transform="translate(960,540)">
					{Array.from({length: N}).map((_, k) => {
						const idx = k + Math.floor(sp);
						const depth = k + 1 - (sp % 1);
						const s = Math.pow(0.66, depth - 6.5);
						const size = 520 * s;
						if (size < 2) return null;
						return <rect key={k} x={-size / 2} y={-size / 2} width={size} height={size} rx={size * 0.22} fill={cols[(((N * 6 - idx) % 6) + 6) % 6]} transform={`rotate(${depth * 17 + t * 40})`} />;
					})}
				</g>
			</svg>
			{word && (
				<div style={{position: 'absolute', inset: 0, mixBlendMode: 'difference', transform: `scale(${lerp(1.35, 1, eo5(clamp(lt / 0.18)))})`}}>
					<Big col="#fff" size={600}>{word}</Big>
				</div>
			)}
		</AbsoluteFill>
	);
};

const Curve: React.FC<{t: number; d: number}> = ({t}) => {
	const u = eo5(clamp(t / 0.3));
	const L = 1500;
	return (
		<AbsoluteFill style={{background: C.cream, overflow: 'hidden'}}>
			<div style={{position: 'absolute', inset: 0, transform: `translateX(${(1 - u) * -500}px)`, filter: `blur(${(1 - u) * 14}px)`}}>
				<Big col={C.navy} size={520}>{(K.words ?? [])[0] ?? ''}</Big>
			</div>
			<svg width={W} height={H} style={{position: 'absolute'}}>
				<path d="M330,860 C700,930 1050,880 1280,620 C1400,480 1480,330 1560,210" fill="none" stroke={C.orange} strokeWidth={22} strokeLinecap="round" strokeDasharray={`${L} ${L}`} strokeDashoffset={L * (1 - eo5(seg(t, 0.08, 0.5)))} />
			</svg>
		</AbsoluteFill>
	);
};
const Speed: React.FC<{t: number}> = ({t}) => {
	const u = eo5(clamp(t / 0.25));
	return (
		<AbsoluteFill style={{background: C.orange, overflow: 'hidden'}}>
			{Array.from({length: 22}).map((_, i) => {
				const y = rnd(i) * H, w = 300 + rnd(i + 4) * 900, sp = 2600 + rnd(i + 2) * 3000;
				const x = ((rnd(i + 9) * 4000 + t * sp) % (W + w * 2)) - w;
				return <div key={i} style={{position: 'absolute', left: W - x - w, top: y, width: w, height: 5 + rnd(i + 1) * 12, background: C.cream, opacity: 0.85, borderRadius: 8}} />;
			})}
			<div style={{position: 'absolute', inset: 0, transform: `translateX(${(1 - u) * 1100}px) skewX(${-14 + (1 - u) * -16}deg)`}}>
				{[3, 2, 1].map((g) => <Big key={g} col={C.navy} size={540} style={{opacity: 0.14, transform: `translateY(-50%) translateX(${g * 34}px)`}}>{(K.words ?? [])[1] ?? ''}</Big>)}
				<Big col={C.navy} size={540}>{(K.words ?? [])[1] ?? ''}</Big>
			</div>
		</AbsoluteFill>
	);
};
const Taste: React.FC<{t: number}> = ({t}) => {
	const u = clamp(t / 0.16);
	return (
		<AbsoluteFill style={{background: C.navy}}>
			<div style={{position: 'absolute', inset: 0, transform: `scale(${lerp(1.25, 1, eo5(u))})`}}>
				<Big col={C.cream} size={520} dot={C.orange}>{(K.words ?? [])[2] ?? ''}</Big>
			</div>
		</AbsoluteFill>
	);
};
const Sign: React.FC<{t: number}> = ({t}) => {
	const up = eo5(clamp(t / 0.55));
	const dt = t - 0.05;
	const drop = dt < 0 ? -1 : dt < 0.42 ? ei(dt / 0.42) : 1 - Math.abs(Math.sin((dt - 0.42) * 9)) * 0.22 * Math.exp(-(dt - 0.42) * 5);
	return (
		<AbsoluteFill style={{background: C.navy}}>
			<div style={{position: 'absolute', left: 0, right: 0, top: 330, height: 330, overflow: 'hidden'}}>
				<div style={{textAlign: 'center', fontFamily: 'Rokh', fontWeight: 900, fontSize: fit(K.brand ?? '', 'Rokh', 900, 200, 1500), lineHeight: '330px', color: C.cream, direction: 'rtl', whiteSpace: 'nowrap', transform: `translateY(${(1 - up) * 340}px)`}}>{K.brand}</div>
			</div>
			<svg width={W} height={H} style={{position: 'absolute'}}>
				{drop >= 0 && <g transform={`translate(318,${lerp(-40, 590, drop)}) rotate(${t * 140})`}><path d={markPath(34, 0.3)} fill={C.orange} transform={`scale(${markScale(34)})`} /></g>}
				<line x1={1920 - 470} x2={1920 - 470 - 980 * eo5(seg(t, 0.5, 1.0))} y1={690} y2={690} stroke={C.cream} strokeOpacity={0.35} strokeWidth={2} />
			</svg>
			<div style={{position: 'absolute', right: 470, top: 712, fontFamily: 'Vaz', fontWeight: 500, fontSize: 22, color: 'rgba(239,233,220,.8)', direction: 'rtl', opacity: seg(t, 0.7, 0.95), letterSpacing: 0.5}}>{K.tagline ?? ''}</div>
			<div style={{position: 'absolute', left: 470, top: 712, fontFamily: 'VazL', fontWeight: 500, fontSize: 22, color: C.orange, opacity: seg(t, 0.9, 1.15), letterSpacing: 1}}>{K.url ?? ''}</div>
		</AbsoluteFill>
	);
};

export const Reel: React.FC = () => {
	useFonts();
	const f = useCurrentFrame();
	const t = f / FPS;
	const sc = SC.find((s) => t >= s.a && t < s.b) ?? SC[SC.length - 1];
	const lt = t - sc.a, d = sc.b - sc.a;
	const dark = ['count', 'w2', 'depth', 'taste', 'sign'].includes(sc.id);
	let body: React.ReactNode = null;
	if (sc.id === 'count') body = <Count t={lt} />;
	if (sc.id === 'w1') body = <Word t={lt} d={d} word={(K.opener ?? [])[0] ?? ''} bg={C.orange} col={C.navy} mode="slam" underline={C.navy} />;
	if (sc.id === 'w2') body = <Word t={lt} d={d} word={(K.opener ?? [])[1] ?? ''} bg={C.navy} col={C.cream} mode="rise" underline={C.orange} />;
	if (sc.id === 'w3') body = <Word t={lt} d={d} word={(K.opener ?? [])[2] ?? ''} bg={C.orange} col={C.navy} mode="smear" note={K.opener_note} />;
	if (sc.id === 'shape') body = <Shape t={lt} />;
	if (sc.id === 'ease') body = <Ease t={lt} />;
	if (sc.id === 'depth') body = <Depth t={lt} />;
	if (sc.id === 'tunnel') body = <Tunnel t={lt} />;
	if (sc.id === 'curve') body = <Curve t={lt} d={d} />;
	if (sc.id === 'speed') body = <Speed t={lt} />;
	if (sc.id === 'taste') body = <Taste t={lt} />;
	if (sc.id === 'sign') body = <Sign t={lt} />;
	// 2-frame flash on hard cuts
	const flash = lt < 2 / FPS && sc.a > 0 ? 0.18 : 0;
	return (
		<AbsoluteFill style={{background: C.navy}}>
			<Fonts />
			{body}
			<Hud t={t} dark={dark} sc={sc} />
			{flash > 0 && <AbsoluteFill style={{background: '#fff', opacity: flash}} />}
		</AbsoluteFill>
	);
};
