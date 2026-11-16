// The Vox kit's 3D layer: a three.js stage inside a scene (three.js r170, MIT, vendored in ./three).
// <Stage3D look cam> holds declarative 3D objects (<Box3/>, <Bars3/>, <Globe3/>, <Phone3/>, <Card3/> ...). Every object sits ON the floor (y = 0 is its base),
// appears at its `at` (a cue of the narration: c('word')), and is a pure function of time: any frame renders on its own. Persian labels are DOM text projected
// from 3D points (sharp, right-to-left, the film's fonts). The canvas is transparent: the look's background (or the 2D page under the stage) shows through,
// and floors are shadow catchers. Techniques after Lemo-Opuscar's three.js demos (MIT, Lemomo (LemoLab)).
import React, {useEffect, useLayoutEffect, useMemo, useRef, useState} from 'react';
import {continueRender, delayRender, staticFile, useCurrentFrame} from 'remotion';
// @ts-ignore
import * as THREE from './three/three.module.min.js';
// @ts-ignore
import {RoundedBoxGeometry} from './three/RoundedBoxGeometry.js';
// @ts-ignore
import {RoomEnvironment} from './three/RoomEnvironment.js';
import {THEME} from './theme';
import world from './world.json';
import {FPS, W, H, clamp, eo, eio, back, lat, RED, MUST, TEAL, INK, TXT, ANTON} from './vox';

type V3 = [number, number, number];
type Move = {at: number; pos: V3; d?: number};
type Enter = 'pop' | 'drop' | 'grow' | 'rise' | 'flip' | 'none';
export type Base3 = {at?: number; out?: number; pos?: V3; rot?: number | V3; s?: number; color?: string; enter?: Enter; spin?: number; bob?: number; move?: Move[];
	label?: string; labelAt?: number; labelColor?: string};
type CamKey = {at: number; pos: V3; look?: V3; fov?: number; d?: number; ortho?: number; zoom?: number};
type Num3 = {to: number; from?: number; prefix?: string; suffix?: string; dur?: number; decimals?: number};
type LabelSpec = {x: number; y: number; at: number; out?: number; text?: React.ReactNode; size?: number; color?: string; bg?: string; dx?: number; dy?: number; num?: Num3; anchor?: boolean; kind?: string};

const Q = 1;                           // canvas resolution scale (software WebGL on the render workers: no antialiasing, full resolution)
const D2R = Math.PI / 180;
const P = (x: number) => Math.max(0, x);
const hash = (n: number) => { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); };
const lerp = (a: number, b: number, u: number) => a + (b - a) * u;
const lerp3 = (a: V3, b: V3, u: number): V3 => [lerp(a[0], b[0], u), lerp(a[1], b[1], u), lerp(a[2], b[2], u)];
const shade = (c: string, k: number) => { const col = new THREE.Color(c); const hsl = {h: 0, s: 0, l: 0}; col.getHSL(hsl); col.setHSL(hsl.h, hsl.s, Math.max(0, Math.min(1, hsl.l * k))); return '#' + col.getHexString(); };

// ————————————————————————————— looks —————————————————————————————
type Look3 = {bg: string; label: 'pill' | 'glass' | 'tag' | 'plain'; shadow: number; env: boolean; edges?: string; flat?: boolean; exposure?: number;
	mat: (c: string, o?: any) => any; hemi: [string, string, number]; key: [string, number, V3]; rims?: [string, number, V3][]; floor?: string; text: string; ortho?: number};
export const LOOK3: Record<string, Look3> = {
	// soft matte pastel clay: rounded toys under a warm key light with long soft shadows
	clay: {bg: 'linear-gradient(180deg,#F8E7DA 0%,#F1CDB9 100%)', label: 'pill', shadow: 0.26, env: false, text: '#2B2420',
		mat: (c) => new THREE.MeshStandardMaterial({color: c, roughness: 0.78, metalness: 0}), hemi: ['#ffffff', '#d8b39d', 1.35], key: ['#fff1e0', 2.3, [5, 10, 6]]},
	// dark keynote stage: glossy lacquer objects, studio reflections, coloured rim lights
	glossy: {bg: 'radial-gradient(ellipse at 50% 38%,#1F2738 0%,#0B0E16 62%,#05060A 100%)', label: 'glass', shadow: 0.55, env: true, text: '#F4F6FB', exposure: 1.05,
		mat: (c) => new THREE.MeshPhysicalMaterial({color: c, roughness: 0.26, metalness: 0.12, clearcoat: 1, clearcoatRoughness: 0.12}),
		hemi: ['#9fb3dd', '#050608', 0.45], key: ['#ffffff', 2.6, [4, 9, 5]], rims: [['#5b8cff', 4, [-6, 3, -5]], ['#ff5fa8', 3, [6, 2.5, -5]]]},
	// folded paper: flat-shaded card stock under one lamp, the page texture of the 2D kit shows behind
	paper: {bg: 'transparent', label: 'tag', shadow: 0.3, env: false, flat: true, text: INK,
		mat: (c) => new THREE.MeshLambertMaterial({color: c, flatShading: true}), hemi: ['#fffaf0', '#b8a58a', 1.5], key: ['#fff3dc', 1.9, [-4, 9, 6]]},
	// low-poly isometric miniature: faceted, bright sky, orthographic camera
	lowpoly: {bg: 'linear-gradient(180deg,#BFE3F7 0%,#EAF4F2 55%,#FCF3E2 100%)', label: 'pill', shadow: 0.3, env: false, flat: true, text: '#1F2A33', ortho: 9,
		mat: (c) => new THREE.MeshStandardMaterial({color: c, roughness: 1, metalness: 0, flatShading: true}), hemi: ['#f4fbff', '#c9b48e', 1.25], key: ['#fff4e2', 2.4, [6, 11, 4]]},
	// blueprint wireframe: cream edges over translucent fills on navy
	wire: {bg: 'radial-gradient(ellipse at 50% 40%,#16295A 0%,#0C1736 75%)', label: 'plain', shadow: 0, env: false, edges: '#F4EBD8', text: '#F4EBD8',
		mat: (c) => new THREE.MeshBasicMaterial({color: c, transparent: true, opacity: 0.16, depthWrite: false}), hemi: ['#ffffff', '#ffffff', 1], key: ['#ffffff', 0.5, [3, 8, 4]]},
};
const lookOf = (k?: string): Look3 => LOOK3[k || (THEME as any).look3 || 'clay'] || LOOK3.clay;

// ————————————————————————————— camera —————————————————————————————
const DEFAULT_CAM: CamKey = {at: 0, pos: [5.5, 4.6, 8.5], look: [0, 1, 0], fov: 34};
type CamState = {pos: V3; look: V3; fov: number; ortho?: number};
const toSph = (p: V3, l: V3) => { const x = p[0] - l[0], y = p[1] - l[1], z = p[2] - l[2]; const r = Math.hypot(x, y, z) || 1; return {r, az: Math.atan2(x, z), el: Math.asin(y / r)}; };
const fromSph = (s: {r: number; az: number; el: number}, l: V3): V3 => [l[0] + s.r * Math.cos(s.el) * Math.sin(s.az), l[1] + s.r * Math.sin(s.el), l[2] + s.r * Math.cos(s.el) * Math.cos(s.az)];
export const camAt = (t: number, keys: CamKey[] | undefined, orbit: number, ortho?: number): CamState => {
	const ks = (keys && keys.length ? keys : [DEFAULT_CAM]).slice().sort((a, b) => a.at - b.at);
	let cur: CamState = {pos: ks[0].pos, look: ks[0].look ?? [0, 1, 0], fov: ks[0].fov ?? 34, ortho: ks[0].ortho ?? ortho};
	for (let i = 1; i < ks.length; i++) {
		const k = ks[i];
		if (t <= k.at) break;
		const u = eio(clamp((t - k.at) / (k.d ?? 1.3)));
		const look = lerp3(cur.look, k.look ?? cur.look, u);
		const a = toSph(cur.pos, cur.look), b = toSph(k.pos, k.look ?? cur.look);
		let daz = b.az - a.az; while (daz > Math.PI) daz -= 2 * Math.PI; while (daz < -Math.PI) daz += 2 * Math.PI;
		const pos = fromSph({r: lerp(a.r, b.r, u), az: a.az + daz * u, el: lerp(a.el, b.el, u)}, look);
		cur = {pos, look, fov: lerp(cur.fov, k.fov ?? cur.fov, u), ortho: cur.ortho !== undefined || k.ortho !== undefined ? lerp(cur.ortho ?? k.ortho ?? 9, k.ortho ?? cur.ortho ?? 9, u) : undefined};
	}
	if (orbit) { const s = toSph(cur.pos, cur.look); s.az += orbit * t * D2R; cur = {...cur, pos: fromSph(s, cur.look)}; }
	return cur;
};
// automatic framing: a key's pos only gives the DIRECTION the camera looks from; its distance is computed so the whole set (its final extent) fits the frame width
// with a margin, divided by the key's zoom (2 = twice closer). The aim is lifted so the set sits in the lower two thirds, under the title zone.
type Bounds = {c: V3; r: number};
const HFOV = (fov: number) => Math.atan(Math.tan((fov / 2) * D2R) * (W / H));
export const fitKeys = (keys: CamKey[] | undefined, b: Bounds | null, ortho?: number): CamKey[] | undefined => {
	if (!b) return keys;
	return (keys && keys.length ? keys : [DEFAULT_CAM]).map((k) => {
		const aim: V3 = k.look ?? b.c, fov = k.fov ?? 34, zoom = (k as any).zoom ?? 1;
		const r = b.r + Math.hypot(aim[0] - b.c[0], aim[2] - b.c[2]) * 0.6;
		let dx = k.pos[0] - aim[0], dy = k.pos[1] - aim[1], dz = k.pos[2] - aim[2]; const n = Math.hypot(dx, dy, dz) || 1; dx /= n; dy /= n; dz /= n;
		if (ortho || k.ortho) { const h = (r * 2.3) / (W / H) / zoom; return {...k, pos: [aim[0] + dx * 60, aim[1] + h * 0.1 + dy * 60, aim[2] + dz * 60], look: [aim[0], aim[1] + h * 0.1, aim[2]], ortho: h}; }
		const dist = (r * 0.98) / Math.sin(HFOV(fov)) / zoom, viewH = 2 * dist * Math.tan((fov / 2) * D2R), lift = viewH * 0.09;
		return {...k, pos: [aim[0] + dx * dist, aim[1] + lift + dy * dist, aim[2] + dz * dist], look: [aim[0], aim[1] + lift, aim[2]]};
	});
};
const applyCam = (cam: any, s: CamState) => {
	cam.position.set(...s.pos); cam.up.set(0, 1, 0); cam.lookAt(...s.look);
	if (cam.isOrthographicCamera) { const h = s.ortho ?? 9, w = (h * W) / H; cam.left = -w / 2; cam.right = w / 2; cam.top = h / 2; cam.bottom = -h / 2; }
	else cam.fov = s.fov;
	cam.updateProjectionMatrix(); cam.updateMatrixWorld();
};

// ————————————————————————————— object timing —————————————————————————————
const enterXf = (t: number, p: Base3, def: Enter) => {
	const at = p.at ?? 0, e = p.enter ?? def;
	let s = 1, sy = 1, dy = 0, rx = 0, vis = t >= at - 1e-6;
	const u = clamp((t - at) / 0.5);
	if (e === 'pop') s = back(clamp((t - at) / 0.45));
	else if (e === 'grow') { sy = eo(clamp((t - at) / 0.8)); s = sy > 0 ? 1 : 0; }
	else if (e === 'drop') { const v = clamp((t - at) / 0.42); dy = 5 * (1 - v * v); const b = t - at - 0.42; if (b > 0) sy = 1 - 0.16 * Math.exp(-b * 9) * Math.sin(b * 24); }
	else if (e === 'rise') { dy = -1.4 * (1 - eo(u)); s = lerp(0.5, 1, eo(u)); }
	else if (e === 'flip') rx = -90 * (1 - back(clamp((t - at) / 0.6)));
	if (p.out !== undefined && t > p.out) { const o = eio(clamp((t - p.out) / 0.35)); s *= 1 - o; if (o >= 1) vis = false; }
	if (p.bob) dy += p.bob * Math.sin((t - at) * 2.2);
	return {s: Math.max(s, 0), sy, dy, rx, vis: vis && s > 0.001};
};
const posAt = (t: number, p: Base3): V3 => {
	let pos: V3 = p.pos ?? [0, 0, 0];
	for (const m of p.move ?? []) if (t > m.at) pos = lerp3(pos, m.pos, eio(clamp((t - m.at) / (m.d ?? 1))));
	return pos;
};

// ————————————————————————————— builders —————————————————————————————
type Kit = {look: Look3; mat: (c: string) => any; tex: (src: string, onReady?: (tx: any) => void) => any; canvasTex: (c: HTMLCanvasElement) => any; edges: (o: any) => void};
type Built = {obj: any; top?: number; tick?: (t: number, p: any) => void; labels?: (t: number, p: any, proj: (v: V3) => [number, number]) => LabelSpec[]; def?: Enter};
const cast = (o: any) => { o.traverse((m: any) => { if (m.isMesh) { m.castShadow = true; m.receiveShadow = true; } }); return o; };
const mesh = (g: any, m: any) => new THREE.Mesh(g, m);
const rbox = (w: number, h: number, d: number, r = 0.08) => { const g = new RoundedBoxGeometry(w, h, d, 3, Math.min(r, w / 2.2, h / 2.2, d / 2.2)); g.translate(0, h / 2, 0); return g; };
const font = (px: number, w = 800, fam = 'Doran') => `${w} ${px}px ${fam}`;

const uiCanvas = (kind: 'shop' | 'dash', accent: string, title?: string, cta?: string) => {
	const c = document.createElement('canvas'); c.width = 512; c.height = kind === 'shop' ? 1024 : 320; const g = c.getContext('2d')!;
	g.fillStyle = '#FBFBFD'; g.fillRect(0, 0, c.width, c.height);
	g.direction = 'rtl' as any; g.textAlign = 'right'; g.textBaseline = 'middle';
	if (kind === 'shop') {
		g.fillStyle = accent; g.fillRect(0, 0, 512, 150);
		g.fillStyle = '#fff'; g.font = font(54); g.fillText(title || 'فروشگاه', 470, 82);
		for (let i = 0; i < 4; i++) { const x = 30 + (i % 2) * 236, y = 190 + Math.floor(i / 2) * 300; g.fillStyle = ['#F2E3D5', '#DDE8F5', '#E5F2E1', '#F6E1E8'][i]; g.beginPath(); g.roundRect(x, y, 216, 270, 22); g.fill();
			g.fillStyle = shade(accent, 0.8 + i * 0.12); g.beginPath(); g.arc(x + 108, y + 110, 62, 0, Math.PI * 2); g.fill(); g.fillStyle = '#B9BCC6'; g.fillRect(x + 30, y + 205, 156, 18); g.fillRect(x + 70, y + 235, 116, 14); }
		g.fillStyle = accent; g.beginPath(); g.roundRect(40, 840, 432, 120, 60); g.fill(); g.fillStyle = '#fff'; g.font = font(50); g.textAlign = 'center'; g.fillText(cta || 'خرید', 256, 902);
	} else {
		g.fillStyle = '#EEF0F5'; g.fillRect(0, 0, 512, 46); g.fillStyle = accent; g.font = font(28); g.fillText(title || '', 490, 24);
		for (let i = 0; i < 7; i++) { const h = 40 + ((i * 37) % 5) * 28 + i * 14; g.fillStyle = i === 6 ? accent : shade(accent, 1.45); g.beginPath(); g.roundRect(40 + i * 64, 300 - h, 42, h, 8); g.fill(); }
	}
	return c;
};
const textCanvas = (text: string, o: {size?: number; color?: string; bg?: string; weight?: number; family?: string; pad?: number}) => {
	const size = o.size ?? 160, pad = o.pad ?? (o.bg ? size * 0.35 : size * 0.08), fam = o.family ?? (/[؀-ۿ]/.test(text) ? 'Doran' : ANTON);
	const m = document.createElement('canvas').getContext('2d')!; m.font = font(size, o.weight ?? 900, fam); const w = Math.ceil(m.measureText(text).width + pad * 2), h = Math.ceil(size * 1.45 + pad * 2);
	const c = document.createElement('canvas'); c.width = w; c.height = h; const g = c.getContext('2d')!;
	if (o.bg) { g.fillStyle = o.bg; g.beginPath(); g.roundRect(0, 0, w, h, Math.min(h / 2, size * 0.5)); g.fill(); }
	g.font = font(size, o.weight ?? 900, fam); g.fillStyle = o.color ?? INK; g.textAlign = 'center'; g.textBaseline = 'middle'; g.direction = 'rtl' as any; g.fillText(text, w / 2, h / 2 + size * 0.04);
	return c;
};
const globeCanvas = (land: string, sea: string, fill: Record<string, string>) => {
	const S = 2, src = document.createElement('canvas'); src.width = Math.round(world.w * S); src.height = Math.round(world.h * S);
	const g = src.getContext('2d')!; g.scale(S, S);
	const paths = (world as any).paths as Record<string, string>;
	for (const [n, d] of Object.entries(paths)) { g.fillStyle = fill[n] ?? land; g.fill(new Path2D(d)); }
	const sd = g.getImageData(0, 0, src.width, src.height).data;
	const OW = 1024, OH = 512, out = document.createElement('canvas'); out.width = OW; out.height = OH; const og = out.getContext('2d')!;
	const od = og.createImageData(OW, OH), seaC = new THREE.Color(sea), k = (world as any).k;
	for (let j = 0; j < OH; j++) {
		const la = 90 - (j + 0.5) / OH * 180, laC = Math.max(-58, Math.min(84, la)), sy = Math.round((84 - laC) * k * 1.18 * S), squeeze = (0.88 + 0.12 * Math.cos(laC * D2R)) * k * S;
		for (let i = 0; i < OW; i++) {
			const lo = (i + 0.5) / OW * 360 - 180, o = (j * OW + i) * 4; let r = seaC.r * 255, gg = seaC.g * 255, b = seaC.b * 255;
			if (la > -58 && la < 84) { const sx = Math.round((lo + 180) * squeeze), q = (sy * src.width + sx) * 4; if (sx >= 0 && sx < src.width && sy >= 0 && sy < src.height && sd[q + 3] > 100) { r = sd[q]; gg = sd[q + 1]; b = sd[q + 2]; } }
			od.data[o] = r; od.data[o + 1] = gg; od.data[o + 2] = b; od.data[o + 3] = 255;
		}
	}
	og.putImageData(od, 0, 0); return out;
};
export const lonLat3 = (lon: number, la: number, r: number): V3 => { const phi = (90 - la) * D2R, th = (lon + 180) * D2R; return [-r * Math.sin(phi) * Math.cos(th), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(th)]; };
const place = (p: string | [number, number]): [number, number] => {
	if (typeof p !== 'string') return p;
	const c = ((world as any).centers as Record<string, [number, number]>)[p]; if (!c) return [0, 0];
	const k = (world as any).k, la = 84 - c[1] / (k * 1.18); return [c[0] / ((0.88 + 0.12 * Math.cos(la * D2R)) * k) - 180, la];
};

// gold reads as gold only with reflections: metal on the glossy stage, a warm satin elsewhere
const gold = (k: Kit, c?: string) => k.look.env ? new THREE.MeshStandardMaterial({color: c ?? '#E8B33C', metalness: 0.75, roughness: 0.3})
	: k.look.edges ? k.mat(c ?? '#E8B33C') : new THREE.MeshStandardMaterial({color: c ?? '#F2BE45', metalness: 0.1, roughness: 0.38, emissive: c ?? '#F2BE45', emissiveIntensity: 0.08});

const B: Record<string, (p: any, k: Kit) => Built> = {
	box: (p, k) => { const [w, h, d] = p.size ?? [1, 1, 1]; return {obj: cast(mesh(rbox(w, h, d, p.radius ?? 0.08), k.mat(p.color ?? RED))), top: h}; },
	cyl: (p, k) => { const g = new THREE.CylinderGeometry(p.r ?? 0.5, p.r2 ?? p.r ?? 0.5, p.h ?? 1, p.seg ?? 48); g.translate(0, (p.h ?? 1) / 2, 0); return {obj: cast(mesh(g, k.mat(p.color ?? TEAL))), top: p.h ?? 1}; },
	ball: (p, k) => { const r = p.r ?? 0.5, g = new THREE.SphereGeometry(r, 48, 32); g.translate(0, r, 0); return {obj: cast(mesh(g, k.mat(p.color ?? MUST))), top: 2 * r}; },
	platform: (p, k) => {
		const r = p.r ?? 2.2, h = p.h ?? 0.3, c = p.color ?? '#FFFFFF', sh = p.shape ?? 'disc';
		const g = sh === 'square' ? rbox(r * 2, h, r * 2, 0.12) : new THREE.CylinderGeometry(r, r * 1.02, h, sh === 'hex' ? 6 : 72); if (sh !== 'square') g.translate(0, h / 2, 0);
		const o = cast(mesh(g, sh === 'square' ? k.mat(c) : [k.mat(shade(c, 0.86)), k.mat(c), k.mat(c)])); return {obj: o, top: h, def: 'rise'};
	},
	bars: (p, k) => {
		const vals: number[] = p.values ?? [1, 2, 3], n = vals.length, w = p.w ?? 0.7, gap = p.gap ?? 1.05, hmax = p.h ?? 3, vmax = Math.max(...vals, 1e-9), dur = p.dur ?? 1.2;
		const cols: string[] = Array.isArray(p.colors) ? p.colors : vals.map((_, i) => (i === n - 1 ? RED : shade(p.color ?? TEAL, 1 + i * 0.06)));
		const grp = new THREE.Group(), bars: any[] = [];
		vals.forEach((v, i) => { const m = cast(mesh(rbox(w, 1, w, 0.06), k.mat(cols[i % cols.length]))); m.position.x = (i - (n - 1) / 2) * gap; grp.add(m); bars.push(m); });
		const tOf = (i: number) => (p.at ?? 0) + (n > 1 ? (i / (n - 1)) * dur * 0.6 : 0);
		const hOf = (i: number, t: number) => Math.max(0.02, (vals[i] / vmax) * hmax * eo(clamp((t - tOf(i)) / (dur * 0.7))));
		return {obj: grp, top: hmax, def: 'none',
			tick: (t) => bars.forEach((m, i) => { m.scale.y = hOf(i, t); m.visible = t >= tOf(i); }),
			labels: (t, q, proj) => {
				const base = posAt(t, q), out: LabelSpec[] = [];
				vals.forEach((v, i) => {
					const x = base[0] + (i - (n - 1) / 2) * gap * (q.s ?? 1);
					const top = proj([x, base[1] + hOf(i, t) * (q.s ?? 1) + 0.25, base[2]]), bot = proj([x, base[1] - 0.05, base[2] + w * 0.8]);
					if (q.values !== false) out.push({x: top[0], y: top[1], at: tOf(i), out: q.out, num: {to: v, prefix: q.prefix, suffix: q.suffix, decimals: q.decimals, dur: dur * 0.7}, size: q.size ?? 54, kind: 'num'});
					if (q.labels?.[i]) out.push({x: bot[0], y: bot[1] + 34, at: tOf(i), out: q.out, text: q.labels[i], size: q.labelSize ?? 38, kind: 'plain'});
				});
				return out;
			}};
	},
	donut: (p, k) => {
		const vals: number[] = p.values ?? [1, 1], tot = vals.reduce((a, b) => a + b, 0) || 1, r = p.r ?? 1.6, hole = p.hole ?? 0.55, h = p.h ?? 0.35;
		const cols: string[] = p.colors ?? [RED, MUST, TEAL, '#6C7A89', '#C9B79C'];
		const grp = new THREE.Group(), parts: any[] = []; let a0 = Math.PI / 2;
		vals.forEach((v, i) => {
			const a1 = a0 - (v / tot) * Math.PI * 2, sh = new THREE.Shape();
			sh.absarc(0, 0, r, a0, a1, true); sh.absarc(0, 0, r * hole, a1, a0, false);
			const g = new THREE.ExtrudeGeometry(sh, {depth: h, bevelEnabled: true, bevelThickness: 0.03, bevelSize: 0.03, bevelSegments: 2, curveSegments: 48}); g.rotateX(-Math.PI / 2);
			const m = cast(mesh(g, k.mat(cols[i % cols.length]))); m.userData.mid = (a0 + a1) / 2; grp.add(m); parts.push(m); a0 = a1;
		});
		const tOf = (i: number) => (p.at ?? 0) + i * (p.step ?? 0.25);
		return {obj: grp, top: h, def: 'none', tick: (t, q) => parts.forEach((m, i) => {
			const u = back(clamp((t - tOf(i)) / 0.45)); m.visible = t >= tOf(i); m.scale.set(1, Math.max(u, 0.001), 1);
			const pull = q.pull === i ? eo(clamp((t - (q.pullAt ?? tOf(i) + 0.6)) / 0.5)) * 0.24 : 0; m.position.set(Math.cos(m.userData.mid) * pull, pull * 0.8, -Math.sin(m.userData.mid) * pull);
		})};
	},
	coins: (p, k) => {
		const n = p.n ?? 8, r = p.r ?? 0.42, th = p.th ?? 0.09, dur = p.dur ?? 1.2, grp = new THREE.Group(), coins: any[] = [];
		const g = new THREE.CylinderGeometry(r, r, th * 0.92, 40); g.translate(0, th / 2, 0);
		const m0 = gold(k, p.color);
		for (let i = 0; i < n; i++) { const m = cast(mesh(g, m0)); m.position.set((hash(i) - 0.5) * 0.06, i * th, (hash(i + 9) - 0.5) * 0.06); m.rotation.y = hash(i + 3) * 6; grp.add(m); coins.push(m); }
		const tOf = (i: number) => (p.at ?? 0) + (n > 1 ? (i / (n - 1)) * dur : 0);
		return {obj: grp, top: n * th, def: 'none', tick: (t) => coins.forEach((m, i) => { const v = clamp((t - tOf(i)) / 0.3); m.visible = t >= tOf(i); m.position.y = i * th + 2.2 * (1 - v * v); })};
	},
	coin: (p, k) => {
		const r = p.r ?? 0.8, th = p.th ?? 0.16, g = new THREE.CylinderGeometry(r, r, th, 64); g.rotateX(Math.PI / 2); g.translate(0, r, 0);
		const face = new THREE.CanvasTexture(textCanvas(p.sym ?? '$', {size: 300, color: shade(p.color ?? '#E8B33C', 0.62), bg: p.color ?? '#E8B33C', pad: 120})); face.colorSpace = THREE.SRGBColorSpace;
		const fm = new THREE.MeshStandardMaterial({map: face, metalness: k.look.env ? 0.55 : 0.15, roughness: 0.35});
		const o = cast(mesh(g, [gold(k, p.color), fm, fm])); return {obj: o, top: 2 * r, def: 'pop'};
	},
	phone: (p, k) => {
		const w = p.w ?? 1.1, h = w * 2.05, d = w * 0.09, grp = new THREE.Group();
		grp.add(cast(mesh(rbox(w, h, d, w * 0.14), k.mat(p.color ?? '#1E1F24'))));
		const tex = p.screen ? k.tex(p.screen) : k.canvasTex(uiCanvas('shop', p.accent ?? RED, p.title, p.cta));
		const scr = mesh(new THREE.PlaneGeometry(w * 0.9, h * 0.93), new THREE.MeshBasicMaterial({map: tex, toneMapped: false})); scr.position.set(0, h / 2, d / 2 + 0.003); grp.add(scr);
		return {obj: grp, top: h, def: 'rise'};
	},
	laptop: (p, k) => {
		const w = p.w ?? 2.4, dd = w * 0.66, grp = new THREE.Group(), body = k.mat(p.color ?? '#C9CDD4');
		grp.add(cast(mesh(rbox(w, 0.07, dd, 0.03), body)));
		const lid = new THREE.Group(); lid.position.set(0, 0.07, -dd / 2);
		const lidM = cast(mesh(rbox(w, dd * 0.95, 0.05, 0.03), body)); lidM.position.z = 0.025; lid.add(lidM);
		const tex = p.screen ? k.tex(p.screen) : k.canvasTex(uiCanvas('dash', p.accent ?? TEAL, p.title));
		const scr = mesh(new THREE.PlaneGeometry(w * 0.9, dd * 0.82), new THREE.MeshBasicMaterial({map: tex, toneMapped: false})); scr.position.set(0, dd * 0.48, 0.052); lid.add(scr);
		grp.add(lid);
		return {obj: grp, top: dd, def: 'pop', tick: (t, q) => { const u = eo(clamp((t - (q.open ?? (q.at ?? 0) + 0.35)) / 0.9)); lid.rotation.x = lerp(Math.PI / 2 * 0.985, -0.22, u); }};
	},
	parcel: (p, k) => {
		const [w, h, d] = p.size ?? [1.1, 0.8, 0.9], c = p.color ?? '#C99A66', grp = new THREE.Group();
		grp.add(cast(mesh(rbox(w, h, d, 0.04), k.mat(c))));
		const tape = k.mat(shade(c, 0.78)); const t1 = mesh(rbox(w * 0.18, 0.012, d + 0.01, 0.004), tape); t1.position.y = h - 0.004; grp.add(t1);
		const t2 = mesh(rbox(w * 0.18, h + 0.01, 0.012, 0.004), tape); t2.position.set(0, -0.004, d / 2); grp.add(t2);
		if (p.text) { const lab = mesh(new THREE.PlaneGeometry(w * 0.42, w * 0.26), new THREE.MeshBasicMaterial({map: k.canvasTex(textCanvas(p.text, {size: 90, color: INK, bg: '#FFFFFF'}))})); lab.position.set(w * 0.22, h * 0.5, d / 2 + 0.008); grp.add(lab); }
		return {obj: grp, top: h, def: 'drop'};
	},
	card: (p, k) => {
		const w = p.w ?? 1.6, grp = new THREE.Group(), inner = new THREE.Group(); grp.add(inner);
		const mat = new THREE.MeshLambertMaterial({map: null, transparent: !p.frame, alphaTest: 0.5, side: THREE.DoubleSide});
		const pl = mesh(new THREE.PlaneGeometry(1, 1), mat); pl.castShadow = true; inner.add(pl);
		let frame: any = null;
		if (p.frame) { frame = cast(mesh(new THREE.BoxGeometry(1, 1, 0.02), k.mat('#FBF8F1'))); inner.add(frame); }
		let aspect = p.h ? p.h / w : 1.25;
		const fit = () => { const h = w * aspect, pad = p.frame ? 0.08 : 0; pl.scale.set(w, h, 1); pl.position.set(0, h / 2 + pad, p.frame ? 0.012 : 0); if (frame) { frame.scale.set(w + pad * 2, h + pad * 2, 1); frame.position.set(0, h / 2 + pad, 0); } };
		fit();
		if (p.src) mat.map = k.tex(p.src, (tx: any) => { if (!p.h && tx.image?.width) { aspect = tx.image.height / tx.image.width; fit(); } });
		pl.customDepthMaterial = new THREE.MeshDepthMaterial({depthPacking: THREE.RGBADepthPacking, map: mat.map, alphaTest: 0.5});
		return {obj: grp, top: w * aspect, def: 'flip', tick: (t, q) => { if (q.face) { /* billboard handled by stage */ } }};
	},
	globe: (p, k) => {
		const r = p.r ?? 1.5, grp = new THREE.Group(), spinG = new THREE.Group(); grp.add(spinG); spinG.position.y = r;
		const fill: Record<string, string> = p.fill ?? {};
		const tex = k.canvasTex(globeCanvas(p.land ?? '#F3E6CC', p.sea ?? '#4F7CAC', fill));
		const ball = cast(mesh(new THREE.SphereGeometry(r, 96, 64), new THREE.MeshStandardMaterial({map: tex, roughness: 0.7})));
		spinG.add(ball);
		const arcs: any[] = [];
		for (const a of p.arcs ?? []) {
			const [f, to] = [place(a[0]), place(a[1])], A = new THREE.Vector3(...lonLat3(f[0], f[1], 1)), Bv = new THREE.Vector3(...lonLat3(to[0], to[1], 1)), pts: any[] = [];
			for (let i = 0; i <= 64; i++) { const u = i / 64, v = A.clone().lerp(Bv, u).normalize(); pts.push(v.multiplyScalar(r * (1 + 0.28 * Math.sin(Math.PI * u) * A.angleTo(Bv) / 1.6))); }
			const g = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 96, r * 0.012, 8, false);
			const m = mesh(g, new THREE.MeshBasicMaterial({color: a[2] ?? p.arcColor ?? RED, toneMapped: false}));
			const head = mesh(new THREE.SphereGeometry(r * 0.035, 16, 12), new THREE.MeshBasicMaterial({color: '#FFFFFF', toneMapped: false}));
			spinG.add(m, head); arcs.push({m, head, pts, at: a[3]});
		}
		const pins: any[] = [];
		for (const q of p.pins ?? []) { const ll = place(q[0] ?? q), pin = mesh(new THREE.SphereGeometry(r * 0.04, 16, 12), new THREE.MeshBasicMaterial({color: q[1] ?? RED, toneMapped: false})); pin.position.set(...lonLat3(ll[0], ll[1], r * 1.01)); spinG.add(pin); pins.push({pin, at: q[2]}); }
		const face = p.face ? place(p.face) : null;
		return {obj: grp, top: 2 * r, def: 'pop', tick: (t, q) => {
			spinG.rotation.y = (face ? -(face[0] + 90) * D2R : 0) + (q.spin3 ?? 6) * D2R * t;
			spinG.rotation.x = face ? face[1] * D2R * 0.6 : 0.25;
			arcs.forEach((a) => { const at = a.at ?? q.at ?? 0, u = eio(clamp((t - at) / (q.arcDur ?? 1.4))); a.m.visible = u > 0; a.m.geometry.setDrawRange(0, Math.floor(a.m.geometry.index.count * u / 6) * 6);
				const pt = a.pts[Math.min(a.pts.length - 1, Math.floor(u * (a.pts.length - 1)))]; a.head.position.copy(pt); a.head.visible = u > 0 && u < 1; });
			pins.forEach((x) => { const s = back(clamp((t - (x.at ?? q.at ?? 0)) / 0.4)); x.pin.scale.setScalar(Math.max(s, 0.001)); x.pin.visible = s > 0; });
		}};
	},
	arc: (p, k) => {
		const a = new THREE.Vector3(...(p.from ?? [-2, 0, 0])), b = new THREE.Vector3(...(p.to ?? [2, 0, 0])), mid = a.clone().lerp(b, 0.5); mid.y += p.h ?? 1.6;
		const curve = new THREE.QuadraticBezierCurve3(a, mid, b), g = new THREE.TubeGeometry(curve, 80, p.width ?? 0.035, 8, false);
		const m = mesh(g, new THREE.MeshBasicMaterial({color: p.color ?? RED, toneMapped: false})); const head = mesh(new THREE.SphereGeometry((p.width ?? 0.035) * 2.6, 16, 12), new THREE.MeshBasicMaterial({color: '#FFFFFF', toneMapped: false}));
		const grp = new THREE.Group(); grp.add(m, head);
		return {obj: grp, def: 'none', tick: (t, q) => { const u = eio(clamp((t - (q.at ?? 0)) / (q.dur ?? 1.2))); m.visible = u > 0; g.setDrawRange(0, Math.floor(g.index.count * u / 6) * 6); head.position.copy(curve.getPoint(u)); head.visible = u > 0 && u < 1; }};
	},
	arrow: (p, k) => {
		const a = p.from ?? [-1.5, 0, 0], b = p.to ?? [1.5, 0, 0], len = Math.hypot(b[0] - a[0], b[2] - a[2]), w = p.w ?? 0.28;
		const sh = new THREE.Shape(); sh.moveTo(0, -w / 2); sh.lineTo(len - w * 1.6, -w / 2); sh.lineTo(len - w * 1.6, -w * 1.25); sh.lineTo(len, 0); sh.lineTo(len - w * 1.6, w * 1.25); sh.lineTo(len - w * 1.6, w / 2); sh.lineTo(0, w / 2); sh.closePath();
		const g = new THREE.ExtrudeGeometry(sh, {depth: p.th ?? 0.12, bevelEnabled: true, bevelThickness: 0.02, bevelSize: 0.02, bevelSegments: 2}); g.rotateX(-Math.PI / 2);
		const m = cast(mesh(g, k.mat(p.color ?? RED))), grp = new THREE.Group(), pivot = new THREE.Group(); pivot.add(m); grp.add(pivot);
		pivot.position.set(a[0], (a[1] ?? 0) + 0.02, a[2]); pivot.rotation.y = -Math.atan2(b[2] - a[2], b[0] - a[0]);
		return {obj: grp, def: 'none', tick: (t, q) => { const u = eo(clamp((t - (q.at ?? 0)) / (q.dur ?? 0.6))); m.scale.set(Math.max(u, 0.001), 1, 1); m.visible = u > 0; }};
	},
	city: (p, k) => {
		const n = p.n ?? 20, [aw, ad] = p.area ?? [4, 3], grp = new THREE.Group(), blds: any[] = [], cols: string[] = p.colors ?? ['#F4EFE6', '#E6DCCD', '#D7E3EA', shade(p.color ?? TEAL, 1.2)];
		const cells = Math.ceil(Math.sqrt(n * (aw / ad))), rows = Math.ceil(n / cells);
		for (let i = 0; i < n; i++) {
			const cx = (i % cells) - (cells - 1) / 2, cz = Math.floor(i / cells) - (rows - 1) / 2, sx = aw / cells, sz = ad / rows;
			const h = 0.4 + Math.pow(hash(i * 3.7 + (p.seed ?? 1)), 2) * (p.hmax ?? 2.2), bw = sx * (0.55 + hash(i + 2) * 0.25), bd = sz * (0.55 + hash(i + 5) * 0.25);
			const m = cast(mesh(rbox(bw, 1, bd, 0.03), k.mat(cols[Math.floor(hash(i * 1.3) * cols.length)]))); m.position.set(cx * sx, 0, cz * sz); m.userData = {h, i}; grp.add(m); blds.push(m);
		}
		const tOf = (i: number) => (p.at ?? 0) + hash(i * 7.1) * (p.dur ?? 1.4);
		return {obj: grp, top: p.hmax ?? 2.2, def: 'none', tick: (t) => blds.forEach((m) => { const u = eo(clamp((t - tOf(m.userData.i)) / 0.6)); m.scale.y = Math.max(0.001, u * m.userData.h); m.visible = u > 0; })};
	},
	person: (p, k) => {
		const h = p.h ?? 1, grp = new THREE.Group(), c = p.color ?? MUST;
		const body = new THREE.CapsuleGeometry(0.2 * h, 0.42 * h, 6, 16); body.translate(0, 0.41 * h, 0);
		const head = new THREE.SphereGeometry(0.17 * h, 24, 16); head.translate(0, 0.98 * h, 0);
		grp.add(cast(mesh(body, k.mat(c))), cast(mesh(head, k.mat(p.skin ?? '#F1C7A5'))));
		return {obj: grp, top: 1.15 * h, def: 'drop'};
	},
	tree: (p, k) => {
		const h = p.h ?? 1.2, grp = new THREE.Group(), tr = new THREE.CylinderGeometry(0.06 * h, 0.08 * h, 0.4 * h, 8); tr.translate(0, 0.2 * h, 0);
		const top = new THREE.IcosahedronGeometry(0.38 * h, 0); top.translate(0, 0.72 * h, 0);
		grp.add(cast(mesh(tr, k.mat('#8A6A4F'))), cast(mesh(top, new THREE.MeshStandardMaterial({color: p.color ?? '#6DB36A', roughness: 1, flatShading: true}))));
		return {obj: grp, top: 1.1 * h, def: 'pop'};
	},
	pin: (p, k) => {
		const s = p.size ?? 0.5, grp = new THREE.Group(), cone = new THREE.ConeGeometry(s * 0.32, s * 0.9, 24); cone.rotateX(Math.PI); cone.translate(0, s * 0.45, 0);
		const ball = new THREE.SphereGeometry(s * 0.42, 32, 20); ball.translate(0, s * 1.05, 0);
		const m = k.mat(p.color ?? RED); grp.add(cast(mesh(cone, m)), cast(mesh(ball, m))); return {obj: grp, top: s * 1.5, def: 'drop'};
	},
	text: (p, k) => {
		const c = textCanvas(String(p.text ?? ''), {size: 160, color: p.color ?? INK, bg: p.bg, weight: p.weight ?? 900, family: p.family});
		const w = p.w ?? 2, h = (w * c.height) / c.width, tex = k.canvasTex(c);
		const m = mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({map: tex, transparent: true, toneMapped: false, depthWrite: !!p.bg, side: THREE.DoubleSide})); m.position.y = h / 2;
		const grp = new THREE.Group(); grp.add(m); grp.userData.billboard = p.billboard !== false; return {obj: grp, top: h, def: 'pop'};
	},
};

// ————————————————————————————— the components —————————————————————————————
const mk = <Pr,>(kind: string) => { const C: React.FC<Pr & Base3> = () => null; (C as any).kind3 = kind; return C; };
/** a rounded box: size [w,h,d] (a product, a block, a building, a wallet) */
export const Box3 = mk<{size?: V3; radius?: number}>('box');
/** a cylinder (r, r2 for a cone top, h) */
export const Cyl3 = mk<{r?: number; r2?: number; h?: number; seg?: number}>('cyl');
/** a ball of radius r */
export const Ball3 = mk<{r?: number}>('ball');
/** a pedestal / island under the objects: shape disc | square | hex */
export const Platform3 = mk<{r?: number; h?: number; shape?: 'disc' | 'square' | 'hex'}>('platform');
/** 3D bar chart that grows bar by bar from `at` over `dur`; values counted on top in the display face, labels under each bar */
export const Bars3 = mk<{values: number[]; labels?: string[]; colors?: string[]; w?: number; gap?: number; h?: number; dur?: number; prefix?: string; suffix?: string; decimals?: number; size?: number; labelSize?: number}>('bars');
/** an extruded donut chart: slices pop up one by one; `pull` lifts one slice out at `pullAt` */
export const Donut3 = mk<{values: number[]; colors?: string[]; r?: number; hole?: number; h?: number; step?: number; pull?: number; pullAt?: number}>('donut');
/** a stack of n gold coins dropping one by one between at and at+dur */
export const Coins3 = mk<{n?: number; r?: number; th?: number; dur?: number}>('coins');
/** one big standing coin with a symbol on its face ($, €, ٪, ₿); give it spin */
export const Coin3 = mk<{sym?: string; r?: number; th?: number}>('coin');
/** a smartphone standing up; screen = a picture file, else a drawn shop app (accent, title, cta) */
export const Phone3 = mk<{w?: number; screen?: string; accent?: string; title?: string; cta?: string}>('phone');
/** a laptop whose lid opens at `open` (default just after at); screen = picture or a drawn dashboard */
export const Laptop3 = mk<{w?: number; screen?: string; accent?: string; title?: string; open?: number}>('laptop');
/** a cardboard parcel with tape (drops in); optional label text */
export const Parcel3 = mk<{size?: V3; text?: string}>('parcel');
/** a standing paper card / cut-out from the film's pictures (public/img/NAME); pops up from flat like a pop-up book; frame = printed photo with a white border */
export const Card3 = mk<{src?: string; w?: number; h?: number; frame?: boolean}>('card');
/** a spinning globe: fill countries {Name: color}, pins [[place, color?, at?]], arcs [[from, to, color?, at?]] (place = English country name or [lon, lat]); face = place turned to the camera */
export const Globe3 = mk<{r?: number; land?: string; sea?: string; fill?: Record<string, string>; pins?: any[]; arcs?: any[]; face?: string | [number, number]; spin3?: number; arcColor?: string; arcDur?: number}>('globe');
/** a glowing arc drawn through the air from one point to another (money, a shipment, data) */
export const Arc3 = mk<{from: V3; to: V3; h?: number; width?: number; dur?: number}>('arc');
/** a thick 3D arrow on the floor from `from` to `to`, growing */
export const Arrow3 = mk<{from: V3; to: V3; w?: number; th?: number; dur?: number}>('arrow');
/** a block of low buildings rising one by one over `dur` (a city, a market, a warehouse district) */
export const City3 = mk<{n?: number; area?: [number, number]; hmax?: number; colors?: string[]; seed?: number; dur?: number}>('city');
/** a simple pawn person (body colour, skin) */
export const Person3 = mk<{h?: number; skin?: string}>('person');
export const Tree3 = mk<{h?: number}>('tree');
/** a map pin */
export const Pin3 = mk<{size?: number}>('pin');
/** a word or number as a flat sign in the 3D space (billboard faces the camera); Persian in Doran, Latin/numbers in the display face */
export const Text3 = mk<{text: string; w?: number; bg?: string; weight?: number; family?: string; billboard?: boolean}>('text');
/** a DOM label anchored to a 3D point: Persian text (children) or a counted number (num), with a leader line when dx/dy move it away */
export const Label3: React.FC<{at?: number; out?: number; pos: V3; children?: React.ReactNode; size?: number; color?: string; bg?: string; dx?: number; dy?: number; num?: Num3}> = () => null;
(Label3 as any).label3 = true;

const flat = (ch: React.ReactNode): React.ReactElement[] => {
	const out: React.ReactElement[] = [];
	React.Children.forEach(ch, (c) => { if (!React.isValidElement(c)) return; if (c.type === React.Fragment) out.push(...flat((c.props as any).children)); else out.push(c); });
	return out;
};

const texCache = new Map<string, any>();
const LabelView: React.FC<{l: LabelSpec; t: number; look: Look3}> = ({l, t, look}) => {
	if (t < l.at) return null;
	const a = eo(clamp((t - l.at) / 0.35)) * (l.out !== undefined ? 1 - clamp((t - l.out) / 0.3) : 1);
	if (a <= 0) return null;
	const size = l.size ?? 48, dx = l.dx ?? 0, dy = l.dy ?? 0;
	let content: React.ReactNode = l.text;
	let fam = 'Doran';
	if (l.num) { const n = l.num, v = lerp(n.from ?? 0, n.to, eo(clamp((t - l.at) / (n.dur ?? 0.9)))); content = `${n.prefix ?? ''}${v.toLocaleString('en-US', {minimumFractionDigits: n.decimals ?? 0, maximumFractionDigits: n.decimals ?? 0})}${n.suffix ?? ''}`; fam = ANTON; }
	if (typeof content === 'string' && !/[؀-ۿ]/.test(content)) { content = lat(content); fam = ANTON; }
	const latin = fam === ANTON, est = (typeof content === 'string' ? content.length : 8) * size * (latin ? 0.55 : 0.5) + size;
	const cx = Math.max(90 + est / 2, Math.min(W - 90 - est / 2, l.x + dx)), cy = Math.max(190, Math.min(1720, l.y + dy));
	const st =l.kind === 'plain' || look.label === 'plain'
		? {color: l.color ?? look.text, textShadow: look.label === 'glass' ? '0 2px 12px rgba(0,0,0,.6)' : 'none'}
		: look.label === 'glass' ? {color: l.color ?? '#fff', background: l.bg ?? 'rgba(255,255,255,0.12)', border: '1.5px solid rgba(255,255,255,0.35)', backdropFilter: 'blur(6px)', borderRadius: 999, padding: `${size * 0.18}px ${size * 0.5}px`}
		: look.label === 'tag' ? {color: l.color ?? INK, background: l.bg ?? '#FBF8F1', padding: `${size * 0.14}px ${size * 0.4}px`, boxShadow: '0 6px 12px rgba(40,30,15,.25)', transform: 'rotate(-2deg)'}
		: {color: l.color ?? look.text, background: l.bg ?? '#FFFFFF', borderRadius: 999, padding: `${size * 0.16}px ${size * 0.5}px`, boxShadow: '0 10px 24px rgba(60,30,20,.18)'};
	if (l.kind === 'num' && look.label !== 'glass') Object.assign(st, {background: 'none', boxShadow: 'none', padding: 0, color: l.color ?? look.text});
	return (
		<>
			{(dx || dy) && l.anchor !== false ? (
				<svg style={{position: 'absolute', left: 0, top: 0, width: W, height: H, opacity: a, pointerEvents: 'none'}}>
					<line x1={l.x} y1={l.y} x2={cx} y2={cy} stroke={look.text} strokeWidth={3} />
					<circle cx={l.x} cy={l.y} r={8} fill={look.text} />
				</svg>
			) : null}
			<div style={{position: 'absolute', left: cx, top: cy, transform: `translate(-50%,-50%) scale(${0.85 + 0.15 * a})`, opacity: a, whiteSpace: 'nowrap', direction: latin ? 'ltr' : 'rtl',
				fontFamily: fam, fontWeight: 800, fontSize: size, lineHeight: 1.15, ...st}}>{content}</div>
		</>
	);
};

type StageProps = {fit?: boolean; look?: string; cam?: CamKey[]; orbit?: number; ortho?: number; floor?: 'shadow' | 'solid' | 'none' | 'grid'; floorColor?: string; bg?: string; children?: React.ReactNode; light?: number};
/** a 3D stage filling the frame. cam = camera keys [{at, pos, look, fov, d}] (each move starts at its `at` and takes d s); orbit = slow turn in degrees per second */
export const Stage3D: React.FC<StageProps> = (props) => {
	const f = useCurrentFrame(), t = f / FPS;
	const look = lookOf(props.look);
	const ref = useRef<HTMLCanvasElement>(null);
	const st = useRef<any>(null);
	const [handle] = useState(() => delayRender('stage3d'));
	const [ready, setReady] = useState(false);
	const items = flat(props.children);
	const objs = items.filter((e) => (e.type as any).kind3);
	const sig = objs.map((e) => (e.type as any).kind3).join(',');
	const ortho = props.ortho ?? look.ortho;
	const camS = camAt(t, props.fit === false ? props.cam : fitKeys(props.cam, st.current?.bounds ?? null, ortho), props.orbit ?? 2.5, ortho);
	const projCam = useMemo(() => (ortho ? new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 400) : new THREE.PerspectiveCamera(34, W / H, 0.1, 400)), [!!ortho]);
	applyCam(projCam, camS);
	const proj = (v: V3): [number, number] => { const p = new THREE.Vector3(...v).project(projCam); return [((p.x + 1) / 2) * W, ((1 - p.y) / 2) * H]; };

	const build = () => {
		const s = st.current;
		for (const b of s.built ?? []) s.scene.remove(b.group);
		const kit: Kit = {look, mat: (c) => { const m = look.mat(c); return m; }, canvasTex: (c) => { const x = new THREE.CanvasTexture(c); x.colorSpace = THREE.SRGBColorSpace; x.anisotropy = 4; return x; },
			tex: (src, onReady) => {
				const url = staticFile('img/' + src);
				if (texCache.has(url)) { const x = texCache.get(url); if (onReady && x.image) onReady(x); return x; }
				const h = delayRender('tex ' + src);
				const x = new THREE.TextureLoader().load(url, (tx: any) => { onReady?.(tx); s.draw?.(); continueRender(h); }, undefined, () => continueRender(h));
				x.colorSpace = THREE.SRGBColorSpace; texCache.set(url, x); return x;
			}, edges: () => null};
		s.built = objs.map((e) => {
			const p = e.props as any, kind = (e.type as any).kind3;
			const b = B[kind](p, kit), group = new THREE.Group(); group.add(b.obj);
			if (look.edges) b.obj.traverse((m: any) => { if (m.isMesh && m.geometry) { const l = new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry, 25), new THREE.LineBasicMaterial({color: look.edges, transparent: true, opacity: 0.9})); m.add(l); } });
			s.scene.add(group); return {...b, group, kind};
		});
		s.sig = sig;
		// the set's final extent (every object fully grown, at its last position) for the automatic framing
		const box = new THREE.Box3();
		s.built.forEach((b: any, i: number) => {
			const p = (objs[i]?.props ?? {}) as any, pos = posAt(1e4, p), g = b.group, sc = p.s ?? 1;
			g.visible = true; g.position.set(...pos); g.scale.set(sc, sc, sc); g.rotation.set(0, ((typeof p.rot === 'number' ? p.rot : p.rot?.[1]) ?? 0) * D2R, 0);
			b.tick?.(1e4, {...p, out: undefined}); g.updateMatrixWorld(true);
			const bb = new THREE.Box3().setFromObject(g); if (!bb.isEmpty()) box.union(bb);
		});
		if (!box.isEmpty()) { const sp = box.getBoundingSphere(new THREE.Sphere()); const sz = box.getSize(new THREE.Vector3());
			s.bounds = {c: [sp.center.x, sp.center.y, sp.center.z], r: Math.max(0.6, Math.max(sz.x, sz.z) / 2 * 0.9, sz.y * 0.34)}; }
		else s.bounds = null;
	};

	useEffect(() => {
		let dead = false;
		document.fonts.ready.then(() => {
			if (dead || !ref.current) return;
			const renderer = new THREE.WebGLRenderer({canvas: ref.current, antialias: false, alpha: true, preserveDrawingBuffer: true, powerPreference: 'high-performance'});
			renderer.setPixelRatio(1); renderer.setSize(W * Q, H * Q, false); renderer.setClearColor(0x000000, 0);
			renderer.shadowMap.enabled = look.shadow > 0; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
			renderer.toneMapping = THREE.NeutralToneMapping; renderer.toneMappingExposure = look.exposure ?? 1;
			const scene = new THREE.Scene();
			if (look.env) { const pm = new THREE.PMREMGenerator(renderer); scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture; scene.environmentIntensity = 0.6; }
			const li = props.light ?? 1;
			scene.add(new THREE.HemisphereLight(look.hemi[0], look.hemi[1], look.hemi[2] * li));
			const key = new THREE.DirectionalLight(look.key[0], look.key[1] * li); key.position.set(...look.key[2]); key.castShadow = look.shadow > 0;
			key.shadow.mapSize.set(2048, 2048); key.shadow.radius = 5; key.shadow.bias = -0.0004; key.shadow.normalBias = 0.02;
			Object.assign(key.shadow.camera, {left: -7, right: 7, top: 7, bottom: -7, near: 0.5, far: 40}); key.shadow.camera.updateProjectionMatrix(); scene.add(key, key.target);
			for (const r of look.rims ?? []) { const l = new THREE.DirectionalLight(r[0], r[1] * li); l.position.set(...r[2]); scene.add(l); }
			const fl = props.floor ?? (look.edges ? 'grid' : 'shadow');
			if (fl === 'shadow' && look.shadow > 0) { const m = mesh(new THREE.PlaneGeometry(60, 60), new THREE.ShadowMaterial({opacity: look.shadow, color: look.label === 'glass' ? '#000000' : '#5a3a2a'})); m.rotation.x = -Math.PI / 2; m.receiveShadow = true; scene.add(m); }
			if (fl === 'solid') { const m = mesh(new THREE.PlaneGeometry(60, 60), new THREE.MeshStandardMaterial({color: props.floorColor ?? '#EAD9CB', roughness: look.env ? 0.35 : 0.95, metalness: look.env ? 0.4 : 0})); m.rotation.x = -Math.PI / 2; m.receiveShadow = true; scene.add(m); }
			if (fl === 'grid') { const g = new THREE.GridHelper(30, 30, look.edges ?? '#ffffff', look.edges ?? '#ffffff'); (g.material as any).transparent = true; (g.material as any).opacity = 0.22; scene.add(g); }
			const camera = ortho ? new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 400) : new THREE.PerspectiveCamera(34, W / H, 0.1, 400);
			st.current = {renderer, scene, camera, sig: ''};
			build();
			setReady(true);
		});
		return () => { dead = true; const s = st.current; if (s) { s.renderer.dispose(); s.renderer.forceContextLoss?.(); st.current = null; } };
	}, []);

	useLayoutEffect(() => {
		const s = st.current;
		if (!ready || !s) return;
		if (s.sig !== sig) build();
		const draw = () => {
			applyCam(s.camera, camS);
			s.built.forEach((b: any, i: number) => {
				const p = (objs[i]?.props ?? {}) as any, x = enterXf(t, p, b.def ?? 'pop'), pos = posAt(t, p), g = b.group;
				g.visible = x.vis; g.position.set(pos[0], pos[1] + x.dy, pos[2]);
				const r = p.rot; const ry = (typeof r === 'number' ? r : r?.[1] ?? 0) + (p.spin ? p.spin * Math.max(0, t - (p.at ?? 0)) : 0);
				g.rotation.set((typeof r === 'object' ? r[0] : 0) * D2R + x.rx * D2R, ry * D2R, (typeof r === 'object' ? r[2] : 0) * D2R);
				const sc = (p.s ?? 1) * x.s; g.scale.set(sc, sc * x.sy, sc);
				if (b.obj.userData?.billboard) b.obj.quaternion.copy(s.camera.quaternion);
				b.tick?.(t, p);
			});
			s.renderer.render(s.scene, s.camera);
		};
		s.draw = draw; draw();
		if (!s.released) { s.released = true; continueRender(handle); }
	});

	// labels: object labels, Bars3 values, standalone Label3
	const labels: LabelSpec[] = [];
	objs.forEach((e, i) => {
		const p = e.props as any, b = st.current?.built?.[i];
		if (p.label) { const pos = posAt(t, p), top = (b?.top ?? 1) * (p.s ?? 1); const [x, y] = proj([pos[0], pos[1] + top + 0.25, pos[2]]); labels.push({x, y: y - 30, at: p.labelAt ?? (p.at ?? 0) + 0.3, out: p.out, text: p.label, color: p.labelColor, size: p.labelSize ?? 46}); }
		if (b?.labels) labels.push(...b.labels(t, p, proj));
	});
	items.filter((e) => (e.type as any).label3).forEach((e) => { const p = e.props as any; const [x, y] = proj(p.pos); labels.push({x, y, at: p.at ?? 0, out: p.out, text: p.children, size: p.size, color: p.color, bg: p.bg, dx: p.dx, dy: p.dy, num: p.num}); });

	return (
		<div style={{position: 'absolute', inset: 0, background: props.bg ?? look.bg}}>
			<canvas ref={ref} style={{position: 'absolute', left: 0, top: 0, width: W, height: H}} />
			{ready ? labels.map((l, i) => <LabelView key={i} l={l} t={t} look={look} />) : null}
		</div>
	);
};
