import React from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame, useVideoConfig, interpolate, continueRender, delayRender} from 'remotion';
import '@fontsource/vazirmatn/400.css';
import '@fontsource/vazirmatn/500.css';
import '@fontsource/vazirmatn/700.css';
import '@fontsource/vazirmatn/800.css';
import '@fontsource/vazirmatn/900.css';
import timing from './timing.json';
import {SceneCtx, useT, clamp} from './lib';
import {SCENES} from './Scenes';

type Al = {chars: string; starts: number[]} | null;

const makeCue = (text: string, dur: number, al: Al) => (s: string, occ = 0, offset = 0) => {
	const src = al ? al.chars : text;
	let idx = -1;
	let from = 0;
	for (let i = 0; i <= occ; i++) {
		idx = src.indexOf(s, from);
		if (idx < 0) break;
		from = idx + 1;
	}
	if (idx < 0) {
		console.warn('cue not found', s);
		return offset;
	}
	if (al) return (al.starts[idx] ?? 0) + offset;
	return (idx / src.length) * dur + offset;
};

const Background: React.FC = () => {
	const t = useT();
	return (
		<AbsoluteFill>
			<AbsoluteFill style={{background: 'radial-gradient(ellipse 85% 65% at 50% 45%, #FAFAF6 0%, #EEEFE9 55%, #D9DBD3 100%)'}} />
			<svg width={1080} height={1920} style={{position: 'absolute', opacity: 0.55}}>
				<defs>
					<radialGradient id="gm" cx="0.5" cy="0.5" r="0.5">
						<stop offset="0" stopColor="#fff" />
						<stop offset="1" stopColor="#000" />
					</radialGradient>
					<mask id="gmask">
						<ellipse cx={540 + Math.sin(t * 0.3) * 60} cy={1150 + Math.cos(t * 0.25) * 80} rx={430} ry={520} fill="url(#gm)" />
					</mask>
				</defs>
				<g mask="url(#gmask)" stroke="#9aa199" strokeWidth={1.6} strokeDasharray="6 9">
					{Array.from({length: 14}).map((_, i) => (
						<line key={'v' + i} x1={i * 90 - 45} x2={i * 90 - 45} y1={0} y2={1920} />
					))}
					{Array.from({length: 24}).map((_, i) => (
						<line key={'h' + i} y1={i * 90} y2={i * 90} x1={0} x2={1080} />
					))}
				</g>
				<g mask="url(#gmask)" fill="#8d948c">
					{Array.from({length: 14 * 24}).map((_, k) => (
						<circle key={k} cx={(k % 14) * 90 - 45} cy={Math.floor(k / 14) * 90} r={3} />
					))}
				</g>
			</svg>
			{/* film grain-ish vignette */}
			<AbsoluteFill style={{boxShadow: 'inset 0 0 260px rgba(0,0,0,0.10)'}} />
		</AbsoluteFill>
	);
};

const SceneWrap: React.FC<{dur: number; children: React.ReactNode; last: boolean}> = ({dur, children, last}) => {
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	const t = f / fps;
	const end = dur;
	const out = last ? 0 : clamp((t - (end - 0.28)) / 0.28);
	const zoom = interpolate(t, [0, end], [1, 1.035]);
	return (
		<AbsoluteFill
			style={{
				opacity: 1 - out,
				transform: `scale(${zoom + out * 0.06})`,
				filter: out > 0 ? `blur(${out * 18}px)` : undefined,
			}}
		>
			{children}
		</AbsoluteFill>
	);
};

export const Main: React.FC = () => {
	const {fps} = useVideoConfig();
	const [h] = React.useState(() => delayRender('fonts'));
	React.useEffect(() => {
		Promise.all(
			[400, 500, 700, 800, 900].map((w) => document.fonts.load(`${w} 40px Vazirmatn`, 'سلام'))
		).then(() => document.fonts.ready).then(() => continueRender(h));
	}, [h]);
	const scenes = timing.scenes as {id: string; text: string; start: number; dur: number; audio: boolean; al: Al}[];
	return (
		<AbsoluteFill style={{background: '#EEEFE9'}}>
			<Background />
			{scenes.map((s, i) => {
				const next = scenes[i + 1];
				const visEnd = next ? next.start + 0.12 : timing.total;
				const from = Math.round((i === 0 ? 0 : s.start - 0.05) * fps);
				const durF = Math.round(visEnd * fps) - from;
				const sceneDur = durF / fps;
				const offset = s.start - from / fps; // audio-relative to scene-relative
				const cueBase = makeCue(s.text, s.dur, s.al);
				const cue = (str: string, occ = 0, off = 0) => cueBase(str, occ, off) + offset;
				const Comp = SCENES[i];
				return (
					<Sequence key={s.id} from={from} durationInFrames={durF} name={'scene ' + s.id}>
						<SceneCtx.Provider value={{dur: sceneDur, cue}}>
							<SceneWrap dur={sceneDur} last={!next}>
								<Comp />
							</SceneWrap>
						</SceneCtx.Provider>
					</Sequence>
				);
			})}
			{scenes.map((s) =>
				s.audio ? (
					<Sequence key={'a' + s.id} from={Math.round(s.start * fps)}>
						<Audio src={staticFile(`voice/proc/${s.id}.wav`)} />
					</Sequence>
				) : null
			)}
		</AbsoluteFill>
	);
};
