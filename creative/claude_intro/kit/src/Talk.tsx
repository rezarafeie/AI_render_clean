// Intro engine 3 — Presenter (1920x1080, 30 fps): the person's own footage + an edit that shows itself: every narration line performs one editing
// technique on screen (its `treatment`). Lines, on-screen words, the cue of every word (from the narration's word times), where the face is and
// which part of the footage each scene uses come from content.json (creative/claude_intro/presenter.py).
import React from 'react';
import {AbsoluteFill, OffthreadVideo, staticFile, useCurrentFrame} from 'remotion';
import {CONTENT, TIMING, Fonts, useFonts, clamp, lerp, seg, eo5, eio, back, rnd, fit, markPath, markScale} from './lib';

const FPS = 30, W = 1920, H = 1080;
const C = {cream: '#f3ecdc', ink: '#161412', orange: (CONTENT.palette ?? {}).accent ?? '#ff5a1f', paper: '#e9e5dc'};
const DUR: number = TIMING.total;
type Line = {text: string; treatment: string; [k: string]: any};
type LT = {a: number; b: number; v: number; src: number[]; cues: Record<string, any>};
const LINES: Line[] = CONTENT.lines ?? [];
const LT_: LT[] = TIMING.lines ?? [];
const F = CONTENT.footage ?? {};
const RATE: number = F.rate ?? 0.7;
const FACE: [number, number] = F.face ?? [0.5, 0.4];
const CUT_X: number = F.cut_x ?? 554, CUT_W: number = F.cut_w ?? 812;

// footage scaled by `scale` and shifted so the face sits at (tx, ty) of the frame, never showing an edge
const place = (scale: number, tx = 0.5, ty = 0.42) => ({
	x: clamp(tx * W - FACE[0] * W * scale, -(scale - 1) * W, 0),
	y: clamp(ty * H - FACE[1] * H * scale, -(scale - 1) * H, 0),
});
const Foot: React.FC<{src0: number; rate?: number; scale?: number; x?: number; y?: number; filter?: string; style?: React.CSSProperties}> = ({src0, rate = RATE, scale = 1, x = 0, y = 0, filter, style}) => (
	<OffthreadVideo src={staticFile(F.file ?? 'talk/footage.mp4')} muted startFrom={Math.max(0, Math.round(src0 * FPS))} playbackRate={rate} style={{position: 'absolute', left: 0, top: 0, width: W, height: H, transform: `translate(${x}px,${y}px) scale(${scale})`, transformOrigin: '0 0', filter, ...style}} />
);
const NIGHT = 'brightness(.6) contrast(1.16) saturate(.85)';
// colour is laid over the footage (soft-light), never rotated: hue-rotate ruins skin
const Grade: React.FC<{o?: number}> = ({o = 1}) => (
	<>
		<AbsoluteFill style={{background: 'linear-gradient(115deg, rgba(0,70,92,.7) 0%, rgba(20,40,60,.45) 55%, rgba(110,45,10,.5) 100%)', mixBlendMode: 'soft-light', opacity: o}} />
		<AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 42%, rgba(0,0,0,0) 35%, rgba(0,0,0,.62) 100%)', opacity: o}} />
	</>
);
const Tag: React.FC<{text?: string; dark?: boolean; left?: boolean}> = ({text, dark, left}) => text ? (
	<div style={{position: 'absolute', top: 54, [left ? 'left' : 'right']: 64, fontFamily: 'Vaz, VazL', fontWeight: 500, fontSize: 18, letterSpacing: 3, color: dark ? 'rgba(22,20,18,.6)' : 'rgba(243,236,220,.7)', direction: 'rtl', display: 'flex', alignItems: 'center', gap: 10} as React.CSSProperties}>
		<span style={{width: 9, height: 9, borderRadius: 9, background: C.orange, display: 'inline-block'}} />
		{text}
	</div>
) : null;
const rise = (t: number, t0: number, d = 0.35) => ({opacity: clamp((t - t0) / 0.12), transform: `translateY(${(1 - eo5(clamp((t - t0) / d))) * 46}px)`});
const big: React.CSSProperties = {position: 'absolute', fontFamily: 'Pey', fontWeight: 900, color: C.cream, direction: 'rtl', whiteSpace: 'nowrap', lineHeight: 1.5};

// ---------- treatments ----------
type TP = {t: number; L: Line; M: LT};
// the brand split around the presenter's head, two small lines under it
const TitleSplit: React.FC<TP> = ({t, L, M}) => {
	const lt = t - M.a, push = 1.3 + lt * 0.012, p = place(push, 0.5, 0.45), c = M.cues;
	const half = W / 2 - 200;
	return (
		<>
			<Foot src0={M.src[0]} scale={push} x={p.x} y={p.y} filter={NIGHT} />
			<Grade />
			<Tag text={L.tag} />
			<div style={{...big, right: 110, top: 170, fontSize: fit(L.a ?? '', 'Pey', 900, 168, half), ...rise(t, c.a ?? M.v)}}>{L.a}</div>
			<div style={{...big, left: 70, top: 170, fontSize: fit(L.b ?? '', 'Pey', 900, 168, half), ...rise(t, c.b ?? M.v + 0.55)}}>{L.b}</div>
			<div style={{position: 'absolute', left: 120, top: 560, fontFamily: 'Vaz', fontWeight: 500, fontSize: 34, color: C.cream, direction: 'rtl', lineHeight: 1.7}}>
				{(L.sub ?? []).slice(0, 2).map((s: string, i: number) => <div key={i} style={rise(t, (c.sub ?? [])[i] ?? M.v + 1.4 + i * 0.6)}>{s}</div>)}
			</div>
		</>
	);
};
// four hard cuts on four words: a colour card, type on the wall, a grading wipe, a waveform
const WordCards: React.FC<TP> = ({t, L, M}) => {
	const ws: {w: string; tag?: string}[] = L.cards ?? [];
	const cs: number[] = M.cues.words ?? [];
	let k = 0;
	for (let i = 0; i < cs.length; i++) if (t >= cs[i]) k = i;
	const l = t - (cs[k] ?? M.a), w = ws[k] ?? {w: ''}, src = M.src[k] ?? M.src[0];
	const mode = k % 4;
	if (mode === 0) return (
		<AbsoluteFill style={{background: `radial-gradient(ellipse at 55% 45%, #ff7a3a 0%, ${C.orange} 70%)`}}>
			<div style={{...big, left: 0, right: 0, top: '50%', marginTop: -390, textAlign: 'center', fontSize: fit(w.w, 'Pey', 900, 520, 1500), transform: `scale(${lerp(1.25, 1, eo5(clamp(l / 0.2)))})`}}>{w.w}</div>
		</AbsoluteFill>
	);
	if (mode === 1) { const p = place(1.12, 0.3, 0.45); return (
		<>
			<Foot src0={src} scale={1.12} x={p.x} y={p.y} filter="brightness(.95) saturate(1.05)" />
			<AbsoluteFill style={{background: 'linear-gradient(90deg, rgba(0,0,0,.0) 40%, rgba(10,20,30,.35) 100%)'}} />
			<div style={{...big, right: 90, top: 60, fontSize: fit(w.w, 'Pey', 900, 470, 900), textShadow: '0 10px 60px rgba(0,0,0,.25)', transform: `translateY(${(1 - eo5(clamp(l / 0.25))) * 120}px)`, opacity: clamp(l / 0.1)}}>{w.w}</div>
			<Tag text={w.tag} left />
		</>
	); }
	if (mode === 2) { const x = lerp(0.12, 0.72, eio(clamp(l / 0.6))), p = place(1.1, 0.45, 0.45); return (
		<>
			<Foot src0={src} scale={1.1} x={p.x} y={p.y} filter="saturate(.25) contrast(.82) brightness(1.05)" />
			<div style={{position: 'absolute', inset: 0, clipPath: `inset(0 0 0 ${x * 100}%)`}}>
				<Foot src0={src} scale={1.1} x={p.x} y={p.y} filter="brightness(.74) contrast(1.2) saturate(1.25)" />
				<AbsoluteFill style={{background: 'linear-gradient(120deg, rgba(0,80,100,.5), rgba(120,50,0,.35))', mixBlendMode: 'soft-light'}} />
			</div>
			<div style={{position: 'absolute', left: `${x * 100}%`, top: 0, bottom: 0, width: 4, background: C.cream}} />
			<div style={{...big, right: 110, bottom: 60, fontSize: fit(w.w, 'Pey', 900, 230, 800), ...rise(t, cs[k] ?? M.a)}}>{w.w}</div>
			{w.tag && <div style={{position: 'absolute', left: 70, bottom: 70, fontFamily: 'Vaz', fontWeight: 500, fontSize: 22, color: '#fff', letterSpacing: 2}}>{w.tag}</div>}
		</>
	); }
	const p = place(1.3, 0.5, 0.45);
	return (
		<>
			<Foot src0={src} scale={1.3} x={p.x} y={p.y} filter={NIGHT} />
			<Grade />
			<svg width={W} height={H} style={{position: 'absolute'}}>
				{Array.from({length: 96}).map((_, i) => {
					const a = (0.25 + rnd(i) * 0.75) * (0.4 + 0.6 * Math.abs(Math.sin(l * 9 + i * 0.6))) * Math.sin((i / 95) * Math.PI) * eo5(clamp(l / 0.3));
					return <rect key={i} x={160 + i * 16.8} y={760 - a * 150} width={8} height={a * 300 + 4} rx={4} fill={i % 12 === 5 ? C.orange : C.cream} opacity={0.9} />;
				})}
			</svg>
			<div style={{...big, right: 150, top: 130, fontSize: fit(w.w, 'Pey', 900, 240, 800), ...rise(t, cs[k] ?? M.a)}}>{w.w}</div>
			<Tag text={w.tag} left />
		</>
	);
};
// the background falls away and the same person stays as a sticker cut-out, then is moved and resized
const CutoutPlace: React.FC<TP> = ({t, L, M}) => {
	const c = M.cues, tc = c.cut ?? M.v + 0.9, tm = c.move ?? M.v + 2.0;
	const cut = eo5(seg(t, tc, tc + 0.45));
	const mv = eio(seg(t, tm, tm + 0.7));
	const personRight = CUT_X + CUT_W / 2 > W / 2;          // the text takes the other side
	const endX = personRight ? W - 250 - CUT_W : 250;
	const sc = lerp(1, 0.74, mv), cx = lerp(CUT_X, endX, mv), cy = lerp(0, 30, mv);
	const sticker = cut * 5;
	const tx: React.CSSProperties = personRight ? {left: 130} : {right: 130};
	return (
		<AbsoluteFill style={{background: `radial-gradient(ellipse at 30% 30%, #f6f2ea 0%, ${C.paper} 60%, #d9d4c8 100%)`}}>
			<AbsoluteFill style={{opacity: 1 - cut}}><Foot src0={M.src[0]} rate={F.cut_rate ?? 0.85} /></AbsoluteFill>
			<div style={{position: 'absolute', left: cx + CUT_W / 2 - 260, top: lerp(140, 190, mv), width: 520, height: 520, borderRadius: 520, background: `radial-gradient(circle at 35% 30%, #ff8a55, ${C.orange})`, transform: `scale(${back(seg(t, tm - 0.1, tm + 0.4))})`}} />
			<div style={{position: 'absolute', left: cx, top: cy, width: CUT_W, height: H, transform: `scale(${sc}) rotate(${mv * -3}deg)`, transformOrigin: '50% 100%', filter: `drop-shadow(${sticker}px 0 0 #fff) drop-shadow(-${sticker}px 0 0 #fff) drop-shadow(0 -${sticker}px 0 #fff) drop-shadow(0 ${sticker}px 0 #fff) drop-shadow(0 18px 26px rgba(0,0,0,${0.28 * cut}))`}}>
				<OffthreadVideo src={staticFile(F.cut ?? 'talk/cut.webm')} transparent muted startFrom={0} playbackRate={F.cut_rate ?? 0.85} style={{width: CUT_W, height: H}} />
			</div>
			<div style={{position: 'absolute', ...tx, top: 300, direction: 'rtl', fontFamily: 'Pey', fontWeight: 400, fontSize: fit(L.l2 ?? L.l1 ?? '', 'Pey', 900, 84, 760), color: C.ink, lineHeight: 1.6, whiteSpace: 'nowrap'}}>
				<div style={rise(t, c.l1 ?? tc + 0.1)}>{L.l1}</div>
				<div style={{...rise(t, c.l2 ?? tm + 0.1), fontWeight: 900}}>{L.l2}</div>
				{L.l3 && <div style={{...rise(t, (c.l2 ?? tm + 0.1) + 0.4), fontFamily: 'VazL', fontWeight: 500, fontSize: 30, color: C.orange, direction: 'ltr', textAlign: 'right', letterSpacing: 2}}>{L.l3}</div>}
			</div>
			<Tag text={L.tag} dark left={personRight} />
		</AbsoluteFill>
	);
};
// b-roll drawn by code: a field of dots under the brand mark
const BrollCode: React.FC<TP> = ({t, L, M}) => {
	const lt = t - M.a;
	const NX = 60, NY = 22, PAL = [C.orange, '#d9ff3d', '#b9a8ff', C.cream, '#5b6bff'];
	const m = eio(clamp(lt / 0.8));
	return (
		<AbsoluteFill style={{background: '#0c0b1a'}}>
			<svg width={W} height={H}>
				{Array.from({length: NX * NY}).map((_, i) => {
					const ix = i % NX, iy = Math.floor(i / NX), gx = (ix / (NX - 1) - 0.5) * 2, gz = iy / (NY - 1);
					const wave = Math.sin(gx * 4.2 + lt * 3 + gz * 3) * 0.17 + Math.sin(gx * 9 - lt * 2 + gz * 7) * 0.05;
					const z = 0.5 + gz * 1.5;
					const px = 960 + (gx / z) * 1300, py = 420 + ((0.4 + wave) / z) * 620;
					const sx = 960 + (rnd(i) - 0.5) * 3600, sy = 540 + (rnd(i + 3) - 0.5) * 2200;
					return <circle key={i} cx={lerp(sx, px, m)} cy={lerp(sy, py, m)} r={lerp(3, 8 / z, m)} fill={PAL[(ix + iy * 2) % 5]} opacity={clamp(1.25 - gz * 0.6)} />;
				})}
				<g transform={`translate(960,330) rotate(${lt * 50}) scale(${back(clamp(lt / 0.5))})`}><path d={markPath(110, 0.3)} fill={C.orange} transform={`scale(${markScale(110)})`} /></g>
			</svg>
			<AbsoluteFill style={{background: 'linear-gradient(20deg, rgba(12,11,26,.95) 8%, rgba(12,11,26,0) 45%)'}} />
			<Tag text={L.tag} />
			<div style={{...big, left: 110, bottom: 70, fontSize: fit(L.title ?? '', 'Pey', 400, 120, 1500), fontWeight: 400, ...rise(t, M.cues.title ?? M.v + 1.2)}}>{L.title}</div>
		</AbsoluteFill>
	);
};
// the footage in a card beside a glass timeline panel: no editing program needed
const NoNle: React.FC<TP> = ({t, L, M}) => {
	const lt = t - M.a;
	const names: string[] = L.tracks ?? [];
	const cols = ['#5d5a55', '#f7a600', '#7d8cff', '#e86a4a', '#58b28a'];
	const clipsOf = [[[0, 0.28], [0.3, 0.6], [0.62, 1]], [[0.03, 0.22], [0.26, 0.5], [0.55, 0.92]], [[0.44, 0.6]], [[0, 1]], [[0, 1]]];
	return (
		<AbsoluteFill style={{background: `radial-gradient(ellipse at 70% 30%, #f6f2ea 0%, ${C.paper} 60%, #d9d4c8 100%)`}}>
			<div style={{position: 'absolute', right: 110, top: 250, width: 800, height: 450, borderRadius: 26, overflow: 'hidden', boxShadow: '0 30px 70px rgba(0,0,0,.25)', transform: `translateY(${(1 - eo5(clamp(lt / 0.4))) * 60}px)`}}>
				<OffthreadVideo src={staticFile(F.file ?? 'talk/footage.mp4')} muted startFrom={Math.round(M.src[0] * FPS)} playbackRate={RATE} style={{width: 800, height: 450, objectFit: 'cover', objectPosition: `${FACE[0] * 100}% ${FACE[1] * 100}%`}} />
			</div>
			<div style={{position: 'absolute', left: 110, top: 330, width: 760, height: 400, borderRadius: 24, background: 'rgba(40,38,36,.86)', boxShadow: '0 30px 70px rgba(0,0,0,.22)', transform: `translateY(${(1 - eo5(clamp((lt - 0.1) / 0.4))) * 60}px)`, opacity: clamp(lt / 0.15)}}>
				<div style={{position: 'absolute', right: 30, top: 22, fontFamily: 'Vaz', fontWeight: 500, fontSize: 17, color: '#aaa', letterSpacing: 2, direction: 'rtl'}}>{L.panel ?? ''}</div>
				{names.slice(0, 5).map((n, i) => (
					<div key={i} style={{position: 'absolute', left: 30, right: 30, top: 70 + i * 62, height: 44}}>
						<div style={{position: 'absolute', right: 0, top: 9, fontFamily: 'Vaz', fontWeight: 500, fontSize: 18, color: '#bbb', direction: 'rtl'}}>{n}</div>
						<div style={{position: 'absolute', left: 0, right: 90, top: 0, bottom: 0, background: 'rgba(255,255,255,.06)', borderRadius: 8}}>
							{clipsOf[i].map(([a, b], k) => <div key={k} style={{position: 'absolute', right: `${a * 100}%`, width: `${(b - a) * 100 * eo5(clamp((lt - 0.25 - i * 0.07 - k * 0.05) / 0.35))}%`, top: 5, bottom: 5, background: cols[i], borderRadius: 6}} />)}
						</div>
					</div>
				))}
				<div style={{position: 'absolute', top: 60, bottom: 20, right: `${14 + clamp(lt / 1.9) * 72}%`, width: 3, background: C.orange}} />
			</div>
			<div style={{position: 'absolute', left: 110, top: 150, fontFamily: 'Pey', fontWeight: 900, fontSize: fit(L.title ?? '', 'Pey', 900, 104, 800), color: C.ink, direction: 'rtl', whiteSpace: 'nowrap', ...rise(t, M.cues.title ?? M.v + 0.5)}}>{L.title}</div>
		</AbsoluteFill>
	);
};
// the one prompt: a chat card whose words arrive with the narrator's
const PromptCard: React.FC<TP> = ({t, L, M}) => {
	const lt = t - M.a, c = M.cues;
	const words: string[] = L.words ?? [], cw: number[] = c.words ?? [];
	const push = 1.3 + lt * 0.015, p = place(push, 0.66, 0.45);
	return (
		<>
			<Foot src0={M.src[0]} scale={push} x={p.x} y={p.y} filter={NIGHT} />
			<Grade />
			<div style={{position: 'absolute', left: 110, top: 300, fontFamily: 'Vaz', fontWeight: 500, fontSize: 30, color: C.cream, direction: 'rtl', ...rise(t, c.label ?? M.v + 0.3)}}>{L.label}</div>
			<div style={{position: 'absolute', left: 110, top: 370, width: 620, minHeight: 190, borderRadius: 24, background: 'rgba(22,22,22,.82)', border: '1px solid rgba(255,255,255,.14)', padding: '26px 32px', boxSizing: 'border-box', direction: 'rtl', ...rise(t, c.card ?? M.v + 0.6)}}>
				<div style={{fontFamily: 'Vaz', fontWeight: 500, fontSize: 17, color: '#9a9a9a', letterSpacing: 2, display: 'flex', alignItems: 'center', gap: 8}}><span style={{width: 8, height: 8, borderRadius: 8, background: C.orange, display: 'inline-block'}} />{L.who ?? ''}</div>
				<div style={{fontFamily: 'Vaz', fontWeight: 500, fontSize: 46, color: '#f3f3f3', marginTop: 18, lineHeight: 1.5}}>
					{words.map((w, i) => <span key={i} style={{opacity: t >= (cw[i] ?? M.v + 1 + i * 0.3) - 0.05 ? 1 : 0, marginLeft: 12, display: 'inline-block'}}>{w}</span>)}
					<span style={{display: 'inline-block', width: 4, height: 44, background: C.orange, verticalAlign: 'middle', opacity: Math.floor(lt * 3) % 2 ? 0.2 : 1}} />
				</div>
			</div>
			<div style={{...big, left: 110, top: 30, fontSize: fit(L.lead ?? '', 'Pey', 900, 220, 700), ...rise(t, c.lead ?? M.v)}}>{L.lead}</div>
		</>
	);
};
// the brand over the blurred, darkened footage
const EndCard: React.FC<TP> = ({t, L, M}) => {
	const lt = t - M.a, c = M.cues;
	const bl = eio(clamp(lt / 0.9)), p = place(1.34, 0.5, 0.45);
	return (
		<>
			<Foot src0={M.src[0]} rate={Math.min(RATE, 0.6)} scale={1.34} x={p.x} y={p.y} filter={`${NIGHT} blur(${bl * 26}px)`} />
			<Grade />
			<AbsoluteFill style={{background: '#050505', opacity: bl * 0.55}} />
			<div style={{position: 'absolute', left: 0, right: 0, top: 268, textAlign: 'center', fontFamily: 'Vaz', fontWeight: 500, fontSize: 22, letterSpacing: 8, color: 'rgba(243,236,220,.7)', direction: 'rtl', ...rise(t, c.pre ?? M.v)}}>{L.pre}</div>
			<div style={{...big, left: 0, right: 0, top: 300, textAlign: 'center', fontSize: fit(CONTENT.brand ?? '', 'Pey', 900, 200, 1600), textShadow: '0 0 60px rgba(255,220,170,.35)', ...rise(t, c.brand ?? M.v + 0.9, 0.6)}}>{CONTENT.brand}</div>
			<div style={{position: 'absolute', left: 0, right: 0, top: 650, textAlign: 'center', fontFamily: 'Vaz', fontWeight: 500, fontSize: 27, color: 'rgba(243,236,220,.85)', direction: 'rtl', ...rise(t, (c.brand ?? M.v + 0.9) + 1.1)}}>{L.features}</div>
			<div style={{position: 'absolute', left: 0, right: 0, top: 720, textAlign: 'center', fontFamily: 'VazL', fontWeight: 500, fontSize: 26, color: C.orange, letterSpacing: 3, ...rise(t, (c.brand ?? M.v + 0.9) + 1.6)}}>{CONTENT.url}</div>
		</>
	);
};
// two lines of type beside the presenter (any other line, and the stand-in when no cut-out can be made)
const Plain: React.FC<TP> = ({t, L, M}) => {
	const lt = t - M.a, push = 1.2 + lt * 0.012, p = place(push, 0.3, 0.45), c = M.cues;
	return (
		<>
			<Foot src0={M.src[0]} scale={push} x={p.x} y={p.y} filter={NIGHT} />
			<Grade />
			<Tag text={L.tag} />
			<div style={{position: 'absolute', right: 130, top: 300, direction: 'rtl', fontFamily: 'Pey', fontWeight: 400, fontSize: fit(L.l2 ?? L.l1 ?? '', 'Pey', 900, 110, 900), color: C.cream, lineHeight: 1.6, whiteSpace: 'nowrap', textShadow: '0 6px 40px rgba(0,0,0,.45)'}}>
				<div style={rise(t, c.l1 ?? M.v + 0.2)}>{L.l1}</div>
				<div style={{...rise(t, c.l2 ?? M.v + 1.0), fontWeight: 900}}>{L.l2}</div>
			</div>
		</>
	);
};
const TREAT: Record<string, React.FC<TP>> = {plain: Plain, title_split: TitleSplit, word_cards: WordCards, cutout_place: CutoutPlace, broll_code: BrollCode, no_nle: NoNle, prompt_card: PromptCard, end_card: EndCard};

export const Talk: React.FC = () => {
	useFonts();
	const f = useCurrentFrame();
	const t = f / FPS;
	let i = 0;
	for (let k = 0; k < LT_.length; k++) if (t >= LT_[k].a) i = k;
	const L = LINES[i], M = LT_[i];
	const Body = L && M ? TREAT[L.treatment] ?? TitleSplit : null;
	const cuts: number[] = TIMING.cuts ?? [];
	const fl = cuts.some((c) => t >= c && t < c + 2 / FPS) ? 0.2 : 0;
	return (
		<AbsoluteFill style={{background: '#000', overflow: 'hidden'}}>
			<Fonts />
			{Body && <Body t={t} L={L} M={M} />}
			{fl > 0 && <AbsoluteFill style={{background: '#fff', opacity: fl}} />}
			<AbsoluteFill style={{opacity: seg(t, DUR - 0.5, DUR), background: '#000'}} />
		</AbsoluteFill>
	);
};
