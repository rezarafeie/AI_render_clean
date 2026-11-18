import React from 'react';
import {AbsoluteFill, Img, interpolate, staticFile} from 'remotion';
import usmap from './usmap.json';
import {
	ANTON, Arrow, CheckMark, CircleMark, Counter, CREAM, Cut, D, Disc, Enter, fa, Flash, Hl, INK, Label, MUST, Paper, Photo, prog, RED, Stamp, T, TEAL, Torn, TW, Type, Underline, useBoil, useSp, useT, Wipe, XMark, eio, eo, H, W, clamp,
} from './vox';

export type SP = {c: (w: string, occ?: number) => number; dur: number};
export const Ctx = React.createContext<SP>({c: () => 0, dur: 1});
const useS = () => React.useContext(Ctx);
const Abs: React.FC<{x: number; y: number; children: React.ReactNode; style?: React.CSSProperties}> = ({x, y, children, style}) => (
	<div style={{position: 'absolute', left: x, top: y, transform: 'translate(-50%,-50%)', ...style}}>{children}</div>
);

/* 01 — $1.2B hook */
const S01: React.FC = () => {
	const {c} = useS();
	const t = useT();
	return (
		<AbsoluteFill>
			<Paper />
			<Disc x={540} y={900} r={400} color={MUST} at={0} />
			<Disc x={830} y={560} r={130} color={TEAL} at={0.2} />
			<Abs x={540} y={290}>
				<Wipe at={0.02}>
					<T size={130}>آمازون</T>
				</Wipe>
			</Abs>
			<Abs x={540} y={420}>
				<Wipe at={c('سایتِ') - 0.1}>
					<T size={62} weight={500}>
						برای یه <Hl at={c('کفش') - 0.1}>سایتِ فروشِ کفش</Hl>
					</T>
				</Wipe>
			</Abs>
			<Enter at={0.15} from="down" x={560} y={1010} rot={-6} d={0.7}>
				<Cut src="money.png" w={780} />
			</Enter>
			<Enter at={c('کفش') - 0.15} from="pop" x={300} y={730} rot={9}>
				<Cut src="shoebox.png" w={430} />
			</Enter>
			<Abs x={540} y={1430}>
				<Counter at={c('یک') - 0.1} dur={c('دلار') - c('یک') + 0.2} to={1200000000} style={{fontSize: 118, color: INK, letterSpacing: 1}} />
			</Abs>
			<Underline x1={110} x2={970} y={1505} at={c('دلار')} />
			<Abs x={540} y={1580}>
				{t > c('دلار') && (
					<Wipe at={c('دلار')}>
						<T size={50} weight={500}>
							حدود {fa('۱.۲')} میلیارد دلار
						</T>
					</Wipe>
				)}
			</Abs>
		</AbsoluteFill>
	);
};

/* 02 — not a single shoe */
const S02: React.FC = () => {
	const {c} = useS();
	return (
		<AbsoluteFill>
			<Paper tex="grid" />
			<Abs x={540} y={330}>
				<Wipe at={c('روزِ') - 0.1}>
					<T size={120}>روزِ اول</T>
				</Wipe>
			</Abs>
			<Enter at={0} from="drop" x={540} y={930} rot={-3}>
				<Cut src="shoebox.png" w={820} />
			</Enter>
			<CircleMark cx={540} cy={930} rx={470} ry={360} at={c('حتی')} />
			<Stamp at={c('جفت') - 0.1} x={560} y={1450} rot={-8} size={92}>
				{fa(0)} جفت کفش
			</Stamp>
		</AbsoluteFill>
	);
};

/* 03 — 1999, Nick, boots */
const S03: React.FC = () => {
	const {c, dur} = useS();
	const t = useT();
	const tw = c('مردی') - 0.2;
	const walk = prog(t, tw, 2.6, (x) => x);
	const bob = Math.abs(Math.sin(t * 9)) * 10 * (walk > 0 && walk < 1 ? 1 : 0);
	return (
		<AbsoluteFill>
			<Paper />
			<Abs x={540} y={300}>
				<Type at={0.05} text="1999" cps={8} style={{fontSize: 230, color: INK, lineHeight: 1}} cursor={false} />
			</Abs>
			<Underline x1={290} x2={790} y={420} at={0.55} />
			<Abs x={540} y={500}>
				<Type at={c('سان‌فرانسیسکو') - 0.05} text="SAN FRANCISCO" cps={24} style={{fontSize: 46, color: RED, letterSpacing: 4}} />
			</Abs>
			<Enter at={tw} from="left" x={540} y={1030} rot={-3}>
				<Photo src="store.jpg" w={880} />
			</Enter>
			<div style={{position: 'absolute', left: interpolate(walk, [0, 1], [1250, 760]), top: 1080 - bob, transform: 'translate(-50%,-50%)', opacity: t > tw ? 1 : 0}}>
				<Cut src="walker.png" w={330} />
			</div>
			{t > c('نیک') - 0.1 && (
				<>
					<Arrow pts={[[330, 1460], [450, 1400], [640, 1260]]} at={c('نیک')} color={INK} />
					<Abs x={290} y={1530}>
						<Wipe at={c('نیک') - 0.05}>
							<Label size={52} rot={-3}>نیک سوینمِرن</Label>
						</Wipe>
					</Abs>
					<Abs x={300} y={1620}>
						<Type at={c('سوینمِرن')} text="Nick Swinmurn" cps={26} style={{fontSize: 34, color: INK}} cursor={false} />
					</Abs>
				</>
			)}
			<Enter at={c('بوت') - 0.15} from="pop" x={290} y={720} rot={-10}>
				<Cut src="boots.png" w={420} />
			</Enter>
			<Enter at={c('بوت') + 0.15} from="pop" x={500} y={640} rot={10}>
				<div style={{fontFamily: ANTON, fontSize: 170, color: RED, lineHeight: 1}}>?</div>
			</Enter>
			<Enter at={c('سایز') - 0.1} from="pop" x={830} y={1500} rot={4}>
				<Label size={56}>سایز</Label>
			</Enter>
			<XMark cx={830} cy={1500} s={70} at={c('سایز') + 0.1} />
			<Enter at={c('رنگِ') - 0.1} from="pop" x={830} y={1660} rot={-3}>
				<Label size={56}>رنگ</Label>
			</Enter>
			<XMark cx={830} cy={1660} s={70} at={c('رنگِ') + 0.1} />
		</AbsoluteFill>
	);
};

/* 04 — went to a shoe store */
const S04: React.FC = () => {
	const {c} = useS();
	return (
		<AbsoluteFill>
			<Paper tint="#F6D79A" tintOp={0.9} />
			<Disc x={180} y={420} r={260} color={RED} at={0.1} half rot={20} />
			<Enter at={0} from="right" x={540} y={850} rot={2}>
				<Photo src="store.jpg" w={940} />
			</Enter>
			<Enter at={0.2} from="left" x={860} y={1180} rot={0}>
				<Cut src="walker.png" w={250} />
			</Enter>
			<Abs x={540} y={1480}>
				<Wipe at={c('پیشنهادِ') - 0.15}>
					<T size={104}>
						یه <Hl at={c('عجیب') - 0.1} color={'#FFFFFF'}>پیشنهادِ عجیب</Hl>
					</T>
				</Wipe>
			</Abs>
			<Enter at={c('عجیب')} from="pop" x={170} y={1470} rot={-12}>
				<div style={{width: 130, height: 130, borderRadius: 65, background: RED, color: '#fff', fontFamily: ANTON, fontSize: 100, display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 10px 18px rgba(0,0,0,0.25)'}}>!</div>
			</Enter>
		</AbsoluteFill>
	);
};

/* 05 — the proposal */
const Polaroid: React.FC<{children: React.ReactNode; w?: number}> = ({children, w = 300}) => (
	<div style={{background: '#FBF8F1', padding: 14, paddingBottom: 54, width: w, boxShadow: '0 14px 22px rgba(40,30,15,0.3)'}}>
		<div style={{width: w, height: w * 0.8, background: '#DDD7CB', overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center'}}>{children}</div>
	</div>
);
const S05: React.FC = () => {
	const {c} = useS();
	const t = useT();
	const tShot = c('عکس') - 0.05;
	const tWeb = c('اینترنت') - 0.2;
	const tBuy = c('خرید') - 0.1;
	return (
		<AbsoluteFill>
			<Paper />
			<Enter at={0} from="pop" x={540} y={470} rot={-6}>
				<Cut src="camera.png" w={560} />
			</Enter>
			<Flash at={tShot} />
			{[0, 1, 2].map((i) => (
				<Enter key={i} at={tShot + 0.1 + i * 0.12} from="pop" x={[190, 880, 860][i]} y={[340, 300, 640][i]} rot={[-12, 10, -6][i]}>
					<Polaroid w={250}>
						<Img src={staticFile('img/' + ['boots.png', 'hands_shoe.png', 'boots.png'][i])} style={{width: 230, transform: i === 2 ? 'scaleX(-1)' : undefined}} />
					</Polaroid>
				</Enter>
			))}
			<Enter at={tWeb} from="down" x={540} y={1130} rot={1}>
				<div style={{position: 'relative'}}>
					<Cut src="crt.png" w={700} />
					{/* fake 1999 web page on the CRT screen */}
					<div style={{position: 'absolute', left: 105, top: 70, width: 360, height: 300, background: '#E9E4D6', transform: 'perspective(800px) rotateY(4deg)', overflow: 'hidden', opacity: prog(t, tWeb + 0.3, 0.3)}}>
						<div style={{background: '#2F4A7A', color: '#fff', fontFamily: TW, fontSize: 24, padding: '6px 10px'}}>shoesite.com</div>
						<div style={{display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, padding: 10}}>
							{Array.from({length: 6}).map((_, i) => (
								<div key={i} style={{background: '#fff', height: 100, border: '1px solid #bbb', display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: prog(t, tWeb + 0.4 + i * 0.08, 0.2)}}>
									<Img src={staticFile('img/boots.png')} style={{width: 90}} />
								</div>
							))}
						</div>
					</div>
				</div>
			</Enter>
			<Enter at={tBuy} from="pop" x={230} y={1500} rot={-6}>
				<Label bg={TEAL} color="#fff" size={54}>
					سفارش!
				</Label>
			</Enter>
			<Arrow pts={[[330, 1560], [480, 1640], [640, 1590]]} at={c('من') - 0.05} />
			<Enter at={c('قیمتِ') - 0.15} from="right" x={820} y={1530} rot={-8}>
				<Cut src="money.png" w={400} />
			</Enter>
			<Abs x={540} y={1760}>
				<Wipe at={c('کامل') - 0.15}>
					<T size={70}>
						<Hl at={c('کامل')}>قیمتِ کامل</Hl>
					</T>
				</Wipe>
			</Abs>
		</AbsoluteFill>
	);
};

/* 06 — no warehouse, no inventory, no capital */
const S06: React.FC = () => {
	const {c} = useS();
	const rows: [string, string][] = [
		['انبار', 'انبار'],
		['موجودی', 'موجودی'],
		['سرمایه‌ی', 'سرمایه'],
	];
	return (
		<AbsoluteFill>
			<Paper tex="grid" />
			<Enter at={0} from="up" x={540} y={560} rot={2}>
				<Photo src="shelf.jpg" w={800} />
			</Enter>
			<Enter at={0.1} from="down" x={540} y={1320} rot={-1.5}>
				<Torn w={820} h={760} seed="s6">
					<div style={{padding: '70px 80px', direction: 'rtl'}}>
						{rows.map(([w, label], i) => (
							<div key={i} style={{height: 112, display: 'flex', alignItems: 'center', fontFamily: D, fontWeight: 800, fontSize: 74, color: INK}}>
								{label}
							</div>
						))}
						<div style={{height: 2, background: '#cfc6b5', margin: '20px 0'}} />
						<div style={{height: 112, display: 'flex', alignItems: 'center', fontFamily: D, fontWeight: 800, fontSize: 74, color: TEAL}}>عکس + سایت</div>
					</div>
				</Torn>
			</Enter>
			{rows.map(([w], i) => (
				<XMark key={i} cx={320} cy={1065 + i * 112} s={42} at={c(w) - 0.05} />
			))}
			<CheckMark cx={300} cy={1470} s={44} at={c('عکس') - 0.05} />
			<Underline x1={480} x2={900} y={1515} at={c('سایت') - 0.05} color={TEAL} />
		</AbsoluteFill>
	);
};

/* 07 — dropshipping title */
const S07: React.FC = () => {
	const {c} = useS();
	const t = useT();
	const s = useSp(c('دراپ‌شیپینگ') - 0.25, 10, 0.7, 220);
	return (
		<AbsoluteFill>
			<Paper tint={RED} tintOp={1} />
			<Abs x={540} y={560}>
				<Wipe at={0.05}>
					<T size={66} weight={500} color={CREAM}>
						امروز اسمِ این مدل رو گذاشتیم
					</T>
				</Wipe>
			</Abs>
			{t > c('دراپ‌شیپینگ') - 0.25 && (
				<Abs x={540} y={960} style={{transform: `translate(-50%,-50%) scale(${interpolate(s, [0, 1], [1.8, 1])}) rotate(-3deg)`}}>
					<div style={{fontFamily: ANTON, fontSize: 230, lineHeight: 0.9, color: CREAM, textAlign: 'center', textShadow: '0 10px 0 rgba(0,0,0,0.15)'}}>
						DROP
						<br />
						SHIPPING
					</div>
				</Abs>
			)}
			<Abs x={540} y={1330}>
				<Wipe at={c('دراپ‌شیپینگ')}>
					<Label bg={INK} color={CREAM} size={74} rot={2}>
						دراپ‌شیپینگ
					</Label>
				</Wipe>
			</Abs>
			<Enter at={0.2} from="down" x={830} y={1620} rot={-10}>
				<Cut src="boxes.png" w={380} />
			</Enter>
		</AbsoluteFill>
	);
};

/* 08 — Zappos name + $1.6M */
const S08: React.FC = () => {
	const {c} = useS();
	const t = useT();
	const s = useSp(c('زاپوس') - 0.15, 10, 0.7, 220);
	const bar = prog(t, c('یک') - 0.1, 1.6, eio);
	return (
		<AbsoluteFill>
			<Paper />
			<Disc x={540} y={380} r={330} color={MUST} at={c('زاپوس') - 0.2} />
			{t > c('زاپوس') - 0.15 && (
				<Abs x={540} y={380} style={{transform: `translate(-50%,-50%) scale(${interpolate(s, [0, 1], [1.8, 1])})`}}>
					<div style={{fontFamily: ANTON, fontSize: 210, color: INK, lineHeight: 1}}>ZAPPOS</div>
				</Abs>
			)}
			<Abs x={540} y={640}>
				<Type at={c('ساپاتوس') - 0.2} text="ZAPATOS" cps={14} style={{fontSize: 96, color: RED}} />
			</Abs>
			<Abs x={540} y={740}>
				<Wipe at={c('یعنی') - 0.05}>
					<T size={52} weight={500}>
						اسپانیایی: «کفش»
					</T>
				</Wipe>
			</Abs>
			<Arrow pts={[[780, 640], [880, 560], [850, 470]]} at={c('ساپاتوس') + 0.4} color={RED} />
			<Enter at={c('کفش') - 0.2} from="pop" x={540} y={1000} rot={-5}>
				<Cut src="boots.png" w={460} />
			</Enter>
			<Abs x={540} y={1260}>
				<Wipe at={c('سالِ') - 0.1}>
					<T size={62}>سالِ اول</T>
				</Wipe>
			</Abs>
			<Abs x={540} y={1400}>
				<Counter at={c('یک') - 0.1} dur={c('فروخت') - c('یک')} to={1600000} style={{fontSize: 140, color: INK}} />
			</Abs>
			<div style={{position: 'absolute', left: 140, top: 1530, width: 800 * bar, height: 40, background: TEAL, transform: 'rotate(-1deg)'}} />
			<Abs x={540} y={1650}>
				<Type at={c('فروخت') - 0.1} text="FIRST-YEAR SALES" cps={26} style={{fontSize: 38, color: INK, letterSpacing: 3}} cursor={false} />
			</Abs>
		</AbsoluteFill>
	);
};

/* 09 — 2003: 25% from dropshipping, dropped */
const Pie: React.FC<{p: number; pull: number; crossAt: number}> = ({p, pull, crossAt}) => {
	const R = 300;
	const C = 2 * Math.PI * R;
	const a0 = -Math.PI / 2;
	const a1 = a0 + Math.PI / 2;
	const mid = (a0 + a1) / 2;
	const ox = Math.cos(mid) * pull * 120;
	const oy = Math.sin(mid) * pull * 120;
	return (
		<svg width={800} height={800} viewBox="-400 -400 800 800" style={{overflow: 'visible'}}>
			<circle r={R} fill={CREAM} stroke={INK} strokeWidth={8} strokeDasharray={C} strokeDashoffset={C * (1 - p)} />
			<g transform={`translate(${ox},${oy})`} opacity={p > 0.9 ? 1 : 0}>
				<path d={`M0,0 L${Math.cos(a0) * R},${Math.sin(a0) * R} A${R},${R} 0 0,1 ${Math.cos(a1) * R},${Math.sin(a1) * R} Z`} fill={RED} stroke={INK} strokeWidth={8} />
				<text x={Math.cos(mid) * R * 0.55} y={Math.sin(mid) * R * 0.55 + 30} textAnchor="middle" fontFamily={ANTON} fontSize={90} fill={CREAM}>
					25%
				</text>
			</g>
		</svg>
	);
};
const S09: React.FC = () => {
	const {c} = useS();
	const t = useT();
	const pp = prog(t, c('یک‌چهارمِ') - 0.3, 0.8, eio);
	const pull = prog(t, c('کنارش') - 0.1, 0.6, eo);
	return (
		<AbsoluteFill>
			<Paper tex="grid" />
			<Abs x={540} y={290}>
				<Type at={c('دو') - 0.1} text="2003" cps={8} style={{fontSize: 210, color: INK, lineHeight: 1}} cursor={false} />
			</Abs>
			<Abs x={540} y={460}>
				<Wipe at={c('تصمیمِ') - 0.1}>
					<T size={66}>
						یه <Hl at={c('عجیب') - 0.05}>تصمیمِ عجیب</Hl>
					</T>
				</Wipe>
			</Abs>
			<Abs x={540} y={1000}>
				<Pie p={pp} pull={pull} crossAt={0} />
			</Abs>
			<XMark cx={540 + 90} cy={1000 - 230 - pull * 80} s={90} at={c('گذاشتن') - 0.1} />
			<Abs x={540} y={1450}>
				<Wipe at={c('درآمدشون') - 0.2}>
					<Label size={58} rot={-2}>
						یک‌چهارمِ درآمد = دراپ‌شیپینگ
					</Label>
				</Wipe>
			</Abs>
			<Abs x={540} y={1620}>
				<Wipe at={c('کنارش') - 0.1}>
					<T size={74} color={RED}>
						کنارش گذاشتن!
					</T>
				</Wipe>
			</Abs>
		</AbsoluteFill>
	);
};

/* 10 — inaccurate stock, out of stock days later */
const S10: React.FC = () => {
	const {c} = useS();
	const t = useT();
	const days = c('چند') - 0.1;
	const dIdx = Math.min(3, Math.max(0, Math.floor((t - days) / 0.35) + 1));
	return (
		<AbsoluteFill>
			<Paper />
			<Enter at={0} from="left" x={560} y={640} rot={-2}>
				<Photo src="shelf.jpg" w={820} />
			</Enter>
			<Abs x={540} y={1060}>
				<Wipe at={c('دقیق') - 0.15}>
					<T size={64}>
						موجودیِ تأمین‌کننده: <Hl at={c('نبود') - 0.1}>نادقیق</Hl>
					</T>
				</Wipe>
			</Abs>
			{t > days && (
				<Enter at={days} from="pop" x={290} y={1380} rot={-6}>
					<div style={{position: 'relative', width: 280, height: 300}}>
						{[2, 1, 0].map((k) => (
							<div key={k} style={{position: 'absolute', left: k * 8, top: k * 8, width: 260, height: 280, background: '#FBF8F1', boxShadow: '0 8px 14px rgba(0,0,0,0.2)', borderTop: `44px solid ${RED}`}} />
						))}
						<div style={{position: 'absolute', left: 0, top: 60, width: 260, textAlign: 'center', fontFamily: D, fontWeight: 800, fontSize: 130, color: INK}}>{fa(dIdx)}</div>
						<div style={{position: 'absolute', left: 0, top: 220, width: 260, textAlign: 'center', fontFamily: D, fontWeight: 500, fontSize: 40, color: INK}}>روز بعد</div>
					</div>
				</Enter>
			)}
			<Stamp at={c('موجود') - 0.1} x={720} y={1390} rot={-12} size={84}>
				ناموجود
			</Stamp>
			<Abs x={720} y={1530}>
				<Type at={c('نیست') - 0.05} text="OUT OF STOCK" cps={28} style={{fontSize: 40, color: RED, letterSpacing: 3}} cursor={false} />
			</Abs>
		</AbsoluteFill>
	);
};

/* 11 — Tony Hsieh quote */
const S11: React.FC = () => {
	const {c} = useS();
	const lines: [string, React.ReactNode, string][] = [
		['پولِ', <>باید <Hl color={RED} at={c('آسون') - 0.05}>پولِ آسون</Hl> رو کنار می‌ذاشتیم،</>, 'آسون'],
		['موجودی', <>موجودی رو <Hl color={RED} at={c('خودمون') - 0.05}>خودمون</Hl> مدیریت می‌کردیم،</>, 'خودمون'],
		['ریسکش', <>و <Hl color={RED} at={c('ریسکش') + 0.05}>ریسکش</Hl> رو می‌پذیرفتیم.</>, 'ریسکش'],
	];
	return (
		<AbsoluteFill>
			<Paper tint="#2A2724" tintOp={1} />
			<Abs x={860} y={430}>
				<Enter at={0} from="pop" x={0} y={0} rot={0}>
					<div style={{fontFamily: ANTON, fontSize: 420, color: MUST, lineHeight: 1}}>“</div>
				</Enter>
			</Abs>
			<div style={{position: 'absolute', right: 70, top: 640, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 44}}>
				{lines.map(([w, node], i) => (
					<Wipe key={i} at={c(w) - 0.15} d={0.6}>
						<T size={56} color={CREAM} weight={800} style={{whiteSpace: 'nowrap'}}>
							<span style={{color: INK}} />
							<span style={{color: CREAM}}>{node}</span>
						</T>
					</Wipe>
				))}
			</div>
			<div style={{position: 'absolute', right: 90, top: 1240, width: 900, height: 3, background: 'rgba(243,236,223,0.3)'}} />
			<div style={{position: 'absolute', right: 90, top: 1290}}>
				<Wipe at={0.1}>
					<T size={56} color={CREAM} weight={700}>
						— تونی شیه، مدیرعاملِ زاپوس
					</T>
				</Wipe>
			</div>
			<div style={{position: 'absolute', right: 90, top: 1380}}>
				<Type at={c('مدیرعاملِ')} text="Tony Hsieh · CEO, Zappos" cps={26} style={{fontSize: 36, color: MUST}} cursor={false} />
			</div>
			<div style={{position: 'absolute', left: 90, top: 1560, opacity: 0.6}}>
				<Type at={c('گفت') + 0.5} text="Bloomberg, 2010" cps={26} style={{fontSize: 30, color: CREAM}} cursor={false} />
			</div>
		</AbsoluteFill>
	);
};

/* 12 — Kentucky warehouse near UPS hub */
const USMap: React.FC<{at: number; kyAt: number; w: number}> = ({at, kyAt, w}) => {
	const t = useT();
	const k = w / usmap.w;
	const p = prog(t, at, 0.8, eio);
	const ky = prog(t, kyAt, 0.4);
	const paths = usmap.paths as Record<string, string>;
	return (
		<svg width={w} height={usmap.h * k} viewBox={`0 0 ${usmap.w} ${usmap.h}`} style={{overflow: 'visible', filter: 'drop-shadow(0 10px 14px rgba(40,30,15,0.25))'}}>
			{Object.entries(paths).map(([n, d], i) => (
				<path key={n} d={d} fill={n === 'Kentucky' ? `rgba(42,157,143,${ky})` : '#FBF8F1'} stroke={INK} strokeWidth={1.4} opacity={clamp(p * 1.6 - (i / 50) * 0.6)} />
			))}
		</svg>
	);
};
const Pin: React.FC<{at: number; color?: string}> = ({at, color = RED}) => {
	const t = useT();
	const s = useSp(at, 9, 0.6, 220);
	if (t < at) return null;
	return (
		<svg width={60} height={90} viewBox="0 0 60 90" style={{transform: `translateY(${(1 - s) * -80}px)`, transformOrigin: '50% 100%'}}>
			<path d="M30,88 C30,88 4,52 4,30 A26,26 0 1,1 56,30 C56,52 30,88 30,88 Z" fill={color} stroke={INK} strokeWidth={3} />
			<circle cx={30} cy={30} r={10} fill={CREAM} />
		</svg>
	);
};
const S12: React.FC = () => {
	const {c} = useS();
	const t = useT();
	const mw = 980;
	const k = mw / usmap.w;
	const mx = 50;
	const my = 230;
	const ky = usmap.pts.ky;
	const sf = usmap.pts.sf;
	const pl = prog(t, c('یو‌پی‌اس') - 0.3, 1.4, eio);
	return (
		<AbsoluteFill>
			<Paper />
			<div style={{position: 'absolute', left: mx, top: my}}>
				<USMap at={0} kyAt={c('کنتاکی') - 0.1} w={mw} />
			</div>
			<div style={{position: 'absolute', left: mx + ky[0] * k - 30, top: my + ky[1] * k - 88}}>
				<Pin at={c('کنتاکی')} color={TEAL} />
			</div>
			<div style={{position: 'absolute', left: mx + sf[0] * k - 22, top: my + sf[1] * k - 66, transform: 'scale(0.75)'}}>
				<Pin at={0.3} />
			</div>
			<Abs x={mx + ky[0] * k + 40} y={my + ky[1] * k + 70}>
				<Wipe at={c('کنتاکی')}>
					<Label size={44} rot={-3}>کنتاکی</Label>
				</Wipe>
			</Abs>
			{pl > 0 && pl < 1 && (
				<div style={{position: 'absolute', left: interpolate(pl, [0, 1], [-200, mx + ky[0] * k - 120]), top: interpolate(pl, [0, 1], [180, my + ky[1] * k - 120]), transform: 'rotate(8deg)'}}>
					<Cut src="plane.png" w={300} />
				</div>
			)}
			<Abs x={830} y={my + 560}>
				<Type at={c('یو‌پی‌اس')} text="UPS HUB" cps={20} style={{fontSize: 42, color: INK, letterSpacing: 4}} cursor={false} />
			</Abs>
			<Enter at={0.1} from="down" x={540} y={1180} rot={-2}>
				<Photo src="warehouse.jpg" w={760} />
			</Enter>
			<Stamp at={c('ارسالِ') - 0.05} x={290} y={1580} rot={-8} size={60} color={TEAL}>
				ارسال رایگان
			</Stamp>
			<Stamp at={c('مرجوعیِ') - 0.05} x={790} y={1610} rot={6} size={60} color={TEAL}>
				مرجوعی رایگان
			</Stamp>
			<Enter at={c('تجربه‌ای') - 0.1} from="pop" x={820} y={1000} rot={8}>
				<Photo src="woman_box.jpg" w={300} tape={false} border={10} />
			</Enter>
			<svg width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
				{t > c('عاشقش') - 0.1 && (
					<path d="M900,880 C900,850 950,840 950,880 C950,840 1000,850 1000,880 C1000,915 950,940 950,960 C950,940 900,915 900,880 Z" fill="none" stroke={RED} strokeWidth={9} strokeDasharray={400} strokeDashoffset={400 * (1 - prog(t, c('عاشقش') - 0.1, 0.4))} strokeLinejoin="round" />
				)}
			</svg>
		</AbsoluteFill>
	);
};

/* 13 — $1B in 2008, Amazon 2009 */
const PTS: [number, number, string][] = [
	[2000, 1.6, '$1.6M'],
	[2001, 8.6, ''],
	[2003, 70, '$70M'],
	[2004, 184, ''],
	[2005, 370, ''],
	[2006, 597, ''],
	[2007, 840, ''],
	[2008, 1000, '$1B'],
];
const S13: React.FC = () => {
	const {c} = useS();
	const t = useT();
	const cx = 120;
	const cy = 1150;
	const cw = 840;
	const ch = 620;
	const X = (y: number) => cx + ((y - 2000) / 8) * cw;
	const Y = (v: number) => cy - (Math.log10(v) - 0) / 3 * ch;
	const p = prog(t, 0.2, Math.max(1.5, c('گذشت') - 0.2), (x) => x);
	const n = PTS.length;
	const seg = p * (n - 1);
	const shown = PTS.slice(0, Math.floor(seg) + 1).map(([y, v]) => [X(y), Y(v)] as [number, number]);
	if (seg < n - 1) {
		const i = Math.floor(seg);
		const f = seg - i;
		const [y0, v0] = PTS[i];
		const [y1, v1] = PTS[i + 1];
		shown.push([X(y0) + (X(y1) - X(y0)) * f, Y(v0) + (Y(v1) - Y(v0)) * f]);
	}
	const d = shown.map((q, i) => `${i ? 'L' : 'M'}${q[0]},${q[1]}`).join(' ');
	const tAm = c('آمازون') - 0.2;
	return (
		<AbsoluteFill>
			<Paper tex="grid" />
			<Abs x={540} y={280}>
				<Type at={0.05} text="2008" cps={8} style={{fontSize: 200, color: INK, lineHeight: 1}} cursor={false} />
			</Abs>
			<svg width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
				<line x1={cx} y1={cy} x2={cx + cw} y2={cy} stroke={INK} strokeWidth={4} />
				<line x1={cx} y1={cy} x2={cx} y2={cy - ch - 20} stroke={INK} strokeWidth={4} />
				{[2000, 2004, 2008].map((y) => (
					<text key={y} x={X(y)} y={cy + 60} textAnchor="middle" fontFamily={TW} fontSize={36} fill={INK}>
						{y}
					</text>
				))}
				<path d={d} fill="none" stroke={RED} strokeWidth={10} strokeLinecap="round" strokeLinejoin="round" />
				{PTS.map(([y, v, lab], i) =>
					i <= seg + 0.01 ? (
						<g key={i}>
							<circle cx={X(y)} cy={Y(v)} r={12} fill={i === n - 1 ? RED : INK} />
							{lab && (
								<text x={X(y) + (i === n - 1 ? -20 : 20)} y={Y(v) - 28} textAnchor={i === n - 1 ? 'end' : 'start'} fontFamily={ANTON} fontSize={i === n - 1 ? 84 : 52} fill={INK}>
									{lab}
								</text>
							)}
						</g>
					) : null,
				)}
			</svg>
			<CircleMark cx={X(2008) - 90} cy={Y(1000) - 55} rx={150} ry={80} at={c('میلیارد') + 0.2} />
			<Enter at={tAm} from="down" x={540} y={1530} rot={-2}>
				<Torn w={900} h={300} seed="am">
					<div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', direction: 'rtl'}}>
						<div style={{fontFamily: TW, fontSize: 44, color: RED}}>2009</div>
						<div style={{fontFamily: D, fontWeight: 800, fontSize: 70, color: INK}}>آمازون، زاپوس رو خرید</div>
					</div>
				</Torn>
			</Enter>
			<Stamp at={c('خریدش') - 0.05} x={860} y={1380} rot={10} size={70}>
				$1.2B
			</Stamp>
		</AbsoluteFill>
	);
};

/* 14 — the lesson */
const S14: React.FC = () => {
	const {c, dur} = useS();
	const t = useT();
	return (
		<AbsoluteFill>
			<Paper />
			<Abs x={540} y={240}>
				<Wipe at={0.05}>
					<T size={80}>درسِ این داستان</T>
				</Wipe>
			</Abs>
			<Enter at={c('دراپ‌شیپینگ') - 0.2} from="right" x={790} y={760} rot={3}>
				<Torn w={460} h={640} seed="l1" color="#F6D79A">
					<div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 40, direction: 'rtl'}}>
						<div style={{fontFamily: D, fontWeight: 800, fontSize: 64, color: INK}}>شروع</div>
						<Img src={staticFile('img/crt.png')} style={{width: 300, marginTop: 20}} />
						<div style={{fontFamily: D, fontWeight: 700, fontSize: 46, color: RED, marginTop: 30}}>دراپ‌شیپینگ</div>
					</div>
				</Torn>
			</Enter>
			<Enter at={c('برندها') - 0.2} from="left" x={290} y={800} rot={-3}>
				<Torn w={460} h={640} seed="l2" color="#BFE3DC">
					<div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 40, direction: 'rtl'}}>
						<div style={{fontFamily: D, fontWeight: 800, fontSize: 64, color: INK}}>ماندگاری</div>
						<Img src={staticFile('img/courier.png')} style={{width: 200, marginTop: 16}} />
						<div style={{fontFamily: D, fontWeight: 700, fontSize: 46, color: TEAL, marginTop: 20}}>تجربه‌ی مشتری</div>
					</div>
				</Torn>
			</Enter>
			<Arrow pts={[[640, 1120], [540, 1180], [440, 1130]]} at={c('ولی') - 0.05} color={INK} />
			<Abs x={540} y={1360}>
				<Wipe at={c('برندها') - 0.1} d={0.5}>
					<T size={74}>برندها با</T>
				</Wipe>
			</Abs>
			<Abs x={540} y={1470}>
				<Wipe at={c('کنترلِ') - 0.1} d={0.6}>
					<T size={86}>
						<Hl at={c('تجربه‌ی')}>تجربه‌ی مشتری</Hl>
					</T>
				</Wipe>
			</Abs>
			<Abs x={540} y={1580}>
				<Wipe at={c('ساخته') - 0.1}>
					<T size={74}>ساخته می‌شن.</T>
				</Wipe>
			</Abs>
			<Abs x={540} y={1760}>
				<div style={{opacity: prog(t, dur - 2.0, 0.5), fontFamily: TW, fontSize: 26, color: '#5d574d', textAlign: 'center', direction: 'ltr'}}>
					Sources: Fortune (2012) · Bloomberg (2010) · MarketingSherpa (2007) · Wikipedia
				</div>
			</Abs>
		</AbsoluteFill>
	);
};

export const SCENES = [S01, S02, S03, S04, S05, S06, S07, S08, S09, S10, S11, S12, S13, S14];
