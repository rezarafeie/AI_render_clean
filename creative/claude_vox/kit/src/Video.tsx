// The frame of a Vox film: every scene is a sheet of paper slid over the previous one (alternating sides, with a shadow), or opened as a circle for the
// big moments (scene type big_term / growth_chart, or `circle` in timing.json); inside, a slow 3.5 % camera push. c('word') is the scene's cue clock.
import React from 'react';
import {AbsoluteFill, Sequence, continueRender, delayRender, staticFile, useCurrentFrame} from 'remotion';
import timing from './timing.json';
import {THEME} from './theme';
import {SCENES} from './Scenes';
import {Ctx, clamp, eo, FPS} from './vox';

type Word = {t: string; s: number; e: number};
type Scene = {id: string; start: number; dur: number; end: number; words: Word[]; type?: string; circle?: boolean};
const scenes = (timing as unknown as {scenes: Scene[]}).scenes;
const IN = 0.32;
const CIRCLE = new Set(['big_term', 'growth_chart']);

const norm = (s: string) => s.replace(/[ً-ْـ]/g, '').replace(/[‌‍]/g, '').replace(/[ي]/g, 'ی').replace(/[ك]/g, 'ک');

const Fonts: React.FC = () => (
	<style>
		{[
			...THEME.faces.map((f: {file: string; weight: string}) => `@font-face{font-family:'Doran';src:url('${staticFile('fonts/' + f.file)}');font-weight:${f.weight};font-display:block;}`),
			...THEME.aliases.map((a: string) => THEME.faces.map((f: {file: string; weight: string}) => `@font-face{font-family:'${a}';src:url('${staticFile('fonts/' + f.file)}');font-weight:${f.weight};font-display:block;}`).join('\n')),
			`@font-face{font-family:'Anton';src:url('${staticFile('fonts/Anton-Regular.ttf')}');font-display:block;}`,
			`@font-face{font-family:'Special Elite';src:url('${staticFile('fonts/SpecialElite-Regular.ttf')}');font-display:block;}`,
		].join('\n')}
	</style>
);

const Wrap: React.FC<{i: number; dur: number; circle: boolean; children?: React.ReactNode}> = ({i, dur, circle, children}) => {
	const f = useCurrentFrame();
	const t = f / FPS;
	const p = i === 0 ? 1 : eo(clamp(t / IN));
	const dir = i % 2 ? 1 : -1;
	const push = 1 + 0.035 * (t / Math.max(dur, 1));
	const style: React.CSSProperties = circle
		? {clipPath: `circle(${p * 125}% at 50% 55%)`}
		: {transform: `translateX(${(1 - p) * dir * 1150}px) rotate(${(1 - p) * dir * 4}deg)`, boxShadow: p < 1 ? '0 0 60px rgba(0,0,0,0.35)' : undefined};
	return (
		<AbsoluteFill style={{...style, overflow: 'hidden'}}>
			<AbsoluteFill style={{transform: `scale(${push})`}}>{children}</AbsoluteFill>
		</AbsoluteFill>
	);
};

export const Main: React.FC = () => {
	const [h] = React.useState(() => delayRender('fonts'));
	React.useEffect(() => {
		const loads = [800, 700, 500].map((w) => document.fonts.load(`${w} 60px Doran`, 'سلام'));
		Promise.all([...loads, document.fonts.load('60px Anton', 'A'), document.fonts.load('60px "Special Elite"', 'A')])
			.catch(() => null)
			.then(() => document.fonts.ready)
			.then(() => continueRender(h));
	}, [h]);
	return (
		<AbsoluteFill style={{background: '#2a2724'}}>
			<Fonts />
			{scenes.map((sc, i) => {
				const from = Math.round((i === 0 ? 0 : sc.start - IN) * FPS);
				const d = Math.round(sc.end * FPS) - from + 2;
				const off = sc.start - from / FPS;
				const words = sc.words.map((x) => ({...x, n: norm(x.t)}));
				const c = (w: string, occ = 0) => {
					const k = norm(String(w ?? ''));
					let m = words.filter((x) => x.n === k);
					if (!m.length) m = words.filter((x) => x.n.startsWith(k) || (k.length > 2 && k.startsWith(x.n) && x.n.length > 1));
					if (!m.length) m = words.filter((x) => x.n.includes(k));
					return (m[occ] ?? m[m.length - 1] ?? {s: 0}).s + off;
				};
				const Comp = SCENES[i] ?? (() => null);
				const circle = sc.circle ?? CIRCLE.has(sc.type ?? '');
				return (
					<Sequence key={sc.id} from={from} durationInFrames={d} name={'S' + sc.id}>
						<Ctx.Provider value={{c, dur: d / FPS}}>
							<Wrap i={i} dur={d / FPS} circle={i > 0 && circle}>
								<Comp />
							</Wrap>
						</Ctx.Provider>
					</Sequence>
				);
			})}
		</AbsoluteFill>
	);
};
