// Intro engine 1 — Story (1080x1920, 30 fps): the product introduces itself as a little tale; a small character made of the brand's own mark
// walks a ground line from scene to scene. Every text, the step visuals and all times come from content.json (creative/claude_intro/story.py).
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {CONTENT, TIMING, Fonts, useFonts, clamp, lerp, seg, eo5, eio, back, rnd, fa, fit, Mascot, blinkAt, Wipe, Words, MASCOT_COLOR} from './lib';

const FPS = 30, W = 1080, H = 1920;
const P = CONTENT.palette ?? {};
const C = {bg: P.bg ?? '#f2eee5', ink: P.ink ?? '#171512', grey: '#b9b3a6', mid: '#8b8579', acc: P.accent ?? '#e8590c', jar: MASCOT_COLOR, dark: '#141414', green: '#3f8f5b', blue: '#4b7bd1'};
const GY = 1500, MX = 110, TW = W - 2 * MX;
const T = (TIMING.T ?? {term: 0, once: 4.6, dict: 9.4, steps: [], hi: 15, moral: 20, total: 24}) as {term: number; once: number; dict: number; steps: number[]; hi: number; moral: number; total: number};
type StepC = {n: string; a: string; b: string; sub: string; visual: string; [k: string]: any};
const STEPS: StepC[] = CONTENT.steps ?? [];
const stepEnd = (i: number) => (i + 1 < STEPS.length ? T.steps[i + 1] : T.hi);
// where the character stands during each kind of step
const HOME: Record<string, number> = {read: 540, think: 540, build: 300, multiply: 540, list: 250, counter: 540};

const Step: React.FC<{t: number; s: StepC; out: number}> = ({t, s, out}) => {
	const o = 1 - seg(t, out - 0.3, out);
	const bu = eo5(seg(t, 0.45, 0.9));
	const size = fit(`${s.a} ${s.b}`, 'Pey', 900, 118, TW);
	return (
		<div style={{position: 'absolute', right: MX, left: MX, top: 500, direction: 'rtl', opacity: o}}>
			<div style={{fontFamily: 'Vaz', fontWeight: 500, fontSize: 30, color: C.acc, opacity: seg(t, 0, 0.2)}}>{s.n}</div>
			<div style={{fontFamily: 'Pey', fontWeight: 900, fontSize: size, lineHeight: 1.5, color: C.ink, whiteSpace: 'nowrap', marginTop: -6}}>
				<span style={{display: 'inline-block', opacity: seg(t, 0.1, 0.3), transform: `translateY(${(1 - eo5(seg(t, 0.1, 0.5))) * 40}px)`}}>{s.a}</span>{' '}
				<span style={{display: 'inline-block', color: bu < 0.99 ? C.grey : C.ink, opacity: seg(t, 0.35, 0.55), transform: `translateY(${(1 - bu) * 40}px) rotate(${(1 - bu) * -4}deg)`}}>{s.b}</span>
			</div>
			<div style={{fontFamily: 'Vaz', fontWeight: 500, fontSize: fit(s.sub ?? '', 'Vaz', 500, 31, TW), color: C.mid, marginTop: 4, opacity: seg(t, 0.9, 1.2), whiteSpace: 'nowrap'}}>{s.sub}</div>
		</div>
	);
};

// ---------- the step visuals (SVG, area y 850-1350, above the ground line) ----------
const VRead: React.FC<{lt: number; o: number; s: StepC; jx: number}> = ({lt, o, s, jx}) => {
	const scroll = lt * 150, scanX = 540;
	const cards: string[] = s.cards ?? ['۱', '۲', '۳'];
	const units: string[] = s.units ?? [];
	return (
		<g opacity={o}>
			<text x={W - MX} y={880} fontFamily="Vaz" fontWeight={500} fontSize={24} fill={C.mid} direction="rtl" textAnchor="start">{s.status ?? ''}</text>
			{units.length > 0 && <text x={MX} y={880} fontFamily="Vaz" fontWeight={500} fontSize={24} fill={C.ink} textAnchor="end" direction="rtl">{fa(Math.min(124, Math.floor(lt * 34)))} {units[0]}{units[1] ? ` · ${fa(Math.min(48, Math.floor(lt * 13)))} ${units[1]}` : ''}</text>}
			<clipPath id="rd"><rect x={MX} y={900} width={TW} height={380} /></clipPath>
			<g clipPath="url(#rd)">
				{[0, 1, 2, 3, 4, 5].map((i) => {
					const x = W - 380 - i * 300 + scroll;
					const read = x + 130 > scanX ? 1 : 0;
					const kind = i % 3;
					return (
						<g key={i} transform={`translate(${x},920)`} opacity={read ? 0.42 : 1}>
							<rect width={270} height={340} rx={14} fill="#fffdf8" stroke="#ddd6c7" strokeWidth={2} />
							<text x={250} y={34} fontFamily="Vaz" fontWeight={500} fontSize={15} fill={C.mid} direction="rtl" textAnchor="start">{cards[kind % cards.length]}</text>
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
};
const VThink: React.FC<{lt: number; o: number; s: StepC; jx: number}> = ({lt, o, s, jx}) => {
	const m = eio(seg(lt, 0.9, 1.9));
	const sb = eio(seg(lt, 2.1, 2.9));
	const nodes = [[540, 930], [330, 1070], [540, 1070], [750, 1070], [240, 1215], [420, 1215], [660, 1215], [840, 1215]];
	const edges = [[0, 1], [0, 2], [0, 3], [1, 4], [1, 5], [3, 6], [3, 7]];
	const pos = nodes.map(([x, y], i) => [lerp(540 + (rnd(i + 3) - 0.5) * 760, x, m), lerp(1060 + (rnd(i + 11) - 0.5) * 330 + Math.sin(lt * 2 + i) * 14 * (1 - m), y, m)]);
	const hot = [0, 1, 5];
	const labels: string[] = s.labels ?? [];
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
						<text x={250} y={34} fontFamily="Vaz" fontWeight={500} fontSize={17} fill={hi ? C.jar : C.mid} direction="rtl" textAnchor="start">{fa(i + 1)}{labels[i] ? ` · ${labels[i]}` : ''}</text>
						<rect x={20} y={56} width={230} height={9} rx={4.5} fill={hi ? '#fff' : C.ink} opacity={0.8} />
						<rect x={90} y={80} width={160} height={9} rx={4.5} fill={hi ? '#fff' : C.ink} opacity={0.4} />
						<rect x={20} y={128} width={230 * [0.6, 0.9, 0.75, 0.8, 0.55, 0.4][i]} height={16} rx={5} fill={hi ? C.jar : C.grey} />
					</g>
				);
			})}
			{[0, 1, 2].map((i) => { const u = (lt * 0.8 + i * 0.33) % 1; return <circle key={i} cx={jx + 44 + i * 6} cy={GY - 170 - u * 90} r={5 + u * 7} fill="none" stroke={C.ink} strokeWidth={2} opacity={(1 - u) * (1 - sb)} />; })}
		</g>
	);
};
const VBuild: React.FC<{lt: number; o: number; s: StepC}> = ({lt, o, s}) => {
	const px = MX, py = 890, pw = TW, ph = 420;
	const rend = seg(lt, 2.3, 3.0);
	const names: string[] = s.tracks ?? ['۱', '۲', '۳', '۴'];
	const cols = ['#5d5a55', C.jar, '#7d8cff', '#58b28a'];
	const clipsOf = [[[0, 0.3], [0.31, 0.62], [0.63, 1]], [[0.02, 0.2], [0.22, 0.45], [0.5, 0.7], [0.73, 0.97]], [[0.1, 0.28], [0.56, 0.86]], [[0, 1]]];
	const ph2 = seg(lt, 0.3, 2.2);
	const total = Number(s.count ?? 100);
	const n = Math.floor(seg(lt, 2.5, 3.9) * total);
	const win: string[] = s.window ?? ['', ''];
	return (
		<g opacity={o}>
			<rect x={px + 6} y={py + 12} width={pw} height={ph} rx={22} fill="#000" opacity={0.12} style={{filter: 'blur(14px)'}} />
			<rect x={px} y={py} width={pw} height={ph} rx={22} fill="#181818" />
			{[0, 1, 2].map((i) => <circle key={i} cx={px + 34 + i * 22} cy={py + 30} r={6} fill="#3a3a3a" />)}
			<text x={px + pw / 2} y={py + 37} fontFamily="Vaz" fontWeight={500} fontSize={19} fill="#8a8a8a" textAnchor="middle" direction="rtl">{rend > 0.5 ? win[1] : win[0]}</text>
			<g opacity={1 - rend}>
				{names.slice(0, 4).map((name, i) => (
					<g key={i}>
						<text x={px + pw - 26} y={py + 105 + i * 76} fontFamily="Vaz" fontWeight={500} fontSize={20} fill="#9a9a9a" direction="rtl" textAnchor="start">{name}</text>
						<rect x={px + 26} y={py + 76 + i * 76} width={pw - 150} height={48} rx={8} fill="#222" />
						{clipsOf[i].map(([a, b], k) => {
							const u = eo5(clamp((lt - 0.2 - i * 0.28 - k * 0.14) / 0.4));
							const x1 = px + 26 + (pw - 150) * (1 - b), w = (pw - 150) * (b - a) - 6;
							return <rect key={k} x={x1 + w * (1 - u)} y={py + 80 + i * 76} width={w * u} height={40} rx={7} fill={cols[i]} />;
						})}
					</g>
				))}
				<line x1={px + 26 + (pw - 150) * (1 - ph2)} x2={px + 26 + (pw - 150) * (1 - ph2)} y1={py + 62} y2={py + 390} stroke="#fff" strokeWidth={2.5} />
			</g>
			<g opacity={rend}>
				<text x={px + pw - 60} y={py + 150} fontFamily="VazL" fontWeight={500} fontSize={30} fill="#eaeaea" textAnchor="end">{s.command ?? ''}</text>
				<rect x={px + 60} y={py + 200} width={pw - 120} height={16} rx={8} fill="#2b2b2b" />
				<rect x={px + 60 + (pw - 120) * (1 - n / total)} y={py + 200} width={(pw - 120) * (n / total)} height={16} rx={8} fill={C.jar} />
				<text x={px + pw - 60} y={py + 275} fontFamily="Vaz" fontWeight={500} fontSize={26} fill="#9a9a9a" direction="rtl" textAnchor="start">{fa(n)} از {fa(total)} {s.unit ?? ''}</text>
				{n >= total && <text x={px + 60} y={py + 275} fontFamily="Vaz" fontWeight={500} fontSize={26} fill="#6fd39b" direction="rtl" textAnchor="end">{s.done ?? '✓'}</text>}
				{n >= total && s.done_note && <text x={px + pw - 60} y={py + 340} fontFamily="Vaz" fontWeight={500} fontSize={22} fill="#777" direction="rtl" textAnchor="start">{s.done_note}</text>}
			</g>
		</g>
	);
};
const VMultiply: React.FC<{lt: number; o: number; s: StepC; t: number}> = ({lt, o, s, t}) => {
	const names: string[] = (s.names ?? []).slice(0, 6);
	return (
		<g opacity={o}>
			{names.map((n, i) => {
				const u = clamp((lt - 0.3 - i * 0.22) / 0.45);
				if (u <= 0) return null;
				const x = W - MX - 140 - (i % 3) * 290, y = 1010 + Math.floor(i / 3) * 215;
				const cx = lerp(540, x, eo5(u)), cy = lerp(GY, y, eo5(u)) - Math.sin(u * Math.PI) * 90;
				return (
					<g key={i}>
						<Mascot x={cx} y={cy} s={1.25} col={C.jar} blink={blinkAt(t, 2.2, i * 0.37)} squash={u >= 1 ? Math.max(0, Math.sin((lt - i * 0.22) * 5)) * 0.05 : 0} />
						<text x={x} y={y + 46} fontFamily="Vaz" fontWeight={500} fontSize={25} fill={C.ink} textAnchor="middle" direction="rtl" opacity={seg(u, 0.8, 1)}>{n}</text>
					</g>
				);
			})}
			<text x={MX} y={GY + 60} fontFamily="Vaz" fontWeight={500} fontSize={28} fill={C.acc} direction="rtl" textAnchor="end" opacity={seg(lt, 1.9, 2.2)}>× {fa(Math.min(names.length, Math.max(1, Math.floor((lt - 0.3) / 0.22) + 1)))}</text>
		</g>
	);
};
// a checklist: 3-4 rows that arrive and are ticked one after the other
const VList: React.FC<{lt: number; o: number; s: StepC}> = ({lt, o, s}) => {
	const items: string[] = (s.items ?? []).slice(0, 4);
	const rowH = 96, x0 = 400, w = W - MX - x0;
	return (
		<g opacity={o}>
			{items.map((it, i) => {
				const u = eo5(clamp((lt - 0.2 - i * 0.45) / 0.4)), ok = lt > 1.0 + i * 0.55;
				const y = 900 + i * (rowH + 14);
				return (
					<g key={i} opacity={clamp((lt - 0.2 - i * 0.45) / 0.15)} transform={`translate(${(1 - u) * -60},0)`}>
						<rect x={x0} y={y} width={w} height={rowH} rx={16} fill="#fffdf8" stroke="#ddd6c7" strokeWidth={2} />
						<circle cx={x0 + w - 50} cy={y + rowH / 2} r={20} fill={ok ? C.green : 'none'} stroke={ok ? C.green : C.grey} strokeWidth={3} />
						{ok && <path d={`M${x0 + w - 60},${y + rowH / 2} l8,9 l14,-17`} fill="none" stroke="#fff" strokeWidth={4} strokeLinecap="round" />}
						<text x={x0 + w - 92} y={y + rowH / 2 + 11} fontFamily="Vaz" fontWeight={500} fontSize={30} fill={C.ink} direction="rtl" textAnchor="start">{it}</text>
					</g>
				);
			})}
		</g>
	);
};
// one big number counting up in a card, with its unit and a caption
const VCounter: React.FC<{lt: number; o: number; s: StepC}> = ({lt, o, s}) => {
	const v = Math.round(Number(s.value ?? 0) * eo5(seg(lt, 0.3, 2.2)));
	const u = back(clamp(lt / 0.45));
	return (
		<g opacity={o} transform={`translate(540,1090) scale(${u}) translate(-540,-1090)`}>
			<rect x={MX + 60} y={900} width={TW - 120} height={380} rx={26} fill="#181818" />
			<text x={540} y={1120} fontFamily="Pey" fontWeight={900} fontSize={190} fill="#fffdf8" textAnchor="middle" direction="rtl">{fa(v.toLocaleString('en-US').replace(/,/g, '٬'))}</text>
			<text x={540} y={1190} fontFamily="Vaz" fontWeight={500} fontSize={34} fill={C.jar} textAnchor="middle" direction="rtl">{s.unit ?? ''}</text>
			{s.caption && <text x={540} y={1245} fontFamily="Vaz" fontWeight={500} fontSize={24} fill="#9a9a9a" textAnchor="middle" direction="rtl">{s.caption}</text>}
		</g>
	);
};

export const Story: React.FC = () => {
	useFonts();
	const f = useCurrentFrame();
	const t = f / FPS;
	const brand: string = CONTENT.brand ?? '';
	const si = STEPS.findIndex((_, i) => t >= T.steps[i] && t < stepEnd(i));

	// ---------- the character's path ----------
	let jx = 540, jy = GY, squash = 0, look = 0, walk = 0, happy = false, js = 1.7, rot = 0;
	const walkTo = (from: number, to: number, a: number, d = 0.65) => { const u = eio(seg(t, a, a + d)); jx = lerp(from, to, u); walk = u > 0 && u < 1 ? t * 3 : 0; };
	if (t < T.once) {
		const d = t - (T.once - 1.6);
		jx = 250; js = 1.5;
		const gy = 1010;
		if (d < 0) jy = -200;
		else if (d < 0.35) jy = lerp(-100, gy, (d / 0.35) * (d / 0.35));
		else { jy = gy - Math.abs(Math.sin((d - 0.35) * 9)) * 60 * Math.exp(-(d - 0.35) * 4.5); squash = 0.28 * Math.exp(-(d - 0.35) * 9); }
	} else if (t < T.dict) {
		const u = seg(t, T.once, T.once + 0.5);
		jx = lerp(250, 240, u); jy = lerp(1010, GY, eio(u)); js = lerp(1.5, 1.7, u);
		const w = seg(t, T.once + 1.2, T.once + 4.0);
		jx = lerp(240, 860, eio(w)); walk = w > 0 && w < 1 ? t * 3 : 0; look = w > 0 && w < 1 ? 1 : 0;
	} else if (t < T.steps[0]) {
		jx = 860; look = t > T.dict + 3.2 ? -0.6 : 0; happy = t > T.dict + 4.2 && t < T.dict + 5.2;
		const hop = seg(t, T.dict + 4.2, T.dict + 4.6); jy = GY - Math.sin(hop * Math.PI) * 50;
	} else if (si >= 0) {
		const kind = STEPS[si].visual, a = T.steps[si], prev = si === 0 ? 860 : HOME[STEPS[si - 1].visual] ?? 540, home = HOME[kind] ?? 540;
		walkTo(prev, home, a);
		if (kind === 'read') look = Math.sin(t * 2.2) * 0.8;
		if (kind === 'think') { squash = 0.05 + Math.sin(t * 2) * 0.03; look = -0.3; rot = seg(t, a + 2.7, a + 3.1) * 360 * (1 - seg(t, a + 3.1, a + 3.11)); }
		if (kind === 'build' || kind === 'counter') { look = 0.7; happy = t > a + 4.0; const hop = seg(t, a + 3.9, a + 4.3); jy = GY - Math.sin(hop * Math.PI) * 60; }
		if (kind === 'list') { look = 0.8; happy = t > a + 3.6; }
	} else if (t < T.moral) {
		const prev = HOME[STEPS[STEPS.length - 1]?.visual] ?? 540;
		walkTo(prev, 540, T.hi, 0.5);
		const hop = seg(t, T.hi + 1.4, T.hi + 1.8); jy = GY - Math.sin(hop * Math.PI) * 70; happy = t > T.hi + 1.4 && t < T.hi + 2.6;
	} else {
		jx = 540; const u = eio(seg(t, T.moral, T.moral + 0.8)); jy = lerp(GY, 1330, u); happy = t > T.moral + 1.6;
	}

	// ---------- background ----------
	const circA = T.once - 0.45;
	const circ = eio(seg(t, circA, circA + 0.6));
	const dark = t < circA + 0.6;
	const groundOn = seg(t, T.once + 0.1, T.once + 0.7) * (1 - seg(t, T.moral, T.moral + 0.5));

	// ---------- terminal ----------
	const prompt: string = CONTENT.prompt ?? '';
	const per = Math.min(0.13, (T.once - 2.5) / Math.max(1, prompt.length));
	const tf = clamp(Math.floor((t - 0.5) / per), 0, prompt.length) / Math.max(1, prompt.length);

	// ---------- name → dictionary ----------
	const dU = eio(seg(t, T.dict, T.dict + 0.8));
	const titleOut = 1 - seg(t, T.steps[0] - 0.4, T.steps[0] - 0.05);
	const sweep = seg(t, T.once + 1.2, T.once + 2.5);
	const nameBig = fit(brand, 'Pey', 900, 148, TW), nameSmall = Math.min(104, nameBig * 0.7);
	const def: string[] = CONTENT.definition ?? [];
	const moral: string[] = CONTENT.moral ?? [];

	return (
		<AbsoluteFill style={{background: C.dark}}>
			<Fonts />
			{dark && (
				<AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 45%, #1f1f1f 0%, #101010 75%)'}}>
					<div style={{position: 'absolute', right: 120, top: 890, direction: 'rtl', fontFamily: 'Vaz', fontWeight: 500, fontSize: fit(prompt, 'Vaz', 500, 50, 760), color: '#e9e6df', whiteSpace: 'nowrap', display: 'flex', alignItems: 'center'}}>
						<span style={{color: '#7c7c7c', marginLeft: 22, fontFamily: 'VazL'}}>‹</span>
						<span style={{position: 'relative', display: 'inline-block'}}>
							<span style={{visibility: 'hidden'}}>{prompt}</span>
							<span style={{position: 'absolute', right: 0, top: 0, clipPath: `inset(-20% 0 -20% ${(1 - tf) * 100}%)`}}>{prompt}</span>
							{(tf < 1 || Math.floor(t * 2.5) % 2 === 0) && t < circA - 0.05 && <span style={{position: 'absolute', right: `calc(${tf * 100}% + 6px)`, top: 12, width: 22, height: 52, background: '#e9e6df'}} />}
						</span>
					</div>
				</AbsoluteFill>
			)}
			<AbsoluteFill style={{background: `radial-gradient(ellipse at 50% 40%, #f7f4ec 0%, ${C.bg} 70%, #e9e4d8 100%)`, clipPath: t < circA + 0.65 ? `circle(${circ * 2300}px at 250px 950px)` : undefined, opacity: t < circA ? 0 : 1}}>
				{t >= T.once && t < T.steps[0] && (
					<>
						<Wipe p={seg(t, T.once + 0.4, T.once + 1.1)} style={{position: 'absolute', right: MX + 10, top: lerp(690, 300, dU), fontFamily: 'Typo', fontSize: 62, color: C.mid, direction: 'rtl', opacity: (1 - dU) * titleOut}}>{CONTENT.once ?? ''}</Wipe>
						<div style={{position: 'absolute', right: MX, top: lerp(800, 330, dU), direction: 'rtl', fontFamily: 'Pey', fontWeight: 900, fontSize: lerp(nameBig, nameSmall, dU), lineHeight: 1.6, whiteSpace: 'nowrap', opacity: seg(t, T.once + 1.1, T.once + 1.3) * titleOut, transformOrigin: '100% 50%'}}>
							<span style={{color: '#d9d4c8'}}>{brand}</span>
							<span style={{position: 'absolute', right: 0, top: 0, color: C.ink, clipPath: `inset(-20% 0 -30% ${(1 - eio(sweep)) * 100}%)`}}>{brand}</span>
						</div>
					</>
				)}
				{t >= T.dict && t < T.steps[0] && (
					<div style={{position: 'absolute', right: MX, left: MX, top: 520, direction: 'rtl', opacity: titleOut}}>
						<div style={{fontFamily: 'Vaz', fontWeight: 500, fontSize: 27, color: C.mid, opacity: seg(t, T.dict + 0.6, T.dict + 0.9), letterSpacing: 1}}>{CONTENT.syllables ?? ''} &nbsp;&nbsp; <span style={{color: C.acc}}>{CONTENT.pos ?? ''}</span></div>
						<div style={{height: 2, background: C.ink, opacity: 0.18, marginTop: 22, width: `${eo5(seg(t, T.dict + 0.7, T.dict + 1.3)) * 100}%`}} />
						{def.slice(0, 3).map((line, i) => (
							<Words key={i} text={line} t={t} t0={T.dict + 1.3 + i * 0.55} style={{fontFamily: 'Pey', fontWeight: 400, fontSize: fit(line, 'Pey', 400, 64, TW), lineHeight: 1.7, color: C.ink, marginTop: i ? 0 : 34, whiteSpace: 'nowrap'}} />
						))}
						{CONTENT.badge && <div style={{position: 'absolute', left: 0, top: 8, fontFamily: 'Vaz', fontWeight: 500, fontSize: 24, color: C.green, opacity: seg(t, T.dict + 3.0, T.dict + 3.3)}}>{CONTENT.badge}</div>}
					</div>
				)}
				{si >= 0 && <Step t={t - T.steps[si]} s={STEPS[si]} out={stepEnd(si) - T.steps[si]} />}

				<svg width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
					<line x1={MX} x2={MX + TW * eo5(groundOn)} y1={GY} y2={GY} stroke={C.ink} strokeWidth={2.5} opacity={groundOn > 0 ? 1 : 0} />
					{t >= T.dict + 3.2 && t < T.steps[0] && (() => {
						const L = 620, u = eo5(seg(t, T.dict + 3.2, T.dict + 4.1));
						return (
							<g opacity={titleOut}>
								<path d="M470,1075 C800,1075 1010,1160 930,1385" fill="none" stroke={C.acc} strokeWidth={3} strokeDasharray={`${L} ${L}`} strokeDashoffset={L * (1 - u)} />
								{u > 0.97 && <path d="M912,1362 L930,1390 L952,1366" fill="none" stroke={C.acc} strokeWidth={3} />}
								{t > T.dict + 4.2 && <text x={780} y={1430} fontFamily="Vaz" fontWeight={500} fontSize={30} fill={C.acc} direction="rtl">{CONTENT.hello ?? ''}</text>}
							</g>
						);
					})()}
					{si >= 0 && t >= T.steps[si] + 0.9 && (() => {
						const s = STEPS[si], lt = t - T.steps[si] - 0.9, end = stepEnd(si);
						const o = clamp(lt / 0.3) * (1 - seg(t, end - 0.35, end - 0.05));
						if (s.visual === 'read') return <VRead lt={lt} o={o} s={s} jx={jx} />;
						if (s.visual === 'think') return <VThink lt={lt} o={o} s={s} jx={jx} />;
						if (s.visual === 'build') return <VBuild lt={lt} o={o} s={s} />;
						if (s.visual === 'multiply') return <VMultiply lt={lt} o={1 - seg(t, end - 0.35, end - 0.05)} s={s} t={t} />;
						if (s.visual === 'list') return <VList lt={lt} o={o} s={s} />;
						if (s.visual === 'counter') return <VCounter lt={lt} o={o} s={s} />;
						return null;
					})()}
					{t >= T.moral && <circle cx={W + 120} cy={-460} r={eo5(seg(t, T.moral, T.moral + 0.9)) * 900} fill={C.dark} />}
					<Mascot x={jx} y={jy} s={js} col={C.jar} blink={blinkAt(t)} squash={squash} look={look} walk={walk} happy={happy} rot={rot} />
				</svg>

				{t >= T.hi && t < T.moral && (
					<div style={{position: 'absolute', left: 0, right: 0, top: 690, textAlign: 'center', direction: 'rtl', opacity: 1 - seg(t, T.moral - 0.35, T.moral - 0.05)}}>
						<Wipe p={seg(t, T.hi + 0.2, T.hi + 0.7)} style={{fontFamily: 'Typo', fontSize: 78, color: C.mid}}>{CONTENT.hi ?? ''}</Wipe>
						<div style={{fontFamily: 'Pey', fontWeight: 900, fontSize: fit(brand + '.', 'Pey', 900, 142, TW), lineHeight: 1.5, color: C.ink, whiteSpace: 'nowrap', transform: `translateY(${(1 - eo5(seg(t, T.hi + 0.6, T.hi + 1.2))) * 60}px)`, opacity: seg(t, T.hi + 0.6, T.hi + 0.8)}}>
							{brand}<span style={{color: C.acc}}>.</span>
						</div>
						{CONTENT.url && <div style={{display: 'inline-block', marginTop: 30, padding: '10px 28px', border: `2px solid #d6cfbf`, borderRadius: 40, fontFamily: 'VazL', fontWeight: 500, fontSize: 28, color: C.mid, opacity: seg(t, T.hi + 1.6, T.hi + 1.9), letterSpacing: 1}}>{CONTENT.url}</div>}
					</div>
				)}
				{t >= T.moral && (
					<div style={{position: 'absolute', left: 0, right: 0, top: 800, textAlign: 'center', direction: 'rtl'}}>
						<div style={{fontFamily: 'Vaz', fontWeight: 500, fontSize: 24, color: C.acc, letterSpacing: 6, opacity: seg(t, T.moral + 0.6, T.moral + 0.9)}}>{CONTENT.moral_label ?? ''}</div>
						{moral.slice(0, 2).map((line, i) => (
							<Words key={i} text={line} t={t} t0={T.moral + 0.9 + i * 0.6} style={{fontFamily: 'Pey', fontWeight: 400, fontSize: fit(line, 'Pey', 400, 88, TW), lineHeight: 1.6, color: C.ink, marginTop: i ? 0 : 26, textAlign: 'center', whiteSpace: 'nowrap'}} />
						))}
					</div>
				)}
			</AbsoluteFill>
			{dark && t >= T.once - 1.6 && t < circA + 0.6 && (
				<svg width={W} height={H} style={{position: 'absolute'}}><Mascot x={jx} y={jy} s={js} col={C.jar} blink={blinkAt(t)} squash={squash} /></svg>
			)}
		</AbsoluteFill>
	);
};
