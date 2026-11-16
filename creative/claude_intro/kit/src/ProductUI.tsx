import React from 'react';
import {CONTENT, clamp, seg, eo5, fa, markPath, markScale, rnd} from './lib';

// The product's interface on the laptop screen (1280x800): a chat-style studio in the product's own tokens and words (content.json: ui).
// It is a rebuilt interface, not a screen recording: the numbers and project names in it are samples.
const U: any = CONTENT.ui ?? {};
const TK: any = U.tokens ?? {};
export const UI_W = 1280, UI_H = 800;
const K = {bg: TK.bg ?? '#101010', side: TK.sidebar ?? '#171717', surf: TK.surface ?? '#202020', el: TK.elevated ?? '#262626', bd: TK.border ?? '#343434', tx: TK.text ?? '#f5f5f5', t2: '#a3a3a3', t3: '#8a8a8a', ok: '#4ade80', acc: TK.accent ?? '#f7a600'};
export const PROMPT: string = U.prompt ?? '';
// narrative clock u (seconds): 0 home · 1–4.2 typing · 4.6 send · 5–17 working · 17–24 timeline/render · 24+ done
export const STEPS: string[] = (U.steps ?? []).slice(0, 6);

const Side: React.FC = () => (
	<div style={{position: 'absolute', right: 0, top: 0, bottom: 0, width: 300, background: K.side, borderLeft: `1px solid ${K.bd}`}}>
		<div style={{display: 'flex', alignItems: 'center', gap: 12, padding: '22px 22px 18px', direction: 'rtl'}}>
			<div style={{width: 36, height: 36, borderRadius: 10, background: K.tx, display: 'grid', placeItems: 'center'}}>
				<svg width={22} height={22} viewBox="-11 -11 22 22"><path d={markPath(10, 0.28)} fill={K.bg} transform={`scale(${markScale(10)})`} /></svg>
			</div>
			<div style={{fontSize: 20, fontWeight: 700, color: K.tx}}>{U.app ?? CONTENT.brand}</div>
		</div>
		{((U.nav ?? []) as string[]).slice(0, 4).map((n, i) => (
			<div key={i} style={{margin: '4px 12px', padding: '12px 14px', borderRadius: 10, background: i === 1 ? K.el : 'transparent', color: K.tx, fontSize: 18, direction: 'rtl'}}>{n}</div>
		))}
		<div style={{margin: '26px 26px 8px', color: K.t3, fontSize: 14, direction: 'rtl'}}>{U.recent_label ?? ''}</div>
		{((U.recent ?? []) as string[]).slice(0, 4).map((n, i) => (
			<div key={i} style={{margin: '2px 12px', padding: '9px 14px', color: K.t2, fontSize: 16, direction: 'rtl'}}>{n}</div>
		))}
	</div>
);

const Composer: React.FC<{text: string; caret: boolean; y: number; sent?: boolean}> = ({text, caret, y}) => (
	<div style={{position: 'absolute', left: 60, right: 360, top: y, height: 128, borderRadius: 22, background: K.surf, border: `1px solid ${K.bd}`, direction: 'rtl'}}>
		<div style={{padding: '22px 26px', fontSize: 25, color: text ? K.tx : K.t3, whiteSpace: 'nowrap'}}>
			{text || (U.placeholder ?? '')}
			{caret && <span style={{display: 'inline-block', width: 3, height: 30, background: K.tx, verticalAlign: 'middle', marginRight: 3}} />}
		</div>
		<div style={{position: 'absolute', left: 16, bottom: 14, width: 46, height: 46, borderRadius: 46, background: text ? K.tx : '#5a5a5a', display: 'grid', placeItems: 'center', color: K.bg, fontSize: 24, fontFamily: 'VazL'}}>↑</div>
		<div style={{position: 'absolute', right: 22, bottom: 20, fontSize: 16, color: K.t2, display: 'flex', gap: 14, alignItems: 'center'}}>
			<span style={{fontSize: 24}}>+</span>
			{U.attachment && <span style={{padding: '4px 12px', borderRadius: 8, background: K.el, display: 'inline-flex', gap: 8}}>{U.attachment}</span>}
				<span>{U.model ?? ''}</span>
			</div>
	</div>
);

const Reel: React.FC<{x: number; y: number; w: number; p?: number; title?: boolean}> = ({x, y, w, p = 1, title}) => {
	const h = (w * 16) / 9;
	return (
		<div style={{position: 'absolute', left: x, top: y, width: w, height: h, borderRadius: 16, overflow: 'hidden', background: 'linear-gradient(160deg,#2b3b4f,#101820 60%,#3a2414)', border: `1px solid ${K.bd}`}}>
			<div style={{position: 'absolute', left: '26%', top: '20%', width: '48%', height: '34%', borderRadius: '45% 45% 40% 40%', background: 'linear-gradient(#c9a184,#8a6a55)'}} />
			<div style={{position: 'absolute', left: '10%', top: '50%', width: '80%', height: '55%', borderRadius: '40% 40% 0 0', background: '#16181c'}} />
			{title && <div style={{position: 'absolute', left: 0, right: 0, bottom: '17%', textAlign: 'center', fontSize: w * 0.085, fontWeight: 800, color: '#fff', direction: 'rtl', lineHeight: 1.5}}>{(U.preview ?? [])[0] ?? ''} <span style={{color: K.acc}}>{(U.preview ?? [])[1] ?? ''}</span></div>}
			<div style={{position: 'absolute', left: '8%', right: '8%', bottom: '6%', height: 5, borderRadius: 5, background: 'rgba(255,255,255,.25)'}}><div style={{width: `${p * 100}%`, height: '100%', background: '#fff', borderRadius: 5, marginRight: 'auto'}} /></div>
		</div>
	);
};

export const ProductUI: React.FC<{u: number}> = ({u}) => {
	const typed = clamp(Math.floor((u - 1) / 0.11), 0, PROMPT.length);
	// reveal whole words only (Persian letters join)
	const words = PROMPT.split(' ');
	let acc = 0, shown = '';
	for (const w of words) { acc += w.length + 1; if (typed >= acc - 1) shown += (shown ? ' ' : '') + w; }
	const home = u < 4.9;
	const work = u >= 4.9 && u < 24;
	const done = u >= 24;
	const stepT = (i: number) => 5.6 + i * 2.2; // step i starts
	const pr = seg(u, 17, 23.6);
	const mm = Math.floor(Math.max(0, u - 4.9) * 9.4), clock = `${fa(String(Math.floor(mm / 60)).padStart(2, '0'))}:${fa(String(mm % 60).padStart(2, '0'))}`;
	return (
		<div style={{width: UI_W, height: UI_H, background: K.bg, position: 'relative', fontFamily: 'Vaz, VazL', fontWeight: 500, overflow: 'hidden', color: K.tx}}>
			<Side />
			{home && (
				<>
					<div style={{position: 'absolute', left: 0, right: 300, top: 150, textAlign: 'center', fontSize: 40, fontWeight: 700, direction: 'rtl'}}>{U.heading ?? ''}</div>
					<Composer text={shown} caret={u > 0.6 && (u < 4.3 ? true : Math.floor(u * 2) % 2 === 0)} y={236} />
					<div style={{position: 'absolute', left: 60, right: 360, top: 392, display: 'flex', gap: 12, justifyContent: 'center', direction: 'rtl'}}>
						{((U.chips ?? []) as string[]).slice(0, 3).map((c, i) => <div key={i} style={{padding: '10px 18px', borderRadius: 40, border: `1px solid ${K.bd}`, color: K.t2, fontSize: 16}}>{c}</div>)}
					</div>
				</>
			)}
			{(work || done) && (
				<>
					<div style={{position: 'absolute', left: 0, right: 300, top: 0, height: 58, borderBottom: `1px solid ${K.bd}`, direction: 'rtl', display: 'flex', alignItems: 'center', padding: '0 28px', fontSize: 18, justifyContent: 'space-between'}}>
						<span>{U.project ?? ''}</span>
						<span style={{color: done ? K.ok : K.t2, fontSize: 16, direction: 'rtl'}}>{done ? (U.ready ?? '✓') : `${U.working ?? ''} · ${clock}`}</span>
					</div>
					{/* user bubble */}
					<div style={{position: 'absolute', right: 330, top: 82, padding: '14px 22px', borderRadius: 20, background: K.el, fontSize: 21, direction: 'rtl'}}>{PROMPT}</div>
					{/* assistant steps */}
					<div style={{position: 'absolute', right: 330, top: 160, width: 420, direction: 'rtl'}}>
						<div style={{fontSize: 18, color: K.t2, lineHeight: 1.7, opacity: seg(u, 5.1, 5.5)}}>{U.reply ?? ''}</div>
						{STEPS.map((s, i) => {
							const a = seg(u, stepT(i), stepT(i) + 0.3), fin = u > stepT(i + 1) || done;
							return (
								<div key={i} style={{display: 'flex', alignItems: 'center', gap: 12, marginTop: 13, opacity: a, fontSize: 20}}>
									<span style={{width: 24, height: 24, borderRadius: 24, border: `2px solid ${fin ? K.ok : K.t3}`, background: fin ? K.ok : 'transparent', color: K.bg, display: 'grid', placeItems: 'center', fontSize: 15, fontFamily: 'VazL', borderTopColor: fin ? K.ok : K.tx, transform: fin ? undefined : `rotate(${u * 300}deg)`}}>{fin ? '✓' : ''}</span>
									<span style={{color: fin ? K.tx : K.t2}}>{s}</span>
								</div>
							);
						})}
					</div>
					{/* preview / storyboard / timeline */}
					<div style={{position: 'absolute', left: 30, top: 82, width: 480, bottom: 30, borderRadius: 18, background: K.side, border: `1px solid ${K.bd}`}}>
						<div style={{position: 'absolute', right: 20, top: 14, fontSize: 15, color: K.t3, direction: 'rtl'}}>{(U.panel ?? ['', '', ''])[done ? 2 : u < 12 ? 0 : 1]}</div>
						{u < 12 ? (
							[0, 1, 2, 3, 4, 5].map((i) => {
								const a = eo5(seg(u, 7.6 + i * 0.5, 8.1 + i * 0.5));
								return (
									<div key={i} style={{position: 'absolute', left: 22 + (i % 3) * 148, top: 52 + Math.floor(i / 3) * 290, width: 136, height: 270, borderRadius: 12, background: i === 0 ? K.tx : K.el, opacity: a, transform: `translateY(${(1 - a) * 20}px)`}}>
										<div style={{position: 'absolute', right: 12, top: 10, fontSize: 13, color: i === 0 ? K.bg : K.t2, direction: 'rtl'}}>{fa(i + 1)}{(U.board ?? [])[i] ? ` · ${U.board[i]}` : ''}</div>
										{[0, 1, 2].map((k) => <div key={k} style={{position: 'absolute', right: 12, top: 44 + k * 18, height: 7, width: 60 + rnd(i * 5 + k) * 50, borderRadius: 4, background: i === 0 ? K.bg : K.t3, opacity: 0.55}} />)}
										<div style={{position: 'absolute', left: 12, right: 12, bottom: 12, height: 120, borderRadius: 8, background: i === 0 ? '#d9d9d9' : '#1a1a1a'}} />
									</div>
								);
							})
						) : (
							<>
								<Reel x={150} y={46} w={180} p={done ? 1 : pr} title={u > 13} />
								{[[(U.tracks ?? [])[0] ?? '', '#6b6b6b'], [(U.tracks ?? [])[1] ?? '', K.acc], [(U.tracks ?? [])[2] ?? '', '#7d8cff'], [(U.tracks ?? [])[3] ?? '', '#58b28a']].map(([n, c], i) => (
									<div key={i} style={{position: 'absolute', left: 22, right: 22, top: 392 + i * 40, height: 30}}>
										<div style={{position: 'absolute', right: 0, top: 4, fontSize: 14, color: K.t2, direction: 'rtl'}}>{n}</div>
										<div style={{position: 'absolute', left: 0, right: 62, top: 0, bottom: 0, borderRadius: 6, background: '#1f1f1f'}}>
											{[0, 1, 2, 3].slice(0, i === 3 ? 1 : i === 2 ? 2 : 4).map((k) => {
												const n4 = i === 3 ? 1 : i === 2 ? 2 : 4, a0 = i === 2 ? 0.2 + k * 0.4 : k / n4, wd = i === 2 ? 0.22 : 1 / n4 - 0.015;
												return <div key={k} style={{position: 'absolute', right: `${a0 * 100}%`, width: `${wd * 100 * eo5(seg(u, 12.3 + i * 0.5 + k * 0.25, 12.9 + i * 0.5 + k * 0.25))}%`, top: 4, bottom: 4, borderRadius: 5, background: c as string}} />;
											})}
										</div>
									</div>
								))}
								<div style={{position: 'absolute', left: 22, right: 22, bottom: 58, height: 8, borderRadius: 8, background: '#2a2a2a', direction: 'rtl'}}><div style={{width: `${(done ? 1 : pr) * 100}%`, height: '100%', borderRadius: 8, background: done ? K.ok : K.tx}} /></div>
								<div style={{position: 'absolute', left: 22, right: 22, bottom: 22, fontSize: 15, color: K.t2, direction: 'rtl', display: 'flex', justifyContent: 'space-between'}}>
									<span>{done ? (U.status ?? ['', '', ''])[2] : u < 17 ? (U.status ?? ['', '', ''])[0] : `${(U.status ?? ['', '', ''])[1]} · ${fa(Math.floor(pr * (U.count ?? 1440)))} / ${fa(U.count ?? 1440)}`}</span>
									<span>{fa(Math.floor((done ? 1 : pr) * 100))}٪</span>
								</div>
							</>
						)}
					</div>
					{done && (
						<div style={{position: 'absolute', right: 330, top: 520, width: 420, direction: 'rtl', opacity: seg(u, 24.2, 24.8)}}>
							<div style={{fontSize: 44, fontWeight: 800}}>{(U.done ?? [])[0] ?? ''}</div>
							<div style={{fontSize: 18, color: K.t2, marginTop: 8}}>{(U.done ?? [])[1] ?? ''}</div>
							<div style={{display: 'flex', gap: 12, marginTop: 20}}>
								<div style={{padding: '12px 22px', borderRadius: 12, background: K.tx, color: K.bg, fontSize: 18, fontWeight: 700}}>{(U.buttons ?? [])[0] ?? ''}</div>
								{(U.buttons ?? [])[1] && <div style={{padding: '12px 22px', borderRadius: 12, border: `1px solid ${K.bd}`, fontSize: 18}}>{U.buttons[1]}</div>}
							</div>
						</div>
					)}
				</>
			)}
		</div>
	);
};
