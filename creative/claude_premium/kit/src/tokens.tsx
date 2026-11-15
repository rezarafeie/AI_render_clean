import React from 'react';
import {Easing} from 'remotion';
import data from './data.json';

/* Tokens shared by the kit and by the graphics written for a video: the palette, the fonts, the easing, the helpers. */

export const W = 1080;
export const H = 1920;
export const FPS = (data as any).fps as number;
export const SRC_W = (data as any).video.w as number;
export const SRC_H = (data as any).video.h as number;
export const D = 'Doran';
export const SERIF = 'Playfair Display';

const PALETTES: Record<string, any> = {
	'cream-gold-espresso': {cream: '#F7EEDF', gold: '#E9C27A', goldGrad: 'linear-gradient(180deg, #FFF6DF 0%, #F1D79C 45%, #D4A24E 100%)', darkGrad: 'linear-gradient(180deg, #4A331A 0%, #22170C 55%, #0F0A05 100%)', ink: '#2E2114', glow: '255,240,215', leak1: '255,150,60', leak2: '255,205,120', vig: '20,10,0', glass: ['rgba(40,30,20,0.55)', 'rgba(15,12,10,0.45)'], glassBorder: 'rgba(255,235,200,0.28)', pill: 'rgba(18,14,10,0.42)', rule: 'rgba(255,235,200,0.35)'},
	'ice-blue-silver': {cream: '#EEF4FA', gold: '#9CC8F0', goldGrad: 'linear-gradient(180deg, #FFFFFF 0%, #CFE3F5 45%, #8FB4D9 100%)', darkGrad: 'linear-gradient(180deg, #27425E 0%, #142234 55%, #08111C 100%)', ink: '#142234', glow: '220,236,255', leak1: '90,150,255', leak2: '160,210,255', vig: '0,8,20', glass: ['rgba(20,32,48,0.55)', 'rgba(8,14,22,0.45)'], glassBorder: 'rgba(200,225,255,0.28)', pill: 'rgba(8,14,22,0.42)', rule: 'rgba(200,225,255,0.35)'},
	'mono-red': {cream: '#FFFFFF', gold: '#FF5A47', goldGrad: 'linear-gradient(180deg, #FF9C8E 0%, #FF5A47 50%, #C41E12 100%)', darkGrad: 'linear-gradient(180deg, #3A0E0A 0%, #1A0605 55%, #0A0202 100%)', ink: '#1A0605', glow: '255,225,220', leak1: '255,70,50', leak2: '255,140,110', vig: '20,0,0', glass: ['rgba(40,14,12,0.6)', 'rgba(14,6,5,0.5)'], glassBorder: 'rgba(255,200,190,0.28)', pill: 'rgba(20,6,5,0.5)', rule: 'rgba(255,200,190,0.35)'},
	'black-neon-green': {cream: '#F2FFF6', gold: '#3BE37A', goldGrad: 'linear-gradient(180deg, #D8FFE6 0%, #6EF0A0 50%, #1FA463 100%)', darkGrad: 'linear-gradient(180deg, #123A22 0%, #08170E 55%, #020805 100%)', ink: '#08170E', glow: '200,255,220', leak1: '40,220,120', leak2: '120,255,180', vig: '0,10,4', glass: ['rgba(10,30,18,0.6)', 'rgba(4,12,8,0.5)'], glassBorder: 'rgba(160,255,200,0.28)', pill: 'rgba(4,14,8,0.5)', rule: 'rgba(160,255,200,0.35)'},
	'coral-beige': {cream: '#FFF8F0', gold: '#F08A6C', goldGrad: 'linear-gradient(180deg, #FFE2D4 0%, #F5A98B 50%, #E8705A 100%)', darkGrad: 'linear-gradient(180deg, #5A3A2E 0%, #2E1C16 55%, #140A07 100%)', ink: '#3A2218', glow: '255,236,225', leak1: '255,140,100', leak2: '255,200,160', vig: '25,8,0', glass: ['rgba(60,34,26,0.55)', 'rgba(24,12,9,0.45)'], glassBorder: 'rgba(255,225,210,0.3)', pill: 'rgba(30,14,10,0.45)', rule: 'rgba(255,225,210,0.35)'},
};
export const STYLE = ((data as any).style ?? {}) as any;
export const P = PALETTES[STYLE.palette] ?? PALETTES['cream-gold-espresso'];
export const CREAM = P.cream as string;
export const GOLD = P.gold as string;
export const goldText: React.CSSProperties = {background: P.goldGrad, WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent'};
export const darkText: React.CSSProperties = {background: P.darkGrad, WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent'};
export const behindStyle: React.CSSProperties = STYLE.behindInk === 'light' ? goldText : darkText;
export const behindGlow = STYLE.behindInk === 'light' ? 'drop-shadow(0 6px 18px rgba(0,0,0,0.55))' : `drop-shadow(0 6px 18px rgba(${P.glow},0.5))`;
export const behindSub = STYLE.behindInk === 'light' ? CREAM : (P.ink as string);
export const CAP_Y = (STYLE.capY as number) ?? 1180;
export const FACE_TARGET_Y = (STYLE.faceTargetY as number) ?? 740;
export const BASE_Z = ((STYLE.baseZoom as number[]) ?? [1.0, 1.12, 1.04, 1.16, 1.0, 1.1]) as number[];

export const clamp = (x: number) => Math.max(0, Math.min(1, x));
export const eo = Easing.bezier(0.16, 1, 0.3, 1);
export const eio = Easing.bezier(0.65, 0, 0.35, 1);
export const prog = (t: number, at: number, d = 0.4, e = eo) => e(clamp((t - at) / d));
export const fa = (n: number | string) => String(n).replace(/[0-9]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[+d]);
/** a font size that keeps `chars` letters of Persian inside `maxW` px */
export const fit = (size: number, chars: number, maxW: number, k = 0.56) => Math.min(size, Math.floor(maxW / Math.max(1, chars * k)));

