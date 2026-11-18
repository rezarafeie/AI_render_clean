import React from 'react';
import {AbsoluteFill, Sequence, continueRender, delayRender, interpolate, random, useCurrentFrame} from 'remotion';
import '@fontsource/vazirmatn/700.css';
import '@fontsource/vazirmatn/800.css';
import '@fontsource/vazirmatn/900.css';
import '@fontsource/lalezar/400.css';
import data from './data.json';
import {At, Block, Check, eio, ein, eo, FA, fa, Glow, H, NumTag, ORANGE, P, Pop, prog, RED, RED2, shake, Slam, Sparks, SpeedLines, Sweep, useSp, useT, vib, W, YEL, clamp} from './kit';

type Word = {t: string; s: number; e: number};
type Scene = {id: string; start: number; dur: number; end: number; words: Word[]};
const scenes = data.scenes as Scene[];
const FPS = 30;

type SP = {c: (w: string, occ?: number) => number; dur: number};
const Ctx = React.createContext<SP>({c: () => 0, dur: 1});
const useS = () => React.useContext(Ctx);

/* ============ background ============ */
const Background: React.FC = () => {
	const f = useCurrentFrame();
	const t = f / FPS;
	return (
		<AbsoluteFill>
			<AbsoluteFill style={{background: 'radial-gradient(ellipse 80% 60% at 50% 45%, #22252B 0%, #111215 55%, #060607 100%)'}} />
			<svg width={W} height={H} style={{position: 'absolute', opacity: 0.5}}>
				{Array.from({length: 5}).map((_, i) => {
					const x = ((t * 140 + i * 420) % 2200) - 600;
					return <rect key={i} x={x} y={-400} width={18 + i * 6} height={2800} fill={i % 2 ? RED : '#ffffff'} opacity={i % 2 ? 0.07 : 0.03} transform={`rotate(24 ${x} 960)`} />;
				})}
			</svg>
			<svg width={W} height={H} style={{position: 'absolute', opacity: 0.09, mixBlendMode: 'overlay'}}>
				<filter id="grain">
					<feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves={2} seed={f % 8} />
				</filter>
				<rect width={W} height={H} filter="url(#grain)" />
			</svg>
			<AbsoluteFill style={{boxShadow: 'inset 0 0 300px rgba(0,0,0,0.85)'}} />
		</AbsoluteFill>
	);
};

/* ============ helpers ============ */
const Dust: React.FC<{x: number; y: number; at: number; w?: number}> = ({x, y, at, w = 700}) => {
	const t = useT();
	const p = (t - at) / 0.8;
	if (p < 0 || p > 1) return null;
	return (
		<svg width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
			{Array.from({length: 10}).map((_, i) => {
				const dir = i % 2 ? 1 : -1;
				const r = 40 + random('d' + i) * 50;
				return <ellipse key={i} cx={x + dir * (40 + p * w * (0.3 + random('dx' + i) * 0.4))} cy={y - p * 60 * random('dy' + i)} rx={r * (1 + p)} ry={r * 0.5 * (1 + p)} fill="#9a9a9a" opacity={0.35 * (1 - p)} filter="blur(8px)" />;
			})}
		</svg>
	);
};

const Cracks: React.FC<{cx: number; cy: number; at: number; n?: number; len?: number; color?: string}> = ({cx, cy, at, n = 14, len = 900, color = '#fff'}) => {
	const t = useT();
	const p = prog(t, at, 0.18);
	if (t < at) return null;
	return (
		<svg width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
			{Array.from({length: n}).map((_, i) => {
				const a = (i / n) * Math.PI * 2 + random('c' + i) * 0.3;
				let d = `M${cx},${cy}`;
				let x = cx, y = cy;
				const segs = 5;
				for (let k = 1; k <= segs; k++) {
					const r = (len * k) / segs * (0.6 + random('r' + i + k) * 0.6);
					const aa = a + (random('a' + i + k) - 0.5) * 0.4;
					x = cx + Math.cos(aa) * r * p;
					y = cy + Math.sin(aa) * r * p;
					d += ` L${x},${y}`;
				}
				return <path key={i} d={d} stroke={color} strokeWidth={4} fill="none" opacity={0.85} />;
			})}
			<circle cx={cx} cy={cy} r={60 * p} fill="none" stroke={color} strokeWidth={5} opacity={0.8} />
		</svg>
	);
};

const Flash: React.FC<{at: number; color?: string; d?: number; o?: number}> = ({at, color = '#fff', d = 0.18, o = 0.9}) => {
	const t = useT();
	const k = t < at ? 0 : Math.max(0, 1 - (t - at) / d);
	return k > 0 ? <AbsoluteFill style={{background: color, opacity: k * o}} /> : null;
};

const Nut: React.FC<{s?: number}> = ({s = 120}) => (
	<svg width={s} height={s} viewBox="0 0 120 120">
		<polygon points="60,6 107,33 107,87 60,114 13,87 13,33" fill="#9b9ea4" stroke="#5c5f64" strokeWidth={5} />
		<polygon points="60,6 107,33 60,60" fill="#c3c6cc" />
		<circle cx={60} cy={60} r={24} fill="#3d3f43" />
		<circle cx={60} cy={60} r={16} fill="#222" />
	</svg>
);

/* ============ S01 hook ============ */
const S01: React.FC = () => {
	const t = useT();
	const {c} = useS();
	const land = 0.2;
	const fall = ein(clamp(t / land));
	const tOpen = c('توی') - 0.08;
	const open = prog(t, tOpen, 0.35, eio);
	const [sx, sy] = shake(t, land, 34, 8);
	const [ox, oy] = shake(t, tOpen + 0.1, 16, 9, 50, 2);
	return (
		<AbsoluteFill style={{transform: `translate(${sx + ox}px,${sy + oy}px)`}}>
			<Glow x={540} y={900} r={700} o={0.35 + 0.35 * open} />
			<SpeedLines cx={540} cy={900} o={open > 0 && open < 1 ? 1 : open >= 1 ? 0.5 : 0} seed="h" />
			<At x={540} y={interpolate(fall, [0, 1], [380, 920])}>
				<div style={{position: 'relative', width: 900, height: 900, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
					<div style={{position: 'absolute', transform: `scaleX(${1 - clamp(open * 2)}) rotate(-4deg)`, opacity: open < 0.5 ? 1 : 0}}>
						<P src="kit_closed.png" w={460} />
					</div>
					<div style={{position: 'absolute', transform: `scale(${open < 0.5 ? 0 : interpolate(open, [0.5, 1], [0.4, 1])})`}}>
						<P src="kit_open.png" w={900} />
						<Sweep at={tOpen + 0.35} />
					</div>
				</div>
			</At>
			<Dust x={540} y={1300} at={land} />
			<At x={540} y={300}>
				<Slam at={c('تعمیرگاهِ') - 0.15} size={128}>
					یه تعمیرگاهِ
				</Slam>
			</At>
			<At x={540} y={450}>
				<Block at={c('کامل') - 0.1} size={110}>
					کامل
				</Block>
			</At>
			<At x={540} y={1420}>
				<Slam at={tOpen} size={120} color={YEL}>
					توی یه کیف!
				</Slam>
			</At>
			<At x={880} y={1150}>
				<Pop at={c('کیف')} rot={-30} from={0.2}>
					<div style={{width: 210, height: 210, borderRadius: '50%', background: RED, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', transform: `rotate(${12 + Math.sin(t * 4) * 4}deg)`, boxShadow: '0 20px 50px rgba(255,42,42,0.5)', border: '6px dashed rgba(255,255,255,0.6)'}}>
						<div style={{fontFamily: FA, fontWeight: 900, fontSize: 92, color: '#fff', lineHeight: 1}}>{fa(71)}</div>
						<div style={{fontFamily: FA, fontWeight: 900, fontSize: 40, color: '#fff'}}>تیکه</div>
					</div>
				</Pop>
			</At>
		</AbsoluteFill>
	);
};

/* ============ S02 problem ============ */
const S02: React.FC = () => {
	const t = useT();
	const {c} = useS();
	const tHalf = c('نیم') - 0.05;
	const cp = prog(t, tHalf, 0.9, (x) => x);
	const secs = Math.floor(cp * (29 * 60 + 59));
	const mm = String(Math.floor(secs / 60)).padStart(2, '0');
	const ss = String(secs % 60).padStart(2, '0');
	const wob = Math.sin(t * 9) * 10 + Math.sin(t * 23) * 3;
	const strain = t > c('سفت') ? 1 : 0.4;
	return (
		<AbsoluteFill>
			<AbsoluteFill style={{background: 'radial-gradient(circle at 50% 55%, rgba(200,0,0,0.25), transparent 60%)'}} />
			<At x={540} y={300}>
				<Pop at={0.02} from={0.6}>
					<div style={{fontFamily: FA, fontWeight: 900, fontSize: 150, color: cp > 0 ? RED : '#fff', direction: 'ltr', letterSpacing: 4, textShadow: cp > 0 ? '0 0 40px rgba(255,42,42,0.7)' : 'none', transform: `scale(${1 + (cp > 0 && cp < 1 ? 0.04 * Math.sin(t * 40) : 0)})`}}>
						{fa(mm)}:{fa(ss)}
					</div>
				</Pop>
			</At>
			<At x={540} y={460}>
				<Slam at={tHalf} size={100} color="#fff">
					<span style={{color: RED}}>نیم ساعت</span> برای یه پیچ؟!
				</Slam>
			</At>
			{/* bolt + wrench */}
			<At x={540} y={950}>
				<Pop at={0.05} from={0.5}>
					<svg width={900} height={700} viewBox="0 0 900 700" style={{overflow: 'visible'}}>
						<defs>
							<radialGradient id="rust" cx="0.4" cy="0.35">
								<stop offset="0" stopColor="#b8733b" />
								<stop offset="0.6" stopColor="#7a3f1a" />
								<stop offset="1" stopColor="#3d1d0b" />
							</radialGradient>
							<linearGradient id="steel" x1="0" y1="0" x2="0" y2="1">
								<stop offset="0" stopColor="#e9ebef" />
								<stop offset="0.5" stopColor="#9aa0a8" />
								<stop offset="1" stopColor="#5d636b" />
							</linearGradient>
						</defs>
						<rect x={150} y={420} width={600} height={60} rx={10} fill="#2a2c30" />
						<polygon points="450,190 560,253 560,377 450,440 340,377 340,253" fill="url(#rust)" stroke="#2b1408" strokeWidth={6} />
						{[0, 1, 2, 3, 4, 5].map((i) => (
							<circle key={i} cx={380 + random('rs' + i) * 140} cy={240 + random('ry' + i) * 150} r={8 + random('rr' + i) * 14} fill="#5a2a0e" opacity={0.6} />
						))}
						<circle cx={450} cy={315} r={42} fill="#2a1306" />
						<g transform={`rotate(${wob * strain} 450 315)`}>
							<path d="M450,315 L850,180" stroke="url(#steel)" strokeWidth={70} strokeLinecap="round" />
							<path d="M450,315 L850,180" stroke="rgba(255,255,255,0.35)" strokeWidth={12} strokeLinecap="round" transform="translate(0,-18)" />
							<path d="M370,250 A110,110 0 1,0 530,250 L500,285 A70,70 0 1,1 400,285 Z" fill="url(#steel)" stroke="#4a4f56" strokeWidth={4} />
						</g>
						{/* sweat / stress marks */}
						{t > c('سفت') &&
							[0, 1, 2].map((i) => {
								const p = ((t - c('سفت')) * 1.6 + i * 0.33) % 1;
								return <path key={i} d={`M${620 + i * 60},${120 - p * 60} l14,-34`} stroke={RED} strokeWidth={10} strokeLinecap="round" opacity={1 - p} />;
							})}
					</svg>
				</Pop>
			</At>
			<At x={540} y={1450}>
				<Block at={c('کلنجار') - 0.1} size={80} bg="#fff" color="#111" rot={2}>
					کلنجار با آچار دستی!
				</Block>
			</At>
		</AbsoluteFill>
	);
};

/* ============ S03 enough ============ */
const S03: React.FC = () => {
	const t = useT();
	const {c} = useS();
	const tb = c('بسه') - 0.12;
	const [sx, sy] = shake(t, tb, 40, 7);
	return (
		<AbsoluteFill style={{transform: `translate(${sx}px,${sy}px)`}}>
			<AbsoluteFill style={{background: `radial-gradient(circle at 50% 48%, rgba(255,42,42,${0.55 * prog(t, tb, 0.1)}), rgba(80,0,0,0.6) 70%)`}} />
			<Cracks cx={540} cy={900} at={0.02} />
			<At x={540} y={620}>
				<Slam at={0.04} size={110} skew={0}>
					دیگه
				</Slam>
			</At>
			<At x={540} y={900}>
				<Slam at={tb} size={360} skew={-8} style={{textShadow: '0 0 80px rgba(255,0,0,0.9), 0 20px 60px rgba(0,0,0,0.8)'}}>
					بسه!
				</Slam>
			</At>
			<Flash at={0} o={0.85} d={0.12} />
			<Flash at={tb} color={RED} o={0.5} d={0.2} />
		</AbsoluteFill>
	);
};

/* ============ S04 reveal ============ */
const S04: React.FC = () => {
	const t = useT();
	const {c} = useS();
	const n = Math.round(interpolate(t, [0.05, c('هفتاد') + 0.35], [0, 71], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: eo}));
	const kp = useSp(0.05, 13, 0.9);
	return (
		<AbsoluteFill>
			<svg width={W} height={H} style={{position: 'absolute'}}>
				<defs>
					<linearGradient id="cone" x1="0" y1="0" x2="0" y2="1">
						<stop offset="0" stopColor="#fff" stopOpacity={0.35} />
						<stop offset="1" stopColor="#fff" stopOpacity={0} />
					</linearGradient>
				</defs>
				<polygon points={`540,0 ${540 - 120},0 ${540 - 560},1500 ${540 + 560},1500 ${540 + 120},0`} fill="url(#cone)" opacity={prog(t, 0, 0.3)} />
			</svg>
			<At x={540} y={330}>
				<div style={{fontFamily: FA, fontWeight: 900, fontSize: 420, lineHeight: 1, color: 'rgba(255,42,42,0.16)', WebkitTextStroke: `5px ${RED}`, direction: 'ltr', transform: `scale(${1 + 0.05 * Math.sin(t * 3)})`}}>{fa(n)}</div>
			</At>
			<Glow x={540} y={960} r={560} o={0.45} />
			<At x={540} y={960}>
				<div style={{position: 'relative', transform: `scale(${interpolate(kp, [0, 1], [0.5, 1])}) rotate(${(1 - kp) * -8}deg)`}}>
					<P src="kit_open.png" w={800} />
					<Sweep at={0.35} dur={0.8} />
				</div>
			</At>
			<Sparks x={80} y={1500} from={0.05} to={1.2} dir={-60} n={50} seed="l" speed={1200} />
			<Sparks x={1000} y={1500} from={0.05} to={1.2} dir={-120} n={50} seed="r" speed={1200} />
			<At x={540} y={1340}>
				<Slam at={c('کیتِ') - 0.1} size={104}>
					کیت ابزار بادی
				</Slam>
			</At>
			<At x={540} y={1480}>
				<Block at={c('هفتاد') - 0.05} size={74}>
					{fa(71)} تیکه
				</Block>
			</At>
			<Flash at={0} o={0.9} d={0.25} />
		</AbsoluteFill>
	);
};

/* ============ tool scene frame ============ */
const ToolTitle: React.FC<{n: number; title: string; at?: number}> = ({n, title, at = 0}) => (
	<>
		<At x={890} y={250}>
			<NumTag n={n} at={at} />
		</At>
		<div style={{position: 'absolute', right: 70, top: 330}}>
			<Slam at={at + 0.05} size={118} skew={-6} style={{textAlign: 'right'}}>
				{title}
			</Slam>
		</div>
	</>
);

/* ============ S05 impact wrench ============ */
const S05: React.FC = () => {
	const t = useT();
	const {c} = useS();
	const s = useSp(0, 12, 0.8);
	const run0 = c('چند') - 0.12;
	const run1 = c('می‌کنه') + 0.5;
	const running = t > run0 && t < run1;
	const [vx, vy] = vib(t, running, 7);
	const tNut = c('باز') - 0.05;
	const np = clamp((t - tNut) / 0.9);
	return (
		<AbsoluteFill>
			<ToolTitle n={1} title="بُکس بادی" />
			<Glow x={560} y={940} r={520} o={0.35} />
			<SpeedLines cx={200} cy={700} o={running ? 1 : 0} seed="w" />
			<At x={560 + (1 - s) * 900 + vx} y={950 + vy}>
				<div style={{transform: `rotate(${(1 - s) * 30}deg)`, position: 'relative'}}>
					<P src="wrench.png" w={760} />
					<Sweep at={0.25} />
				</div>
			</At>
			{t > tNut && (
				<div style={{position: 'absolute', left: 140 - np * 260, top: 640 - np * 380 + np * np * 900, transform: `rotate(${np * 1440}deg) scale(${1 - np * 0.3})`}}>
					<Nut s={130} />
				</div>
			)}
			{running && <Sparks x={190} y={700} from={run0} to={run1} dir={200} spread={80} n={60} seed="n" speed={900} />}
			<At x={540} y={1440}>
				<Block at={c('چند') - 0.05} size={86} bg={YEL} color="#111" rot={-2}>
					فقط چند ثانیه <svg width={60} height={70} viewBox="0 0 60 70" style={{verticalAlign: "middle", marginLeft: 14}}><path d="M36,2 L6,40 L28,40 L22,68 L54,26 L32,26 Z" fill="#111" /></svg>
				</Block>
			</At>
		</AbsoluteFill>
	);
};

/* ============ S06 ratchet ============ */
const S06: React.FC = () => {
	const t = useT();
	const {c} = useS();
	const s = useSp(0, 13, 0.8);
	const tg = c('جاهای') - 0.1;
	const close = prog(t, tg, 0.45, eio);
	const running = t > c('دستت') - 0.1;
	const [vx, vy] = vib(t, running, 5);
	return (
		<AbsoluteFill>
			<ToolTitle n={2} title="جغجغه‌ی بادی" />
			{/* closing walls */}
			{[0, 1].map((i) => {
				const y = i === 0 ? interpolate(close, [0, 1], [640, 800]) : interpolate(close, [0, 1], [1250, 1060]);
				return (
					<div key={i} style={{position: 'absolute', left: 0, width: W, top: i === 0 ? y - 180 : y, height: 180, background: 'repeating-linear-gradient(135deg,#2b2e33 0 40px,#23262a 40px 80px)', borderTop: i === 1 ? `8px solid ${YEL}` : undefined, borderBottom: i === 0 ? `8px solid ${YEL}` : undefined, opacity: prog(t, tg - 0.1, 0.2), boxShadow: '0 0 60px rgba(0,0,0,0.6)'}} />
				);
			})}
			<At x={540 + (1 - s) * -900 + vx} y={930 + vy}>
				<div style={{position: 'relative'}}>
					<P src="ratchet_only.png" w={980} />
					<Sweep at={0.3} />
				</div>
			</At>
			{close > 0.9 &&
				[0, 1].map((i) => (
					<At key={i} x={i ? 960 : 120} y={930}>
						<svg width={110} height={110} viewBox="0 0 110 110" style={{transform: `translateX(${Math.sin(t * 8) * 10 * (i ? 1 : -1)}px) scaleX(${i ? 1 : -1})`}}><path d="M80,15 L30,55 L80,95" stroke={YEL} strokeWidth={16} fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
					</At>
				))}
			<At x={540} y={1400}>
				<Block at={c('تنگی') - 0.1} size={84} rot={2}>
					جاهای تنگ و سخت
				</Block>
			</At>
		</AbsoluteFill>
	);
};

/* ============ S07 die grinder ============ */
const S07: React.FC = () => {
	const t = useT();
	const {c, dur} = useS();
	const s = useSp(0, 12, 0.8);
	const run = t > 0.3;
	const [vx, vy] = vib(t, run, 4);
	const chips: [string, string, string, string][] = [
		['سنباده', 'سنباده', '#fff', '#111'],
		['برش', 'برش', RED, '#fff'],
		['پولیش', 'پولیش', YEL, '#111'],
	];
	return (
		<AbsoluteFill>
			<ToolTitle n={3} title="فرز انگشتی" />
			<Glow x={200} y={820} r={380} color={ORANGE} o={run ? 0.4 + 0.1 * Math.sin(t * 30) : 0} />
			<At x={560 + (1 - s) * 900 + vx} y={820 + vy}>
				<div style={{transform: `rotate(${-6 + (1 - s) * 20}deg)`, position: 'relative'}}>
					<P src="grinder_only.png" w={860} />
				</div>
			</At>
			{run && <Sparks x={150} y={830} from={0.3} to={dur} dir={130} spread={60} n={200} seed="g" speed={1500} />}
			<At x={540} y={1090}>
				<div style={{opacity: prog(t, 0.4, 0.4), transform: `translateY(${(1 - prog(t, 0.4, 0.5)) * 60}px)`}}>
					<P src="stones.png" w={880} />
				</div>
			</At>
			<div style={{position: 'absolute', top: 1290, width: W, display: 'flex', justifyContent: 'center', gap: 24, direction: 'rtl'}}>
				{chips.map(([w, label, bg, col], i) => (
					<Block key={i} at={c(w) - 0.08} size={68} bg={bg} color={col} rot={i % 2 ? 3 : -3}>
						{label}
					</Block>
				))}
			</div>
		</AbsoluteFill>
	);
};

/* ============ S08 air hammer ============ */
const S08: React.FC = () => {
	const t = useT();
	const {c} = useS();
	const land = 0.26;
	const fall = ein(clamp(t / land));
	const [sx, sy] = shake(t, land, 44, 7);
	const run = t > c('برای') - 0.05;
	const [vx, vy] = vib(t, run, 9);
	return (
		<AbsoluteFill style={{transform: `translate(${sx}px,${sy}px)`}}>
			<ToolTitle n={4} title="چکش بادی" />
			<Cracks cx={460} cy={1230} at={land} n={10} len={420} color="rgba(255,255,255,0.7)" />
			<Dust x={480} y={1230} at={land} w={600} />
			<At x={540 + vx} y={interpolate(fall, [0, 1], [-600, 900]) + vy}>
				<div style={{transform: 'rotate(-90deg)'}}>
					<P src="hammer.png" w={620} />
				</div>
			</At>
			<At x={540} y={1420}>
				<Slam at={c('کارای') - 0.1} size={124} color="#fff">
					کارای <span style={{color: RED}}>سنگین</span>
				</Slam>
			</At>
			<Flash at={land} o={0.35} d={0.12} />
		</AbsoluteFill>
	);
};

/* ============ S09 accessories ============ */
const S09: React.FC = () => {
	const t = useT();
	const {c} = useS();
	return (
		<AbsoluteFill>
			<At x={540} y={270}>
				<Slam at={0.02} size={96}>
					+ کلی لوازم جانبی
				</Slam>
			</At>
			<At x={540} y={470}>
				<Pop at={c('سری') - 0.1} x={-600} from={0.8}>
					<P src="bits.png" w={900} />
				</Pop>
			</At>
			<At x={300} y={600}>
				<Block at={c('سری') - 0.05} size={58} rot={-4}>
					سری‌ها
				</Block>
			</At>
			<At x={420} y={900}>
				<Pop at={c('اتصالاتِ') - 0.1} rot={-10} from={0.4}>
					<div style={{width: 560, height: 560, borderRadius: 40, overflow: 'hidden', border: '6px solid #fff', boxShadow: '0 30px 70px rgba(0,0,0,0.6)', transform: 'rotate(-4deg)'}}>
						<P src="accessories.jpg" w={560} />
					</div>
				</Pop>
			</At>
			<At x={420} y={1210}>
				<Block at={c('شیلنگ') - 0.15} size={58} bg={YEL} color="#111" rot={2}>
					اتصالات شیلنگ
				</Block>
			</At>
			<At x={850} y={1010}>
				<Pop at={c('کیفِ') - 0.1} rot={20} from={0.3} y={300}>
					<div style={{transform: 'rotate(6deg)'}}>
						<P src="kit_closed.png" w={340} />
					</div>
				</Pop>
			</At>
			<At x={850} y={1400}>
				<Block at={c('محکم') - 0.1} size={58} rot={-3}>
					کیف محکم
				</Block>
			</At>
			<At x={960} y={760}>
				<Pop at={c('مرتب') - 0.05} from={0.2} damping={9}>
					<Check s={110} />
				</Pop>
			</At>
		</AbsoluteFill>
	);
};

/* ============ S10 trust ============ */
const Icon: React.FC<{k: 'steel' | 'truck' | 'money'}> = ({k}) => (
	<svg width={130} height={130} viewBox="0 0 130 130">
		<circle cx={65} cy={65} r={62} fill={RED} />
		{k === 'steel' && <path d="M65,22 L100,36 L100,66 C100,88 84,102 65,110 C46,102 30,88 30,66 L30,36 Z" fill="#fff" />}
		{k === 'steel' && <text x={65} y={78} textAnchor="middle" fontSize={34} fontWeight={900} fill={RED} fontFamily="Vazirmatn">Fe</text>}
		{k === 'truck' && (
			<g fill="#fff">
				<rect x={20} y={45} width={55} height={38} rx={4} />
				<path d="M75,55 L95,55 L108,70 L108,83 L75,83 Z" />
				<circle cx={38} cy={88} r={10} stroke={RED} strokeWidth={4} />
				<circle cx={92} cy={88} r={10} stroke={RED} strokeWidth={4} />
			</g>
		)}
		{k === 'money' && (
			<g>
				<circle cx={65} cy={65} r={34} fill="#fff" />
				<text x={65} y={79} textAnchor="middle" fontSize={42} fontWeight={900} fill={RED} fontFamily="Vazirmatn">$</text>
				<path d="M28,40 A44,44 0 0,1 92,24" stroke="#fff" strokeWidth={7} fill="none" strokeLinecap="round" />
				<path d="M92,24 L80,16 M92,24 L86,37" stroke="#fff" strokeWidth={7} strokeLinecap="round" />
			</g>
		)}
	</svg>
);

const S10: React.FC = () => {
	const t = useT();
	const {c} = useS();
	const rows: [string, 'steel' | 'truck' | 'money', string][] = [
		['فولاده', 'steel', 'جنس فولادی'],
		['سریعه', 'truck', 'ارسال سریع'],
		['ضمانتِ', 'money', 'ضمانت بازگشت پول'],
	];
	return (
		<AbsoluteFill>
			<At x={540} y={880}>
				<div style={{opacity: 0.16, filter: 'blur(3px)', transform: `scale(${1.15 + t * 0.01})`}}>
					<P src="kit_open.png" w={1000} />
				</div>
			</At>
			<At x={540} y={330}>
				<Slam at={0.02} size={92}>
					با خیال راحت بخر
				</Slam>
			</At>
			{rows.map(([w, k, label], i) => {
				const at = c(w) - 0.15;
				return (
					<div key={i} style={{position: 'absolute', right: 90, top: 560 + i * 280}}>
						<Pop at={at} x={300} from={0.7}>
							<div style={{display: 'flex', alignItems: 'center', gap: 34, direction: 'rtl', background: 'rgba(255,255,255,0.06)', border: '2px solid rgba(255,255,255,0.12)', borderRadius: 40, padding: '26px 40px 26px 34px', width: 840, backdropFilter: 'blur(6px)'}}>
								<Icon k={k} />
								<div style={{fontFamily: FA, fontWeight: 900, fontSize: 60, color: '#fff', flex: 1, whiteSpace: 'nowrap'}}>{label}</div>
								<Pop at={at + 0.25} from={0.2} damping={9}>
									<Check s={80} />
								</Pop>
							</div>
						</Pop>
					</div>
				);
			})}
		</AbsoluteFill>
	);
};

/* ============ S11 price ============ */
const Roll: React.FC<{ch: string; at: number; i: number}> = ({ch, at, i}) => {
	const t = useT();
	const d = /[0-9]/.test(ch);
	if (!d) return <span>{ch}</span>;
	const target = +ch;
	const p = prog(t, at + i * 0.06, 0.9 + i * 0.05, eo);
	const v = (target + 30 * (1 - p)) % 10;
	const shown = p >= 1 ? target : Math.floor(v);
	return <span style={{display: 'inline-block', transform: `translateY(${p < 1 ? Math.sin(t * 60 + i) * 8 : 0}px)`, filter: p < 1 ? 'blur(2px)' : undefined}}>{shown}</span>;
};

const S11: React.FC = () => {
	const t = useT();
	const {c} = useS();
	const tp = c('صد') - 0.12;
	const tools = ['wrench.png', 'hammer.png', 'grinder_only.png', 'ratchet_only.png'];
	const settle = tp + 1.25;
	const [sx, sy] = shake(t, settle, 18, 8);
	const ps = useSp(tp, 11, 0.7);
	return (
		<AbsoluteFill style={{transform: `translate(${sx}px,${sy}px)`}}>
			<At x={540} y={300}>
				<Slam at={0.05} size={110}>
					این‌همه ابزار...
				</Slam>
			</At>
			<Glow x={540} y={760} r={500} o={0.35} />
			<At x={540} y={760}>
				<Pop at={0.1} from={0.6}>
					<P src="kit_open.png" w={600} />
				</Pop>
			</At>
			{tools.map((src, i) => {
				const a = (i / 4) * Math.PI * 2 + t * 0.9;
				const p = prog(t, 0.15 + i * 0.08, 0.5);
				return (
					<div key={i} style={{position: 'absolute', left: 540 + Math.cos(a) * 420 * p - 120, top: 760 + Math.sin(a) * 300 * p - 90, opacity: p, transform: `rotate(${a * 20}deg)`}}>
						<P src={src} w={240} />
					</div>
				);
			})}
			<At x={540} y={1130}>
				<Slam at={c('فقط') - 0.05} size={110} color={YEL}>
					فقط
				</Slam>
			</At>
			{t > tp && (
				<At x={540} y={1340}>
					<div style={{position: 'relative'}}>
						<Glow x={330} y={120} r={420} color={YEL} o={0.25 + (t > settle ? 0.15 : 0)} />
						<div style={{position: 'relative', fontFamily: FA, fontWeight: 900, fontSize: 230, color: YEL, direction: 'ltr', whiteSpace: 'nowrap', textShadow: '0 0 50px rgba(255,212,0,0.6), 0 12px 40px rgba(0,0,0,0.8)', transform: `scale(${interpolate(ps, [0, 1], [0.4, 1])})`}}>
							{'$133.99'.split('').map((ch, i) => (
								<Roll key={i} ch={ch} at={tp} i={i} />
							))}
						</div>
					</div>
				</At>
			)}
			<Sparks x={540} y={1340} from={settle} to={settle + 0.25} dir={-90} spread={180} n={90} seed="p" speed={1600} />
			<Flash at={settle} color={YEL} o={0.25} d={0.2} />
		</AbsoluteFill>
	);
};

/* ============ S12 CTA ============ */
const S12: React.FC = () => {
	const t = useT();
	const {c} = useS();
	const tap = c('بزن') - 0.05;
	const press = t > tap && t < tap + 0.18 ? 0.92 : 1;
	const pulse = 1 + 0.04 * Math.sin(t * 7);
	const handP = prog(t, tap - 0.5, 0.45, eio);
	const ripple = clamp((t - tap) / 0.6);
	return (
		<AbsoluteFill>
			<Glow x={540} y={560} r={520} o={0.4} />
			<At x={540} y={560}>
				<Pop at={0.02} from={0.6}>
					<div style={{transform: `translateY(${Math.sin(t * 2) * 12}px)`, position: 'relative'}}>
						<P src="kit_open.png" w={720} />
						<Sweep at={0.5} dur={0.9} />
					</div>
				</Pop>
			</At>
			<At x={540} y={1060}>
				<Pop at={0.15} from={0.4}>
					<div style={{position: 'relative', transform: `scale(${pulse * press})`}}>
						{t > tap && <div style={{position: 'absolute', inset: -30 * ripple, borderRadius: 140, border: `6px solid ${RED}`, opacity: 1 - ripple}} />}
						<div style={{width: 900, height: 200, borderRadius: 110, background: `linear-gradient(180deg, #FF4A4A, ${RED2})`, display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 24px 70px rgba(255,42,42,0.55), inset 0 3px 0 rgba(255,255,255,0.35)', fontFamily: FA, fontWeight: 900, fontSize: 84, color: '#fff', direction: 'rtl', overflow: 'hidden', position: 'relative'}}>
							همین الان سفارش بده
							<Sweep at={0.9} dur={0.8} />
						</div>
					</div>
				</Pop>
			</At>
			{/* hand cursor */}
			<div style={{position: 'absolute', left: interpolate(handP, [0, 1], [1100, 640]), top: interpolate(handP, [0, 1], [1500, 1070]), transform: `scale(${press < 1 ? 0.9 : 1})`, opacity: prog(t, tap - 0.5, 0.2)}}>
				<svg width={150} height={170} viewBox="0 0 150 170">
					<path d="M50,20 C50,8 70,8 70,20 L70,80 L78,80 C78,70 96,70 96,82 L102,82 C102,72 120,72 120,86 L124,88 C124,78 142,80 142,92 L142,125 C142,150 122,165 98,165 L78,165 C60,165 48,155 40,140 L14,98 C8,86 24,78 32,88 L50,110 Z" fill="#fff" stroke="#111" strokeWidth={6} strokeLinejoin="round" />
				</svg>
			</div>
			<At x={540} y={1330}>
				<div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', opacity: prog(t, c('لینک') - 0.1, 0.2)}}>
					<div style={{fontFamily: FA, fontWeight: 900, fontSize: 64, color: YEL, direction: 'rtl'}}>لینک خرید</div>
					<svg width={90} height={90} viewBox="0 0 90 90" style={{transform: `translateY(${Math.abs(Math.sin(t * 6)) * 18}px)`}}>
						<path d="M45,8 L45,70 M18,46 L45,74 L72,46" stroke={YEL} strokeWidth={12} fill="none" strokeLinecap="round" strokeLinejoin="round" />
					</svg>
				</div>
			</At>
			<At x={540} y={1460}>
				<div style={{fontFamily: FA, fontWeight: 800, fontSize: 40, color: 'rgba(255,255,255,0.75)', direction: 'rtl', opacity: prog(t, 1.4, 0.4), whiteSpace: 'nowrap'}}>ارسال سریع · ضمانت بازگشت پول · پشتیبانی ۲۴/۷</div>
			</At>
		</AbsoluteFill>
	);
};

const SCENES = [S01, S02, S03, S04, S05, S06, S07, S08, S09, S10, S11, S12];

/* ============ captions (karaoke chunks) ============ */
const chunks = (() => {
	const out: {s: number; e: number; words: Word[]; scene: string}[] = [];
	for (const sc of scenes) {
		let cur: Word[] = [];
		const flush = () => {
			if (cur.length) out.push({s: sc.start + cur[0].s - 0.03, e: sc.start + cur[cur.length - 1].e, words: cur.map((w) => ({...w, s: sc.start + w.s, e: sc.start + w.e})), scene: sc.id});
			cur = [];
		};
		sc.words.forEach((w, i) => {
			if (cur.length && (cur.length >= 3 || w.s - cur[cur.length - 1].e > 0.3)) flush();
			cur.push(w);
		});
		flush();
	}
	for (let i = 0; i < out.length - 1; i++) out[i].e = Math.min(out[i].e + 0.15, out[i + 1].s);
	return out;
})();

const Captions: React.FC = () => {
	const f = useCurrentFrame();
	const t = f / FPS;
	const ch = chunks.find((x) => t >= x.s && t < x.e);
	if (!ch || ch.scene === '03' || ch.scene === '11') return null;
	const local = t - ch.s;
	const pop = 0.8 + 0.2 * eo(clamp(local / 0.1));
	return (
		<div style={{position: 'absolute', left: 0, width: W, top: 1665, transform: `translateY(-50%) scale(${pop})`, display: 'flex', justifyContent: 'center', gap: 20, direction: 'rtl', flexWrap: 'wrap', padding: '0 60px', boxSizing: 'border-box'}}>
			{ch.words.map((w, i) => {
				const on = t >= w.s && t < w.e + 0.05;
				return (
					<span
						key={i}
						style={{
							fontFamily: FA,
							fontWeight: 900,
							fontSize: on ? 84 : 76,
							color: on ? YEL : '#fff',
							WebkitTextStroke: '10px #000',
							paintOrder: 'stroke fill',
							textShadow: '0 8px 24px rgba(0,0,0,0.6)',
							transition: 'none',
							display: 'inline-block',
							transform: on ? 'translateY(-4px) rotate(-2deg)' : 'none',
							lineHeight: 1.25,
						}}
					>
						{w.t}
					</span>
				);
			})}
		</div>
	);
};

/* ============ scene wrapper ============ */
const Wrap: React.FC<{children: React.ReactNode; first: boolean}> = ({children, first}) => {
	const t = useT();
	const e = first ? 1 : eo(clamp(t / 0.2));
	return <AbsoluteFill style={{transform: `scale(${1 + (1 - e) * 0.14})`, filter: e < 1 ? `blur(${(1 - e) * 18}px)` : undefined}}>{children}</AbsoluteFill>;
};

const Progress: React.FC = () => {
	const f = useCurrentFrame();
	const p = f / (data.total * FPS);
	return (
		<div style={{position: 'absolute', left: 0, top: 0, width: W, height: 10, background: 'rgba(255,255,255,0.12)'}}>
			<div style={{position: 'absolute', right: 0, width: `${p * 100}%`, height: '100%', background: RED, boxShadow: `0 0 16px ${RED}`}} />
		</div>
	);
};

export const Reel: React.FC = () => {
	const [h] = React.useState(() => delayRender('fonts'));
	React.useEffect(() => {
		Promise.all([900, 800, 700].map((w) => document.fonts.load(`${w} 40px Vazirmatn`, 'سلام')))
			.then(() => document.fonts.ready)
			.then(() => continueRender(h));
	}, [h]);
	return (
		<AbsoluteFill style={{background: '#000'}}>
			<Background />
			{scenes.map((sc, i) => {
				const from = Math.round((i === 0 ? 0 : sc.start) * FPS);
				const d = Math.round(sc.end * FPS) - from;
				const off = sc.start - from / FPS;
				const c = (w: string, occ = 0) => {
					const m = sc.words.filter((x) => x.t === w || x.t.startsWith(w));
					return (m[occ] ?? m[0] ?? {s: 0}).s + off;
				};
				const Comp = SCENES[i];
				return (
					<Sequence key={sc.id} from={from} durationInFrames={d} name={'S' + sc.id}>
						<Ctx.Provider value={{c, dur: d / FPS}}>
							<Wrap first={i === 0}>
								<Comp />
							</Wrap>
						</Ctx.Provider>
					</Sequence>
				);
			})}
			<Captions />
			<Progress />
		</AbsoluteFill>
	);
};
