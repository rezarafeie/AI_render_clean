import React from 'react';
import {interpolate, spring, useCurrentFrame} from 'remotion';
import {CREAM, D, FPS, GOLD, P, SERIF, clamp, eio, eo, fa, fit, goldText, prog} from './tokens';

/* The primitives a video's own graphics are drawn with (the graphics are written per video, on THIS kit). A graphic draws inside its zone: a box of w x h px; coordinates start at its top-left.
   Time: useT() = seconds since the graphic appeared; k(i) (given to the graphic) = seconds, in the same clock, at which word i of the transcript is heard. */

export type GP = {k: (i: number) => number; dur: number; w: number; h: number};
export {CREAM, D, GOLD, P, SERIF, clamp, eio, eo, fa, fit, goldText, prog};

export const useT = () => useCurrentFrame() / FPS;
export const useSp = (at: number, damping = 14, mass = 0.8, stiffness = 140) => spring({frame: useCurrentFrame() - Math.round(at * FPS), fps: FPS, config: {damping, mass, stiffness}});

export const Glass: React.FC<{children: React.ReactNode; style?: React.CSSProperties}> = ({children, style}) => (
	<div style={{background: `linear-gradient(160deg, ${P.glass[0]}, ${P.glass[1]})`, border: `1.5px solid ${P.glassBorder}`, borderRadius: 40, backdropFilter: 'blur(18px) saturate(1.3)', boxShadow: '0 30px 80px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.18)', ...style}}>{children}</div>
);


export const Icon: React.FC<{k: string; s?: number}> = ({k: kind, s = 80}) => {
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
			{kind === 'heart' && <path d="M40,68 C10,46 12,18 30,16 C36,16 40,20 40,24 C40,20 44,16 50,16 C68,18 70,46 40,68 Z" {...st} />}
			{kind === 'star' && <path d="M40,8 L49,30 L72,31 L54,46 L60,70 L40,57 L20,70 L26,46 L8,31 L31,30 Z" {...st} />}
			{kind === 'check' && (
				<g {...st}>
					<circle cx={40} cy={40} r={30} />
					<path d="M26,41 L36,51 L56,29" />
				</g>
			)}
			{kind === 'chart' && <path d="M12,66 L12,14 M12,66 L70,66 M22,54 L34,38 L46,46 L64,22 M54,22 L64,22 L64,32" {...st} />}
			{kind === 'coin' && (
				<g {...st}>
					<circle cx={40} cy={40} r={28} />
					<path d="M40,22 L40,58 M30,31 C30,25 50,25 50,32 C50,40 30,38 30,47 C30,55 50,55 50,49" />
				</g>
			)}
			{kind === 'clock' && (
				<g {...st}>
					<circle cx={40} cy={40} r={30} />
					<path d="M40,22 L40,40 L54,48" />
				</g>
			)}
			{kind === 'target' && (
				<g {...st}>
					<circle cx={40} cy={40} r={30} />
					<circle cx={40} cy={40} r={17} />
					<circle cx={40} cy={40} r={4} fill={GOLD} />
				</g>
			)}
			{kind === 'rocket' && <path d="M40,8 C56,18 58,40 50,58 L30,58 C22,40 24,18 40,8 Z M30,58 L22,72 L34,66 M50,58 L58,72 L46,66 M40,34 a6,6 0 1,0 0.1,0" {...st} />}
			{kind === 'lock' && (
				<g {...st}>
					<rect x={18} y={36} width={44} height={34} rx={6} />
					<path d="M28,36 L28,26 C28,12 52,12 52,26 L52,36" />
				</g>
			)}
			{kind === 'chat' && <path d="M14,18 L66,18 C70,18 72,20 72,24 L72,50 C72,54 70,56 66,56 L40,56 L26,68 L26,56 L14,56 C10,56 8,54 8,50 L8,24 C8,20 10,18 14,18 Z" {...st} />}
			{kind === 'phone' && (
				<g {...st}>
					<rect x={22} y={8} width={36} height={64} rx={8} />
					<path d="M34,62 L46,62" />
				</g>
			)}
			{kind === 'mail' && (
				<g {...st}>
					<rect x={8} y={18} width={64} height={44} rx={6} />
					<path d="M10,22 L40,44 L70,22" />
				</g>
			)}
			{kind === 'book' && <path d="M12,16 L38,20 L38,66 L12,62 Z M68,16 L42,20 L42,66 L68,62 Z" {...st} />}
			{kind === 'doc' && <path d="M20,8 L48,8 L62,22 L62,72 L20,72 Z M48,8 L48,22 L62,22 M30,40 L52,40 M30,52 L52,52" {...st} />}
			{kind === 'cart' && <path d="M8,14 L18,14 L26,52 L62,52 L68,26 L22,26 M32,64 a3,3 0 1,0 0.1,0 M56,64 a3,3 0 1,0 0.1,0" {...st} />}
			{kind === 'question' && <path d="M28,28 C28,12 54,12 54,28 C54,40 40,40 40,52 M40,64 L40,66" {...st} />}
			{kind === 'play' && (
				<g {...st}>
					<circle cx={40} cy={40} r={30} />
					<path d="M33,26 L58,40 L33,54 Z" fill={GOLD} />
				</g>
			)}
		</svg>
	);
};


/** opacity + rise + blur-in at `at` seconds */
export const Rise: React.FC<{at?: number; d?: number; y?: number; children: React.ReactNode; style?: React.CSSProperties}> = ({at = 0, d = 0.45, y = 40, children, style}) => {
	const p = prog(useT(), at, d);
	return <div style={{opacity: p, transform: `translateY(${(1 - p) * y}px) scale(${0.94 + 0.06 * p})`, filter: p < 1 ? `blur(${(1 - p) * 10}px)` : undefined, ...style}}>{children}</div>;
};

/** spring pop from a small scale (rot: degrees of a small tilt that settles) */
export const Pop: React.FC<{at?: number; from?: number; rot?: number; damping?: number; children: React.ReactNode; style?: React.CSSProperties}> = ({at = 0, from = 0.4, rot = 0, damping = 11, children, style}) => {
	const s = useSp(at, damping, 0.8);
	const t = useT();
	return <div style={{opacity: prog(t, at, 0.1), transform: `scale(${interpolate(s, [0, 1], [from, 1])}) rotate(${(1 - s) * rot}deg)`, ...style}}>{children}</div>;
};

/** a hand-drawn curved pointer: draws itself along `d` (an SVG path in a w x h box) and ends in an arrow head */
export const Curl: React.FC<{d: string; w: number; h: number; at?: number; dur?: number; color?: string; width?: number; length?: number}> = ({d, w, h, at = 0, dur = 0.7, color = CREAM, width = 4, length = 600}) => {
	const p = prog(useT(), at, dur, eio);
	return (
		<svg width={w} height={h} style={{position: 'absolute', left: 0, top: 0, overflow: 'visible', opacity: 0.9}}>
			<path d={d} fill="none" stroke={color} strokeWidth={width} strokeLinecap="round" strokeLinejoin="round" strokeDasharray={length} strokeDashoffset={length * (1 - p)} />
		</svg>
	);
};

/** a highlighter swipe that grows behind its children (right to left: Persian) */
export const Mark: React.FC<{at?: number; color?: string; children: React.ReactNode}> = ({at = 0, color = 'rgba(233,194,122,0.55)', children}) => {
	const p = prog(useT(), at, 0.4, eio);
	return (
		<span style={{position: 'relative', display: 'inline-block'}}>
			<span style={{position: 'absolute', right: -8, left: -8, top: '18%', bottom: '4%', borderRadius: 10, background: color, transformOrigin: 'right center', transform: `scaleX(${p})`, zIndex: 0}} />
			<span style={{position: 'relative', zIndex: 1}}>{children}</span>
		</span>
	);
};

/** typing: shows the text letter by letter from `at`, with a blinking caret */
export const Typed: React.FC<{text: string; at?: number; cps?: number; style?: React.CSSProperties}> = ({text, at = 0, cps = 16, style}) => {
	const t = useT();
	const n = Math.max(0, Math.min(text.length, Math.floor((t - at) * cps)));
	return (
		<span style={style}>
			{text.slice(0, n)}
			{n < text.length && <span style={{opacity: Math.sin(t * 14) > 0 ? 1 : 0}}>|</span>}
		</span>
	);
};

/** a number that counts up to `to` (Persian digits) */
export const Counter: React.FC<{to: number; at?: number; dur?: number; style?: React.CSSProperties; suffix?: string}> = ({to, at = 0, dur = 1.1, style, suffix = ''}) => {
	const p = prog(useT(), at, dur, eio);
	return <span style={style}>{fa(Math.round(to * p).toLocaleString('en-US'))}{suffix}</span>;
};

/** words stacked on top of each other at very different sizes (the typographic hit): each {t, size, weight?, accent?, at?} */
export const WordStack: React.FC<{words: {t: string; size: number; weight?: number; accent?: boolean; at?: number}[]; align?: 'center' | 'right' | 'left'; gap?: number}> = ({words, align = 'center', gap = -6}) => (
	<div style={{display: 'flex', flexDirection: 'column', alignItems: align === 'center' ? 'center' : align === 'right' ? 'flex-end' : 'flex-start', direction: 'rtl', gap}}>
		{words.map((w, i) => (
			<Rise key={i} at={w.at ?? i * 0.18} y={30}>
				<div style={{fontFamily: D, fontWeight: w.weight ?? 800, fontSize: w.size, lineHeight: 1.08, whiteSpace: 'nowrap', textShadow: '0 6px 24px rgba(0,0,0,0.45)', ...(w.accent ? goldText : {color: CREAM})}}>{w.t}</div>
			</Rise>
		))}
	</div>
);

/** a notification rows stack like a phone's: rows = [{title, sub}] slide in one after another; the older ones recede */
export const NotifStack: React.FC<{rows: {title: string; sub?: string; tag?: string}[]; at?: number; step?: number; width?: number}> = ({rows, at = 0, step = 0.28, width = 640}) => {
	const t = useT();
	return (
		<div style={{position: 'relative', width, height: 150 + rows.length * 46}}>
			{rows.map((r, i) => {
				const p = prog(t, at + i * step, 0.4);
				const depth = rows.length - 1 - i;
				return (
					<div key={i} style={{position: 'absolute', left: 0, right: 0, top: i * 46 + (1 - p) * -30, opacity: p, direction: 'rtl', transform: `scale(${1 - depth * 0.02})`, transformOrigin: 'center top'}}>
						<Glass style={{display: 'flex', alignItems: 'center', gap: 16, padding: '14px 22px', borderRadius: 26, width}}>
							<div style={{width: 46, height: 46, borderRadius: 14, background: `linear-gradient(160deg, ${GOLD}, rgba(255,255,255,0.4))`, display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 'none'}}>
								<Icon k="chat" s={30} />
							</div>
							<div style={{flex: 1, minWidth: 0}}>
								<div style={{display: 'flex', justifyContent: 'space-between', fontFamily: D, fontWeight: 700, fontSize: 28, color: CREAM}}>
									<span>{r.title}</span>
									{r.tag && <span style={{fontWeight: 400, fontSize: 22, opacity: 0.6}}>{r.tag}</span>}
								</div>
								{r.sub && <div style={{fontFamily: D, fontWeight: 400, fontSize: 24, color: 'rgba(247,238,223,0.75)', whiteSpace: 'nowrap', overflow: 'hidden'}}>{r.sub}</div>}
							</div>
						</Glass>
					</div>
				);
			})}
		</div>
	);
};

/** a chat bubble: side 'in' (grey, left) or 'out' (green-tinted, right) */
export const Bubble: React.FC<{text: string; side?: 'in' | 'out'; at?: number; time?: string; size?: number}> = ({text, side = 'in', at = 0, time, size = 34}) => {
	const s = useSp(at, 13, 0.7);
	const t = useT();
	return (
		<div style={{display: 'flex', justifyContent: side === 'out' ? 'flex-end' : 'flex-start', opacity: prog(t, at, 0.12), transform: `scale(${interpolate(s, [0, 1], [0.7, 1])})`, transformOrigin: side === 'out' ? 'bottom right' : 'bottom left'}}>
			<div style={{direction: 'rtl', maxWidth: 560, padding: '14px 24px 12px', borderRadius: 28, borderBottomLeftRadius: side === 'in' ? 6 : 28, borderBottomRightRadius: side === 'out' ? 6 : 28, background: side === 'out' ? 'rgba(120,214,150,0.92)' : 'rgba(244,244,246,0.94)', color: '#1a1a1a', fontFamily: D, fontWeight: 600, fontSize: size, lineHeight: 1.3, boxShadow: '0 10px 30px rgba(0,0,0,0.25)'}}>
				{text}
				{time && <div style={{fontSize: 18, fontWeight: 400, opacity: 0.5, textAlign: 'left', direction: 'ltr', marginTop: 2}}>{time}</div>}
			</div>
		</div>
	);
};

/** a round app-style badge: an icon in a glass circle with a label under it */
export const AppIcon: React.FC<{icon: string; label?: string; at?: number; size?: number}> = ({icon, label, at = 0, size = 120}) => (
	<Pop at={at} rot={-6}>
		<div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6}}>
			<div style={{width: size, height: size, borderRadius: '50%', background: `linear-gradient(160deg, ${P.glass[0]}, ${P.glass[1]})`, border: `1.5px solid ${P.glassBorder}`, backdropFilter: 'blur(16px)', boxShadow: '0 16px 40px rgba(0,0,0,0.35)', display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
				<Icon k={icon} s={size * 0.55} />
			</div>
			{label && <div style={{fontFamily: D, fontWeight: 700, fontSize: Math.max(24, size * 0.26), color: CREAM, textShadow: '0 3px 12px rgba(0,0,0,0.6)'}}>{label}</div>}
		</div>
	</Pop>
);

/** numbered steps in circles joined by little arrows (a countdown or a process); `active` = the step lit now (0-based; -1 = none) */
export const Steps: React.FC<{labels?: string[]; n?: number; active?: number; at?: number; size?: number}> = ({labels, n = 3, active = -1, at = 0, size = 84}) => {
	const t = useT();
	const items = labels ?? Array.from({length: n}, (_, i) => fa(i + 1));
	return (
		<div style={{display: 'flex', alignItems: 'center', gap: 16, direction: 'ltr'}}>
			{items.map((l, i) => {
				const p = prog(t, at + i * 0.15, 0.35);
				const on = i === active;
				return (
					<React.Fragment key={i}>
						{i > 0 && <div style={{width: 34, height: 3, borderRadius: 2, background: 'rgba(255,255,255,0.45)', opacity: p}} />}
						<div style={{width: size, height: size, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: D, fontWeight: 800, fontSize: size * 0.5, color: on ? '#1a1a1a' : CREAM, background: on ? P.goldGrad : `linear-gradient(160deg, ${P.glass[0]}, ${P.glass[1]})`, border: `2px solid ${on ? 'transparent' : P.glassBorder}`, opacity: p, transform: `scale(${0.7 + 0.3 * p + (on ? 0.1 : 0)})`, boxShadow: on ? `0 0 30px rgba(${P.leak2},0.7)` : '0 10px 26px rgba(0,0,0,0.3)'}}>{l}</div>
					</React.Fragment>
				);
			})}
		</div>
	);
};

/** a label pill (a small tag: «جدید», a name, a price) */
export const Pill: React.FC<{children: React.ReactNode; at?: number; accent?: boolean; size?: number}> = ({children, at = 0, accent, size = 34}) => (
	<Pop at={at} from={0.6}>
		<div style={{direction: 'rtl', display: 'inline-block', padding: '8px 24px 12px', borderRadius: 999, fontFamily: D, fontWeight: 700, fontSize: size, whiteSpace: 'nowrap', color: accent ? '#1a1a1a' : CREAM, background: accent ? P.goldGrad : P.pill, border: accent ? 'none' : `1px solid ${P.glassBorder}`, backdropFilter: 'blur(12px)', boxShadow: '0 10px 28px rgba(0,0,0,0.3)'}}>{children}</div>
	</Pop>
);
