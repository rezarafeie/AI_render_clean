// The intro kit's shared library: easings, fonts, Persian-safe text reveals, and the brand character.
// Everything a film says or times comes from content.json (written by creative/claude_intro): no brand text lives in the templates.
import React from 'react';
import {continueRender, delayRender, staticFile} from 'remotion';
import content from './content.json';

export const CONTENT: any = content;
export const THEME: any = CONTENT.theme ?? {};
export const TIMING: any = CONTENT.timing ?? {};

export const clamp = (x: number, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const lerp = (a: number, b: number, u: number) => a + (b - a) * u;
export const seg = (t: number, a: number, b: number) => clamp((t - a) / (b - a));
export const eo = (u: number) => 1 - Math.pow(1 - u, 3);
export const eo5 = (u: number) => 1 - Math.pow(1 - u, 5);
export const ei = (u: number) => u * u * u;
export const eio = (u: number) => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2);
export const back = (u: number, s = 1.7) => 1 + (s + 1) * Math.pow(u - 1, 3) + s * Math.pow(u - 1, 2);
export const spring = (u: number, k = 9, z = 5) => (u <= 0 ? 0 : 1 - Math.exp(-z * u) * Math.cos(k * u));
export const rnd = (i: number) => {
	const x = Math.sin(i * 127.1 + 311.7) * 43758.5453;
	return x - Math.floor(x);
};
export const fa = (n: number | string) => String(n).replace(/\d/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[+d]);

// ---------- fonts ----------
// Families the templates use: Rokh (heavy grotesque), Pey (display serif), Typo (script), Vaz (Persian UI), VazL (Latin/code).
// THEME.faces = [{family, file, weight}] with files under public/fonts; a family the person's library lacks is mapped to Vazirmatn by the engine.
type Face = {family: string; file: string; weight: string | number};
const FACES: Face[] = THEME.faces ?? [];
let fontsReady = false;
export const Fonts: React.FC = () => (
	<style>{FACES.map((f) => `@font-face{font-family:'${f.family}';src:url('${staticFile('fonts/' + f.file)}') format('${/\.woff2$/i.test(f.file) ? 'woff2' : /\.otf$/i.test(f.file) ? 'opentype' : 'truetype'}');font-weight:${f.weight};font-display:block;}`).join('\n')}</style>
);
export const useFonts = () => {
	const [h] = React.useState(() => delayRender('fonts'));
	const [, tick] = React.useState(0);
	React.useEffect(() => {
		const loads: Promise<unknown>[] = [];
		for (const f of FACES) for (const w of String(f.weight).split(/\s+/)) loads.push(document.fonts.load(`${w} 40px ${f.family}`, f.family === 'VazL' ? 'Editor' : 'سلام۱'));
		Promise.all(loads).catch(() => null).then(() => document.fonts.ready).then(() => { fontsReady = true; tick(1); continueRender(h); });
	}, [h]);
};
// the font size at which `text` fits `maxW` px (never above `base`): measured only after the fonts are loaded
const widths = new Map<string, number>();
export const fit = (text: string, family: string, weight: number, base: number, maxW: number) => {
	if (!fontsReady || typeof document === 'undefined') return Math.min(base, maxW / Math.max(1, text.length * 0.5));
	const key = `${family}|${weight}|${text}`;
	if (!widths.has(key)) {
		const g = document.createElement('canvas').getContext('2d')!;
		g.font = `${weight} 100px ${family}`;
		widths.set(key, g.measureText(text).width / 100);
	}
	return Math.min(base, maxW / Math.max(0.2, widths.get(key)!));
};

// ---------- Persian-safe reveals (letters join: never letter by letter) ----------
/** a curtain opening from the right; the negative insets keep the tall strokes and dots of Persian letters */
export const Wipe: React.FC<{p: number; style?: React.CSSProperties; children: React.ReactNode}> = ({p, style, children}) => (
	<div style={{...style, clipPath: `inset(-20% 0 -30% ${(1 - clamp(p)) * 100}%)`}}>{children}</div>
);
/** word by word, each a whole inline-block */
export const Words: React.FC<{text: string; t: number; t0: number; gap?: number; style?: React.CSSProperties}> = ({text, t, t0, gap = 0.09, style}) => (
	<div style={{direction: 'rtl', ...style}}>
		{String(text ?? '').split(' ').map((w, i) => {
			const u = clamp((t - t0 - i * gap) / 0.3);
			return <span key={i} style={{display: 'inline-block', marginLeft: '0.26em', opacity: u, transform: `translateY(${(1 - eo5(u)) * 26}px)`}}>{w}</span>;
		})}
	</div>
);

// ---------- the brand's mark and its character ----------
export const sparkPath = (r: number, k = 0.22) => {
	const p: string[] = [];
	for (let i = 0; i < 4; i++) {
		const a = (i * Math.PI) / 2 - Math.PI / 2, b = a + Math.PI / 4, c = a + Math.PI / 2;
		const x0 = r * Math.cos(a), y0 = r * Math.sin(a), x1 = r * Math.cos(c), y1 = r * Math.sin(c);
		const qx = r * k * Math.cos(b), qy = r * k * Math.sin(b);
		p.push(`${i === 0 ? 'M' + x0.toFixed(2) + ',' + y0.toFixed(2) : ''} Q${qx.toFixed(2)},${qy.toFixed(2)} ${x1.toFixed(2)},${y1.toFixed(2)}`);
	}
	return p.join(' ') + ' Z';
};
const poly = (n: number, r: number, rot = -Math.PI / 2) => Array.from({length: n}).map((_, i) => `${i ? 'L' : 'M'}${(r * Math.cos(rot + (i * 2 * Math.PI) / n)).toFixed(2)},${(r * Math.sin(rot + (i * 2 * Math.PI) / n)).toFixed(2)}`).join(' ') + ' Z';
/** the brand mark as an SVG path centred on 0,0 with radius r. THEME.mascot.shape: spark | circle | square | drop | hex | diamond | cloud | path (THEME.mascot.path, drawn for r = 40) */
export const markPath = (r: number, soft = 0.42): string => {
	const m = THEME.mascot ?? {};
	switch (m.shape) {
		case 'circle': return `M${-r},0 a${r},${r} 0 1,0 ${2 * r},0 a${r},${r} 0 1,0 ${-2 * r},0 Z`;
		case 'square': { const s = r * 0.86, c = r * 0.26; return `M${-s + c},${-s} H${s - c} Q${s},${-s} ${s},${-s + c} V${s - c} Q${s},${s} ${s - c},${s} H${-s + c} Q${-s},${s} ${-s},${s - c} V${-s + c} Q${-s},${-s} ${-s + c},${-s} Z`; }
		case 'drop': return `M0,${-r} C${r * 0.9},${-r * 0.2} ${r},${r * 0.35} 0,${r} C${-r},${r * 0.35} ${-r * 0.9},${-r * 0.2} 0,${-r} Z`;
		case 'hex': return poly(6, r);
		case 'diamond': return poly(4, r * 1.05);
		case 'cloud': return `M${-r * 0.7},${r * 0.55} a${r * 0.42},${r * 0.42} 0 0,1 ${-r * 0.05},${-r * 0.8} a${r * 0.5},${r * 0.5} 0 0,1 ${r * 0.9},${-r * 0.25} a${r * 0.42},${r * 0.42} 0 0,1 ${r * 0.6},${r * 1.05} Z`;
		case 'path': return m.path ? String(m.path) : sparkPath(r, soft);
		default: return sparkPath(r, soft);
	}
};
export const markScale = (r: number) => ((THEME.mascot ?? {}).shape === 'path' ? r / 40 : 1);
export const MASCOT_COLOR: string = (THEME.mascot ?? {}).color ?? '#f7a600';

/** the film's own little character: the brand mark with two eyes and two feet */
export const Mascot: React.FC<{x: number; y: number; s?: number; col?: string; eye?: string; blink?: number; look?: number; squash?: number; rot?: number; walk?: number; happy?: boolean}> = ({x, y, s = 1, col = MASCOT_COLOR, eye = (THEME.mascot ?? {}).eye ?? '#1b1b1b', blink = 0, look = 0, squash = 0, rot = 0, walk = 0, happy}) => {
	const sy = 1 - squash, sx = 1 + squash * 0.8;
	const f = Math.sin(walk * Math.PI * 2);
	return (
		<g transform={`translate(${x},${y}) scale(${s})`}>
			<g transform={`translate(0,${-38}) scale(${sx},${sy}) translate(0,${38})`}>
				<rect x={-17 + f * 3} y={-12 - Math.max(0, f) * 6} width={10} height={12} rx={3} fill={col} />
				<rect x={7 - f * 3} y={-12 - Math.max(0, -f) * 6} width={10} height={12} rx={3} fill={col} />
				<g transform={`translate(0,-44) rotate(${rot})`}>
					<path d={markPath(40, 0.42)} fill={col} transform={`scale(${markScale(40)})`} />
					<g transform={`translate(${look * 4},0)`}>
						{happy ? (
							<>
								<path d="M-13,-1 q5,-7 10,0" stroke={eye} strokeWidth={3.5} fill="none" strokeLinecap="round" />
								<path d="M3,-1 q5,-7 10,0" stroke={eye} strokeWidth={3.5} fill="none" strokeLinecap="round" />
							</>
						) : (
							<>
								<rect x={-12} y={-7 + blink * 5} width={6} height={12 * (1 - blink) + 1} rx={3} fill={eye} />
								<rect x={6} y={-7 + blink * 5} width={6} height={12 * (1 - blink) + 1} rx={3} fill={eye} />
							</>
						)}
					</g>
				</g>
			</g>
		</g>
	);
};
export const blinkAt = (t: number, period = 2.7, off = 0.4) => {
	const u = ((t + off) % period) / 0.16;
	return u < 1 ? Math.sin(u * Math.PI) : 0;
};
