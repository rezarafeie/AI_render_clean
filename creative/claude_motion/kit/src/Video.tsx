import React from 'react';
import {AbsoluteFill, Sequence, staticFile, useCurrentFrame, useVideoConfig, interpolate, continueRender, delayRender} from 'remotion';
import timing from './timing.json';
import {THEME} from './theme';
import {SceneCtx, clamp} from './lib';
import {Backdrop} from './art';
import {SCENES} from './Scenes';

/* The film's frame: its own backdrop (art.tsx), every scene in its time window with the word clock `cue`, a slow push-in and a soft blurred exit.
   The narration audio is muxed after the render, so nothing here plays sound. */

type Al = {chars: string; starts: number[]} | null;
type SceneT = {id: string; text: string; start: number; dur: number; al: Al};

const makeCue = (text: string, dur: number, al: Al) => (s: string, occ = 0, offset = 0) => {
	const src = al ? al.chars : text;
	let idx = -1;
	let from = 0;
	for (let i = 0; i <= occ; i++) {
		idx = src.indexOf(s, from);
		if (idx < 0) break;
		from = idx + 1;
	}
	if (idx < 0) return Math.max(0, offset);
	if (al) return Math.max(0, (al.starts[idx] ?? 0) + offset);
	return Math.max(0, (idx / Math.max(1, src.length)) * dur + offset);
};

// The film's font under its own name AND under every other font name a writer may have used in the code ('hasti', 'doran'...): one consistent family, never a silent fallback to a system font.
const fontNames = [THEME.font, ...(((THEME as any).aliases as string[] | undefined) ?? [])];
const fontCss = fontNames.flatMap((name) => (THEME.faces as {file: string; weight: string}[]).map((f) => `@font-face{font-family:'${name}';font-weight:${f.weight};src:url('${staticFile('fonts/' + f.file)}') format('truetype');}`)).join('');

const SceneWrap: React.FC<{dur: number; children: React.ReactNode; last: boolean}> = ({dur, children, last}) => {
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	const t = f / fps;
	const out = last ? 0 : clamp((t - (dur - 0.28)) / 0.28);
	const zoom = interpolate(t, [0, Math.max(0.01, dur)], [1, 1.035]);
	return (
		<AbsoluteFill style={{opacity: 1 - out, transform: `scale(${zoom + out * 0.06})`, filter: out > 0 ? `blur(${out * 18}px)` : undefined}}>
			{children}
		</AbsoluteFill>
	);
};

export const Main: React.FC = () => {
	const {fps} = useVideoConfig();
	const [h] = React.useState(() => delayRender('fonts'));
	React.useEffect(() => {
		Promise.all([400, 500, 700, 800, 900].map((w) => document.fonts.load(`${w} 40px ${THEME.font}`, 'سلام')))
			.then(() => document.fonts.ready)
			.then(() => continueRender(h))
			.catch(() => continueRender(h));
	}, [h]);
	const scenes = timing.scenes as SceneT[];
	return (
		<AbsoluteFill style={{background: THEME.background}}>
			<style>{fontCss}</style>
			<Backdrop />
			{scenes.map((s, i) => {
				const Comp = SCENES[i];
				if (!Comp) return null;
				const next = scenes[i + 1];
				const visEnd = next ? next.start + 0.12 : timing.total;
				const from = Math.round((i === 0 ? 0 : Math.max(0, s.start - 0.05)) * fps);
				const durF = Math.max(1, Math.round(visEnd * fps) - from);
				const sceneDur = durF / fps;
				const offset = s.start - from / fps;
				const cueBase = makeCue(s.text, s.dur, s.al);
				const cue = (str: string, occ = 0, off = 0) => cueBase(str, occ, off) + offset;
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
		</AbsoluteFill>
	);
};
