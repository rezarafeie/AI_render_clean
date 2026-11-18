import React from 'react';
import {AbsoluteFill, Easing, OffthreadVideo, Sequence, continueRender, delayRender, interpolate, random, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import '@fontsource/playfair-display/800-italic.css';
import '@fontsource/playfair-display/900-italic.css';
import data from './data.json';

const W = 1080;
const H = 1920;
const FPS = 30;
const D = 'Doran';
const SERIF = 'Playfair Display';
const GOLD_GRAD = 'linear-gradient(180deg, #FFF6DF 0%, #F1D79C 45%, #D4A24E 100%)';
const CREAM = '#F7EEDF';
const GOLD = '#E9C27A';
const clamp = (x: number) => Math.max(0, Math.min(1, x));
const eo = Easing.bezier(0.16, 1, 0.3, 1);
const eio = Easing.bezier(0.65, 0, 0.35, 1);
const prog = (t: number, at: number, d = 0.4, e = eo) => e(clamp((t - at) / d));
const fa = (n: number | string) => String(n).replace(/[0-9]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[+d]);
const DARK_GRAD = 'linear-gradient(180deg, #4A331A 0%, #22170C 55%, #0F0A05 100%)';
const INKB = '#2E2114';
const darkText: React.CSSProperties = {background: DARK_GRAD, WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent'};
const goldText: React.CSSProperties = {background: GOLD_GRAD, WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent'};

type Cap = {s: number; e: number; words: {t: string; s: number; key: boolean}[]; hide: boolean; big: boolean};
type TB = {s: number; e: number; kind: string};
type Topic = {s: number; e: number; title: string; icon: string};
const caps = data.caps as Cap[];
const tbs = data.tb as TB[];
const topics = data.topics as Topic[];
const cuts = data.cuts as number[];
const KW = data.kw as Record<string, number>;
const k = (i: number) => KW[String(i)];

const useTime = () => useCurrentFrame() / FPS;
const useSpAt = (at: number, damping = 14, mass = 0.8, stiffness = 140) => {
	const f = useCurrentFrame();
	return spring({frame: f - Math.round(at * FPS), fps: FPS, config: {damping, mass, stiffness}});
};

/* ========== font faces ========== */
const Fonts: React.FC = () => (
	<style>
		{[
			['Thin', 100],
			['Light', 300],
			['Regular', 400],
			['Medium', 500],
			['Bold', 700],
			['ExtraBold', 800],
		]
			.map(([n, w]) => `@font-face{font-family:'Doran';src:url('${staticFile(`fonts/DoranFaNum-${n}.woff2`)}') format('woff2');font-weight:${w};font-display:block;}`)
			.join('\n')}
	</style>
);

/* ========== transitions (section changes) ========== */
const EVENTS = [2.62, 7.9, 9.68, 13.72, 27.55, 31.25, 34.45, 38.85];
const evAmt = (t: number, d = 0.28) => {
	let m = 0;
	for (const e of EVENTS) {
		const x = (t - e) / d;
		if (x >= -0.5 && x <= 1) m = Math.max(m, x < 0 ? 1 + x * 2 : 1 - x);
	}
	return clamp(m);
};

/* ========== camera ========== */
const BASE = [1.0, 1.12, 1.04, 1.16, 1.0, 1.1];
const zoomAt = (t: number) => {
	const seg = cuts.filter((c) => c <= t).length;
	let z = BASE[seg % BASE.length];
	// emphasis
	const tb2 = tbs[1];
	z *= 1 + 0.12 * prog(t, tb2.s - 0.1, 0.5, eio) * (1 - prog(t, tb2.e - 0.2, 0.4, eio));
	const tb4 = tbs[3];
	z *= 1 + 0.22 * prog(t, tb4.s - 0.2, 3.2, eio);
	z *= 1 + 0.006 * (t % 6);
	return z;
};
const faceX = (t: number) => {
	const i = t / data.faceStep;
	const a = Math.max(0, Math.min(data.face.length - 1, Math.floor(i)));
	const b = Math.min(data.face.length - 1, a + 1);
	return data.face[a] + (data.face[b] - data.face[a]) * (i - a);
};
const camAt = (t: number) => {
	const Z = zoomAt(t);
	const S = (H / 1080) * Z;
	const cx = faceX(t) - 60;
	const tx = Math.min(0, Math.max(W - 1920 * S, W / 2 - cx * S));
	const ty = Math.min(0, Math.max(H - 1080 * S, 760 - data.faceY * S));
	return {S, tx, ty};
};

const Cam: React.FC = () => {
	const t = useTime();
	const {S, tx, ty} = camAt(t);
	return <OffthreadVideo src={staticFile('graded.mp4')} muted style={{position: 'absolute', left: tx, top: ty, width: 1920 * S, height: 1080 * S, maxWidth: 'none'}} />;
};

/** person cut-out (alpha webm) aligned with camera, shown during a TB window */
const FG: React.FC<{i: number; tb: TB}> = ({i, tb}) => {
	const f = useCurrentFrame();
	const t = tb.s + f / FPS;
	const {S, tx, ty} = camAt(t);
	return <OffthreadVideo src={staticFile(`seg/fg${i}.webm`)} transparent muted style={{position: 'absolute', left: tx + 300 * S, top: ty, width: 812 * S, height: 1080 * S, maxWidth: 'none'}} />;
};

/* ========== look: vignette, light leaks, grain ========== */
const Look: React.FC = () => {
	const f = useCurrentFrame();
	const t = f / FPS;
	const burst = evAmt(t, 0.6);
	const a = 0.18 + 0.35 * burst;
	return (
		<>
			<AbsoluteFill style={{background: 'radial-gradient(ellipse 75% 60% at 50% 42%, rgba(0,0,0,0) 50%, rgba(20,10,0,0.45) 100%)'}} />
			<AbsoluteFill style={{mixBlendMode: 'screen', opacity: a}}>
				<div style={{position: 'absolute', left: -300 + Math.sin(t * 0.4) * 120, top: -200 + Math.cos(t * 0.3) * 100, width: 900, height: 900, borderRadius: '50%', background: 'radial-gradient(circle, rgba(255,150,60,0.9), rgba(255,120,40,0) 65%)', filter: 'blur(30px)'}} />
				<div style={{position: 'absolute', right: -350 + Math.cos(t * 0.5) * 120, bottom: 200 + Math.sin(t * 0.35) * 160, width: 1000, height: 1000, borderRadius: '50%', background: 'radial-gradient(circle, rgba(255,205,120,0.8), rgba(255,180,90,0) 65%)', filter: 'blur(40px)'}} />
			</AbsoluteFill>
			<AbsoluteFill style={{background: 'linear-gradient(180deg, rgba(0,0,0,0.12) 0%, rgba(0,0,0,0) 15%, rgba(0,0,0,0) 55%, rgba(0,0,0,0.45) 100%)'}} />
			<svg width={W} height={H} style={{position: 'absolute', opacity: 0.08, mixBlendMode: 'overlay'}}>
				<filter id="gr">
					<feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves={2} seed={f % 10} />
				</filter>
				<rect width={W} height={H} filter="url(#gr)" />
			</svg>
		</>
	);
};

/* ========== text-behind-subject layers ========== */
const Rise: React.FC<{at: number; children: React.ReactNode; d?: number; y?: number; style?: React.CSSProperties}> = ({at, children, d = 0.5, y = 80, style}) => {
	const t = useTime();
	const p = prog(t, at, d);
	return <div style={{opacity: p, transform: `translateY(${(1 - p) * y}px) scale(${0.92 + 0.08 * p})`, filter: `blur(${(1 - p) * 16}px)`, ...style}}>{children}</div>;
};

const BehindText: React.FC<{tb: TB}> = ({tb}) => {
	const f = useCurrentFrame();
	const t = f / FPS; // local
	const dur = tb.e - tb.s;
	const out = 1 - prog(t, dur - 0.25, 0.25);
	const wrap: React.CSSProperties = {position: 'absolute', left: 0, width: W, display: 'flex', flexDirection: 'column', alignItems: 'center', opacity: out};
	if (tb.kind === 'overview') {
		const letters = 'OVERVIEW'.split('');
		return (
			<div style={{...wrap, top: 150}}>
				<Rise at={0.05} y={30}>
					<div style={{fontFamily: D, fontWeight: 500, fontSize: 54, color: INKB, direction: 'rtl', letterSpacing: 2}}>یه نگاهِ کلی</div>
				</Rise>
				<div style={{display: 'flex', direction: 'ltr', marginTop: -10}}>
					{letters.map((c, i) => {
						const p = prog(t, 0.12 + i * 0.05, 0.5);
						return (
							<span key={i} style={{fontFamily: SERIF, fontStyle: 'italic', fontWeight: 900, fontSize: 210, lineHeight: 1, ...darkText, display: 'inline-block', opacity: p, transform: `translateY(${(1 - p) * 120}px)`, filter: `drop-shadow(0 6px 18px rgba(255,240,215,0.5))`}}>
								{c}
							</span>
						);
					})}
				</div>
			</div>
		);
	}
	if (tb.kind === 'brand') {
		const s = useSpAt(tb.s + 0.12, 16, 1);
		return (
			<div style={{...wrap, top: 110}}>
				<svg width={900} height={900} style={{position: 'absolute', top: -150, opacity: 0.22 * prog(t, 0, 0.5)}}>
					<g transform={`translate(450,450) rotate(${t * 18})`} fill="none" stroke={INKB} strokeWidth={2.5}>
						<circle r={400} />
						{[-0.7, -0.35, 0, 0.35, 0.7].map((y, i) => (
							<ellipse key={i} rx={400 * Math.sqrt(1 - y * y)} ry={26} cy={y * 400} />
						))}
						{[0.3, 0.62, 0.9].map((x, i) => (
							<ellipse key={'m' + i} rx={400 * x} ry={400} />
						))}
					</g>
				</svg>
				<Rise at={0.02} y={30}>
					<div style={{fontFamily: D, fontWeight: 500, fontSize: 52, color: INKB, direction: 'rtl'}}>پروژه‌ی</div>
				</Rise>
				<div style={{fontFamily: D, fontWeight: 800, fontSize: 225, lineHeight: 1.05, ...darkText, direction: 'rtl', whiteSpace: 'nowrap', transform: `scale(${interpolate(s, [0, 1], [1.35, 1])})`, opacity: prog(t, 0.1, 0.25), filter: `blur(${(1 - prog(t, 0.1, 0.35)) * 20}px) drop-shadow(0 6px 18px rgba(255,240,215,0.5))`}}>
					بدون مرز
				</div>
			</div>
		);
	}
	if (tb.kind === 'important') {
		const s = useSpAt(tb.s + 1.15, 12, 0.8, 180);
		return (
			<div style={{...wrap, top: 110}}>
				<div style={{display: 'flex', gap: 30, direction: 'rtl'}}>
					<Rise at={0.06} y={40}>
						<div style={{fontFamily: D, fontWeight: 300, fontSize: 86, color: INKB}}>بسیار</div>
					</Rise>
					<Rise at={0.66} y={40}>
						<div style={{fontFamily: D, fontWeight: 300, fontSize: 86, color: INKB}}>بسیار</div>
					</Rise>
				</div>
				<div style={{fontFamily: D, fontWeight: 800, fontSize: 300, lineHeight: 0.95, ...darkText, direction: 'rtl', transform: `scale(${interpolate(s, [0, 1], [1.6, 1])})`, opacity: prog(t, 1.15, 0.15), filter: 'drop-shadow(0 6px 18px rgba(255,240,215,0.5))'}}>
					مهمه
				</div>
			</div>
		);
	}
	// most important
	const s = useSpAt(tb.s + 0.15, 14, 1);
	return (
		<div style={{...wrap, top: 100}}>
			<Rise at={0.9} y={30}>
				<div style={{fontFamily: D, fontWeight: 500, fontSize: 60, color: INKB, direction: 'rtl'}}>قسمتِ این پروژه</div>
			</Rise>
			<div style={{fontFamily: D, fontWeight: 800, fontSize: 185, lineHeight: 1.05, ...darkText, direction: 'rtl', whiteSpace: 'nowrap', transform: `scale(${interpolate(s, [0, 1], [1.4, 1]) * (1 + 0.03 * t)})`, opacity: prog(t, 0.12, 0.25), filter: `blur(${(1 - prog(t, 0.12, 0.35)) * 18}px) drop-shadow(0 6px 18px rgba(255,240,215,0.5))`}}>
				مهم‌ترین
			</div>
		</div>
	);
};

/* ========== glass card ========== */
const Glass: React.FC<{children: React.ReactNode; style?: React.CSSProperties}> = ({children, style}) => (
	<div
		style={{
			background: 'linear-gradient(160deg, rgba(40,30,20,0.55), rgba(15,12,10,0.45))',
			border: '1.5px solid rgba(255,235,200,0.28)',
			borderRadius: 40,
			backdropFilter: 'blur(18px) saturate(1.3)',
			boxShadow: '0 30px 80px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.18)',
			...style,
		}}
	>
		{children}
	</div>
);

const InOut: React.FC<{s: number; e: number; children: React.ReactNode; y?: number}> = ({s, e, children, y = -60}) => {
	const t = useTime();
	const pin = useSpAt(s, 15, 0.8);
	const po = prog(t, e - 0.22, 0.22, eio);
	if (t < s - 0.05 || t > e + 0.05) return null;
	return (
		<div style={{opacity: Math.min(prog(t, s, 0.15), 1 - po), transform: `translateY(${(1 - pin) * y + po * -30}px) scale(${0.9 + 0.1 * pin})`, filter: po > 0 ? `blur(${po * 12}px)` : undefined}}>
			{children}
		</div>
	);
};

/* icons (gold line) */
const Icon: React.FC<{k: string; s?: number}> = ({k: kind, s = 80}) => {
	const st = {fill: 'none', stroke: GOLD, strokeWidth: 5, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const};
	return (
		<svg width={s} height={s} viewBox="0 0 80 80">
			{kind === 'spark' && <path d="M40,8 C43,28 52,37 72,40 C52,43 43,52 40,72 C37,52 28,43 8,40 C28,37 37,28 40,8 Z" {...st} />}
			{kind === 'fork' && <path d="M40,74 L40,42 M40,42 L18,18 M40,42 L62,18 M18,18 L18,30 M18,18 L30,18 M62,18 L50,18 M62,18 L62,30" {...st} />}
			{kind === 'compass' && (
				<g {...st}>
					<circle cx={40} cy={40} r={30} />
					<path d="M52,28 L44,44 L28,52 L36,36 Z" fill={GOLD} />
				</g>
			)}
			{kind === 'tools' && <path d="M50,12 a14,14 0 0,0 -6,22 L14,64 a5,5 0 0,0 7,7 L51,41 a14,14 0 0,0 22,-6 l-9,-2 -3,-9 Z" {...st} />}
			{kind === 'user' && (
				<g {...st}>
					<circle cx={40} cy={28} r={13} />
					<path d="M14,70 C16,52 64,52 66,70" />
				</g>
			)}
			{kind === 'group' && (
				<g {...st}>
					<circle cx={40} cy={26} r={11} />
					<path d="M20,66 C22,50 58,50 60,66" />
					<circle cx={16} cy={34} r={8} />
					<circle cx={64} cy={34} r={8} />
					<path d="M2,64 C3,54 14,50 22,52 M78,64 C77,54 66,50 58,52" />
				</g>
			)}
			{kind === 'list' && <path d="M26,22 L66,22 M26,40 L66,40 M26,58 L66,58 M12,22 L14,22 M12,40 L14,40 M12,58 L14,58" {...st} strokeWidth={6} />}
			{kind === 'bulb' && (
				<g {...st}>
					<path d="M28,50 C18,42 18,18 40,14 C62,18 62,42 52,50 L52,58 L28,58 Z" />
					<path d="M30,66 L50,66 M34,73 L46,73" />
				</g>
			)}
			{kind === 'arrow' && <path d="M60,40 L20,40 M34,26 L20,40 L34,54" {...st} strokeWidth={6} />}
		</svg>
	);
};

const Graphics: React.FC = () => {
	const t = useTime();
	const ti = topics.findIndex((x) => t >= x.s && t < x.e);
	return (
		<>
			{/* episode card */}
			<div style={{position: 'absolute', top: 150, width: W, display: 'flex', justifyContent: 'center'}}>
				<InOut s={2.66} e={4.66}>
					<Glass style={{display: 'flex', alignItems: 'center', gap: 34, padding: '22px 46px 26px', direction: 'rtl'}}>
						<div style={{fontFamily: D, fontWeight: 800, fontSize: 120, lineHeight: 1, ...goldText}}>{fa('01')}</div>
						<div style={{width: 2, height: 100, background: 'rgba(255,235,200,0.35)'}} />
						<div>
							<div style={{fontFamily: SERIF, fontStyle: 'italic', fontWeight: 800, fontSize: 40, color: GOLD, direction: 'ltr', letterSpacing: 3}}>EPISODE</div>
							<div style={{fontFamily: D, fontWeight: 700, fontSize: 60, color: CREAM}}>قسمت اول</div>
						</div>
					</Glass>
				</InOut>
			</div>
			{/* list header */}
			<div style={{position: 'absolute', top: 150, width: W, display: 'flex', justifyContent: 'center'}}>
				<InOut s={9.72} e={13.6}>
					<Glass style={{display: 'flex', alignItems: 'center', gap: 24, padding: '24px 44px 28px', direction: 'rtl'}}>
						<Icon k="list" s={74} />
						<div>
							<div style={{fontFamily: D, fontWeight: 800, fontSize: 64, color: CREAM}}>توی این قسمت</div>
							<div style={{display: 'flex', gap: 12, marginTop: 8}}>
								{Array.from({length: 6}).map((_, i) => (
									<div key={i} style={{width: 18, height: 18, borderRadius: 9, background: GOLD, opacity: prog(t, 10.2 + i * 0.12, 0.3) * 0.8}} />
								))}
							</div>
						</div>
					</Glass>
				</InOut>
			</div>
			{/* topics */}
			{ti >= 0 && (
				<div style={{position: 'absolute', top: 140, width: W, display: 'flex', justifyContent: 'center'}}>
					<TopicCard i={ti} />
				</div>
			)}
			{/* bulb: mind ready */}
			<div style={{position: 'absolute', top: 150, width: W, display: 'flex', justifyContent: 'center'}}>
				<InOut s={31.3} e={34.35}>
					<Glass style={{display: 'flex', alignItems: 'center', gap: 26, padding: '24px 44px 28px', direction: 'rtl'}}>
						<div style={{filter: `drop-shadow(0 0 ${14 + 8 * Math.sin(t * 6)}px rgba(255,210,120,0.9))`}}>
							<Icon k="bulb" s={90} />
						</div>
						<div>
							<div style={{fontFamily: D, fontWeight: 500, fontSize: 40, color: 'rgba(247,238,223,0.8)'}}>ذهنِ تو</div>
							<div style={{fontFamily: D, fontWeight: 800, fontSize: 66, color: CREAM}}>آماده‌ی پذیرش</div>
						</div>
					</Glass>
				</InOut>
			</div>
			{/* next episode */}
			<div style={{position: 'absolute', top: 150, width: W, display: 'flex', justifyContent: 'center'}}>
				<InOut s={34.5} e={37.9}>
					<Glass style={{display: 'flex', alignItems: 'center', gap: 30, padding: '22px 44px 26px', direction: 'rtl'}}>
						<div style={{fontFamily: D, fontWeight: 800, fontSize: 110, lineHeight: 1, ...goldText}}>{fa('02')}</div>
						<div>
							<div style={{fontFamily: SERIF, fontStyle: 'italic', fontWeight: 800, fontSize: 36, color: GOLD, direction: 'ltr', letterSpacing: 3}}>NEXT EPISODE</div>
							<div style={{fontFamily: D, fontWeight: 700, fontSize: 56, color: CREAM}}>قسمت دوم</div>
						</div>
						<div style={{transform: `translateX(${Math.sin(t * 6) * 8}px)`}}>
							<Icon k="arrow" s={70} />
						</div>
					</Glass>
				</InOut>
			</div>
			{/* end brand */}
			<div style={{position: 'absolute', top: 1580, width: W, display: 'flex', justifyContent: 'center'}}>
				<InOut s={41.25} e={data.total + 1} y={40}>
					<div style={{display: 'flex', alignItems: 'center', gap: 18, direction: 'rtl'}}>
						<div style={{fontFamily: D, fontWeight: 800, fontSize: 56, ...goldText}}>بدون مرز</div>
						<div style={{width: 2, height: 50, background: 'rgba(255,235,200,0.5)'}} />
						<div style={{fontFamily: D, fontWeight: 500, fontSize: 44, color: CREAM}}>قسمت ۱</div>
					</div>
				</InOut>
			</div>
		</>
	);
};

const TopicCard: React.FC<{i: number}> = ({i}) => {
	const t = useTime();
	const tp = topics[i];
	const p = useSpAt(tp.s, 15, 0.8);
	const first = i === 0;
	const last = i === topics.length - 1;
	const out = last ? prog(t, tp.e - 0.22, 0.22, eio) : 0;
	const enter = first ? prog(t, tp.s, 0.3) : 1;
	return (
		<div style={{opacity: enter * (1 - out), transform: `translateY(${first ? (1 - p) * -60 : 0}px)`, filter: out > 0 ? `blur(${out * 12}px)` : undefined}}>
			<Glass style={{width: 900, padding: '26px 40px 30px', direction: 'rtl', position: 'relative', overflow: 'hidden'}}>
				<div style={{display: 'flex', alignItems: 'center', gap: 28, transform: `translateX(${(1 - p) * -120}px)`, opacity: prog(t, tp.s, 0.2)}}>
					<div style={{fontFamily: D, fontWeight: 800, fontSize: 104, lineHeight: 1, ...goldText, minWidth: 120, textAlign: 'center'}}>{fa(String(i + 1).padStart(2, '0'))}</div>
					<div style={{width: 96, height: 96, borderRadius: 48, border: '2px solid rgba(233,194,122,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(233,194,122,0.08)'}}>
						<Icon k={tp.icon} s={62} />
					</div>
					<div style={{fontFamily: D, fontWeight: 700, fontSize: 46, color: CREAM, flex: 1, lineHeight: 1.3, whiteSpace: 'nowrap'}}>{tp.title}</div>
				</div>
				<div style={{display: 'flex', gap: 10, marginTop: 18, justifyContent: 'flex-start'}}>
					{topics.map((_, j) => (
						<div key={j} style={{height: 8, flex: j === i ? 3 : 1, borderRadius: 4, background: j <= i ? GOLD : 'rgba(255,255,255,0.2)'}} />
					))}
				</div>
			</Glass>
		</div>
	);
};

/* ========== captions ========== */
const Caption: React.FC<{c: Cap}> = ({c}) => {
	const t = useTime();
	const out = prog(t, c.e - 0.16, 0.16, eio);
	const pin = useSpAt(c.s, 15, 0.7);
	const keys = c.words.filter((w) => w.key);
	const small = c.words.filter((w) => !w.key);
	const Word: React.FC<{w: Cap['words'][0]; size: number; weight: number; color?: string; gold?: boolean}> = ({w, size, weight, color = CREAM, gold}) => {
		const p = prog(t, w.s - 0.06, 0.32);
		const clip = gold ? `inset(0 0 0 ${(1 - prog(t, w.s - 0.06, 0.4, eio)) * 100}%)` : undefined;
		return (
			<span
				style={{
					fontFamily: D,
					fontWeight: weight,
					fontSize: size,
					lineHeight: 1.15,
					display: 'inline-block',
					whiteSpace: 'nowrap',
					opacity: gold ? (t >= w.s - 0.06 ? 1 : 0) : 0.0 + p,
					transform: `translateY(${(1 - p) * 28}px)`,
					filter: gold ? 'drop-shadow(0 8px 24px rgba(0,0,0,0.55))' : `blur(${(1 - p) * 8}px)`,
					textShadow: gold ? undefined : '0 4px 18px rgba(0,0,0,0.7), 0 0 2px rgba(0,0,0,0.6)',
					clipPath: clip,
					...(gold ? goldText : {color}),
				}}
			>
				{w.t}
			</span>
		);
	};
	if (c.big) {
		const ks = keys[0];
		const ul = prog(t, ks.s + 0.1, 0.5, eio);
		return (
			<div style={{position: 'absolute', left: 0, width: W, top: 1180, display: 'flex', flexDirection: 'column', alignItems: 'center', direction: 'rtl', opacity: 1 - out, transform: `translateY(${-out * 30}px)`, filter: out > 0 ? `blur(${out * 10}px)` : undefined}}>
				{small.length > 0 && (
					<div style={{display: 'flex', gap: 16, direction: 'rtl'}}>
						{small.map((w, i) => (
							<Word key={i} w={w} size={58} weight={500} />
						))}
					</div>
				)}
				<div style={{display: 'flex', gap: 26, direction: 'rtl', marginTop: -8}}>
					{keys.map((w, i) => (
						<Word key={i} w={w} size={keys.length > 1 || keys[0].t.length > 8 ? 118 : 140} weight={800} gold />
					))}
				</div>
				<svg width={420} height={24} style={{marginTop: -6, opacity: 0.9}}>
					<path d="M410,14 C300,4 120,4 10,16" stroke={GOLD} strokeWidth={4} fill="none" strokeLinecap="round" strokeDasharray={420} strokeDashoffset={420 * (1 - ul)} />
				</svg>
			</div>
		);
	}
	const cur = c.words.findIndex((w, i) => t >= w.s - 0.05 && (i + 1 >= c.words.length || t < c.words[i + 1].s - 0.05));
	return (
		<div style={{position: 'absolute', left: 0, width: W, top: 1250, display: 'flex', justifyContent: 'center', opacity: Math.min(prog(t, c.s, 0.12), 1 - out), transform: `translateY(${(1 - pin) * 30 - out * 20}px) scale(${0.94 + 0.06 * pin})`}}>
			<div style={{display: 'flex', gap: 18, direction: 'rtl', padding: '16px 38px 22px', borderRadius: 30, background: 'rgba(18,14,10,0.42)', border: '1px solid rgba(255,235,200,0.18)', backdropFilter: 'blur(14px)', boxShadow: '0 20px 50px rgba(0,0,0,0.3)'}}>
				{c.words.map((w, i) => (
					<span key={i} style={{fontFamily: D, fontWeight: 700, fontSize: 64, lineHeight: 1.2, whiteSpace: 'nowrap', color: i === cur ? GOLD : CREAM, opacity: t >= w.s - 0.08 ? 1 : 0.28, transform: i === cur ? 'translateY(-3px)' : 'none', display: 'inline-block', textShadow: '0 3px 12px rgba(0,0,0,0.5)'}}>
						{w.t}
					</span>
				))}
			</div>
		</div>
	);
};

const Captions: React.FC = () => {
	const t = useTime();
	const c = caps.find((x) => t >= x.s && t < x.e);
	if (!c || c.hide) return null;
	return <Caption key={c.s} c={c} />;
};

/* ========== main ========== */
export const V3: React.FC = () => {
	const f = useCurrentFrame();
	const t = f / FPS;
	const [h] = React.useState(() => delayRender('fonts'));
	React.useEffect(() => {
		const id = setTimeout(() => {
			Promise.all([800, 700, 500, 300].map((w) => document.fonts.load(`${w} 60px Doran`, 'سلام')))
				.then(() => document.fonts.load('italic 900 60px "Playfair Display"', 'OVERVIEW'))
				.then(() => document.fonts.ready)
				.then(() => continueRender(h));
		}, 50);
		return () => clearTimeout(id);
	}, [h]);
	const ev = evAmt(t, 0.25);
	return (
		<AbsoluteFill style={{background: '#000'}}>
			<Fonts />
			<AbsoluteFill style={{transform: `scale(${1 + ev * 0.05})`, filter: ev > 0.02 ? `blur(${ev * 10}px) brightness(${1 + ev * 0.25})` : undefined}}>
				<Cam />
				{tbs.map((tb, i) => (
					<Sequence key={'b' + i} from={Math.round(tb.s * FPS)} durationInFrames={Math.round((tb.e - tb.s) * FPS)}>
						<BehindText tb={tb} />
					</Sequence>
				))}
				{tbs.map((tb, i) => (
					<Sequence key={'f' + i} from={Math.round(tb.s * FPS)} durationInFrames={Math.round((tb.e - tb.s) * FPS)}>
						<FG i={i} tb={tb} />
					</Sequence>
				))}
			</AbsoluteFill>
			<Look />
			<Graphics />
			<Captions />
		</AbsoluteFill>
	);
};
