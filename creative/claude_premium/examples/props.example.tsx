import React from 'react';
import {interpolate} from 'remotion';
import {AppIcon, Bubble, Counter, Curl, D, GOLD, CREAM, Mark, NotifStack, Pill, Pop, Rise, Steps, Typed, WordStack, fa, goldText, prog, useSp, useT} from './gfx';
import type {GP} from './gfx';

/* THE STANDARD. Graphics of another film, in the quality wanted: each one illustrates what is being SAID with a designed object (a phone notification stack, a chat, a countdown, a stacked typographic hit, a
   hand-drawn pointer), glass or text with a soft shadow so the video shows through, small enough to sit beside the speaker, one idea per graphic, every step landing on a spoken word through k(i). */

/* zone "lower" (960 x ~480): «پیام می‌دادن ... ۵ تا پیام» -> notifications arrive one after another, a tag pops on the last */
export const G_notifications: React.FC<GP> = ({k, w}) => {
	const t = useT();
	const first = k(12);
	return (
		<div style={{position: 'absolute', left: (w - 640) / 2, top: 10}}>
			<NotifStack
				at={first}
				step={0.32}
				rows={[
					{title: 'پیام جدید', sub: 'سلام، قیمت این چنده؟', tag: 'الان'},
					{title: 'پیام جدید', sub: 'ممنون، بعداً خبر می‌دم', tag: 'الان'},
					{title: 'پیام جدید', sub: 'میشه تخفیف بدین؟', tag: 'الان'},
				]}
			/>
			<div style={{position: 'absolute', right: -30, top: -26, opacity: prog(t, k(15), 0.2)}}>
				<Pill accent at={k(15)}>{fa(3)} بی‌جواب</Pill>
			</div>
		</div>
	);
};

/* zone "lower": «بین سه دستگاه موندم» -> a countdown of steps lighting up on the spoken numbers */
export const G_countdown: React.FC<GP> = ({k, w}) => {
	const t = useT();
	const a = t >= k(30) ? 2 : t >= k(29) ? 1 : t >= k(28) ? 0 : -1;
	return (
		<div style={{position: 'absolute', left: 0, width: w, top: 30, display: 'flex', justifyContent: 'center'}}>
			<Steps n={3} active={a} at={k(27)} />
		</div>
	);
};

/* zone "left" (~300 x 560): «این جزوه رو بهت هدیه می‌دم» -> small stacked words beside the head and a hand-drawn pointer that draws itself down toward the lap */
export const G_gift_note: React.FC<GP> = ({k, w, h}) => {
	const t = useT();
	return (
		<div style={{position: 'absolute', inset: 0}}>
			<div style={{position: 'absolute', right: 0, top: 20}}>
				<WordStack align="right" words={[{t: 'این', size: 40, weight: 500, at: k(40)}, {t: 'جزوه', size: 86, accent: true, at: k(41)}, {t: 'هدیه', size: 64, weight: 800, at: k(43)}, {t: 'از من', size: 40, weight: 500, at: k(44)}]} />
			</div>
			<div style={{position: 'absolute', left: 0, top: 250, width: w, height: h - 250}}>
				<Curl d={`M ${w * 0.7},10 C ${w * 0.1},60 ${w * 0.05},${(h - 250) * 0.5} ${w * 0.6},${h - 270} M ${w * 0.6},${h - 270} l -16,-34 M ${w * 0.6},${h - 270} l 30,-18`} w={w} h={h - 250} at={k(43)} dur={0.8} length={900} />
			</div>
		</div>
	);
};

/* zone "lower": a short dialogue -> two chat bubbles, the answer typed */
export const G_chat: React.FC<GP> = ({k, w}) => (
	<div style={{position: 'absolute', left: 80, width: w - 160, top: 10, display: 'flex', flexDirection: 'column', gap: 16}}>
		<Bubble side="in" text="سلام، چیشد؟" at={k(52)} time="۱۲:۴۰" />
		<Bubble side="out" text="الان جواب می‌دم" at={k(58)} time="۱۲:۴۱" />
	</div>
);

/* zone "lower": the typographic hit on a key phrase: «حقیقت بین دستگاه‌ها متفاوته» (a big word in the warm colour, the rest small), the key word marked */
export const G_big_hit: React.FC<GP> = ({k, w}) => {
	const s = useSp(k(66), 12, 0.8, 180);
	const t = useT();
	return (
		<div style={{position: 'absolute', left: 0, width: w, top: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', direction: 'rtl'}}>
			<Rise at={k(64)}><div style={{fontFamily: D, fontWeight: 400, fontSize: 52, color: CREAM, textShadow: '0 4px 18px rgba(0,0,0,0.6)'}}>حقیقتِ بین دستگاه‌ها</div></Rise>
			<div style={{transform: `scale(${interpolate(s, [0, 1], [1.5, 1])})`, opacity: prog(t, k(66), 0.1)}}>
				<Mark at={k(66) + 0.1}><span style={{fontFamily: D, fontWeight: 900, fontSize: 150, lineHeight: 1.1, color: CREAM, textShadow: '0 8px 30px rgba(0,0,0,0.5)'}}>متفاوته</span></Mark>
			</div>
		</div>
	);
};

/* zone "right" (~300 x 560): «تعداد ۲۰ تا» -> a counting number in a small glass badge with an app icon */
export const G_count_badge: React.FC<GP> = ({k, w}) => (
	<div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18, paddingTop: 30}}>
		<AppIcon icon="chat" at={k(70)} size={110} />
		<Pop at={k(71)}>
			<div style={{fontFamily: D, fontWeight: 900, fontSize: Math.min(120, w * 0.36), ...goldText, textShadow: undefined}}>
				<Counter to={20} at={k(71)} dur={0.9} />
			</div>
		</Pop>
	</div>
);
