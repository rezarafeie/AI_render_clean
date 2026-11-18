import React from 'react';
import {AbsoluteFill, Sequence, continueRender, delayRender, staticFile, useCurrentFrame} from 'remotion';
import '@fontsource/special-elite/400.css';
import '@fontsource/anton/400.css';
import data from './data.json';
import {SCENES, Ctx} from './Scenes';
import {clamp, eo, eio, FPS, W, H} from './vox';

type Word = {t: string; s: number; e: number};
type Scene = {id: string; start: number; dur: number; end: number; words: Word[]};
const scenes = data.scenes as Scene[];
const IN = 0.32;

const Fonts: React.FC = () => (
	<style>
		{[['Light', 300], ['Regular', 400], ['Medium', 500], ['Bold', 700], ['ExtraBold', 800]]
			.map(([n, w]) => `@font-face{font-family:'Doran';src:url('${staticFile(`fonts/DoranFaNum-${n}.woff2`)}') format('woff2');font-weight:${w};font-display:block;}`)
			.join('\n')}
	</style>
);

const Wrap: React.FC<{i: number; dur: number; children: React.ReactNode}> = ({i, dur, children}) => {
	const f = useCurrentFrame();
	const t = f / FPS;
	const p = i === 0 ? 1 : eo(clamp(t / IN));
	const dir = i % 2 ? 1 : -1;
	const push = 1 + 0.035 * (t / Math.max(dur, 1));
	const circle = i === 6 || i === 12;
	const style: React.CSSProperties = circle
		? {clipPath: `circle(${p * 125}% at 50% 55%)`}
		: {transform: `translateX(${(1 - p) * dir * 1150}px) rotate(${(1 - p) * dir * 4}deg)`, boxShadow: p < 1 ? '0 0 60px rgba(0,0,0,0.35)' : undefined};
	return (
		<AbsoluteFill style={style}>
			<AbsoluteFill style={{transform: `scale(${push})`}}>{children}</AbsoluteFill>
		</AbsoluteFill>
	);
};

export const Vox: React.FC = () => {
	const [h] = React.useState(() => delayRender('fonts'));
	React.useEffect(() => {
		Promise.all([800, 700, 500].map((w) => document.fonts.load(`${w} 60px Doran`, 'سلام')))
			.then(() => Promise.all([document.fonts.load('60px Anton', 'A'), document.fonts.load('60px "Special Elite"', 'A')]))
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
				const c = (w: string, occ = 0) => {
					const m = sc.words.filter((x) => x.t === w || x.t.startsWith(w));
					return (m[occ] ?? m[0] ?? {s: 0}).s + off;
				};
				const Comp = SCENES[i];
				return (
					<Sequence key={sc.id} from={from} durationInFrames={d} name={'S' + sc.id}>
						<Ctx.Provider value={{c, dur: d / FPS}}>
							<Wrap i={i} dur={d / FPS}>
								<Comp />
							</Wrap>
						</Ctx.Provider>
					</Sequence>
				);
			})}
		</AbsoluteFill>
	);
};
