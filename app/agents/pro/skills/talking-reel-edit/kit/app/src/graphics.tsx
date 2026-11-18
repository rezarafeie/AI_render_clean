import React from 'react';
import {interpolate, random} from 'remotion';
import {
	At, BoxIcon, Briefcase, Card, Check, Coin, CORAL, CORAL2, coralText, eio, eo, FA, fa, Gear, GOLD, GREEN, INK, Laptop, Mic, MUTED, NASKH, Phone, Play, Pop, prog, SERIF, Sparkle, StampX, Tag, useFloat, useSp, useT,
} from './ui';

export type GP = {k: (i: number) => number; dur: number};

/* ---------- 1. فروش خدمات + مهر ضربدر ---------- */
export const GService: React.FC<GP> = ({k}) => {
	const t = useT();
	const tS = k(4);
	const st = useSp(tS, 9, 0.6, 220);
	const shake = t > tS ? Math.sin((t - tS) * 60) * 14 * Math.exp(-(t - tS) * 8) : 0;
	const fl = useFloat(8, 0.9);
	const gray = prog(t, tS, 0.3);
	return (
		<>
			<At x={540} y={500 + fl}>
				<Pop at={0.02} rot={-8} from={0.5}>
					<div style={{transform: `translateX(${shake}px)`, filter: `grayscale(${gray * 0.7})`}}>
						<Card w={600} h={440}>
							<div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 18}}>
								<Briefcase s={170} />
								<div style={{fontFamily: FA, fontWeight: 900, fontSize: 76, color: INK, direction: 'rtl'}}>فروش خدمات</div>
								<div style={{fontFamily: FA, fontWeight: 600, fontSize: 34, color: MUTED, direction: 'rtl'}}>درآمد = ساعتِ کارِ تو</div>
							</div>
						</Card>
					</div>
				</Pop>
			</At>
			{t > tS - 0.05 && (
				<At x={760} y={330 + fl}>
					<div style={{transform: `scale(${interpolate(st, [0, 1], [2.4, 1])}) rotate(-14deg)`, opacity: prog(t, tS - 0.02, 0.08)}}>
						<StampX s={250} />
					</div>
				</At>
			)}
		</>
	);
};

/* ---------- coins burst (full overlay) ---------- */
export const GCoins: React.FC<GP & {seed?: string}> = ({seed = 'c'}) => {
	const t = useT();
	const n = 28;
	return (
		<div style={{position: 'absolute', inset: 0, pointerEvents: 'none'}}>
			<div
				style={{
					position: 'absolute',
					inset: 0,
					background: `radial-gradient(circle at 50% 75%, rgba(245,184,61,${0.45 * Math.max(0, 1 - t * 2)}) 0%, rgba(245,184,61,0) 60%)`,
				}}
			/>
			{Array.from({length: n}).map((_, i) => {
				const vx = (random(seed + 'x' + i) - 0.5) * 1300;
				const vy = -1900 - random(seed + 'y' + i) * 1200;
				const d = random(seed + 'd' + i) * 0.18;
				const tt = Math.max(0, t - d);
				if (tt <= 0) return null;
				const x = 540 + vx * tt;
				const y = 1950 + vy * tt + 2600 * tt * tt;
				const s = 60 + random(seed + 's' + i) * 60;
				return (
					<div key={i} style={{position: 'absolute', left: x - s / 2, top: y - s / 2, transform: `rotate(${tt * 400 * (i % 2 ? 1 : -1)}deg)`}}>
						<Coin s={s} spin={Math.cos(tt * 12 + i)} />
					</div>
				);
			})}
		</div>
	);
};

/* ---------- sparkle overlay ---------- */
export const GSparkle: React.FC<GP> = () => {
	const t = useT();
	const pts = [
		[250, 520, 0, 90], [840, 450, 0.08, 70], [190, 900, 0.15, 55], [900, 820, 0.05, 100], [330, 300, 0.2, 50], [760, 1100, 0.12, 60], [560, 260, 0.1, 80],
	];
	return (
		<div style={{position: 'absolute', inset: 0}}>
			{pts.map(([x, y, d, s], i) => {
				const p = prog(t, d, 0.35);
				const tw = 0.7 + 0.3 * Math.sin(t * 9 + i);
				return (
					<div key={i} style={{position: 'absolute', left: x - s / 2, top: y - s / 2, transform: `scale(${p * tw}) rotate(${t * 90}deg)`, opacity: p, filter: 'drop-shadow(0 0 18px rgba(255,255,255,0.9))'}}>
						<Sparkle s={s} color={i % 3 === 0 ? '#FFE7A3' : '#fff'} />
					</div>
				);
			})}
		</div>
	);
};

/* ---------- 2. محصول (full graphic) ---------- */
export const GProduct: React.FC<GP> = () => {
	const t = useT();
	const ts = useSp(0.0, 14, 0.9);
	const fl = useFloat(12, 0.8);
	return (
		<>
			<At x={540} y={640}>
				<div
					style={{
						fontFamily: NASKH,
						fontWeight: 700,
						fontSize: 330,
						lineHeight: 1,
						...coralText,
						opacity: prog(t, 0, 0.3),
						transform: `scale(${interpolate(ts, [0, 1], [1.4, 1])})`,
						filter: `blur(${(1 - prog(t, 0, 0.35)) * 16}px)`,
						whiteSpace: 'nowrap',
					}}
				>
					محصول
				</div>
			</At>
			<At x={540} y={1010 + fl}>
				<Pop at={0.18} rot={12} from={0.3} damping={10}>
					<Card w={460} h={460} r={90}>
						<div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'linear-gradient(160deg,#fff,#F6F1EA)'}}>
							<BoxIcon s={290} />
						</div>
					</Card>
				</Pop>
			</At>
			{[[250, 860, 0.4], [840, 1180, 0.5], [820, 820, 0.6]].map(([x, y, d], i) => (
				<At key={i} x={x} y={y}>
					<div style={{transform: `scale(${prog(t, d, 0.3) * (0.8 + 0.2 * Math.sin(t * 8 + i))}) rotate(${t * 60}deg)`}}>
						<Sparkle s={50} color={CORAL} />
					</div>
				</At>
			))}
		</>
	);
};

/* ---------- 3. نمودار رشد ---------- */
export const GChart: React.FC<GP> = ({k}) => {
	const t = useT();
	const t1 = k(21), t2 = k(24), t3 = k(27);
	const p = 0.08 + 0.3 * prog(t, t1 - 0.3, 0.6, eio) + 0.3 * prog(t, t2 - 0.2, 0.6, eio) + 0.32 * prog(t, t3 - 0.2, 0.7, eio);
	const pts: [number, number][] = [];
	for (let i = 0; i <= 60; i++) {
		const x = i / 60;
		pts.push([70 + x * 740, 520 - Math.pow(x, 3.2) * 440]);
	}
	const n = Math.max(2, Math.round(p * 60));
	const d = pts.slice(0, n + 1).map((q, i) => `${i ? 'L' : 'M'}${q[0]},${q[1]}`).join(' ');
	const head = pts[n];
	const mult = t < t1 ? 1 : t < t2 ? 10 : t < t3 ? 100 : 1000;
	const ms = useSp(t < t1 ? 0.1 : t < t2 ? t1 : t < t3 ? t2 : t3, 9, 0.6);
	const labels: [number, string, number][] = [
		[t1, 'بزرگ', 0.38],
		[t2, 'Scale', 0.68],
		[t3, 'Scale Level', 1],
	];
	return (
		<At x={540} y={490}>
			<Pop at={0.02} from={0.6}>
				<Card w={900} h={680}>
					<svg width={900} height={680} style={{position: 'absolute', top: 40}}>
						{[0, 1, 2, 3].map((i) => (
							<line key={i} x1={70} x2={830} y1={520 - i * 140} y2={520 - i * 140} stroke="#EEE9E3" strokeWidth={3} />
						))}
						<path d={d + ` L${head[0]},520 L70,520 Z`} fill="rgba(232,112,90,0.12)" />
						<path d={d} fill="none" stroke={CORAL} strokeWidth={12} strokeLinecap="round" strokeLinejoin="round" />
						<circle cx={head[0]} cy={head[1]} r={18} fill={CORAL} />
						<circle cx={head[0]} cy={head[1]} r={34 + Math.sin(t * 10) * 6} fill="none" stroke={CORAL} strokeWidth={4} opacity={0.5} />
					</svg>
					{labels.map(([at, txt, x], i) => {
						const q = pts[Math.round(x * 60)];
						return (
							<div key={i} style={{position: 'absolute', left: q[0] - (i === 2 ? 260 : 60), top: q[1] + 40 - 110}}>
								<Pop at={at - 0.05} from={0.3} damping={10}>
									<div style={{fontFamily: i ? SERIF : FA, fontStyle: i ? 'italic' : 'normal', fontWeight: 800, fontSize: 40, color: '#fff', background: INK, padding: '6px 22px 10px', borderRadius: 16, whiteSpace: 'nowrap'}}>{txt}</div>
								</Pop>
							</div>
						);
					})}
					<div style={{position: 'absolute', left: 60, top: 40, fontFamily: SERIF, fontStyle: 'italic', fontWeight: 900, fontSize: 110, ...coralText, transform: `scale(${0.7 + 0.3 * ms})`, transformOrigin: '0% 0%'}}>
						×{mult.toLocaleString('en-US')}
					</div>
				</Card>
			</Pop>
		</At>
	);
};

/* ---------- 4. فیزیکی / دیجیتال (full graphic) ---------- */
export const GTwo: React.FC<GP> = ({k}) => {
	const t = useT();
	const c = (n: string, label: string, icon: React.ReactNode, at: number, x: number, rot: number) => (
		<At x={x} y={930}>
			<Pop at={at} rot={rot} from={0.3} damping={10}>
				<div style={{transform: `translateY(${Math.sin(t * 1.8 + x) * 10}px)`}}>
					<Card w={440} h={600} r={60}>
						<div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 26}}>
							<div style={{fontFamily: NASKH, fontWeight: 700, fontSize: 120, lineHeight: 1, ...coralText}}>{n}</div>
							{icon}
							<div style={{fontFamily: FA, fontWeight: 900, fontSize: 70, color: INK, direction: 'rtl'}}>{label}</div>
						</div>
					</Card>
				</div>
			</Pop>
		</At>
	);
	return (
		<>
			<At x={540} y={420}>
				<Pop at={0.05} from={0.6}>
					<div style={{fontFamily: NASKH, fontWeight: 700, fontSize: 130, ...coralText, whiteSpace: 'nowrap'}}>دو نوع محصول</div>
				</Pop>
			</At>
			{c(fa(1), 'فیزیکی', <BoxIcon s={220} />, k(36) - 0.08, 780, 10)}
			{c(fa(2), 'دیجیتال', <Laptop s={250} />, k(39) - 0.08, 300, -10)}
			<At x={540} y={930}>
				<div style={{fontFamily: FA, fontWeight: 900, fontSize: 54, color: MUTED, opacity: prog(t, k(37), 0.2) * (t < k(39) - 0.1 ? 1 : 0)}}>یا</div>
			</At>
		</>
	);
};

/* ---------- 5. گوشی ---------- */
export const GPhone: React.FC<GP> = ({k}) => {
	const t = useT();
	const at = k(44) - 0.15;
	const fl = useFloat(10, 1);
	const swing = Math.sin((t - at) * 5) * 10 * Math.exp(-Math.max(0, t - at) * 1.5);
	return (
		<>
			<At x={300} y={170}>
				<Tag at={0.1}>محصول فیزیکی</Tag>
			</At>
			<At x={560} y={540 + fl}>
				<Pop at={at} rot={-20} from={0.4} y={200}>
					<div style={{transform: 'rotate(-7deg)'}}>
						<Phone w={340}>
							<div style={{position: 'absolute', top: 70, left: 24, right: 24, height: 300, borderRadius: 30, background: 'linear-gradient(160deg,#FFE3D8,#F5A98B)', display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
								<div style={{width: 110, height: 220, borderRadius: 22, background: '#1a1a1a', border: '6px solid #333', boxShadow: '12px 16px 30px rgba(0,0,0,0.25)'}} />
							</div>
							<div style={{position: 'absolute', top: 395, right: 30, fontFamily: FA, fontWeight: 800, fontSize: 30, color: INK, direction: 'rtl'}}>گوشی هوشمند</div>
							<div style={{position: 'absolute', top: 445, right: 30, fontFamily: FA, fontWeight: 900, fontSize: 34, color: CORAL, direction: 'rtl'}}>{fa('۲۹٬۹۰۰٬۰۰۰')} تومان</div>
							<div style={{position: 'absolute', bottom: 40, left: 30, right: 30, height: 74, borderRadius: 22, background: GREEN, color: '#fff', fontFamily: FA, fontWeight: 900, fontSize: 34, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>خرید</div>
						</Phone>
					</div>
				</Pop>
			</At>
			<At x={830} y={330}>
				<div style={{transformOrigin: '50% 0%', transform: `rotate(${swing + 8}deg)`}}>
					<Pop at={at + 0.25} from={0.2}>
						<div style={{width: 6, height: 70, background: '#B9AFA4', margin: '0 auto'}} />
						<div style={{background: CORAL, color: '#fff', fontFamily: FA, fontWeight: 900, fontSize: 40, padding: '14px 26px 18px', borderRadius: 18, boxShadow: '0 16px 30px rgba(232,112,90,0.4)'}}>فروش</div>
					</Pop>
				</div>
			</At>
		</>
	);
};

/* ---------- 6. دوره آموزشی ---------- */
export const GCourse: React.FC<GP> = ({k, dur}) => {
	const t = useT();
	const at = k(49) - 0.15;
	const pb = prog(t, at + 0.3, dur, (x) => x);
	const rows = ['معرفی دوره', 'اولین قدم', 'ساخت محصول', 'فروش'];
	return (
		<>
			<At x={290} y={150}>
				<Tag at={0.1}>محصول دیجیتال</Tag>
			</At>
			<At x={540} y={540}>
				<Pop at={at} from={0.5} rot={6}>
					<Card w={920} h={600}>
						<div style={{position: 'absolute', left: 30, top: 30, width: 540, height: 400, borderRadius: 28, background: 'linear-gradient(150deg,#2A2D33,#121315)', overflow: 'hidden'}}>
							<div style={{position: 'absolute', inset: 0, background: 'radial-gradient(circle at 70% 30%, rgba(232,112,90,0.5), transparent 60%)'}} />
							<div style={{position: 'absolute', left: '50%', top: '50%', transform: `translate(-50%,-50%) scale(${1 + 0.06 * Math.sin(t * 6)})`}}>
								<Play s={130} />
							</div>
							<div style={{position: 'absolute', right: 24, bottom: 22, fontFamily: FA, fontWeight: 900, fontSize: 44, color: '#fff', direction: 'rtl'}}>دوره آموزشی</div>
						</div>
						<div style={{position: 'absolute', left: 30, top: 460, width: 540, height: 14, borderRadius: 10, background: '#EEE9E3'}}>
							<div style={{width: `${pb * 100}%`, height: '100%', borderRadius: 10, background: CORAL}} />
						</div>
						<div style={{position: 'absolute', left: 30, top: 500, fontFamily: FA, fontWeight: 700, fontSize: 30, color: MUTED, direction: 'rtl'}}>{fa(Math.round(1240 + pb * 380))} دانشجو</div>
						<div style={{position: 'absolute', right: 30, top: 30, width: 300, display: 'flex', flexDirection: 'column', gap: 18}}>
							{rows.map((r, i) => {
								const on = t > at + 0.35 + i * 0.35;
								return (
									<div key={i} style={{direction: 'rtl', display: 'flex', alignItems: 'center', gap: 14, padding: '18px 18px', borderRadius: 20, background: on ? '#FFF1EC' : '#F7F5F2', opacity: prog(t, at + 0.2 + i * 0.08, 0.3)}}>
										<div style={{width: 40, height: 40, borderRadius: 20, background: on ? CORAL : '#DDD7D0', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 26, fontWeight: 900}}>{on ? '✓' : fa(i + 1)}</div>
										<div style={{fontFamily: FA, fontWeight: 700, fontSize: 30, color: INK}}>{r}</div>
									</div>
								);
							})}
						</div>
					</Card>
				</Pop>
			</At>
		</>
	);
};

/* ---------- 7. پادکست ---------- */
export const GPodcast: React.FC<GP> = ({k, dur}) => {
	const t = useT();
	const ty = k(60) - 0.1;
	return (
		<>
			<At x={300} y={300}>
				<Pop at={ty} rot={-14} from={0.3}>
					<div style={{transform: 'rotate(-8deg)'}}>
						<Card w={420} h={260} r={32} style={{background: '#16171A'}}>
							<div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
								<Play s={110} bg="#fff" fg="#16171A" />
							</div>
							<div style={{position: 'absolute', bottom: 18, right: 24, fontFamily: FA, fontWeight: 900, fontSize: 36, color: '#fff'}}>یوتیوب</div>
							<div style={{position: 'absolute', bottom: 0, left: 0, height: 8, width: `${prog(t, ty, 2, (x) => x) * 100}%`, background: '#FF4D4D'}} />
						</Card>
					</div>
				</Pop>
			</At>
			<At x={600} y={560}>
				<Pop at={0.03} from={0.5} rot={6}>
					<Card w={760} h={440}>
						<div style={{position: 'absolute', right: 40, top: 40, display: 'flex', alignItems: 'center', gap: 26, direction: 'rtl'}}>
							<div style={{width: 150, height: 150, borderRadius: 34, background: 'linear-gradient(150deg,#FFE3D8,#F5A98B)', display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
								<Mic s={90} />
							</div>
							<div>
								<div style={{fontFamily: FA, fontWeight: 900, fontSize: 64, color: INK}}>پادکست</div>
								<div style={{fontFamily: FA, fontWeight: 600, fontSize: 32, color: MUTED}}>قسمت {fa(12)} · محصول دیجیتال</div>
							</div>
						</div>
						<div style={{position: 'absolute', left: 40, right: 40, top: 240, height: 110, display: 'flex', alignItems: 'center', gap: 8}}>
							{Array.from({length: 40}).map((_, i) => {
								const h = 18 + Math.abs(Math.sin(t * 7 + i * 0.6) * Math.sin(i * 1.7 + t * 2)) * 88;
								const played = i / 40 < prog(t, 0, dur, (x) => x);
								return <div key={i} style={{flex: 1, height: h, borderRadius: 6, background: played ? CORAL : '#E5DFD8'}} />;
							})}
						</div>
						<div style={{position: 'absolute', left: 40, bottom: 34, fontFamily: FA, fontWeight: 700, fontSize: 28, color: MUTED}}>{fa('۱۲:۴۰')}</div>
					</Card>
				</Pop>
			</At>
			<At x={790} y={860}>
				<Tag at={k(66) - 0.1}>محصول دیجیتال</Tag>
			</At>
		</>
	);
};

/* ---------- 8. دو سال ---------- */
export const GYears: React.FC<GP> = ({k}) => {
	const t = useT();
	const t2 = k(78);
	const p = prog(t, 0.15, Math.max(0.6, t2 - 0.15 + 0.6), eio);
	const R = 220;
	const C = 2 * Math.PI * R;
	const chips = ['تحقیق', 'ساخت', 'تست'];
	return (
		<>
			<At x={540} y={480}>
				<Pop at={0.02} from={0.5}>
					<div style={{position: 'relative', width: 560, height: 560}}>
						<svg width={560} height={560} style={{position: 'absolute'}}>
							<circle cx={280} cy={280} r={R} fill="#fff" stroke="#EEE9E3" strokeWidth={34} />
							<circle cx={280} cy={280} r={R} fill="none" stroke={CORAL} strokeWidth={34} strokeLinecap="round" strokeDasharray={`${C * p} ${C}`} transform="rotate(-90 280 280)" />
						</svg>
						<div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center'}}>
							<div style={{fontFamily: NASKH, fontWeight: 700, fontSize: 230, lineHeight: 1, ...coralText}}>{fa(Math.min(2, Math.floor(p * 2.001)))}</div>
							<div style={{fontFamily: FA, fontWeight: 900, fontSize: 64, color: INK, marginTop: -10}}>سال</div>
						</div>
					</div>
				</Pop>
			</At>
			{chips.map((c, i) => (
				<At key={i} x={[880, 180, 860][i]} y={[230, 470, 760][i]}>
					<Pop at={k(80) - 0.1 + i * 0.18} from={0.3} rot={i % 2 ? -10 : 10}>
						<div style={{fontFamily: FA, fontWeight: 800, fontSize: 38, color: '#fff', background: INK, padding: '10px 28px 14px', borderRadius: 18, boxShadow: '0 14px 30px rgba(0,0,0,0.2)'}}>{c}</div>
					</Pop>
				</At>
			))}
		</>
	);
};

/* ---------- 9. بدون مرز ---------- */
export const GBoundless: React.FC<GP> = ({k}) => {
	const t = useT();
	const tb = k(88) - 0.1;
	const fl = useFloat(8, 0.9);
	return (
		<At x={540} y={500 + fl}>
			<Pop at={0.04} from={0.5} rot={-6}>
				<Card w={880} h={560} r={56} style={{background: 'linear-gradient(140deg,#0E6E43 0%,#1FA463 60%,#3BCB80 100%)'}}>
					<svg width={880} height={560} style={{position: 'absolute', left: -180, top: 0, opacity: 0.25}}>
						<g transform={`translate(330,280) rotate(${t * 12})`}>
							<circle r={250} fill="none" stroke="#fff" strokeWidth={4} />
							{[-0.66, -0.33, 0, 0.33, 0.66].map((y, i) => (
								<ellipse key={i} rx={250 * Math.sqrt(1 - y * y)} ry={18} cy={y * 250} fill="none" stroke="#fff" strokeWidth={3} />
							))}
							{[0.25, 0.55, 0.85].map((x, i) => (
								<ellipse key={'m' + i} rx={250 * x} ry={250} fill="none" stroke="#fff" strokeWidth={3} />
							))}
						</g>
					</svg>
					<div style={{position: 'absolute', right: 60, top: 70, direction: 'rtl'}}>
						<div style={{fontFamily: FA, fontWeight: 900, fontSize: 150, color: '#fff', lineHeight: 1.1, transform: `scale(${0.85 + 0.15 * prog(t, tb, 0.4)})`, transformOrigin: '100% 50%'}}>بدون مرز</div>
						<div style={{fontFamily: FA, fontWeight: 700, fontSize: 44, color: 'rgba(255,255,255,0.92)', marginTop: 10}}>آموزش‌های جدید</div>
					</div>
					<div style={{position: 'absolute', right: 60, bottom: 60}}>
						<Pop at={k(91) - 0.1} from={0.4}>
							<div style={{display: 'flex', alignItems: 'center', gap: 16, background: '#fff', borderRadius: 100, padding: '12px 30px 16px', direction: 'rtl'}}>
								<div style={{width: 22, height: 22, borderRadius: 11, background: '#FF3B30', boxShadow: `0 0 0 ${6 + Math.sin(t * 8) * 5}px rgba(255,59,48,0.25)`}} />
								<div style={{fontFamily: FA, fontWeight: 900, fontSize: 38, color: INK}}>شروع شد</div>
							</div>
						</Pop>
					</div>
				</Card>
			</Pop>
		</At>
	);
};

/* ---------- 10. SaaS (full graphic, dark) ---------- */
export const GSaas: React.FC<GP> = ({k}) => {
	const t = useT();
	const tS = k(97) - 0.05;
	const letters = 'SaaS'.split('');
	const shown = Math.max(0, Math.min(4, Math.floor((t - tS) / 0.07) + 1));
	const words: [string, number][] = [
		['Software', k(99)],
		['as a', k(100)],
		['Service', k(102)],
	];
	const glow = prog(t, tS, 0.3);
	return (
		<>
			<div style={{position: 'absolute', inset: 0, background: `radial-gradient(circle at 50% 42%, rgba(232,112,90,${0.35 * glow}) 0%, rgba(0,0,0,0) 55%)`}} />
			<At x={540} y={300}>
				<div style={{fontFamily: FA, fontWeight: 700, fontSize: 48, color: 'rgba(255,255,255,0.6)', opacity: prog(t, 0.05, 0.3), direction: 'rtl', whiteSpace: 'nowrap'}}>اصطلاحاً بهش میگن</div>
			</At>
			<At x={540} y={700}>
				<div style={{fontFamily: SERIF, fontStyle: 'italic', fontWeight: 900, fontSize: 300, color: '#fff', whiteSpace: 'nowrap', transform: `scale(${t > tS ? 1 + 0.15 * Math.exp(-(t - tS) * 6) : 1})`, textShadow: `0 0 60px rgba(232,112,90,${0.6 * glow})`}}>
					{letters.slice(0, t >= tS ? shown : 0).join('')}
					<span style={{opacity: Math.sin(t * 12) > 0 && t < tS + 0.9 ? 1 : 0, color: CORAL, fontStyle: 'normal'}}>|</span>
				</div>
			</At>
			<At x={540} y={1060}>
				<div style={{display: 'flex', gap: 30, direction: 'ltr', whiteSpace: 'nowrap'}}>
					{words.map(([w, at], i) => (
						<Pop key={i} at={at - 0.08} from={0.5} y={40}>
							<div style={{fontFamily: SERIF, fontStyle: 'italic', fontWeight: 800, fontSize: 86, color: '#fff'}}>
								{i === 1 ? (
									<>
										<span style={{color: CORAL2}}>a</span>s <span style={{color: CORAL2}}>a</span>
									</>
								) : (
									<>
										<span style={{color: CORAL2}}>{w[0]}</span>
										{w.slice(1)}
									</>
								)}
							</div>
						</Pop>
					))}
				</div>
			</At>
			<At x={540} y={1200}>
				<div style={{fontFamily: FA, fontWeight: 800, fontSize: 52, color: 'rgba(255,255,255,0.85)', direction: 'rtl', whiteSpace: 'nowrap', opacity: prog(t, k(102) + 0.25, 0.4)}}>نرم‌افزار به‌عنوان سرویس</div>
			</At>
		</>
	);
};

/* ---------- 11. نرم‌افزار ---------- */
export const GSoftware: React.FC<GP> = ({k}) => {
	const t = useT();
	const tw = k(106) - 0.2;
	const lines = [0.7, 0.45, 0.85, 0.6, 0.35, 0.75, 0.5, 0.65];
	const cols = [CORAL, '#6C8CFF', GREEN, '#B07CFF', CORAL, GREEN, '#6C8CFF', CORAL];
	return (
		<>
			<At x={540} y={500}>
				<Pop at={0.03} from={0.5} rot={-5}>
					<Card w={900} h={620} style={{background: '#17181B'}}>
						<div style={{height: 64, background: '#222327', display: 'flex', alignItems: 'center', gap: 14, paddingLeft: 26}}>
							{['#FF5F57', '#FEBC2E', '#28C840'].map((c) => (
								<div key={c} style={{width: 22, height: 22, borderRadius: 11, background: c}} />
							))}
							<div style={{marginLeft: 'auto', marginRight: 30, fontFamily: FA, fontWeight: 700, fontSize: 28, color: '#9b9ea6'}}>my-saas.app</div>
						</div>
						<div style={{position: 'absolute', left: 40, top: 110, right: 280}}>
							{lines.map((w, i) => {
								const p = prog(t, tw + i * 0.16, 0.25, (x) => x);
								return (
									<div key={i} style={{display: 'flex', gap: 12, marginBottom: 26, paddingLeft: (i % 3) * 40}}>
										<div style={{height: 22, width: 30, borderRadius: 6, background: '#3a3c42', opacity: p > 0 ? 1 : 0}} />
										<div style={{height: 22, width: `${w * 100 * p}%`, borderRadius: 6, background: cols[i]}} />
									</div>
								);
							})}
						</div>
						<div style={{position: 'absolute', right: 40, top: 120, width: 210, display: 'flex', flexDirection: 'column', gap: 20}}>
							{[0, 1, 2].map((i) => (
								<div key={i} style={{height: 120, borderRadius: 20, background: '#222327', display: 'flex', alignItems: 'flex-end', gap: 8, padding: 16, opacity: prog(t, tw + 0.6 + i * 0.2, 0.3)}}>
									{[0.4, 0.7, 0.5, 0.9, 0.65].map((h, j) => (
										<div key={j} style={{flex: 1, height: `${h * 100 * prog(t, tw + 0.7 + i * 0.2 + j * 0.05, 0.4)}%`, borderRadius: 4, background: j === 3 ? CORAL : '#4a4d55'}} />
									))}
								</div>
							))}
						</div>
					</Card>
				</Pop>
			</At>
			<At x={900} y={220}>
				<Pop at={0.25} from={0.3}>
					<div style={{background: '#fff', borderRadius: 40, padding: 14, boxShadow: '0 20px 40px rgba(0,0,0,0.2)'}}>
						<Gear s={110} color={CORAL} rot={t * 120} />
					</div>
				</Pop>
			</At>
			<At x={260} y={880}>
				<Tag at={k(106) - 0.05} color={INK}>نرم‌افزارِ خودت</Tag>
			</At>
		</>
	);
};

/* ---------- 12. نرم‌افزار ← خدمات را می‌فروشد ---------- */
export const GFlow: React.FC<GP> = ({k}) => {
	const t = useT();
	const tSv = k(113) - 0.15;
	const tSell = k(115);
	const ap = prog(t, 0.2, 0.6, eio);
	return (
		<>
			<At x={830} y={460}>
				<Pop at={0.02} from={0.4}>
					<Card w={300} h={300} r={60} style={{background: '#17181B'}}>
						<div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10}}>
							<Gear s={130} color={CORAL} rot={t * 140} />
							<div style={{fontFamily: FA, fontWeight: 900, fontSize: 40, color: '#fff'}}>نرم‌افزار</div>
						</div>
					</Card>
				</Pop>
			</At>
			<svg width={1080} height={1010} style={{position: 'absolute', left: 0, top: 0}}>
				<path d="M660,460 L430,460" stroke={INK} strokeWidth={10} strokeDasharray="18 16" strokeDashoffset={-t * 120} opacity={ap} strokeLinecap="round" />
				<path d="M440,430 L405,460 L440,490" fill="none" stroke={INK} strokeWidth={10} strokeLinecap="round" strokeLinejoin="round" opacity={ap} />
			</svg>
			<At x={250} y={460}>
				<Pop at={tSv} from={0.4} rot={8}>
					<Card w={330} h={330} r={60}>
						<div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 14}}>
							<Briefcase s={130} />
							<div style={{fontFamily: FA, fontWeight: 900, fontSize: 48, color: INK}}>خدمات</div>
						</div>
					</Card>
				</Pop>
			</At>
			<At x={370} y={320}>
				<Pop at={tSv + 0.3} from={0.2} damping={9}>
					<Check s={100} />
				</Pop>
			</At>
			<At x={540} y={800}>
				<Pop at={tSv + 0.2} from={0.5}>
					<div style={{fontFamily: FA, fontWeight: 900, fontSize: 46, color: '#fff', background: GREEN, padding: '12px 34px 16px', borderRadius: 100, direction: 'rtl', boxShadow: '0 16px 30px rgba(31,164,99,0.35)'}}>
						فروش خودکار · {fa('۲۴/۷')}
					</div>
				</Pop>
			</At>
			{Array.from({length: 5}).map((_, i) => {
				const p = prog(t, tSv + 0.5 + i * 0.12, 0.7, eio);
				return p > 0 && p < 1 ? (
					<div key={i} style={{position: 'absolute', left: 250 + Math.sin(i * 2) * 60 - 30, top: 380 - p * 300, opacity: 1 - p}}>
						<Coin s={60} spin={Math.cos(t * 10 + i)} />
					</div>
				) : null;
			})}
		</>
	);
};

export const GRAPHICS: Record<string, React.FC<GP>> = {
	service: GService,
	coins: GCoins,
	coins2: (p) => <GCoins {...p} seed="z" />,
	sparkle: GSparkle,
	product: GProduct,
	chart: GChart,
	two: GTwo,
	phone: GPhone,
	course: GCourse,
	podcast: GPodcast,
	years: GYears,
	boundless: GBoundless,
	saas: GSaas,
	software: GSoftware,
	flow: GFlow,
};
export {GOLD, eo};
