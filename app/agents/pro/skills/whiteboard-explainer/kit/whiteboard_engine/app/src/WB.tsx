import React from 'react';
import {AbsoluteFill, continueRender, delayRender, staticFile, useCurrentFrame} from 'remotion';
import {FPS, W, H, clamp, lerp, eio, eo, INK, ItemView, Item, Marker, Eraser, Magnet, MagnetCard, camAt, s2w, tipOf, prog, ptAt, setFontsReady, S, cat, Erase} from './engine';
import {ITEMS, CAM, BOARD, MAGNETS, CAPS, TOTAL} from './scenes';

const FontCSS = () => (
	<style>
		{`@font-face{font-family:'VazL';src:url('${staticFile('fonts/vazL800.woff2')}') format('woff2');font-weight:800;font-display:block;}@font-face{font-family:'Marhey';src:url('${staticFile('fonts/marhey.woff2')}') format('woff2');font-weight:600;font-display:block;}` +
			[['Medium', 500], ['Bold', 700], ['ExtraBold', 800]]
				.map(([n, w]) => `@font-face{font-family:'Doran';src:url('${staticFile(`fonts/DoranFaNum-${n}.woff2`)}') format('woff2');font-weight:${w};font-display:block;}`)
				.join('\n')}
	</style>
);

// faint ghosts of old lessons
const GHOSTS = (() => {
	const g: {d: string}[] = [];
	let seed = 7;
	const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
	for (let k = 0; k < 46; k++) {
		const x = rnd() * BOARD.w, y = rnd() * BOARD.h, r = 40 + rnd() * 120, m = Math.floor(rnd() * 4);
		const p = m === 0 ? S.circle(x, y, r * 2) : m === 1 ? S.arrow([[x, y], [x + r * 1.6, y - r * 0.4]]) : m === 2 ? S.rect(x, y, r * 2, r * 1.2) : S.curve([[x, y], [x + r, y - r * 0.6], [x + r * 2, y], [x + r * 3, y - r * 0.5]]);
		p.forEach((q) => g.push({d: q.d}));
	}
	return g;
})();

const Board: React.FC = () => (
	<>
		<rect x={-6000} y={-6000} width={BOARD.w + 12000} height={BOARD.h + 12000} fill="#d5d9dc" />
		<rect x={-60} y={-60} width={BOARD.w + 120} height={BOARD.h + 120} rx={18} fill="#b9bec4" />
		<rect x={-44} y={-44} width={BOARD.w + 88} height={BOARD.h + 88} rx={12} fill="#e6e8ea" />
		<rect x={0} y={0} width={BOARD.w} height={BOARD.h} fill="url(#tex)" />
		<rect x={0} y={0} width={BOARD.w} height={BOARD.h} fill="url(#boardgrad)" />
		<g opacity={0.055} stroke="#55606e" strokeWidth={6} fill="none" strokeLinecap="round">
			{GHOSTS.map((q, i) => (
				<path key={i} d={q.d} />
			))}
		</g>
		{/* marker tray */}
		<rect x={300} y={BOARD.h + 50} width={BOARD.w - 600} height={70} rx={14} fill="#aeb4ba" />
		<rect x={300} y={BOARD.h + 50} width={BOARD.w - 600} height={18} rx={9} fill="#c9ced3" />
	</>
);

const BoxIcon = () => (
	<g stroke="#fff" strokeWidth={5} fill="none" strokeLinejoin="round">
		<rect x={-22} y={-14} width={44} height={34} />
		<path d="M-22,-14 L-10,-26 L32,-26 L22,-14 M22,-14 L32,-26 L32,8 L22,20" />
	</g>
);

const PEN = ITEMS.filter((i) => i.pen !== false).sort((a, b) => a.t0 - b.t0);
const ERASES: {e: Erase; ox: number; oy: number}[] = [];
ITEMS.forEach((i) => {
	if (i.erase && !ERASES.find((x) => x.e === i.erase)) ERASES.push({e: i.erase, ox: i.ox ?? 0, oy: i.oy ?? 0});
});

const penState = (t: number, cam: any) => {
	let act: Item | null = null;
	for (const j of PEN) if (t >= j.t0 && t <= j.t0 + j.dur) act = j;
	if (act) return {pos: tipOf(act, prog(act, t)), lift: 0, col: act.col, show: true};
	let prev: Item | null = null, next: Item | null = null;
	for (const j of PEN) {
		if (j.t0 + j.dur < t && (!prev || j.t0 + j.dur > prev.t0 + prev.dur)) prev = j;
		if (j.t0 > t && (!next || j.t0 < next.t0)) next = j;
	}
	const park = s2w(cam, W + 260, H * 0.62) as [number, number];
	if (prev && next) {
		const a = tipOf(prev, 1), b = tipOf(next, 0), gap = next.t0 - (prev.t0 + prev.dur);
		if (gap < 1.3) {
			const u = (t - (prev.t0 + prev.dur)) / gap;
			const d = Math.hypot(b[0] - a[0], b[1] - a[1]);
			return {pos: [lerp(a[0], b[0], eio(u)), lerp(a[1], b[1], eio(u))], lift: Math.sin(Math.PI * u) * (0.35 + clamp(d / 700) * 0.65), col: u < 0.5 ? prev.col : next.col, show: true};
		}
	}
	if (prev && t - (prev.t0 + prev.dur) < 0.45) {
		const u = eio((t - (prev.t0 + prev.dur)) / 0.45), a = tipOf(prev, 1);
		return {pos: [lerp(a[0], park[0], u), lerp(a[1], park[1], u)], lift: Math.min(1, u * 2), col: prev.col, show: true};
	}
	if (next && next.t0 - t < 0.45) {
		const u = eio(1 - (next.t0 - t) / 0.45), b = tipOf(next, 0);
		return {pos: [lerp(park[0], b[0], u), lerp(park[1], b[1], u)], lift: Math.min(1, (1 - u) * 2), col: next.col, show: true};
	}
	return {pos: park, lift: 1, col: INK.k, show: false};
};

const Captions: React.FC<{t: number}> = ({t}) => {
	const cap = CAPS.find((c) => t >= c.t0 && t < c.t1);
	if (!cap) return null;
	const a = clamp((t - cap.t0) / 0.12);
	return (
		<div style={{position: 'absolute', left: 0, right: 0, top: 1490, display: 'flex', justifyContent: 'center', opacity: a}}>
			<div
				style={{
					maxWidth: 940,
					background: 'rgba(255,255,255,0.94)',
					borderRadius: 22,
					padding: '14px 34px 18px',
					boxShadow: '0 6px 22px rgba(0,0,0,0.12)',
					direction: 'rtl',
					fontFamily: 'Doran',
					fontWeight: 700,
					fontSize: 50,
					lineHeight: 1.45,
					color: '#23262c',
					textAlign: 'center',
					transform: `translateY(${(1 - eo(a)) * 10}px)`,
					borderBottom: `6px solid ${INK.b}`,
				}}
			>
				{cap.text}
			</div>
		</div>
	);
};

export const WB: React.FC = () => {
	const [h] = React.useState(() => delayRender('fonts'));
	React.useEffect(() => {
		Promise.all([document.fonts.load('600 60px Marhey', 'سلام'), document.fonts.load('800 60px Doran', 'سلام۱'), document.fonts.load('700 60px Doran', 'سلام'), document.fonts.load('800 50px VazL', 'Rafiei')])
			.then(() => document.fonts.ready)
			.then(() => {
				setFontsReady();
				continueRender(h);
			});
	}, [h]);
	const f = useCurrentFrame();
	const t = f / FPS;
	const cam = camAt(CAM, t);
	const pen = penState(t, cam);
	const tf = `translate(${W / 2},${H / 2}) scale(${cam.z}) translate(${-cam.x},${-cam.y})`;
	// sheen drifts slower than the camera
	const sx = -cam.x * cam.z * 0.35, sy = -cam.y * cam.z * 0.12;
	return (
		<AbsoluteFill style={{background: '#d5d9dc'}}>
			<FontCSS />
			<svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
				<defs>
					<pattern id="tex" patternUnits="userSpaceOnUse" width={1024} height={1024}>
						<image href={staticFile('board.jpg')} width={1024} height={1024} />
					</pattern>
					<linearGradient id="boardgrad" x1="0" y1="0" x2="1" y2="1">
						<stop offset="0" stopColor="#fff" stopOpacity={0.25} />
						<stop offset="1" stopColor="#e9e6dc" stopOpacity={0.25} />
					</linearGradient>
					<radialGradient id="gloss" cx="0.35" cy="0.3" r="0.7">
						<stop offset="0" stopColor="#fff" stopOpacity={0.55} />
						<stop offset="0.45" stopColor="#fff" stopOpacity={0.08} />
						<stop offset="1" stopColor="#000" stopOpacity={0.18} />
					</radialGradient>
					<linearGradient id="sheen" gradientUnits="userSpaceOnUse" x1={sx} y1={0} x2={sx + 2600} y2={900} spreadMethod="repeat">
						<stop offset="0" stopColor="#fff" stopOpacity={0} />
						<stop offset="0.45" stopColor="#fff" stopOpacity={0.13} />
						<stop offset="0.55" stopColor="#fff" stopOpacity={0.1} />
						<stop offset="1" stopColor="#fff" stopOpacity={0} />
					</linearGradient>
				</defs>
				<g transform={tf}>
					<Board />
					<g style={{mixBlendMode: 'multiply'}}>
						{ITEMS.map((it) => (
							<ItemView key={it.id} it={it} t={t} />
						))}
					</g>
					{MAGNETS.map((m, i) => {
						if (t < m.t0) return null;
						const drop = eo(clamp((t - m.t0) / 0.28));
						if (m.kind === 'box') {
							const u = clamp((t - m.t0 - 0.25) / (m.t1! - m.t0 - 0.25));
							const p = ptAt(m.path!, eio(u));
							return <Magnet key={i} x={p[0]} y={p[1]} col={m.col} drop={drop} icon={<BoxIcon />} />;
						}
						return (
							<MagnetCard key={i} x={m.x!} y={m.y!} w={860} h={170} col={m.col} drop={drop}>
								<text x={390} y={22} textAnchor="start" direction="rtl" fontFamily="Marhey" fontWeight={600} fontSize={50} fill="#23262c">
									{m.sub}
								</text>
								<text x={-390} y={30} textAnchor="start" fontFamily="VazL" fontWeight={800} fontSize={50} fill={m.col}>
									{m.title}
								</text>
							</MagnetCard>
						);
					})}
					{ERASES.map(({e, ox, oy}, i) => {
						if (t < e.t0 - 0.3 || t > e.t0 + e.dur + 0.3) return null;
						const u = clamp((t - e.t0) / e.dur);
						const p = ptAt(e.pts, u);
						const a = t < e.t0 ? 1 - (e.t0 - t) / 0.3 : t > e.t0 + e.dur ? 1 - (t - e.t0 - e.dur) / 0.3 : 1;
						return (
							<g key={i} opacity={clamp(a * 1.5)}>
								<Eraser x={p[0] + ox} y={p[1] + oy + (1 - a) * -60} s={1 + (1 - a) * 0.15} />
							</g>
						);
					})}
					{pen.show && <Marker x={pen.pos[0]} y={pen.pos[1]} col={pen.col} lift={pen.lift} />}
				</g>
				<rect x={0} y={0} width={W} height={H} fill="url(#sheen)" opacity={0.9} />
			</svg>
			<Captions t={t} />
		</AbsoluteFill>
	);
};
export const DURATION = Math.round(TOTAL * FPS);
