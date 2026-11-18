import React from 'react';
import {AbsoluteFill, interpolate} from 'remotion';
import {Abs, Badge, G, GL, Hl, INK, MUTED, Pill, Pop, Txt, Words, fa, prog, useFloat, useScene, useSpr, useT, clamp, easeInOut, FONT} from './lib';
import {Defs, Bag, BlockHouse, CameraGlyph, Chip, Coins, Cube, Door, FeedCard, Hourglass, Pawn, Phone, Plane, Plate, Shadow, Sprout, Svg, Window} from './art';

const Full: React.FC<{children: React.ReactNode}> = ({children}) => <AbsoluteFill>{children}</AbsoluteFill>;

/* 01 تاریخ داره تکرار می‌شه */
const S01: React.FC = () => {
	const t = useT();
	const {cue} = useScene();
	const s = useSpr(0.05, 15);
	return (
		<Full>
			<svg width={900} height={900} style={{position: 'absolute', left: 90, top: 510, opacity: 0.9}}>
					<g transform={`translate(450,450) rotate(${t * 70}) scale(${s})`}>
						<circle r={360} fill="none" stroke={G} strokeWidth={6} strokeDasharray="14 22" opacity={0.35} />
						<path d="M 0,-300 A 300 300 0 1 1 -260,-150" fill="none" stroke={G} strokeWidth={10} strokeLinecap="round" opacity={0.6} />
						<path d="M -290,-200 L -262,-148 L -205,-170" fill="none" stroke={G} strokeWidth={10} strokeLinecap="round" strokeLinejoin="round" opacity={0.6} />
					</g>
				</svg>
			<Abs y={960}>
				<Words text="تاریخ داره" at={0.05} size={170} />
				<Words text="تکرار می‌شه" at={cue('تکرار', 0, -0.1)} size={170} hl={['تکرار']} />
			</Abs>
		</Full>
	);
};

/* 02 سال ۹۵ اینستاگرام — الان کجان؟ */
const S02: React.FC = () => {
	const t = useT();
	const {cue} = useScene();
	const fl = useFloat(12, 0.8);
	const ph = useSpr(0.15, 14);
	const year = Math.round(interpolate(prog(t, 0.1, 1.2), [0, 1], [1405, 1395]));
	return (
		<Full>
			<Abs y={330}>
				<Txt at={0} size={56} color={MUTED}>
					یادته اونایی که
				</Txt>
				<Txt at={cue('سال', 0, -0.1)} size={64} weight={800}>
					سالِ <span style={{color: G}}>{fa(year)}</span>
				</Txt>
				<Words text="اینستاگرام" at={cue('اینستاگرام', 0, -0.1)} size={150} />
				<Txt at={cue('جدی', 0, -0.05)} size={56} color={MUTED}>
					رو جدی گرفتن؟
				</Txt>
			</Abs>
			<div style={{position: 'absolute', left: 330, top: 820 + fl, transform: `translateY(${(1 - ph) * 500}px) rotate(${-6 + (1 - ph) * 10}deg)`}}>
				<Svg w={420} h={860}>
					<Shadow cx={210} y={900} w={380} />
					<Phone id="p2">
						<g transform="translate(210,250)">
							<CameraGlyph s={150} />
						</g>
						{[0, 1, 2, 3, 4, 5].map((k) => (
							<rect key={k} x={40 + (k % 3) * 116} y={420 + Math.floor(k / 3) * 116} width={108} height={108} rx={10} fill={['#cfe3d6', '#e2e0d6', '#d3dde3'][k % 3]} opacity={prog(t, 0.6 + k * 0.08, 0.3)} />
						))}
					</Phone>
				</Svg>
			</div>
			<Abs y={1700}>
				<Pill at={cue('الان', 0, -0.05)} size={52}>
					الان <Hl>کجان؟</Hl>
				</Pill>
			</Abs>
		</Full>
	);
};

/* 03 خبر بد — همون لحظه دوباره رسیده */
const S03: React.FC = () => {
	const t = useT();
	const {cue, dur} = useScene();
	const hs = useSpr(0.1, 14);
	return (
		<Full>
			<div style={{position: 'absolute', left: 70, top: 640, transform: `scale(${hs}) rotate(${(1 - hs) * -20}deg)`, transformOrigin: '50% 60%'}}>
				<Svg w={440} h={700}>
					<Hourglass p={prog(t, 0.2, dur * 1.25, (x) => x)} />
				</Svg>
			</div>
			<Abs x={1000} y={560} anchor="right">
				<Txt at={0} size={52} color={MUTED}>
					خبر بد اینه که
				</Txt>
				<Txt at={cue('دقیقاً', 0, -0.05)} size={52} color={MUTED}>
					دقیقاً
				</Txt>
				<Words text="همون" at={cue('همون', 0, -0.1)} size={170} style={{justifyContent: 'flex-end'}} />
				<Words text="لحظه" at={cue('لحظه', 0, -0.1)} size={170} style={{justifyContent: 'flex-end'}} hl={['لحظه']} />
				<Txt at={cue('دوباره', 0, -0.05)} size={56} weight={700}>
					دوباره رسیده
				</Txt>
			</Abs>
			<Abs y={1560}>
				<Pill at={cue('و تو', 0, -0.05)} size={46}>
					و تو داری باز از <Hl>کنارش رد</Hl> می‌شی
				</Pill>
			</Abs>
		</Full>
	);
};

/* stage tracker used in several scenes */
const Tracker: React.FC<{at: number; active?: number; strike?: number; y: number; stagger?: number}> = ({at, active, strike, y, stagger = 0.12}) => (
	<Abs y={y}>
		<div style={{display: 'flex', flexDirection: 'row-reverse', gap: 22, direction: 'ltr'}}>
			{[1, 2, 3, 4].map((n, i) => (
				<Badge key={n} n={fa(n)} at={at + i * stagger} active={active === n} strike={strike === n} dim={strike === n} />
			))}
		</div>
	</Abs>
);

/* 04 چهار مرحله — پول اصلی توی مرحله‌ی دومه */
const S04: React.FC = () => {
	const t = useT();
	const {cue} = useScene();
	const tMoney = cue('پولِ', 0, -0.15);
	const tMost = cue('ولی', 0, -0.1);
	const p1 = 1 - prog(t, tMoney - 0.1, 0.4);
	const cubeS = useSpr(tMoney, 13);
	const fl = useFloat(10, 0.9);
	// curve
	const curveP = prog(t, 0.6, 1.4, easeInOut);
	return (
		<Full>
			{/* Phase 1: four stages */}
			<AbsoluteFill style={{opacity: p1}}>
				<Abs y={470}>
					<Txt at={0} size={58} color={MUTED}>
						هر فرصت بزرگی
					</Txt>
					<Words text={`${fa(4)} مرحله داره`} at={cue('چهار', 0, -0.1)} size={160} hl={[fa(4)]} />
				</Abs>
				<Abs y={1150}>
					<svg width={900} height={520} style={{overflow: 'visible'}}>
						<path d="M60,470 C260,470 300,420 380,300 C460,170 560,80 840,70" fill="none" stroke={G} strokeWidth={10} strokeLinecap="round" strokeDasharray={1200} strokeDashoffset={1200 * (1 - curveP)} />
						<line x1={40} x2={880} y1={490} y2={490} stroke="#b9beb7" strokeWidth={3} />
						{[0, 1, 2, 3].map((k) => (
							<line key={k} x1={60 + k * 230} x2={60 + k * 230} y1={60} y2={490} stroke="#b9beb7" strokeWidth={2} strokeDasharray="6 10" opacity={prog(t, 0.6 + k * 0.15)} />
						))}
						<rect x={290} y={40} width={230} height={450} fill={G} opacity={0.12 * prog(t, cue('مرحله', 0, 0.3))} />
					</svg>
				</Abs>
				<Tracker at={cue('مرحله', 0, 0)} y={1510} />
			</AbsoluteFill>
			{/* Phase 2: money in stage 2 */}
			<AbsoluteFill style={{opacity: 1 - p1}}>
				<div style={{position: 'absolute', left: 290, top: 380 + fl, transform: `scale(${cubeS})`, transformOrigin: '50% 80%'}}>
					<Svg w={500} h={560}>
						<circle cx={250} cy={300} r={240} fill="none" stroke="#7f877f" strokeWidth={3} strokeDasharray="8 12" transform={`rotate(${t * 20} 250 300)`} />
						<Shadow cx={250} y={545} w={330} o={0.3} />
						<Cube x={250} y={380} s={300} />
						<Coins x={250} y={360} n={12} at={tMoney + 0.15} />
					</Svg>
				</div>
				<Abs y={1300}>
					<Txt at={tMoney} size={56} color={MUTED}>
						پولِ اصلی توی
					</Txt>
					<Words text="مرحله‌ی دومه" at={cue('مرحله', 0, -0.1)} size={150} hl={['دومه']} />
				</Abs>
				<Abs y={1640}>
					<Pill at={tMost} size={44}>
						بیشتر آدما وقتی می‌رسن که <Hl>مرحله‌ی چهارمه</Hl>
					</Pill>
				</Abs>
			</AbsoluteFill>
		</Full>
	);
};

/* 05 مرحله‌ی اول — عکس غذا؟ */
const S05: React.FC = () => {
	const t = useT();
	const {cue} = useScene();
	const plate = useSpr(0.1, 14);
	const phone = useSpr(0.35, 15);
	const tPhoto = cue('عکسِ', 0, -0.1);
	const tLaugh = cue('مسخره', 0, -0.05);
	const flash = clamp(1 - Math.abs(t - tPhoto - 0.05) / 0.12);
	return (
		<Full>
			<Abs x={70} y={160} anchor="left">
				<div />
			</Abs>
			<div style={{position: 'absolute', left: 90, top: 330, transform: `scale(${plate})`}}>
				<Svg w={640} h={640}>
					<Plate cx={320} cy={320} r={300} />
				</Svg>
			</div>
			<div style={{position: 'absolute', left: 520, top: -60, transform: `translate(${(1 - phone) * 500}px, ${(1 - phone) * -300}px) rotate(${24 - phone * 6}deg)`}}>
				<Svg w={460} h={900}>
					<Phone id="p5" w={460} h={900}>
						<rect x={0} y={0} width={460} height={900} fill="#101211" />
						<g transform="translate(230,420) scale(0.62)">
							<Plate cx={0} cy={0} r={300} />
						</g>
						<circle cx={230} cy={800} r={42} fill="none" stroke="#fff" strokeWidth={6} />
						<circle cx={230} cy={800} r={32} fill="#fff" opacity={0.9} />
						<rect x={0} y={0} width={460} height={900} fill="#fff" opacity={flash * 0.9} />
					</Phone>
				</Svg>
			</div>
			{/* laughing bubbles */}
			{[
				[160, 1060, 0],
				[860, 1110, 1],
				[300, 1240, 2],
			].map(([x, y, i]) => (
				<div key={i} style={{position: 'absolute', left: x, top: y}}>
					<Pop at={tLaugh + 0.2 + i * 0.15} damping={9}>
						<div style={{fontFamily: FONT, fontWeight: 800, fontSize: 40, color: MUTED, background: '#fff', padding: '10px 26px', borderRadius: 40, boxShadow: '0 10px 25px rgba(0,0,0,0.12)', transform: `rotate(${(i - 1) * 8}deg)`, direction: 'rtl'}}>
							{['هه!', 'جدی؟!', 'هاها'][i]}
						</div>
					</Pop>
				</div>
			))}
			<Abs x={1000} y={1400} anchor="right">
				<Badge n={fa(1)} at={0} style={{marginBottom: 20}} />
				<Txt at={cue('چند', 0, -0.1)} size={56} weight={700}>
					چند نفر شروع می‌کنن و
				</Txt>
				<Txt at={tLaugh - 0.1} size={56} weight={700}>
					بقیه <span style={{color: G}}>مسخره‌شون</span> می‌کنن
				</Txt>
			</Abs>
			<Abs y={1700}>
				<Words text="«عکسِ غذا؟»" at={tPhoto} size={140} />
			</Abs>
		</Full>
	);
};

/* 06 مرحله‌ی دوم — بی‌سروصدا جلو می‌افتن */
const S06: React.FC = () => {
	const t = useT();
	const {cue} = useScene();
	const tPage = cue('پیج', 0, -0.15);
	const tDay = cue('یه روز', 0, -0.1);
	const ph1 = 1 - prog(t, tPage - 0.15, 0.35);
	const ph2 = prog(t, tPage - 0.15, 0.35) * (1 - prog(t, tDay - 0.1, 0.35));
	const ph3 = prog(t, tDay - 0.1, 0.35);
	const sprout = prog(t, cue('بی‌سروصدا', 0, 0), 1.6, easeInOut);
	const bagS = useSpr(tPage, 12);
	const fl = useFloat(8, 1);
	const chart = prog(t, tDay + 0.6, 1.4, easeInOut);
	return (
		<Full>
			<AbsoluteFill style={{opacity: ph1}}>
				<Abs y={420}>
					<Badge n={fa(2)} at={0} active style={{marginBottom: 26}} />
					<Txt at={cue('همون', 0, -0.1)} size={54} color={MUTED}>
						همون چند نفر
					</Txt>
					<Words text="بی‌سروصدا" at={cue('بی‌سروصدا', 0, -0.1)} size={170} />
					<Txt at={cue('جلو', 0, -0.05)} size={56} weight={700}>
						جلو می‌افتن
					</Txt>
				</Abs>
				<div style={{position: 'absolute', left: 240, top: 900}}>
					<Svg w={600} h={600}>
						<Shadow cx={300} y={520} w={480} />
						<g transform="translate(300,430) skewX(-20) scale(1,0.45)">
							<rect x={-200} y={-300} width={400} height={600} rx={60} fill="#151817" />
							<rect x={-188} y={-288} width={376} height={576} rx={50} fill="#1f2422" />
						</g>
						<path d="M300,420 l-30,-20 l-20,10 M300,420 l35,-15 l15,18 M300,420 l-5,35" stroke="#555" strokeWidth={3} fill="none" opacity={sprout} />
						<Sprout p={sprout} x={300} y={425} s={1.1} />
					</Svg>
				</div>
				<div style={{position: 'absolute', left: 0, top: 1560, width: 1080, display: 'flex', justifyContent: 'center', gap: 24, direction: 'rtl'}}>
					<Pill at={cue('سرمایه', 0, -0.3)} size={44}>
						بدون <Hl>سرمایه</Hl>
					</Pill>
					<Pill at={cue('فالوور', 0, -0.3)} size={44} style={{marginTop: 40}}>
						بدون <Hl>فالوور</Hl>
					</Pill>
					<Pill at={cue('تجربه', 0, -0.3)} size={44}>
						بدون <Hl>تجربه</Hl>
					</Pill>
				</div>
			</AbsoluteFill>
			<AbsoluteFill style={{opacity: ph2}}>
				<Abs x={980} y={430} anchor="right">
					<Txt at={tPage} size={70} weight={800}>
						<span style={{color: G}}>←</span> پیج می‌زنن
					</Txt>
					<Txt at={cue('فروش', 0, -0.1)} size={70} weight={800}>
						<span style={{color: G}}>←</span> فروش راه می‌ندازن
					</Txt>
				</Abs>
				<div style={{position: 'absolute', left: 340, top: 900 + fl, transform: `scale(${bagS})`, transformOrigin: '50% 90%'}}>
					<Svg w={400} h={600}>
						<Bag x={-120} y={200} s={0.6} o={0.35} />
						<Bag x={520} y={160} s={0.55} o={0.3} />
						<Bag x={200} y={260} s={1} />
					</Svg>
				</div>
			</AbsoluteFill>
			<AbsoluteFill style={{opacity: ph3}}>
				<Abs y={480}>
					<Txt at={tDay} size={54} color={MUTED}>
						یه روز می‌بینی از همون
					</Txt>
					<Txt at={cue('عکسِ', 0, -0.1)} size={90} weight={900}>
						«عکسِ غذا»
					</Txt>
					<Words text="یه برند ساختن" at={cue('برند', 0, -0.25)} size={150} hl={['برند']} />
				</Abs>
				<Abs y={1250}>
					<svg width={760} height={520} style={{overflow: 'visible'}}>
						{[0, 1, 2, 3, 4, 5].map((k) => {
							const h = [70, 110, 150, 230, 330, 460][k] * prog(t, tDay + 0.3 + k * 0.12, 0.6);
							return <rect key={k} x={40 + k * 120} y={500 - h} width={84} height={h} rx={14} fill={k === 5 ? G : '#cdd3cc'} />;
						})}
						<path d="M60,440 L200,400 L320,360 L440,290 L560,190 L700,40" fill="none" stroke={G} strokeWidth={8} strokeLinecap="round" strokeDasharray={900} strokeDashoffset={900 * (1 - chart)} />
						<circle cx={700} cy={40} r={16} fill={G} opacity={chart} />
					</svg>
				</Abs>
			</AbsoluteFill>
		</Full>
	);
};

/* 07 مرحله‌ی سوم — هجوم میارن */
const S07: React.FC = () => {
	const t = useT();
	const {cue} = useScene();
	const tRush = cue('هجوم', 0, -0.2);
	const doorS = useSpr(0.1, 14);
	const people = [] as {x: number; y: number; d: number}[];
	for (let r = 0; r < 6; r++) for (let c = 0; c < 8; c++) people.push({x: c * 140 + 30 + (r % 2) * 70, y: 1420 + r * 95, d: (r * 8 + c) * 0.03});
	return (
		<Full>
			<Abs x={1000} y={470} anchor="right">
				<Badge n={fa(3)} at={0} style={{marginBottom: 20}} />
				<Txt at={cue('همه', 0, -0.1)} size={56} color={MUTED}>
					همه می‌فهمن و
				</Txt>
				<Words text="هجوم" at={tRush} size={180} style={{justifyContent: 'flex-end'}} />
				<Words text="میارن" at={tRush + 0.2} size={180} style={{justifyContent: 'flex-end'}} hl={['میارن']} />
			</Abs>
			<Abs x={250} y={720} anchor="center">
				<div style={{display: 'flex', flexDirection: 'column', gap: 18, alignItems: 'center'}}>
					<Pill at={cue('رقابت', 0, -0.1)} size={42}>
						رقابت <Hl>سنگین</Hl>
					</Pill>
					<Pill at={cue('دیده', 0, -0.1)} size={42} light>
						دیده‌شدن <b>سخت</b>
					</Pill>
				</div>
			</Abs>
			<svg width={1080} height={1920} style={{position: 'absolute', left: 0, top: 0}}>
				<Defs />
				<g transform={`translate(0,${(1 - doorS) * 400})`} opacity={doorS}>
					<Door x={560} y={1330} w={220} h={380} />
				</g>
				{people
					.sort((a, b) => a.y - b.y)
					.map((p, i) => {
						const go = prog(t, tRush + p.d, 2.5, (x) => x);
						const dx = (560 - p.x) * go * 0.45;
						const dy = (1330 - p.y) * go * 0.35;
						const app = prog(t, 0.2 + p.d * 0.6, 0.4);
						const bob = Math.abs(Math.sin(t * 9 + i)) * 10 * (go > 0 && go < 1 ? 1 : 0);
						const sc = 1.0 + (p.y - 1420) / 700;
						return (
							<g key={i} opacity={app} transform={`translate(0,${(1 - app) * 80})`}>
								<Pawn x={p.x + dx} y={p.y + dy - bob} s={sc} c={['#9c8c76', '#ab9b84', '#8e7f6b'][i % 3]} />
							</g>
						);
					})}
			</svg>
		</Full>
	);
};

/* 08 مرحله‌ی چهارم — دیر شده */
const S08: React.FC = () => {
	const t = useT();
	const {cue} = useScene();
	const ph = useSpr(0.2, 15);
	const tScroll = cue('اسکرول', 0, -0.2);
	const scroll = t > tScroll ? (t - tScroll) * 260 : 0;
	return (
		<Full>
			<Abs x={1000} y={520} anchor="right">
				<Badge n={fa(4)} at={0} style={{marginBottom: 20}} />
				<Txt at={cue('دیگه', 0, -0.1)} size={56} color={MUTED}>
					دیگه
				</Txt>
				<Words text="دیر" at={cue('دیر', 0, -0.15)} size={190} style={{justifyContent: 'flex-end'}} />
				<Words text="شده" at={cue('شده', 0, -0.15)} size={190} style={{justifyContent: 'flex-end'}} hl={['شده']} />
			</Abs>
			<Abs x={80} y={560} anchor="left">
				<Txt at={cue('بازار', 0, -0.1)} size={48} weight={700} color={MUTED}>
					بازار
				</Txt>
				<Txt at={cue('اشباع', 0, -0.1)} size={86} weight={900}>
					اشباع شده
				</Txt>
			</Abs>
			<div style={{position: 'absolute', left: 300, top: 860, transform: `translateY(${(1 - ph) * 700}px) rotate(${-8 + ph * 4}deg)`}}>
				<Svg w={480} h={980}>
					<Shadow cx={240} y={1000} w={440} />
					<Phone id="p8" w={480} h={980}>
						<g transform={`translate(0,${-(scroll % 470)})`}>
							{[0, 1, 2, 3, 4].map((k) => (
								<FeedCard key={k} x={40} y={90 + k * 470} w={400} seed={k + Math.floor(scroll / 470)} />
							))}
						</g>
					</Phone>
				</Svg>
			</div>
			<Abs y={1720}>
				<Pill at={cue('پیجِ', 0, -0.1)} size={40}>
					پیجِ همونایی رو دنبال می‌کنی که <Hl>مرحله‌ی دوم</Hl> اومده بودن
				</Pill>
			</Abs>
			<Abs y={1450}>
				<Pill at={tScroll} size={38} light>
					فقط اسکرول می‌کنی…
				</Pill>
			</Abs>
		</Full>
	);
};

/* 09 خبر خوب — هوش مصنوعی الان توی مرحله‌ی دومه */
const S09: React.FC = () => {
	const t = useT();
	const {cue} = useScene();
	const chipS = useSpr(cue('هوش', 0, -0.2), 13);
	const glow = prog(t, cue('مرحله', 0, -0.2), 0.6);
	return (
		<Full>
			<Abs y={360}>
				<Txt at={0} size={58} weight={800} color={G}>
					حالا خبرِ خوب:
				</Txt>
				<Txt at={cue('هوش', 0, -0.1)} size={60} color={MUTED}>
					هوش مصنوعی الان دقیقاً توی
				</Txt>
				<Words text="مرحله‌ی دومه" at={cue('مرحله', 0, -0.15)} size={160} hl={['دومه']} />
			</Abs>
			<div style={{position: 'absolute', left: 240, top: 820, transform: `scale(${chipS}) rotate(${(1 - chipS) * 30}deg)`}}>
				<Svg w={600} h={600}>
					<Chip cx={300} cy={300} s={210} glow={0.25 + 0.75 * glow} />
				</Svg>
			</div>
			<Tracker at={cue('مرحله', 0, 0.1)} active={t > cue('دومه', 0, 0) ? 2 : undefined} y={1560} stagger={0.08} />
		</Full>
	);
};

/* 10 سؤال می‌پرسن vs کسب‌وکار می‌سازن */
const S10: React.FC = () => {
	const t = useT();
	const {cue} = useScene();
	const tBuild = cue('ولی', 0, -0.1);
	const qS = useSpr(0.15, 11);
	const shift = prog(t, tBuild, 0.6);
	const fl = useFloat(14, 0.8);
	return (
		<Full>
			<Abs y={420}>
				<div style={{opacity: 1 - shift, position: 'absolute', display: 'flex', flexDirection: 'column', alignItems: 'center'}}>
					<Txt at={0} size={56} color={MUTED}>
						اکثرِ آدما هنوز فقط
					</Txt>
					<Words text="سؤال می‌پرسن" at={cue('سؤال', 0, -0.15)} size={130} />
				</div>
				<div style={{opacity: shift, position: 'absolute', display: 'flex', flexDirection: 'column', alignItems: 'center'}}>
					<Txt at={tBuild} size={56} color={MUTED}>
						ولی یه عده‌ی کم دارن باهاش
					</Txt>
					<Words text="کسب‌وکار می‌سازن" at={cue('کسب', 0, -0.15)} size={118} hl={['کسب‌وکار']} />
				</div>
			</Abs>
			{/* question mark */}
			<div
				style={{
					position: 'absolute',
					left: interpolate(shift, [0, 1], [330, 90]),
					top: 760 + fl,
					transform: `scale(${qS * interpolate(shift, [0, 1], [1, 0.62])})`,
					transformOrigin: '50% 50%',
					fontFamily: FONT,
					fontWeight: 900,
					fontSize: 560,
					lineHeight: 1,
					color: '#c9c6bf',
					textShadow: '6px 6px 0 #a9a69e, 12px 12px 0 #8f8c85, 30px 40px 50px rgba(0,0,0,0.25)',
					opacity: interpolate(shift, [0, 1], [1, 0.7]),
				}}
			>
				؟
			</div>
			<Abs x={interpolate(shift, [0, 1], [540, 250])} y={1500}>
				<Pill at={cue('سؤال', 0, 0.2)} size={42} light>
					فقط <b>سؤال</b> می‌پرسن
				</Pill>
			</Abs>
			<div style={{position: 'absolute', left: 470, top: 790, opacity: shift}}>
				<Svg w={420} h={520}>
					<BlockHouse x={60} y={500} at={cue('کسب', 0, -0.3)} bs={75} />
				</Svg>
			</div>
			<div style={{position: 'absolute', right: 70, top: 1440, display: 'flex', flexDirection: 'column', gap: 18, alignItems: 'flex-end'}}>
				<Pill at={cue('محتوا', 0, -0.1)} size={44}>
					<Hl>محتوا</Hl> تولید می‌کنن
				</Pill>
				<Pill at={cue('مشتری', 0, -0.35)} size={44}>
					برای <Hl>مشتری</Hl> کار می‌کنن
				</Pill>
			</div>
		</Full>
	);
};

/* 11 پنجره خیلی کوتاه‌تره */
const S11: React.FC = () => {
	const t = useT();
	const {cue, dur} = useScene();
	const tShort = cue('کوتاه', 0, -0.2);
	const open = prog(t, 0.2, 0.7, easeInOut) * (1 - 0.75 * prog(t, tShort + 0.2, 1.0, easeInOut));
	const ws = useSpr(0.05, 14);
	return (
		<Full>
			<Abs y={430}>
				<Txt at={0} size={58} color={MUTED}>
					فقط این بار
				</Txt>
				<Words text="پنجره" at={cue('پنجره', 0, -0.15)} size={170} />
				<Words text="خیلی کوتاه‌تره" at={tShort - 0.15} size={110} hl={['کوتاه‌تره']} />
			</Abs>
			<div style={{position: 'absolute', left: 190, top: 820, transform: `scale(${ws}) perspective(1000px) rotateY(-8deg)`}}>
				<Svg w={700} h={820}>
					<Shadow cx={350} y={860} w={640} o={0.3} />
					<Window open={open} cx={350} cy={420} w={520} h={680} />
				</Svg>
			</div>
			<Abs y={1700}>
				<div style={{width: 600, height: 14, borderRadius: 10, background: '#d4d8d2', overflow: 'hidden', opacity: prog(t, 0.3)}}>
					<div style={{width: `${100 * (1 - prog(t, 0.3, dur - 0.3, (x) => x))}%`, height: '100%', background: G, borderRadius: 10}} />
				</div>
			</Abs>
		</Full>
	);
};

/* 12 حالا تو بگو */
const S12: React.FC = () => {
	const t = useT();
	const {cue} = useScene();
	const tQ = cue('کدوم', 0, -0.1);
	const sweep = t > tQ ? Math.floor(((t - tQ) / 0.35) % 4) + 1 : 0;
	return (
		<Full>
			<Abs y={720}>
				<Words text="حالا تو بگو" at={0} size={150} hl={['تو']} />
				<Txt at={cue('توی', 0, -0.1)} size={58} weight={700} style={{marginTop: 30}}>
					توی موجِ اینستاگرام،
				</Txt>
				<Txt at={tQ} size={58} weight={700}>
					کدوم <span style={{color: G}}>مرحله</span> وارد شدی؟
				</Txt>
			</Abs>
			<Tracker at={cue('توی', 0, 0)} active={sweep || undefined} y={1180} stagger={0.1} />
			<Abs y={1420}>
				<svg width={120} height={120} style={{opacity: prog(t, tQ + 0.4), transform: `translateY(${Math.sin(t * 6) * 10}px)`}}>
					<path d="M60,10 L60,90 M30,62 L60,95 L90,62" stroke={G} strokeWidth={10} fill="none" strokeLinecap="round" strokeLinejoin="round" />
				</svg>
			</Abs>
		</Full>
	);
};

/* 13 فقط بنویس ۲ */
const S13: React.FC = () => {
	const t = useT();
	const {cue, dur} = useScene();
	const tWrite = cue('فقط', 0, -0.1);
	const tMap = cue('تا', 0, -0.1);
	const two = useSpr(cue('«', 0, 0), 9);
	const ring = prog(t, cue('«', 0, -0.1), 0.9, easeInOut);
	const ph2 = prog(t, tMap + 0.5, 0.45);
	const send = prog(t, dur - 1.7, 0.9, easeInOut);
	const card = useSpr(tMap + 0.5, 14);
	const route = prog(t, tMap + 0.4, 1.2, easeInOut);
	return (
		<Full>
			<AbsoluteFill style={{opacity: 1 - ph2}}>
				<Abs y={330}>
					<Txt at={0} size={52} color={MUTED}>
						اگه نمی‌خوای این بار هم
					</Txt>
				</Abs>
				<Abs y={460}>
					<Badge n={fa(4)} at={cue('چهارم', 0, -0.2)} strike dim />
				</Abs>
				<Abs y={640}>
					<Txt at={tWrite} size={72} weight={800}>
						فقط بنویس
					</Txt>
				</Abs>
				<svg width={620} height={620} style={{position: 'absolute', left: 230, top: 790}}>
						<circle cx={310} cy={310} r={280} fill="none" stroke={G} strokeWidth={5} strokeDasharray="12 14" strokeDashoffset={0} opacity={0.7} pathLength={1000} />
						<circle cx={310} cy={310} r={280} fill="none" stroke="#F3F3EF" strokeWidth={10} strokeDasharray={`${1760 * (1 - ring)} 1760`} transform="rotate(-90 310 310)" />
				</svg>
				<Abs y={1100}>
					<div style={{fontFamily: FONT, fontWeight: 900, fontSize: 480, color: G, lineHeight: 1, transform: `scale(${two}) translateY(20px)`, textShadow: '0 30px 60px rgba(23,132,79,0.3)'}}>{fa(2)}</div>
				</Abs>
			</AbsoluteFill>
			<AbsoluteFill style={{opacity: ph2}}>
				<Abs y={330}>
					<Txt at={tMap} size={54} color={MUTED}>
						تا نقشه‌ی ورود به مرحله‌ی دوم رو
					</Txt>
					<Txt at={cue('برات', 0, -0.1)} size={64} weight={800}>
						برات <span style={{color: G}}>بفرستم</span>
					</Txt>
				</Abs>
				<div
					style={{
						position: 'absolute',
						left: 190,
						top: 560,
						transform: `scale(${card * (1 - 0.82 * send)}) translate(${send * 900}px, ${-send * 1500}px) rotate(${send * -25}deg)`,
						opacity: 1 - prog(t, dur - 0.9, 0.3),
					}}
				>
					<div style={{width: 700, height: 860, background: '#fbfbf8', borderRadius: 40, boxShadow: '0 40px 90px rgba(0,0,0,0.22)', position: 'relative', overflow: 'hidden'}}>
						<svg width={700} height={860} style={{position: 'absolute'}}>
							{Array.from({length: 8}).map((_, i) => (
								<line key={i} x1={i * 100} x2={i * 100} y1={0} y2={860} stroke="#eceee9" strokeWidth={2} />
							))}
							{Array.from({length: 9}).map((_, i) => (
								<line key={i} y1={i * 100} y2={i * 100} x1={0} x2={700} stroke="#eceee9" strokeWidth={2} />
							))}
							<path d="M480,720 C300,700 180,620 260,520 C340,420 520,470 470,360 C430,270 300,300 330,220" fill="none" stroke={INK} strokeWidth={6} strokeDasharray="14 14" pathLength={1000} style={{strokeDasharray: `14 14`}} opacity={0.85} strokeDashoffset={0} clipPath="url(#rc)" />
							<clipPath id="rc">
								<rect x={0} y={860 - 860 * route} width={700} height={860} />
							</clipPath>
							<circle cx={480} cy={720} r={30} fill={INK} />
							<circle cx={470} cy={360} r={46} fill={G} opacity={prog(t, tMap + 0.9)} />
							<circle cx={470} cy={360} r={64} fill="none" stroke={G} strokeWidth={4} opacity={prog(t, tMap + 0.9) * (0.5 + 0.5 * Math.sin(t * 6))} />
							<g transform="translate(330,200)" opacity={prog(t, tMap + 1.2)}>
								<path d="M0,-50 C-28,-50 -40,-28 -40,-12 C-40,15 0,40 0,40 C0,40 40,15 40,-12 C40,-28 28,-50 0,-50 Z" fill={GL} />
								<circle cx={0} cy={-14} r={14} fill="#fff" />
							</g>
						</svg>
						<div style={{position: 'absolute', top: 50, width: '100%', textAlign: 'center', fontFamily: FONT, fontWeight: 900, fontSize: 52, color: INK, direction: 'rtl'}}>نقشه‌ی ورود به مرحله‌ی {fa(2)}</div>
						<div style={{position: 'absolute', left: 520, top: 690, fontFamily: FONT, fontWeight: 700, fontSize: 34, color: MUTED, direction: 'rtl'}}>تو اینجایی</div>
						<div style={{position: 'absolute', left: 160, top: 335, fontFamily: FONT, fontWeight: 800, fontSize: 38, color: G, direction: 'rtl', opacity: prog(t, tMap + 1)}}>ورود از اینجا</div>
						<div style={{position: 'absolute', left: 449, top: 328, fontFamily: FONT, fontWeight: 900, fontSize: 46, color: '#fff', opacity: prog(t, tMap + 0.9)}}>{fa(2)}</div>
						<div style={{position: 'absolute', left: 469, top: 696, fontFamily: FONT, fontWeight: 900, fontSize: 34, color: '#fff'}}>{fa(1)}</div>
					</div>
				</div>
				<svg width={1080} height={1920} style={{position: 'absolute', left: 0, top: 0, opacity: prog(t, dur - 1.0, 0.2)}}>
					<path d={`M200,1700 C400,1500 700,1400 ${200 + 700 * clamp((t - (dur - 1.0)) / 0.9)},${1700 - 1000 * clamp((t - (dur - 1.0)) / 0.9)}`} fill="none" stroke="#7d847d" strokeWidth={4} strokeDasharray="10 12" />
					<Plane x={200 + 700 * clamp((t - (dur - 1.0)) / 0.9)} y={1700 - 1000 * clamp((t - (dur - 1.0)) / 0.9)} rot={-35} s={1.3} />
				</svg>
				<Abs y={1720}>
					<Txt at={dur - 0.6} size={56} weight={800} color={G}>
						ارسال شد ✓
					</Txt>
				</Abs>
			</AbsoluteFill>
		</Full>
	);
};

export const SCENES: React.FC[] = [S01, S02, S03, S04, S05, S06, S07, S08, S09, S10, S11, S12, S13];
