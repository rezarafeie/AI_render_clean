// Whiteboard engine: hand-drawn ink items, floating markers, eraser, magnets, camera.
import React from 'react';
// @ts-ignore
import rough from 'roughjs/bundled/rough.esm.js';
import {getLength, getPointAtLength, getTangentAtLength} from '@remotion/paths';

export const FPS = 30, W = 1080, H = 1920;
export const clamp = (x: number, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const lerp = (a: number, b: number, u: number) => a + (b - a) * u;
export const eio = (u: number) => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2);
export const eo = (u: number) => 1 - Math.pow(1 - u, 3);
// slow-fast-slow hand curve
export const hand = (u: number) => clamp(u - (Math.sin(2 * Math.PI * u) / (2 * Math.PI)) * 0.8);

export const INK = {k: '#23262c', b: '#2a5cb3', r: '#d0453a', g: '#2e8b57', o: '#e08a1e'};
export const HAND = 'Marhey', NUM = 'Doran';

const gen = rough.generator();
let SEED = 11;
type P = {d: string; len: number};
const toP = (dr: any, keepFill = true): P[] =>
	gen.toPaths(dr).filter((p: any) => keepFill || p.stroke !== 'none').map((p: any) => ({d: p.d, len: Math.max(1, getLength(p.d))}));
const O = (o: any = {}) => ({roughness: 0.9, bowing: 0.7, disableMultiStroke: true, preserveVertices: false, seed: SEED++, ...o});

// ----- shape builders (world coords) -----
export const S = {
	line: (x1: number, y1: number, x2: number, y2: number, o?: any) => toP(gen.line(x1, y1, x2, y2, O(o))),
	rect: (x: number, y: number, w: number, h: number, o?: any) => toP(gen.rectangle(x, y, w, h, O(o))),
	circle: (cx: number, cy: number, d: number, o?: any) => toP(gen.circle(cx, cy, d, O({curveStepCount: 11, ...o}))),
	ellipse: (cx: number, cy: number, w: number, h: number, o?: any) => toP(gen.ellipse(cx, cy, w, h, O(o))),
	poly: (pts: number[][], o?: any) => toP(gen.linearPath(pts, O(o))),
	closed: (pts: number[][], o?: any) => toP(gen.polygon(pts, O(o))),
	curve: (pts: number[][], o?: any) => toP(gen.curve(pts, O(o))),
	path: (d: string, o?: any) => toP(gen.path(d, O(o))),
	arc: (cx: number, cy: number, w: number, h: number, a0: number, a1: number, o?: any) => toP(gen.arc(cx, cy, w, h, a0, a1, false, O(o))),
	hatchRect: (x: number, y: number, w: number, h: number, o?: any) =>
		toP(gen.rectangle(x, y, w, h, O({stroke: 'none', fill: '#000', fillStyle: 'hachure', hachureGap: 16, fillWeight: 5, hachureAngle: -50, ...o}))),
	hatchCircle: (cx: number, cy: number, d: number, o?: any) =>
		toP(gen.circle(cx, cy, d, O({stroke: 'none', fill: '#000', fillStyle: 'hachure', hachureGap: 15, fillWeight: 5, hachureAngle: -45, ...o}))),
	hatchPoly: (pts: number[][], o?: any) =>
		toP(gen.polygon(pts, O({stroke: 'none', fill: '#000', fillStyle: 'hachure', hachureGap: 15, fillWeight: 5, ...o}))),
	// a smooth hand line through points with an arrow head at the end
	arrow: (pts: number[][], o: any = {}) => {
		const body = pts.length > 2 ? toP(gen.curve(pts, O(o))) : toP(gen.line(pts[0][0], pts[0][1], pts[1][0], pts[1][1], O(o)));
		const [a, b] = [pts[pts.length - 2], pts[pts.length - 1]];
		const ang = Math.atan2(b[1] - a[1], b[0] - a[0]), L = o.head ?? 34;
		const h1 = [b[0] - L * Math.cos(ang - 0.5), b[1] - L * Math.sin(ang - 0.5)];
		const h2 = [b[0] - L * Math.cos(ang + 0.5), b[1] - L * Math.sin(ang + 0.5)];
		return [...body, ...toP(gen.linearPath([h1, b, h2], O({...o, roughness: 0.5})))];
	},
	check: (x: number, y: number, s = 1, o?: any) => toP(gen.linearPath([[x - 28 * s, y], [x - 6 * s, y + 24 * s], [x + 34 * s, y - 30 * s]], O({roughness: 0.6, ...o}))),
	cross: (x: number, y: number, s = 1, o?: any) => [
		...toP(gen.line(x - 30 * s, y - 30 * s, x + 30 * s, y + 30 * s, O(o))),
		...toP(gen.line(x + 30 * s, y - 30 * s, x - 30 * s, y + 30 * s, O(o))),
	],
};
export const cat = (...a: P[][]) => a.flat();

// ----- items -----
export type Erase = {t0: number; dur: number; pts: number[][]; w: number};
export type Item = {
	id: number;
	k: 'path' | 'text' | 'dash';
	t0: number;
	dur: number;
	col: string;
	w?: number;
	paths?: P[];
	// text
	text?: string;
	x?: number; // right edge (rtl) or center
	y?: number; // baseline
	size?: number;
	font?: string;
	weight?: number;
	center?: boolean;
	op?: number;
	erase?: Erase;
	pen?: boolean; // default true
	snd?: string | null; // sound key, null = silent
	ox?: number;
	oy?: number;
};
let ID = 1;
export const mkPath = (t0: number, dur: number, col: string, paths: P[], o: Partial<Item> = {}): Item => ({id: ID++, k: 'path', t0, dur, col, paths, w: 7, ...o});
export const mkDash = (t0: number, dur: number, col: string, paths: P[], o: Partial<Item> = {}): Item => ({id: ID++, k: 'dash', t0, dur, col, paths, w: 9, ...o});
export const mkText = (t0: number, text: string, x: number, y: number, size: number, col: string, o: Partial<Item> = {}): Item => ({
	id: ID++,
	k: 'text',
	t0,
	dur: o.dur ?? clamp(0.18 + text.length * 0.045, 0.35, 1.6),
	col,
	text,
	x,
	y,
	size,
	font: HAND,
	weight: 600,
	...o,
});

// ----- text metrics -----
let fontsReady = false;
export const setFontsReady = () => (fontsReady = true);
const mcache = new Map<string, number>();
let cvs: CanvasRenderingContext2D | null = null;
export const measure = (text: string, size: number, font: string, weight = 600) => {
	const key = `${font}|${weight}|${size}|${text}`;
	const c = mcache.get(key);
	if (c !== undefined) return c;
	if (!cvs) cvs = document.createElement('canvas').getContext('2d');
	cvs!.font = `${weight} ${size}px ${font}`;
	const w = cvs!.measureText(text).width;
	if (fontsReady) mcache.set(key, w);
	return w;
};
const textBox = (it: Item) => {
	const w = measure(it.text!, it.size!, it.font!, it.weight);
	const right = it.center ? it.x! + w / 2 : it.x!;
	return {w, right, left: right - w};
};

// progress of an item at time t
export const prog = (it: Item, t: number) => hand(clamp((t - it.t0) / it.dur));

// pen tip of an item at progress p (world)
export const tipOf = (it: Item, p: number): [number, number] => {
	const [a, b] = tipLocal(it, p);
	return [a + (it.ox ?? 0), b + (it.oy ?? 0)];
};
const tipLocal = (it: Item, p: number): [number, number] => {
	if (it.k === 'text') {
		const {w, right} = textBox(it);
		const s = it.size!;
		return [right - w * p, it.y! - s * 0.32 + Math.sin(p * w * 0.11) * s * 0.18];
	}
	const ps = it.paths!;
	const L = ps.reduce((a, b) => a + b.len, 0);
	let d = p * L;
	for (const q of ps) {
		if (d <= q.len) {
			const pt = getPointAtLength(q.d, Math.max(0, Math.min(q.len, d)));
			return [pt.x, pt.y];
		}
		d -= q.len;
	}
	const last = ps[ps.length - 1];
	const pt = getPointAtLength(last.d, last.len);
	return [pt.x, pt.y];
};

// ----- rendering of one item -----
const PathsDraw: React.FC<{it: Item; p: number; dashed?: boolean}> = ({it, p, dashed}) => {
	const ps = it.paths!;
	const L = ps.reduce((a, b) => a + b.len, 0);
	let d = p * L;
	return (
		<>
			{ps.map((q, i) => {
				const loc = clamp(d / q.len);
				d -= q.len;
				if (loc <= 0) return null;
				return (
					<path
						key={i}
						d={q.d}
						fill="none"
						stroke={it.col}
						strokeWidth={it.w}
						strokeLinecap="round"
						strokeLinejoin="round"
						strokeDasharray={dashed ? undefined : `${q.len + 2} ${q.len + 2}`}
						strokeDashoffset={dashed ? undefined : (q.len + 2) * (1 - loc)}
					/>
				);
			})}
		</>
	);
};

export const ItemView: React.FC<{it: Item; t: number}> = ({it, t}) => {
	if (t < it.t0) return null;
	const p = prog(it, t);
	let body: React.ReactNode;
	if (it.k === 'text') {
		const {w, right, left} = textBox(it);
		const s = it.size!;
		const cid = `c${it.id}`;
		body = (
			<>
				<clipPath id={cid}>
					<rect x={right - (w + 20) * p - 6} y={it.y! - s * 1.6} width={(w + 20) * p + 12} height={s * 2.4} />
				</clipPath>
				<text
					x={left + w / 2}
					y={it.y}
					textAnchor="middle"
					fontFamily={it.font}
					fontWeight={it.weight}
					fontSize={s}
					fill={it.col}
					direction="rtl"
					clipPath={`url(#${cid})`}
				>
					{it.text}
				</text>
			</>
		);
	} else if (it.k === 'dash') {
		const mid = `m${it.id}`;
		body = (
			<>
				<mask id={mid} maskUnits="userSpaceOnUse" x={-5000} y={-5000} width={20000} height={20000}>
					<g style={{filter: 'none'}}>
						<PathsDraw it={{...it, col: '#fff', w: (it.w ?? 9) + 16}} p={p} />
					</g>
				</mask>
				<g mask={`url(#${mid})`}>
					{it.paths!.map((q, i) => (
						<path key={i} d={q.d} fill="none" stroke={it.col} strokeWidth={it.w} strokeLinecap="round" strokeDasharray="26 22" />
					))}
				</g>
			</>
		);
	} else body = <PathsDraw it={it} p={p} />;

	const op = it.op ?? 0.94;
	return <g transform={`translate(${it.ox ?? 0},${it.oy ?? 0})`}><Inner it={it} t={t} body={body} op={op} /></g>;
};
const Inner: React.FC<{it: Item; t: number; body: React.ReactNode; op: number}> = ({it, t, body, op}) => {
	if (it.erase && t >= it.erase.t0) {
		const e = it.erase;
		const ep = clamp((t - e.t0) / e.dur);
		const eid = `e${it.id}`;
		return (
			<>
				<g opacity={0.09}>{body}</g>
				<mask id={eid} maskUnits="userSpaceOnUse" x={-5000} y={-5000} width={20000} height={20000}>
					<rect x={-5000} y={-5000} width={20000} height={20000} fill="#fff" />
					<polyline points={partialPts(e.pts, ep).map((q) => q.join(',')).join(' ')} fill="none" stroke="#000" strokeWidth={e.w} strokeLinecap="round" strokeLinejoin="round" />
				</mask>
				<g mask={`url(#${eid})`} opacity={op}>
					{body}
				</g>
			</>
		);
	}
	return <g opacity={op}>{body}</g>;
};

// polyline helpers
const segLen = (pts: number[][]) => pts.slice(1).reduce((a, q, i) => a + Math.hypot(q[0] - pts[i][0], q[1] - pts[i][1]), 0);
export const partialPts = (pts: number[][], u: number) => {
	const L = segLen(pts) * u;
	const out = [pts[0]];
	let acc = 0;
	for (let i = 1; i < pts.length; i++) {
		const l = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
		if (acc + l >= L) {
			const v = (L - acc) / l;
			out.push([lerp(pts[i - 1][0], pts[i][0], v), lerp(pts[i - 1][1], pts[i][1], v)]);
			return out;
		}
		acc += l;
		out.push(pts[i]);
	}
	return out;
};
export const ptAt = (pts: number[][], u: number) => {
	const pp = partialPts(pts, clamp(u));
	return pp[pp.length - 1];
};
// zig-zag eraser path over a box
export const zig = (x0: number, y0: number, x1: number, y1: number, rows: number) => {
	const pts: number[][] = [];
	for (let i = 0; i <= rows; i++) {
		const y = lerp(y0, y1, i / rows);
		pts.push(i % 2 ? [x0, y] : [x1, y]);
	}
	return pts;
};

// ----- props -----
export const Marker: React.FC<{x: number; y: number; col: string; lift: number; s?: number}> = ({x, y, col, lift, s = 1}) => {
	const sh = 10 + lift * 60;
	const body = (fill: string, stroke: string, op = 1) => (
		<g opacity={op}>
			<path d="M0,0 L18,-10 L30,-8 L36,-20 L50,-14 L46,-2 L34,4 L18,10 Z" transform="rotate(0)" fill={fill} stroke={stroke} strokeWidth={2} />
		</g>
	);
	// marker drawn along +x axis then rotated so the nib (origin) points down-left
	const M = (shadow: boolean) => (
		<g transform={`rotate(-38)`}>
			{/* nib */}
			<path d="M0,0 L22,-9 L22,9 Z" fill={shadow ? '#000' : col} />
			<rect x={20} y={-15} width={26} height={30} rx={4} fill={shadow ? '#000' : '#3a3d42'} />
			{/* barrel */}
			<rect x={44} y={-24} width={170} height={48} rx={14} fill={shadow ? '#000' : '#f3f3f0'} stroke={shadow ? 'none' : '#b9bcc0'} strokeWidth={2.5} />
			<rect x={150} y={-24} width={22} height={48} fill={shadow ? '#000' : col} />
			{/* cap end */}
			<rect x={206} y={-27} width={60} height={54} rx={16} fill={shadow ? '#000' : col} />
			{!shadow && <rect x={58} y={-17} width={84} height={9} rx={4.5} fill="#fff" opacity={0.85} />}
		</g>
	);
	return (
		<g transform={`translate(${x},${y}) scale(${s * (1 + lift * 0.06)})`}>
			<g transform={`translate(${sh * 0.9},${sh * 0.7})`} opacity={0.16 - lift * 0.05} style={{filter: `blur(${4 + lift * 7}px)`}}>
				{M(true)}
			</g>
			<g transform={`translate(${-lift * 8},${-lift * 14})`}>{M(false)}</g>
		</g>
	);
};

export const Eraser: React.FC<{x: number; y: number; s?: number}> = ({x, y, s = 1}) => (
	<g transform={`translate(${x},${y}) rotate(-12) scale(${s})`}>
		<rect x={-110} y={-40} width={220} height={90} rx={14} fill="#000" opacity={0.15} transform="translate(14,16)" style={{filter: 'blur(6px)'}} />
		<rect x={-110} y={-10} width={220} height={52} rx={6} fill="#5b5f66" />
		<rect x={-110} y={-48} width={220} height={46} rx={12} fill="#2f6fb2" />
		<rect x={-96} y={-40} width={130} height={10} rx={5} fill="#fff" opacity={0.35} />
	</g>
);

export const MagnetCard: React.FC<{x: number; y: number; w: number; h: number; col: string; drop: number; children?: React.ReactNode}> = ({x, y, w, h, col, drop, children}) => {
	const lift = 1 - drop;
	const sc = 1 + lift * 0.25;
	return (
		<g transform={`translate(${x},${y}) scale(${sc})`} opacity={clamp(drop * 4)}>
			<rect x={-w / 2 + 10 + lift * 30} y={-h / 2 + 14 + lift * 40} width={w} height={h} rx={18} fill="#000" opacity={0.18 - lift * 0.08} style={{filter: `blur(${6 + lift * 10}px)`}} />
			<rect x={-w / 2} y={-h / 2} width={w} height={h} rx={18} fill="#fffdf6" stroke={col} strokeWidth={6} />
			<rect x={-w / 2} y={-h / 2} width={w} height={26} rx={12} fill={col} />
			<circle cx={0} cy={-h / 2 + 2} r={22} fill={col} stroke="#fff" strokeWidth={4} />
			<circle cx={-6} cy={-h / 2 - 5} r={6} fill="#fff" opacity={0.7} />
			{children}
		</g>
	);
};

export const Magnet: React.FC<{x: number; y: number; col: string; drop: number; icon?: React.ReactNode}> = ({x, y, col, drop, icon}) => {
	const lift = 1 - drop;
	return (
		<g transform={`translate(${x},${y}) scale(${1 + lift * 0.3})`} opacity={clamp(drop * 4)}>
			<circle cx={8 + lift * 25} cy={12 + lift * 35} r={50} fill="#000" opacity={0.2} style={{filter: 'blur(6px)'}} />
			<circle r={50} fill={col} />
			<circle r={50} fill="url(#gloss)" />
			{icon}
		</g>
	);
};

// ----- camera -----
export type Cam = {t: number; x: number; y: number; z: number};
export const camAt = (keys: Cam[], t: number) => {
	if (t <= keys[0].t) return keys[0];
	for (let i = 1; i < keys.length; i++) {
		const a = keys[i - 1], b = keys[i];
		if (t <= b.t) {
			const u = eio((t - a.t) / Math.max(1e-6, b.t - a.t));
			const iz = lerp(1 / a.z, 1 / b.z, u);
			return {t, x: lerp(a.x, b.x, u), y: lerp(a.y, b.y, u), z: 1 / iz};
		}
	}
	return keys[keys.length - 1];
};
export const w2s = (c: Cam, x: number, y: number) => [(x - c.x) * c.z + W / 2, (y - c.y) * c.z + H / 2];
export const s2w = (c: Cam, x: number, y: number) => [(x - W / 2) / c.z + c.x, (y - H / 2) / c.z + c.y];
export {getTangentAtLength};
