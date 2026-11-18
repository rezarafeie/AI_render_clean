import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {Fonts, useFonts, clamp, lerp, seg, eo, eo5, eio, back, rnd, fa, Jaraqe, blinkAt, sparkPath} from './lib';

const FPS = 30, W = 1080, H = 1920;
const C = {bg: '#f2eee5', ink: '#171512', grey: '#b9b3a6', mid: '#8b8579', acc: '#e8590c', jar: '#f7a600', dark: '#141414', green: '#3f8f5b', blue: '#4b7bd1'};
export const STORY_DUR = 47;
export const STORY_EV: {t: number; k: string; g?: number}[] = [];
const ev = (t: number, k: string, g = 0.6) => STORY_EV.push({t, k, g});
const GY = 1500, MX = 110;

const T = {term: 0, once: 4.6, dict: 9.4, s1: 15.2, s2: 21.2, s3: 27.0, s4: 33.4, hi: 38.6, moral: 43.2};
for (let i = 0; i < 16; i++) ev(0.55 + i * 0.13, 'key', 0.5);
ev(3.0, 'drop', 0.7); ev(4.3, 'whoosh', 0.6); ev(5.9, 'swell', 0.5); ev(9.4, 'whoosh', 0.5); ev(13.6, 'pop', 0.6);
[T.s1, T.s2, T.s3, T.s4].forEach((t) => { ev(t - 0.25, 'whoosh', 0.5); ev(t + 0.2, 'tick', 0.6); });
ev(T.s1 + 1.2, 'scan', 0.5); ev(T.s2 + 2.9, 'pop', 0.6); ev(T.s3 + 3.9, 'ding', 0.6);
[0, 1, 2, 3, 4, 5].forEach((i) => ev(T.s4 + 1.2 + i * 0.22, 'pop', 0.5));
ev(T.hi - 0.2, 'whoosh', 0.5); ev(T.hi + 1.5, 'ding', 0.5); ev(T.moral, 'swell', 0.6);

const Wipe: React.FC<{p: number; style?: React.CSSProperties; children: React.ReactNode}> = ({p, style, children}) => (
	<div style={{...style, clipPath: `inset(-20% 0 -30% ${(1 - clamp(p)) * 100}%)`}}>{children}</div>
);
const Words: React.FC<{text: string; t: number; t0: number; gap?: number; style?: React.CSSProperties; hi?: Record<string, string>}> = ({text, t, t0, gap = 0.09, style, hi = {}}) => (
	<div style={{direction: 'rtl', ...style}}>
		{text.split(' ').map((w, i) => {
			const u = clamp((t - t0 - i * gap) / 0.3);
			return (
				<span key={i} style={{display: 'inline-block', marginLeft: '0.26em', opacity: u, transform: `translateY(${(1 - eo5(u)) * 26}px)`, color: hi[w.replace(/[،.؛]/g, '')]}}>
					{w}
				</span>
			);
		})}
	</div>
);
const Step: React.FC<{t: number; n: string; a: string; b: string; sub: string; out: number}> = ({t, n, a, b, sub, out}) => {
	const o = 1 - seg(t, out - 0.3, out);
	const bu = eo5(seg(t, 0.45, 0.9));
	return (
		<div style={{position: 'absolute', right: MX, left: MX, top: 500, direction: 'rtl', opacity: o}}>
			<div style={{fontFamily: 'Vaz', fontWeight: 500, fontSize: 30, color: C.acc, opacity: seg(t, 0, 0.2)}}>{n}</div>
			<div style={{fontFamily: 'Pey', fontWeight: 900, fontSize: 118, lineHeight: 1.5, color: C.ink, whiteSpace: 'nowrap', marginTop: -6}}>
				<span style={{display: 'inline-block', opacity: seg(t, 0.1, 0.3), transform: `translateY(${(1 - eo5(seg(t, 0.1, 0.5))) * 40}px)`}}>{a}</span>{' '}
				<span style={{display: 'inline-block', color: bu < 0.99 ? C.grey : C.ink, opacity: seg(t, 0.35, 0.55), transform: `translateY(${(1 - bu) * 40}px) rotate(${(1 - bu) * -4}deg)`}}>{b}</span>
			</div>
			<div style={{fontFamily: 'Vaz', fontWeight: 500, fontSize: 31, color: C.mid, marginTop: 4, opacity: seg(t, 0.9, 1.2)}}>{sub}</div>
		</div>
	);
};

export const Story: React.FC = () => {
	useFonts();
	const f = useCurrentFrame();
	const t = f / FPS;

	// ---------- mascot path ----------
	let jx = 540, jy = GY, squash = 0, look = 0, walk = 0, happy = false, js = 1.7, rot = 0;
	if (t < T.once) {
		const d = t - 3.0;
		jx = 250; js = 1.5;
		const gy = 1010;
		if (d < 0) jy = -200;
		else if (d < 0.35) jy = lerp(-100, gy, d / 0.35 * (d / 0.35));
		else { jy = gy - Math.abs(Math.sin((d - 0.35) * 9)) * 60 * Math.exp(-(d - 0.35) * 4.5); squash = 0.28 * Math.exp(-(d - 0.35) * 9); }
	} else if (t < T.dict) {
		const u = seg(t, T.once, T.once + 0.5);
		jx = lerp(250, 240, u); jy = lerp(1010, GY, eio(u)); js = lerp(1.5, 1.7, u);
		const w = seg(t, 5.8, 8.6);
		jx = lerp(240, 860, eio(w)); walk = w > 0 && w < 1 ? t * 3 : 0; look = w > 0 && w < 1 ? 1 : 0;
	} else if (t < T.s1) {
		jx = 860; look = t > 12.6 ? -0.6 : 0; happy = t > 13.6 && t < 14.6;
		const hop = seg(t, 13.6, 14.0); jy = GY - Math.sin(hop * Math.PI) * 50;
	} else if (t < T.s2) {
		const u = eio(seg(t, T.s1 - 0.0, T.s1 + 0.7)); jx = lerp(860, 540, u); walk = u > 0 && u < 1 ? t * 3 : 0; look = Math.sin(t * 2.2) * 0.8;
	} else if (t < T.s3) {
		jx = 540; squash = 0.05 + Math.sin(t * 2) * 0.03; look = -0.3;
		rot = seg(t, T.s2 + 2.7, T.s2 + 3.1) * 360 * (1 - seg(t, T.s2 + 3.1, T.s2 + 3.11));
	} else if (t < T.s4) {
		const u = eio(seg(t, T.s3, T.s3 + 0.6)); jx = lerp(540, 300, u); walk = u > 0 && u < 1 ? t * 3 : 0; look = 0.7;
		happy = t > T.s3 + 4.0; const hop = seg(t, T.s3 + 3.9, T.s3 + 4.3); jy = GY - Math.sin(hop * Math.PI) * 60;
	} else if (t < T.hi) {
		const u = eio(seg(t, T.s4, T.s4 + 0.6)); jx = lerp(300, 540, u); walk = u > 0 && u < 1 ? t * 3 : 0;
	} else {
		jx = 540; const hop = seg(t, T.hi + 1.4, T.hi + 1.8); jy = GY - Math.sin(hop * Math.PI) * 70; happy = t > T.hi + 1.4 && t < T.hi + 2.6;
		if (t > T.moral) { const u = eio(seg(t, T.moral, T.moral + 0.8)); jy = lerp(GY, 1330, u); happy = t > T.moral + 1.6; }
	}

	// ---------- background ----------
	const circ = eio(seg(t, 4.15, 4.75));
	const dark = t < 4.75;
	const groundOn = seg(t, 4.7, 5.3) * (1 - seg(t, T.moral, T.moral + 0.5));

	// ---------- terminal ----------
	const prompt = 'خودت رو معرفی کن';
	const typed = clamp(Math.floor((t - 0.5) / 0.13), 0, prompt.length);
	const tf = typed / prompt.length;

	// ---------- dict ----------
	const dU = eio(seg(t, T.dict, T.dict + 0.8));
	const titleOut = 1 - seg(t, T.s1 - 0.4, T.s1 - 0.05);
	const sweep = seg(t, 5.8, 7.1);

	const st = (k: number) => t - k;
	return (
		<AbsoluteFill style={{background: C.dark}}>
			<Fonts />
			{/* terminal */}
			{dark && (
				<AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 45%, #1f1f1f 0%, #101010 75%)'}}>
					<div style={{position: 'absolute', right: 120, top: 890, direction: 'rtl', fontFamily: 'Vaz', fontWeight: 500, fontSize: 50, color: '#e9e6df', whiteSpace: 'nowrap', display: 'flex', alignItems: 'center'}}>
						<span style={{color: '#7c7c7c', marginLeft: 22, fontFamily: 'VazL'}}>‹</span>
						<span style={{position: 'relative', display: 'inline-block'}}>
							<span style={{visibility: 'hidden'}}>{prompt}</span>
							<span style={{position: 'absolute', right: 0, top: 0, clipPath: `inset(-20% 0 -20% ${(1 - tf) * 100}%)`}}>{prompt}</span>
							{(t < 2.7 || Math.floor(t * 2.5) % 2 === 0) && t < 4.1 && <span style={{position: 'absolute', right: `calc(${tf * 100}% + 6px)`, top: 12, width: 22, height: 52, background: '#e9e6df'}} />}
						</span>
					</div>
				</AbsoluteFill>
			)}
			{/* cream world */}
			<AbsoluteFill style={{background: `radial-gradient(ellipse at 50% 40%, #f7f4ec 0%, ${C.bg} 70%, #e9e4d8 100%)`, clipPath: t < 4.8 ? `circle(${circ * 2300}px at 250px 950px)` : undefined, opacity: t < 4.15 ? 0 : 1}}>
				{/* once upon */}
				{t >= T.once && t < T.s1 && (
					<>
						<Wipe p={seg(t, 5.0, 5.7)} style={{position: 'absolute', right: MX + 10, top: lerp(690, 300, dU), fontFamily: 'Typo', fontSize: 62, color: C.mid, direction: 'rtl', opacity: (1 - dU) * titleOut}}>روزی روزگاری، یک پیام…</Wipe>
						<div style={{position: 'absolute', right: MX, top: lerp(800, 330, dU), direction: 'rtl', fontFamily: 'Pey', fontWeight: 900, fontSize: lerp(148, 104, dU), lineHeight: 1.6, whiteSpace: 'nowrap', opacity: seg(t, 5.7, 5.9) * titleOut, transformOrigin: '100% 50%'}}>
							<span style={{color: '#d9d4c8'}}>ادیتور جی‌پی‌تی</span>
							<span style={{position: 'absolute', right: 0, top: 0, color: C.ink, clipPath: `inset(-20% 0 -30% ${(1 - eio(sweep)) * 100}%)`}}>ادیتور جی‌پی‌تی</span>
						</div>
					</>
				)}
				{t >= T.dict && t < T.s1 && (
					<div style={{position: 'absolute', right: MX, left: MX, top: 520, direction: 'rtl', opacity: titleOut}}>
						<div style={{fontFamily: 'Vaz', fontWeight: 500, fontSize: 27, color: C.mid, opacity: seg(t, T.dict + 0.6, T.dict + 0.9), letterSpacing: 1}}>اِ · دی · تور · جی · پی · تی &nbsp;&nbsp; <span style={{color: C.acc}}>اسم</span></div>
						<div style={{height: 2, background: C.ink, opacity: 0.18, marginTop: 22, width: `${eo5(seg(t, T.dict + 0.7, T.dict + 1.3)) * 100}%`}} />
						<Words text="تدوینگری که با حرف‌زدن" t={t} t0={T.dict + 1.3} style={{fontFamily: 'Pey', fontWeight: 400, fontSize: 64, lineHeight: 1.7, color: C.ink, marginTop: 34}} />
						<Words text="کار می‌کند؛ از یک پیام" t={t} t0={T.dict + 1.8} style={{fontFamily: 'Pey', fontWeight: 400, fontSize: 64, lineHeight: 1.7, color: C.ink}} />
						<Words text="تا ویدیوی آماده." t={t} t0={T.dict + 2.4} style={{fontFamily: 'Pey', fontWeight: 400, fontSize: 64, lineHeight: 1.7, color: C.ink}} />
						<div style={{position: 'absolute', left: 0, top: 8, fontFamily: 'Vaz', fontWeight: 500, fontSize: 24, color: C.green, opacity: seg(t, T.dict + 3.0, T.dict + 3.3)}}>✓ {fa(47)} ثانیه</div>
					</div>
				)}
				{/* steps */}
				{t >= T.s1 - 0.05 && t < T.s2 && <Step t={st(T.s1)} n="یک." a="اول،" b="می‌بینم." sub="ویدیو، عکس، لینک محصول؛ هر چه بدهی" out={T.s2 - T.s1} />}
				{t >= T.s2 && t < T.s3 && <Step t={st(T.s2)} n="دو." a="بعد،" b="فکر می‌کنم." sub="قلاب، برش‌ها، استوری‌بورد؛ قبل از هر رندر" out={T.s3 - T.s2} />}
				{t >= T.s3 && t < T.s4 && <Step t={st(T.s3)} n="سه." a="بعد،" b="می‌سازم." sub="کپشن، موشن، رنگ و صدا؛ تا خروجی نهایی" out={T.s4 - T.s3} />}
				{t >= T.s4 && t < T.hi && <Step t={st(T.s4)} n="چهار." a="و چند نفر" b="می‌شوم." sub="هر کار، موتور خودش را دارد" out={T.hi - T.s4} />}

				<svg width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
					{/* ground */}
					<line x1={MX} x2={MX + (W - 2 * MX) * eo5(groundOn)} y1={GY} y2={GY} stroke={C.ink} strokeWidth={2.5} opacity={groundOn > 0 ? 1 : 0} />
					{/* dict arrow */}
					{t >= T.dict + 3.2 && t < T.s1 && (() => {
						const L = 620, u = eo5(seg(t, T.dict + 3.2, T.dict + 4.1));
						return (
							<g opacity={titleOut}>
								<path d="M470,1075 C800,1075 1010,1160 930,1385" fill="none" stroke={C.acc} strokeWidth={3} strokeDasharray={`${L} ${L}`} strokeDashoffset={L * (1 - u)} />
								{u > 0.97 && <path d="M912,1362 L930,1390 L952,1366" fill="none" stroke={C.acc} strokeWidth={3} />}
								{t > 13.6 && <text x={780} y={1430} fontFamily="Vaz" fontWeight={500} fontSize={30} fill={C.acc} direction="rtl">سلام.</text>}
							</g>
						);
					})()}
					{/* step 1: reading */}
					{t >= T.s1 + 0.9 && t < T.s2 && (() => {
						const lt = t - T.s1 - 0.9, o = clamp(lt / 0.3) * (1 - seg(t, T.s2 - 0.35, T.s2 - 0.05));
						const scroll = lt * 150;
						const cards = [0, 1, 2, 3, 4, 5];
						const scanX = 540;
						return (
							<g opacity={o}>
								<text x={W - MX} y={880} fontFamily="Vaz" fontWeight={500} fontSize={24} fill={C.mid} direction="rtl" textAnchor="start">در حال دیدن…</text>
								<text x={MX} y={880} fontFamily="Vaz" fontWeight={500} fontSize={24} fill={C.ink} textAnchor="end" direction="rtl">{fa(Math.min(124, Math.floor(lt * 34)))} کلمه · {fa(Math.min(48, Math.floor(lt * 13)))} ثانیه</text>
								<clipPath id="rd"><rect x={MX} y={900} width={W - 2 * MX} height={380} /></clipPath>
								<g clipPath="url(#rd)">
									{cards.map((i) => {
										const x = W - 380 - i * 300 + scroll;
										const read = x + 130 > scanX ? 1 : 0;
										const kind = i % 3;
										return (
											<g key={i} transform={`translate(${x},920)`} opacity={read ? 0.42 : 1}>
												<rect width={270} height={340} rx={14} fill="#fffdf8" stroke="#ddd6c7" strokeWidth={2} />
												<text x={250} y={34} fontFamily="Vaz" fontWeight={500} fontSize={15} fill={C.mid} direction="rtl" textAnchor="start">{['ویدیو.mp4', 'رونوشت', 'محصول.jpg'][kind]}</text>
												{kind === 0 && <>
													<rect x={20} y={54} width={230} height={150} rx={8} fill="#2a2724" />
													<path d="M120,105 l36,24 l-36,24 z" fill="#fffdf8" />
													{Array.from({length: 26}).map((_, k) => <rect key={k} x={22 + k * 8.8} y={262 - rnd(i * 31 + k) * 34} width={5} height={rnd(i * 31 + k) * 68 + 6} rx={2} fill={k % 7 === 0 ? C.acc : C.ink} opacity={0.75} />)}
												</>}
												{kind === 1 && Array.from({length: 9}).map((_, k) => <rect key={k} x={250 - (90 + rnd(i * 7 + k) * 130)} y={62 + k * 29} width={90 + rnd(i * 7 + k) * 130} height={10} rx={5} fill={[C.ink, C.blue, C.green, C.acc][k % 4]} opacity={k % 4 === 0 ? 0.8 : 0.6} />)}
												{kind === 2 && <>
													<rect x={20} y={54} width={230} height={190} rx={8} fill="#efe7d6" />
													<circle cx={135} cy={150} r={52} fill={C.jar} opacity={0.85} />
													<rect x={130} y={266} width={120} height={10} rx={5} fill={C.ink} opacity={0.8} /><rect x={170} y={292} width={80} height={10} rx={5} fill={C.acc} opacity={0.7} />
												</>}
											</g>
										);
									})}
									<rect x={scanX - 3} y={900} width={6} height={380} fill={C.acc} opacity={0.75} />
									<rect x={scanX} y={900} width={70} height={380} fill={C.acc} opacity={0.1} />
								</g>
								<path d={`M${scanX},1285 L${jx},${GY - 150}`} stroke={C.acc} strokeWidth={2} strokeDasharray="4 8" opacity={0.7} />
							</g>
						);
					})()}
					{/* step 2: thinking → storyboard */}
					{t >= T.s2 + 0.9 && t < T.s3 && (() => {
						const lt = t - T.s2 - 0.9, o = clamp(lt / 0.3) * (1 - seg(t, T.s3 - 0.35, T.s3 - 0.05));
						const m = eio(seg(lt, 0.9, 1.9));
						const sb = eio(seg(lt, 2.1, 2.9));
						const nodes = [[540, 930], [330, 1070], [540, 1070], [750, 1070], [240, 1215], [420, 1215], [660, 1215], [840, 1215]];
						const edges = [[0, 1], [0, 2], [0, 3], [1, 4], [1, 5], [3, 6], [3, 7]];
						const pos = nodes.map(([x, y], i) => [lerp(540 + (rnd(i + 3) - 0.5) * 760, x, m), lerp(1060 + (rnd(i + 11) - 0.5) * 330 + Math.sin(lt * 2 + i) * 14 * (1 - m), y, m)]);
						const hot = [0, 1, 5];
						return (
							<g opacity={o}>
								<g opacity={1 - sb}>
									{edges.map(([a, b], i) => {
										const u = seg(lt, 1.2 + i * 0.09, 1.6 + i * 0.09);
										const isHot = hot.includes(a) && hot.includes(b);
										return <line key={i} x1={pos[a][0]} y1={pos[a][1]} x2={lerp(pos[a][0], pos[b][0], u)} y2={lerp(pos[a][1], pos[b][1], u)} stroke={isHot && lt > 1.9 ? C.acc : C.ink} strokeWidth={isHot && lt > 1.9 ? 4 : 2.5} />;
									})}
									{pos.map(([x, y], i) => <circle key={i} cx={x} cy={y} r={i === 0 ? 20 : 15} fill={hot.includes(i) && lt > 1.9 ? C.acc : C.bg} stroke={hot.includes(i) && lt > 1.9 ? C.acc : C.ink} strokeWidth={3} />)}
								</g>
								{sb > 0 && [0, 1, 2, 3, 4, 5].map((i) => {
									const u = back(clamp((lt - 2.1 - i * 0.07) / 0.4));
									const x = W - MX - 270 - (i % 3) * 295, y = 905 + Math.floor(i / 3) * 195;
									const hi = i === 0;
									return (
										<g key={i} transform={`translate(${x + 135},${y + 85}) scale(${u}) translate(-135,-85)`} opacity={clamp((lt - 2.1 - i * 0.07) / 0.15)}>
											<rect width={270} height={170} rx={12} fill={hi ? C.ink : '#fffdf8'} stroke={hi ? C.ink : '#d8d1c2'} strokeWidth={2} />
											<text x={250} y={34} fontFamily="Vaz" fontWeight={500} fontSize={17} fill={hi ? C.jar : C.mid} direction="rtl" textAnchor="start">{fa(i + 1)} · {['قلاب', 'معرفی', 'نکته', 'مثال', 'جمع‌بندی', 'دعوت'][i]}</text>
											<rect x={20} y={56} width={230} height={9} rx={4.5} fill={hi ? '#fff' : C.ink} opacity={0.8} />
											<rect x={90} y={80} width={160} height={9} rx={4.5} fill={hi ? '#fff' : C.ink} opacity={0.4} />
											<rect x={20} y={128} width={(230 * [0.6, 0.9, 0.75, 0.8, 0.55, 0.4][i])} height={16} rx={5} fill={hi ? C.jar : C.grey} />
										</g>
									);
								})}
								{[0, 1, 2].map((i) => { const u = (lt * 0.8 + i * 0.33) % 1; return <circle key={i} cx={jx + 44 + i * 6} cy={GY - 170 - u * 90} r={5 + u * 7} fill="none" stroke={C.ink} strokeWidth={2} opacity={(1 - u) * (1 - sb)} />; })}
							</g>
						);
					})()}
					{/* step 3: building */}
					{t >= T.s3 + 0.9 && t < T.s4 && (() => {
						const lt = t - T.s3 - 0.9, o = clamp(lt / 0.3) * (1 - seg(t, T.s4 - 0.35, T.s4 - 0.05));
						const px = MX, py = 890, pw = W - 2 * MX, ph = 420;
						const rend = seg(lt, 2.3, 3.0);
						const tracks = [{n: 'ویدیو', c: '#5d5a55', clips: [[0, 0.3], [0.31, 0.62], [0.63, 1]]}, {n: 'کپشن', c: C.jar, clips: [[0.02, 0.2], [0.22, 0.45], [0.5, 0.7], [0.73, 0.97]]}, {n: 'موشن', c: '#7d8cff', clips: [[0.1, 0.28], [0.56, 0.86]]}, {n: 'صدا', c: '#58b28a', clips: [[0, 1]]}];
						const ph2 = seg(lt, 0.3, 2.2);
						const frames = Math.floor(seg(lt, 2.5, 3.9) * 1410);
						return (
							<g opacity={o}>
								<rect x={px + 6} y={py + 12} width={pw} height={ph} rx={22} fill="#000" opacity={0.12} style={{filter: 'blur(14px)'}} />
								<rect x={px} y={py} width={pw} height={ph} rx={22} fill="#181818" />
								{[0, 1, 2].map((i) => <circle key={i} cx={px + 34 + i * 22} cy={py + 30} r={6} fill="#3a3a3a" />)}
								<text x={px + pw / 2} y={py + 37} fontFamily="Vaz" fontWeight={500} fontSize={19} fill="#8a8a8a" textAnchor="middle" direction="rtl">{rend > 0.5 ? 'رندر' : 'تایم‌لاین'}</text>
								<g opacity={1 - rend}>
									{tracks.map((tr, i) => (
										<g key={i}>
											<text x={px + pw - 26} y={py + 105 + i * 76} fontFamily="Vaz" fontWeight={500} fontSize={20} fill="#9a9a9a" direction="rtl" textAnchor="start">{tr.n}</text>
											<rect x={px + 26} y={py + 76 + i * 76} width={pw - 150} height={48} rx={8} fill="#222" />
											{tr.clips.map(([a, b], k) => {
												const u = eo5(clamp((lt - 0.2 - i * 0.28 - k * 0.14) / 0.4));
												const x1 = px + 26 + (pw - 150) * (1 - b), w = (pw - 150) * (b - a) - 6;
												return <rect key={k} x={x1 + w * (1 - u)} y={py + 80 + i * 76} width={w * u} height={40} rx={7} fill={tr.c} />;
											})}
										</g>
									))}
									<line x1={px + 26 + (pw - 150) * (1 - ph2)} x2={px + 26 + (pw - 150) * (1 - ph2)} y1={py + 62} y2={py + 390} stroke="#fff" strokeWidth={2.5} />
								</g>
								<g opacity={rend}>
									<text x={px + pw - 60} y={py + 150} fontFamily="VazL" fontWeight={500} fontSize={30} fill="#eaeaea" textAnchor="end">$ render --final</text>
									<rect x={px + 60} y={py + 200} width={pw - 120} height={16} rx={8} fill="#2b2b2b" />
									<rect x={px + 60 + (pw - 120) * (1 - frames / 1410)} y={py + 200} width={(pw - 120) * (frames / 1410)} height={16} rx={8} fill={C.jar} />
									<text x={px + pw - 60} y={py + 275} fontFamily="Vaz" fontWeight={500} fontSize={26} fill="#9a9a9a" direction="rtl" textAnchor="start">{fa(frames)} از {fa(1410)} فریم</text>
									{frames >= 1410 && <text x={px + 60} y={py + 275} fontFamily="Vaz" fontWeight={500} fontSize={26} fill="#6fd39b" direction="rtl" textAnchor="end">✓ آماده · ۱۰۸۰×۱۹۲۰</text>}
									{frames >= 1410 && <text x={px + pw - 60} y={py + 340} fontFamily="Vaz" fontWeight={500} fontSize={22} fill="#777" direction="rtl" textAnchor="start">صدا تراز شد · کپشن‌ها روی کلمه · خروجی پریمیر</text>}
								</g>
							</g>
						);
					})()}
					{/* step 4: multiply */}
					{t >= T.s4 + 0.9 && t < T.hi && (() => {
						const lt = t - T.s4 - 0.9, o = 1 - seg(t, T.hi - 0.35, T.hi - 0.05);
						const names = ['تدوین', 'موشن‌گرافیک', 'اکسپلینر', 'دوبله', 'کلیپ‌یاب', 'اینستاگرام'];
						return (
							<g opacity={o}>
								{names.map((n, i) => {
									const u = clamp((lt - 0.3 - i * 0.22) / 0.45);
									if (u <= 0) return null;
									const x = W - MX - 140 - (i % 3) * 290, y = 1010 + Math.floor(i / 3) * 215;
									const cx = lerp(540, x, eo5(u)), cy = lerp(GY, y, eo5(u)) - Math.sin(u * Math.PI) * 90;
									return (
										<g key={i}>
											<Jaraqe x={cx} y={cy} s={1.25} col={C.jar} blink={blinkAt(t, 2.2, i * 0.37)} squash={u >= 1 ? Math.max(0, Math.sin((lt - i * 0.22) * 5)) * 0.05 : 0} />
											<text x={x} y={y + 46} fontFamily="Vaz" fontWeight={500} fontSize={25} fill={C.ink} textAnchor="middle" direction="rtl" opacity={seg(u, 0.8, 1)}>{n}</text>
										</g>
									);
								})}
								<text x={MX} y={GY + 60} fontFamily="Vaz" fontWeight={500} fontSize={28} fill={C.acc} direction="rtl" textAnchor="end" opacity={seg(lt, 1.9, 2.2)}>× {fa(Math.min(6, Math.max(1, Math.floor((lt - 0.3) / 0.22) + 1)))}</text>
							</g>
						);
					})()}
					{/* moral arc */}
					{t >= T.moral && <circle cx={W + 120} cy={-460} r={eo5(seg(t, T.moral, T.moral + 0.9)) * 900} fill={C.dark} />}
					<Jaraqe x={jx} y={jy} s={js} col={C.jar} blink={blinkAt(t)} squash={squash} look={look} walk={walk} happy={happy} rot={rot} />
				</svg>

				{/* hi */}
				{t >= T.hi && t < T.moral && (
					<div style={{position: 'absolute', left: 0, right: 0, top: 690, textAlign: 'center', direction: 'rtl', opacity: 1 - seg(t, T.moral - 0.35, T.moral - 0.05)}}>
						<Wipe p={seg(t, T.hi + 0.2, T.hi + 0.7)} style={{fontFamily: 'Typo', fontSize: 78, color: C.mid}}>سلام، من</Wipe>
						<div style={{fontFamily: 'Pey', fontWeight: 900, fontSize: 142, lineHeight: 1.5, color: C.ink, whiteSpace: 'nowrap', transform: `translateY(${(1 - eo5(seg(t, T.hi + 0.6, T.hi + 1.2))) * 60}px)`, opacity: seg(t, T.hi + 0.6, T.hi + 0.8)}}>
							ادیتور جی‌پی‌تی<span style={{color: C.acc}}>.</span>
						</div>
						<div style={{display: 'inline-block', marginTop: 30, padding: '10px 28px', border: `2px solid #d6cfbf`, borderRadius: 40, fontFamily: 'VazL', fontWeight: 500, fontSize: 28, color: C.mid, opacity: seg(t, T.hi + 1.6, T.hi + 1.9), letterSpacing: 1}}>editor.rafiei.co</div>
					</div>
				)}
				{/* moral */}
				{t >= T.moral && (
					<div style={{position: 'absolute', left: 0, right: 0, top: 800, textAlign: 'center', direction: 'rtl'}}>
						<div style={{fontFamily: 'Vaz', fontWeight: 500, fontSize: 24, color: C.acc, letterSpacing: 6, opacity: seg(t, T.moral + 0.6, T.moral + 0.9)}}>نتیجهٔ قصه</div>
						<Words text="همه‌چیز با یک پیام" t={t} t0={T.moral + 0.9} style={{fontFamily: 'Pey', fontWeight: 400, fontSize: 88, lineHeight: 1.6, color: C.ink, marginTop: 26, textAlign: 'center'}} />
						<Words text="شروع می‌شود." t={t} t0={T.moral + 1.5} style={{fontFamily: 'Pey', fontWeight: 400, fontSize: 88, lineHeight: 1.6, color: C.ink, textAlign: 'center'}} />
					</div>
				)}
			</AbsoluteFill>
			{dark && t >= 3.0 && t < 4.75 && (
				<svg width={W} height={H} style={{position: 'absolute'}}><Jaraqe x={jx} y={jy} s={js} col={C.jar} blink={blinkAt(t)} squash={squash} /></svg>
			)}
		</AbsoluteFill>
	);
};
