import React from 'react';
import {continueRender, delayRender, staticFile} from 'remotion';

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

const FACES: [string, string, number | string][] = [
	['Doran', 'DoranFaNum-Light.woff2', 300],
	['Doran', 'DoranFaNum-Regular.woff2', 400],
	['Doran', 'DoranFaNum-Medium.woff2', 500],
	['Doran', 'DoranFaNum-Bold.woff2', 700],
	['Doran', 'DoranFaNum-ExtraBold.woff2', 800],
	['Laz', 'lalezar.woff2', 400],
	['Vaz', 'vaz500.woff2', 500],
	['Vaz', 'vaz900.woff2', 900],
	['VazL', 'vazL500.woff2', 500],
	['VazL', 'vazL900.woff2', 900],
	['Rokh', 'RokhFaNum-Black.ttf', 900],
	['Rokh', 'RokhFaNum-Bold.ttf', 700],
	['Rokh', 'RokhFaNum-Regular.ttf', 400],
	['Pey', 'PaykanFaNum-ExtraBlack.ttf', 900],
	['Pey', 'PaykanFaNum-Regular.ttf', 400],
	['Typo', 'typokar-2.ttf', 400],
];
export const Fonts: React.FC = () => (
	<style>{FACES.map(([f, file, w]) => `@font-face{font-family:'${f}';src:url('${staticFile('fonts/' + file)}') format('${String(file).endsWith('ttf') ? 'truetype' : 'woff2'}');font-weight:${w};font-display:block;}`).join('\n')}</style>
);
export const useFonts = () => {
	const [h] = React.useState(() => delayRender('fonts'));
	React.useEffect(() => {
		Promise.all(FACES.map(([f, , w]) => document.fonts.load(`${w} 40px ${f}`, f === 'VazL' ? 'Editor' : 'سلام۱')))
			.then(() => document.fonts.ready)
			.then(() => continueRender(h));
	}, [h]);
};

// brand spark (4-point star)
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

// "Jaraqe" — our own little spark character (body = brand spark, two eyes, two feet)
export const Jaraqe: React.FC<{x: number; y: number; s?: number; col?: string; eye?: string; blink?: number; look?: number; squash?: number; rot?: number; walk?: number; happy?: boolean}> = ({x, y, s = 1, col = '#f2a900', eye = '#1b1b1b', blink = 0, look = 0, squash = 0, rot = 0, walk = 0, happy}) => {
	const sy = 1 - squash, sx = 1 + squash * 0.8;
	const f = Math.sin(walk * Math.PI * 2);
	return (
		<g transform={`translate(${x},${y}) scale(${s})`}>
			<g transform={`translate(0,${-38}) scale(${sx},${sy}) translate(0,${38})`}>
				<rect x={-17 + f * 3} y={-12 - Math.max(0, f) * 6} width={10} height={12} rx={3} fill={col} />
				<rect x={7 - f * 3} y={-12 - Math.max(0, -f) * 6} width={10} height={12} rx={3} fill={col} />
				<g transform={`translate(0,-44) rotate(${rot})`}>
					<path d={sparkPath(40, 0.42)} fill={col} />
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
