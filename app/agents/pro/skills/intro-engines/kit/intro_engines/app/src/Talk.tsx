import React from 'react';
import {AbsoluteFill, OffthreadVideo, staticFile, useCurrentFrame} from 'remotion';
import {Fonts, useFonts, clamp, lerp, seg, eo, eo5, eio, back, rnd, fa, sparkPath} from './lib';

const FPS = 30, W = 1920, H = 1080;
const C = {cream: '#f3ecdc', ink: '#161412', orange: '#ff5a1f', paper: '#e9e5dc', teal: '#0d2a33'};
export const TALK_DUR = 24;
// voice starts (processed lines) and word offsets
const V = {p1: 0.5, p2: 4.15, p3: 7.0, p4: 10.55, p5: 13.7, p6: 15.65, p7: 18.9};
export const TALK_VOICE = Object.entries(V).map(([k, t]) => ({f: `audio/vproc/${k}.wav`, t}));
export const TALK_EV: {t: number; k: string; g?: number}[] = [
	{t: 0.5, k: 'swell', g: 0.4}, {t: V.p2, k: 'hit', g: 0.8}, {t: V.p2 + 0.76, k: 'shutter', g: 0.7}, {t: V.p2 + 1.43, k: 'whoosh', g: 0.6}, {t: V.p2 + 2.17, k: 'pop', g: 0.6},
	{t: V.p3 - 0.1, k: 'whoosh', g: 0.6}, {t: V.p3 + 1.0, k: 'pop', g: 0.7}, {t: V.p3 + 2.1, k: 'whoosh', g: 0.5}, {t: V.p4 - 0.05, k: 'hit', g: 0.7}, {t: V.p4 + 1.7, k: 'riser', g: 0.4},
	{t: V.p5 - 0.1, k: 'whoosh', g: 0.6}, {t: V.p6 - 0.1, k: 'whoosh', g: 0.5}, {t: V.p6 + 1.17, k: 'key', g: 0.6}, {t: V.p6 + 1.41, k: 'key', g: 0.6}, {t: V.p6 + 1.84, k: 'key', g: 0.6}, {t: V.p6 + 2.16, k: 'key', g: 0.6},
	{t: V.p7 - 0.2, k: 'swell', g: 0.6}, {t: V.p7 + 1.45, k: 'ding', g: 0.5},
];

const Foot: React.FC<{src0: number; t: number; rate?: number; scale?: number; x?: number; y?: number; filter?: string; style?: React.CSSProperties}> = ({src0, rate = 0.7, scale = 1, x = 0, y = 0, filter, style}) => (
	<OffthreadVideo src={staticFile('talk/graded.mp4')} muted startFrom={Math.round(src0 * FPS)} playbackRate={rate} style={{position: 'absolute', left: 0, top: 0, width: W, height: H, transform: `translate(${x}px,${y}px) scale(${scale})`, transformOrigin: '0 0', filter, ...style}} />
);
const NIGHT = 'brightness(.6) contrast(1.16) saturate(.85)';
const Grade: React.FC<{o?: number}> = ({o = 1}) => (
	<>
		<AbsoluteFill style={{background: 'linear-gradient(115deg, rgba(0,70,92,.7) 0%, rgba(20,40,60,.45) 55%, rgba(110,45,10,.5) 100%)', mixBlendMode: 'soft-light', opacity: o}} />
		<AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 42%, rgba(0,0,0,0) 35%, rgba(0,0,0,.62) 100%)', opacity: o}} />
	</>
);
const Tag: React.FC<{text: string; dark?: boolean; left?: boolean}> = ({text, dark, left}) => (
	<div style={{position: 'absolute', top: 54, [left ? 'left' : 'right']: 64, fontFamily: 'Vaz, VazL', fontWeight: 500, fontSize: 18, letterSpacing: 3, color: dark ? 'rgba(22,20,18,.6)' : 'rgba(243,236,220,.7)', direction: 'rtl', display: 'flex', alignItems: 'center', gap: 10} as React.CSSProperties}>
		<span style={{width: 9, height: 9, borderRadius: 9, background: C.orange, display: 'inline-block'}} />
		{text}
	</div>
);
const rise = (t: number, t0: number, d = 0.35) => ({opacity: clamp((t - t0) / 0.12), transform: `translateY(${(1 - eo5(clamp((t - t0) / d))) * 46}px)`});

export const Talk: React.FC = () => {
	useFonts();
	const f = useCurrentFrame();
	const t = f / FPS;
	const big: React.CSSProperties = {position: 'absolute', fontFamily: 'Pey', fontWeight: 900, color: C.cream, direction: 'rtl', whiteSpace: 'nowrap', lineHeight: 1.5};
	let body: React.ReactNode;

	if (t < V.p2) {
		// A — title over night-graded footage
		const push = 1.3 + t * 0.012;
		body = (
			<>
				<Foot src0={1.0} t={t} scale={push} x={-(push - 1.3) * 900} y={-60 - (push - 1.3) * 300} filter={NIGHT} />
				<Grade />
				<Tag text="تدوین با" />
				<div style={{...big, right: 130, top: 170, fontSize: 168, ...rise(t, V.p1)}}>ادیتور</div>
				<div style={{...big, left: 70, top: 170, fontSize: 168, ...rise(t, V.p1 + 0.55)}}>جی‌پی‌تی</div>
				<div style={{position: 'absolute', left: 120, top: 560, fontFamily: 'Vaz', fontWeight: 500, fontSize: 34, color: C.cream, direction: 'rtl', lineHeight: 1.7}}>
					<div style={rise(t, V.p1 + 1.39)}>ویدیوت رو</div>
					<div style={rise(t, V.p1 + 2.0)}>خودش تدوین می‌کنه</div>
				</div>
			</>
		);
	} else if (t < V.p3 - 0.1) {
		const lt = t - V.p2;
		if (lt < 0.76) {
			body = (
				<AbsoluteFill style={{background: 'radial-gradient(ellipse at 55% 45%, #ff7a3a 0%, #f04a17 70%)'}}>
					<div style={{...big, left: 0, right: 0, top: 140, textAlign: 'center', fontSize: 520, transform: `scale(${lerp(1.25, 1, eo5(clamp(lt / 0.2)))})`}}>برش</div>
				</AbsoluteFill>
			);
		} else if (lt < 1.43) {
			const l = lt - 0.76;
			body = (
				<>
					<Foot src0={8.2} t={t} scale={1.12} x={-230} y={-40} filter="brightness(.95) saturate(1.05)" />
					<AbsoluteFill style={{background: 'linear-gradient(90deg, rgba(0,0,0,.0) 40%, rgba(10,20,30,.35) 100%)'}} />
					<div style={{...big, right: 90, top: 60, fontSize: 470, textShadow: '0 10px 60px rgba(0,0,0,.25)', transform: `translateY(${(1 - eo5(clamp(l / 0.25))) * 120}px)`, opacity: clamp(l / 0.1)}}>متن</div>
					<Tag text="تایپوگرافی" left />
				</>
			);
		} else if (lt < 2.17) {
			const l = lt - 1.43, x = lerp(0.12, 0.72, eio(clamp(l / 0.6)));
			body = (
				<>
					<Foot src0={11.0} t={t} scale={1.1} x={-100} y={-40} filter="saturate(.25) contrast(.82) brightness(1.05)" />
					<div style={{position: 'absolute', inset: 0, clipPath: `inset(0 0 0 ${x * 100}%)`}}>
						<Foot src0={11.0} t={t} scale={1.1} x={-100} y={-40} filter="brightness(.74) contrast(1.2) saturate(1.25)" />
						<AbsoluteFill style={{background: 'linear-gradient(120deg, rgba(0,80,100,.5), rgba(120,50,0,.35))', mixBlendMode: 'soft-light'}} />
					</div>
					<div style={{position: 'absolute', left: `${x * 100}%`, top: 0, bottom: 0, width: 4, background: C.cream}} />
					<div style={{...big, right: 110, bottom: 60, fontSize: 230, ...rise(t, V.p2 + 1.43)}}>رنگ</div>
					<div style={{position: 'absolute', left: 70, bottom: 70, fontFamily: 'Vaz', fontWeight: 500, fontSize: 22, color: '#fff', letterSpacing: 2}}>قبل</div>
				</>
			);
		} else {
			const l = lt - 2.17;
			body = (
				<>
					<Foot src0={13.9} t={t} scale={1.3} y={-60} filter={NIGHT} />
					<Grade />
					<svg width={W} height={H} style={{position: 'absolute'}}>
						{Array.from({length: 96}).map((_, i) => {
							const a = (0.25 + rnd(i) * 0.75) * (0.4 + 0.6 * Math.abs(Math.sin(l * 9 + i * 0.6))) * Math.sin((i / 95) * Math.PI) * eo5(clamp(l / 0.3));
							return <rect key={i} x={160 + i * 16.8} y={760 - a * 150} width={8} height={a * 300 + 4} rx={4} fill={i % 12 === 5 ? C.orange : C.cream} opacity={0.9} />;
						})}
					</svg>
					<div style={{...big, right: 150, top: 130, fontSize: 240, ...rise(t, V.p2 + 2.17)}}>صدا</div>
					<Tag text="تراز روی −۱۴ LUFS" left />
				</>
			);
		}
	} else if (t < V.p4 - 0.05) {
		// C — cut out, place anywhere
		const lt = t - V.p3 + 0.1;
		const cut = eo5(seg(t, V.p3 + 0.9, V.p3 + 1.35));
		const mv = eio(seg(t, V.p3 + 2.0, V.p3 + 2.7));
		const sc = lerp(1, 0.74, mv), cx = lerp(300, 250, mv), cy = lerp(0, 30, mv);
		const sticker = cut * 5;
		body = (
			<AbsoluteFill style={{background: `radial-gradient(ellipse at 30% 30%, #f6f2ea 0%, ${C.paper} 60%, #d9d4c8 100%)`}}>
				<AbsoluteFill style={{opacity: 1 - cut}}><Foot src0={38.85} t={t} rate={0.85} /></AbsoluteFill>
				<div style={{position: 'absolute', left: lerp(450, 396, mv), top: lerp(140, 190, mv), width: 520, height: 520, borderRadius: 520, background: 'radial-gradient(circle at 35% 30%, #ff8a55, #f0501f)', transform: `scale(${back(seg(t, V.p3 + 1.9, V.p3 + 2.4))})`}} />
				<div style={{position: 'absolute', left: cx, top: cy, width: 812, height: 1080, transform: `scale(${sc}) rotate(${mv * -3}deg)`, transformOrigin: '50% 100%', filter: `drop-shadow(${sticker}px 0 0 #fff) drop-shadow(-${sticker}px 0 0 #fff) drop-shadow(0 -${sticker}px 0 #fff) drop-shadow(0 ${sticker}px 0 #fff) drop-shadow(0 18px 26px rgba(0,0,0,${0.28 * cut}))`}}>
					<OffthreadVideo src={staticFile('talk/fg3.webm')} transparent muted startFrom={0} playbackRate={0.85} style={{width: 812, height: 1080}} />
				</div>
				<div style={{position: 'absolute', right: 130, top: 300, direction: 'rtl', fontFamily: 'Pey', fontWeight: 400, fontSize: 84, color: C.ink, lineHeight: 1.6, whiteSpace: 'nowrap'}}>
					<div style={rise(t, V.p3 + 1.0)}>جدا می‌کنه</div>
					<div style={{...rise(t, V.p3 + 2.12), fontWeight: 900}}>هر جا بخوای.</div>
					<div style={{...rise(t, V.p3 + 2.5), fontFamily: 'VazL', fontWeight: 500, fontSize: 30, color: C.orange, direction: 'ltr', textAlign: 'right', letterSpacing: 2}}>anywhere.</div>
				</div>
				<Tag text="جداسازی سوژه" dark />
			</AbsoluteFill>
		);
		void lt;
	} else if (t < V.p5 - 0.1) {
		// D — b-roll from scratch
		const lt = t - V.p4;
		const NX = 60, NY = 22, PAL = [C.orange, '#d9ff3d', '#b9a8ff', C.cream, '#5b6bff'];
		const m = eio(clamp(lt / 0.8));
		body = (
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
					<g transform={`translate(960,330) rotate(${lt * 50}) scale(${back(clamp(lt / 0.5))})`}><path d={sparkPath(110, 0.3)} fill={C.orange} /></g>
				</svg>
				<AbsoluteFill style={{background: 'linear-gradient(20deg, rgba(12,11,26,.95) 8%, rgba(12,11,26,0) 45%)'}} />
				<Tag text="بی‌رول · ۰ عکس استوک · ۰ مدل ویدیو" />
				<div style={{...big, left: 110, bottom: 70, fontSize: 120, fontWeight: 400, ...rise(t, V.p4 + 1.55)}}>از صفر می‌سازه</div>
			</AbsoluteFill>
		);
	} else if (t < V.p6 - 0.1) {
		// E — no Premiere
		const lt = t - V.p5 + 0.1;
		const tracks = [['برش', '#5d5a55', [[0, 0.28], [0.3, 0.6], [0.62, 1]]], ['کپشن', '#f7a600', [[0.03, 0.22], [0.26, 0.5], [0.55, 0.92]]], ['موشن', '#7d8cff', [[0.44, 0.6]]], ['رنگ', '#e86a4a', [[0, 1]]], ['صدا', '#58b28a', [[0, 1]]]] as const;
		body = (
			<AbsoluteFill style={{background: `radial-gradient(ellipse at 70% 30%, #f6f2ea 0%, ${C.paper} 60%, #d9d4c8 100%)`}}>
				<div style={{position: 'absolute', right: 110, top: 250, width: 800, height: 450, borderRadius: 26, overflow: 'hidden', boxShadow: '0 30px 70px rgba(0,0,0,.25)', transform: `translateY(${(1 - eo5(clamp(lt / 0.4))) * 60}px)`}}>
					<OffthreadVideo src={staticFile('talk/graded.mp4')} muted startFrom={Math.round(16.2 * FPS)} playbackRate={0.7} style={{width: 800, height: 450, objectFit: 'cover'}} />
				</div>
				<div style={{position: 'absolute', left: 110, top: 330, width: 760, height: 400, borderRadius: 24, background: 'rgba(40,38,36,.86)', boxShadow: '0 30px 70px rgba(0,0,0,.22)', transform: `translateY(${(1 - eo5(clamp((lt - 0.1) / 0.4))) * 60}px)`, opacity: clamp(lt / 0.15)}}>
					<div style={{position: 'absolute', right: 30, top: 22, fontFamily: 'Vaz', fontWeight: 500, fontSize: 17, color: '#aaa', letterSpacing: 2, direction: 'rtl'}}>تایم‌لاین · همین ویدیو</div>
					{tracks.map(([n, c, clips], i) => (
						<div key={i} style={{position: 'absolute', left: 30, right: 30, top: 70 + i * 62, height: 44}}>
							<div style={{position: 'absolute', right: 0, top: 9, fontFamily: 'Vaz', fontWeight: 500, fontSize: 18, color: '#bbb', direction: 'rtl'}}>{n}</div>
							<div style={{position: 'absolute', left: 0, right: 90, top: 0, bottom: 0, background: 'rgba(255,255,255,.06)', borderRadius: 8}}>
								{clips.map(([a, b], k) => <div key={k} style={{position: 'absolute', right: `${a * 100}%`, width: `${(b - a) * 100 * eo5(clamp((lt - 0.25 - i * 0.07 - k * 0.05) / 0.35))}%`, top: 5, bottom: 5, background: c, borderRadius: 6}} />)}
							</div>
						</div>
					))}
					<div style={{position: 'absolute', top: 60, bottom: 20, right: `${14 + clamp(lt / 1.9) * 72}%`, width: 3, background: C.orange}} />
				</div>
				<div style={{position: 'absolute', left: 110, top: 150, fontFamily: 'Pey', fontWeight: 900, fontSize: 104, color: C.ink, direction: 'rtl', whiteSpace: 'nowrap', ...rise(t, V.p5 + 0.54)}}>بدون پریمیر.</div>
			</AbsoluteFill>
		);
	} else if (t < V.p7 - 0.25) {
		// F — the only prompt
		const lt = t - V.p6;
		const words = [['یه', 1.17], ['ویدیوی', 1.41], ['خفن', 1.84], ['بساز', 2.16]] as const;
		const push = 1.3 + lt * 0.015;
		body = (
			<>
				<Foot src0={22.2} t={t} scale={push} x={-(push - 1.3) * 900} y={-60} filter={NIGHT} />
				<Grade />
				<div style={{position: 'absolute', left: 110, top: 300, fontFamily: 'Vaz', fontWeight: 500, fontSize: 30, color: C.cream, direction: 'rtl', ...rise(t, V.p6 + 0.32)}}>کافیه بگی</div>
				<div style={{position: 'absolute', left: 110, top: 370, width: 620, minHeight: 190, borderRadius: 24, background: 'rgba(22,22,22,.82)', border: '1px solid rgba(255,255,255,.14)', padding: '26px 32px', boxSizing: 'border-box', direction: 'rtl', ...rise(t, V.p6 + 0.6)}}>
					<div style={{fontFamily: 'Vaz', fontWeight: 500, fontSize: 17, color: '#9a9a9a', letterSpacing: 2, display: 'flex', alignItems: 'center', gap: 8}}><span style={{width: 8, height: 8, borderRadius: 8, background: C.orange, display: 'inline-block'}} />کاربر</div>
					<div style={{fontFamily: 'Vaz', fontWeight: 500, fontSize: 46, color: '#f3f3f3', marginTop: 18, lineHeight: 1.5}}>
						{words.map(([w, s], i) => <span key={i} style={{opacity: lt >= s - 0.05 ? 1 : 0, marginLeft: 12}}>{w}</span>)}
						<span style={{display: 'inline-block', width: 4, height: 44, background: C.orange, verticalAlign: 'middle', opacity: Math.floor(lt * 3) % 2 ? 0.2 : 1}} />
					</div>
				</div>
				<div style={{...big, right: 130, top: 130, fontSize: 250, ...rise(t, V.p6)}}>فقط</div>
			</>
		);
	} else {
		// G — end card
		const lt = t - (V.p7 - 0.25);
		const bl = eio(clamp(lt / 0.9));
		body = (
			<>
				<Foot src0={31.6} t={t} rate={0.6} scale={1.34} x={-40} y={-80} filter={`${NIGHT} blur(${bl * 26}px)`} />
				<Grade />
				<AbsoluteFill style={{background: '#050505', opacity: bl * 0.55}} />
				<div style={{position: 'absolute', left: 0, right: 0, top: 268, textAlign: 'center', fontFamily: 'Vaz', fontWeight: 500, fontSize: 22, letterSpacing: 8, color: 'rgba(243,236,220,.7)', direction: 'rtl', ...rise(t, V.p7)}}>تدوین، با</div>
				<div style={{...big, left: 0, right: 0, top: 300, textAlign: 'center', fontSize: 200, textShadow: '0 0 60px rgba(255,220,170,.35)', ...rise(t, V.p7 + 0.9, 0.6)}}>ادیتور جی‌پی‌تی</div>
				<div style={{position: 'absolute', left: 0, right: 0, top: 650, textAlign: 'center', fontFamily: 'Vaz', fontWeight: 500, fontSize: 27, color: 'rgba(243,236,220,.85)', direction: 'rtl', ...rise(t, V.p7 + 2.0)}}>برش · کپشن · رنگ · موشن · صدا — همه در یک گفت‌وگو</div>
				<div style={{position: 'absolute', left: 0, right: 0, top: 720, textAlign: 'center', fontFamily: 'VazL', fontWeight: 500, fontSize: 26, color: C.orange, letterSpacing: 3, ...rise(t, V.p7 + 2.5)}}>editor.rafiei.co</div>
			</>
		);
	}
	// flash on cuts
	const cuts = [V.p2, V.p2 + 0.76, V.p2 + 1.43, V.p2 + 2.17, V.p3 - 0.1, V.p4 - 0.05, V.p5 - 0.1, V.p6 - 0.1];
	const fl = cuts.some((c) => t >= c && t < c + 2 / FPS) ? 0.2 : 0;
	return (
		<AbsoluteFill style={{background: '#000', overflow: 'hidden'}}>
			<Fonts />
			{body}
			{fl > 0 && <AbsoluteFill style={{background: '#fff', opacity: fl}} />}
			<AbsoluteFill style={{opacity: seg(t, TALK_DUR - 0.5, TALK_DUR), background: '#000'}} />
		</AbsoluteFill>
	);
};
