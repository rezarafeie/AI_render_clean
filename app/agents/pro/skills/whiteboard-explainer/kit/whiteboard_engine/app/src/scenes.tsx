import data from './data.json';
import {S, cat, mkPath, mkText, mkDash, Item, INK, NUM, Cam, zig} from './engine';

type Word = {t: string; s: number; e: number};
export const SC = data.scenes as {id: string; start: number; dur: number; words: Word[]; split: any}[];
export const TOTAL = data.total as number;
const st = (i: number) => SC[i - 1].start;
const en = (i: number) => SC[i - 1].start + SC[i - 1].dur;
const norm = (s: string) => s.replace(/[«»،؛:.؟!,]/g, '');
export const c = (i: number, w: string, occ = 0, off = 0) => {
	const ws = SC[i - 1].words.filter((x) => norm(x.t) === w || norm(x.t).startsWith(w));
	const m = ws[occ] ?? ws[0];
	if (!m) throw new Error(`word ${w} not in scene ${i}`);
	return st(i) + m.s + off;
};

// ---------- board layout ----------
export const BOARD = {w: 3600, h: 7550};
const cell = (r: number, col: number) => ({x: col * 1200, y: 1300 + (r - 1) * 1650});
const HDR = {x: 0, y: 0}, FTR = {x: 0, y: 6250};
export const CELLS = [HDR, HDR, cell(1, 2), cell(1, 1), cell(1, 0), cell(2, 0), cell(2, 1), cell(2, 2), cell(3, 2), cell(3, 1), cell(3, 0), FTR];
const view = (i: number, z = 0.95): Cam => {
	const o = CELLS[i];
	if (i === 1) return {t: 0, x: 1800, y: 937, z};
	if (i === 11) return {t: 0, x: 1800, y: 6250 + 820, z};
	return {t: 0, x: o.x + 600, y: o.y + 935, z};
};
export const FULL: Cam = {t: 0, x: 1800, y: BOARD.h / 2 + 40, z: 0.236};

export const ITEMS: Item[] = [];
export const EV: {t: number; k: string; g: number}[] = [];
export const MAGNETS: {kind: 'box' | 'card'; t0: number; t1?: number; path?: number[][]; x?: number; y?: number; col: string; title?: string; sub?: string}[] = [];
const ev = (t: number, k: string, g = 0.5) => EV.push({t, k, g});

const B = (ox: number, oy: number) => ({
	P: (t0: number, dur: number, col: string, paths: any, o: Partial<Item> = {}) => {
		const it = mkPath(t0, dur, col, paths, {ox, oy, ...o});
		ITEMS.push(it);
		return it;
	},
	D: (t0: number, dur: number, col: string, paths: any, o: Partial<Item> = {}) => {
		const it = mkDash(t0, dur, col, paths, {ox, oy, ...o});
		ITEMS.push(it);
		return it;
	},
	T: (t0: number, text: string, x: number, y: number, size: number, col: string, o: Partial<Item> = {}) => {
		const it = mkText(t0, text, x, y, size, col, {ox, oy, ...o});
		ITEMS.push(it);
		return it;
	},
});

// ---------- icon helpers (local coords) ----------
const star = (cx: number, cy: number, r: number) => {
	const pts: number[][] = [];
	for (let k = 0; k < 10; k++) {
		const a = -Math.PI / 2 + (k * Math.PI) / 5, rr = k % 2 ? r * 0.45 : r;
		pts.push([cx + rr * Math.cos(a), cy + rr * Math.sin(a)]);
	}
	return pts;
};
const stick = (x: number, y: number, s = 1, happy = false) =>
	cat(
		S.circle(x, y - 130 * s, 80 * s),
		S.line(x, y - 90 * s, x, y + 40 * s),
		S.line(x, y - 50 * s, x - 55 * s, y + 5 * s),
		S.line(x, y - 50 * s, x + 55 * s, y - 25 * s),
		S.line(x, y + 40 * s, x - 38 * s, y + 130 * s),
		S.line(x, y + 40 * s, x + 38 * s, y + 130 * s),
		happy ? S.arc(x, y - 125 * s, 44 * s, 30 * s, 0.3, Math.PI - 0.3, {roughness: 0.4}) : [],
	);
const badge = (b: ReturnType<typeof B>, t: number, tn: number, label: string, isStar = false) => {
	b.P(t, 0.32, INK.b, S.circle(1060, 150, 124, {roughness: 0.7}), {snd: 'marker'});
	if (isStar) b.P(tn, 0.4, INK.b, S.closed(star(1060, 152, 40)), {w: 6});
	else b.T(tn, label, 1060, 180, 82, INK.b, {font: NUM, weight: 800, center: true, dur: 0.3});
	ev(t, 'pop', 0.25);
};
const title = (b: ReturnType<typeof B>, t: number, text: string, size = 90) => b.T(t, text, 985, 182, size, INK.k, {dur: Math.min(1.1, 0.3 + text.length * 0.05)});

// ---------- road ----------
const roadPts = (i: number): number[][] => {
	const A = CELLS[i - 1], Bc = CELLS[i];
	if (i === 2) return [[2300, 1180], [3460, 1180], [3460, 1300 + 84]];
	if (i === 11) return [[A.x + 1124, A.y + 150], [A.x + 1170, A.y + 150], [1170, 6250 + 110], [1318, 6250 + 110]];
	if (A.y === Bc.y) return [[A.x + 1060, A.y + 86], [A.x + 1060, A.y + 30], [Bc.x + 1060, Bc.y + 30], [Bc.x + 1060, Bc.y + 86]];
	return [[A.x + 1124, A.y + 150], [A.x + 1170, A.y + 150], [A.x + 1170, Bc.y + 150], [Bc.x + 1124, Bc.y + 150]];
};
for (let i = 2; i <= 11; i++) {
	const t0 = st(i) - 0.78;
	ITEMS.push(mkDash(t0, 0.72, INK.b, S.poly(roadPts(i), {roughness: 0.5}), {w: 9, snd: 'marker2'}));
	ev(st(i) - 0.8, 'whoosh', 0.32);
}

// ---------- scene 1: hook (header) ----------
{
	const b = B(0, 0);
	// online shop
	const sx = 2110;
	b.P(st(1) + 0.02, 0.95, INK.k, cat(
		S.rect(sx - 135, 550, 270, 230),
		S.rect(sx - 150, 480, 300, 70),
		S.path(`M${sx - 150},550 q25,40 50,0 q25,40 50,0 q25,40 50,0 q25,40 50,0 q25,40 50,0 q25,40 50,0`, {roughness: 0.5}),
		S.rect(sx - 40, 630, 80, 150),
		S.rect(sx - 115, 590, 58, 58),
	));
	b.P(c(1, 'اینترنتی') - 0.05, 0.4, INK.r, S.hatchRect(sx - 150, 480, 300, 70, {hachureGap: 22}), {w: 5});
	b.T(c(1, 'اینترنتی') + 0.25, 'فروشگاه آنلاین', sx, 880, 44, INK.k, {center: true});
	// warehouse
	const wx = 1800;
	b.P(c(1, 'بدون') - 0.1, 0.55, INK.k, cat(
		S.closed([[wx - 140, 780], [wx - 140, 590], [wx, 505], [wx + 140, 590], [wx + 140, 780]]),
		S.rect(wx - 65, 660, 130, 120),
		S.line(wx - 65, 690, wx + 65, 690), S.line(wx - 65, 720, wx + 65, 720), S.line(wx - 65, 750, wx + 65, 750),
	));
	b.P(c(1, 'انبار') - 0.05, 0.35, INK.r, S.cross(wx, 650, 3.2), {w: 11});
	b.T(c(1, 'انبار') + 0.3, 'بدون انبار', wx, 880, 44, INK.r, {center: true});
	// stock boxes
	const bx = 1490;
	b.P(c(1, 'بدون', 1) - 0.12, 0.6, INK.k, cat(
		S.rect(bx - 95, 700, 90, 80), S.rect(bx + 5, 700, 90, 80), S.rect(bx - 45, 620, 90, 80),
		S.line(bx - 50, 700, bx - 50, 780), S.line(bx + 50, 700, bx + 50, 780), S.line(bx, 620, bx, 700),
	));
	b.P(c(1, 'جنس') - 0.05, 0.35, INK.r, S.cross(bx, 700, 2.6), {w: 11});
	b.T(c(1, 'جنس') + 0.25, 'بدون خرید جنس', bx, 880, 44, INK.r, {center: true});
	// title
	b.T(c(1, 'دراپ') - 0.12, 'دراپ‌شیپینگ', 1800, 330, 170, INK.k, {center: true, dur: 1.0});
	b.P(c(1, 'دراپ') + 0.9, 0.4, INK.b, S.curve([[1530, 375], [1800, 392], [2070, 372]], {roughness: 0.4}), {w: 10});
	// start flag + subtitle
	b.P(c(1, 'بیا'), 0.45, INK.k, cat(S.line(2300, 1185, 2300, 1050)), {w: 8});
	b.P(c(1, 'بیا') + 0.42, 0.3, INK.r, cat(S.closed([[2300, 1052], [2390, 1078], [2300, 1104]]), S.hatchPoly([[2300, 1052], [2390, 1078], [2300, 1104]], {hachureGap: 10})), {w: 6});
	b.T(c(1, 'تخته') - 0.1, 'شروع', 2265, 1170, 46, INK.b, {dur: 0.35});
	b.T(c(1, 'از', 1) - 0.08, 'از صفر تا اولین فروش', 1800, 1060, 70, INK.b, {center: true, dur: 1.05});
}

// ---------- scene 2: the model ----------
{
	const o = CELLS[2], b = B(o.x, o.y);
	badge(b, st(2) - 0.02, st(2) + 0.3, '؟');
	title(b, st(2) + 0.35, 'دراپ‌شیپینگ چیه؟', 84);
	// store (laptop)
	b.P(c(2, 'فروشگاه') - 0.2, 0.6, INK.k, cat(
		S.rect(470, 330, 260, 170),
		S.closed([[440, 500], [760, 500], [795, 545], [405, 545]]),
		S.poly([[545, 385], [565, 385], [585, 450], [650, 450], [665, 405], [575, 405]]),
		S.circle(595, 470, 16), S.circle(640, 470, 16),
	));
	b.T(c(2, 'تو') + 0.05, 'فروشگاه تو', 600, 610, 50, INK.k, {center: true});
	// customer
	b.P(c(2, 'مشتری') - 0.3, 0.75, INK.k, cat(stick(930, 830, 1), S.rect(985, 750, 40, 66)));
	b.T(c(2, 'مشتری') + 0.45, 'مشتری', 930, 1045, 50, INK.k, {center: true});
	// arrow customer -> store
	b.P(c(2, 'می‌خره') - 0.35, 0.5, INK.b, S.arrow([[905, 660], [880, 560], [790, 495]], {roughness: 0.6}), {w: 8});
	b.T(c(2, 'می‌خره') + 0.1, 'سفارش + پول', 1000, 540, 42, INK.b, {center: true});
	// supplier (factory)
	b.P(c(2, 'تأمین') - 0.15, 0.75, INK.k, cat(
		S.rect(150, 765, 240, 185),
		S.poly([[150, 765], [150, 705], [210, 745], [210, 705], [270, 745], [270, 705], [330, 745], [330, 765]]),
		S.rect(340, 640, 38, 125),
		S.curve([[360, 620], [380, 590], [350, 565], [375, 535]], {roughness: 0.5}),
		S.rect(185, 830, 50, 50), S.rect(295, 830, 50, 50),
	));
	b.T(c(2, 'تأمین') + 0.55, 'تأمین‌کننده', 265, 1045, 50, INK.k, {center: true});
	b.P(c(2, 'تأمین') + 0.95, 0.45, INK.b, S.arrow([[425, 500], [320, 575], [285, 680]], {roughness: 0.6}), {w: 8});
	b.T(c(2, 'تأمین') + 1.3, 'سفارش', 225, 560, 42, INK.b, {center: true, dur: 0.3});
	// direct shipping (dashed) + box magnet
	const ship = [[410, 905], [620, 965], [840, 900]];
	b.D(c(2, 'مستقیم') - 0.05, 0.55, INK.r, S.curve(ship, {roughness: 0.4}), {w: 9});
	b.P(c(2, 'مستقیم') + 0.5, 0.15, INK.r, S.poly([[808, 878], [846, 898], [812, 932]], {roughness: 0.4}), {w: 9});
	b.T(c(2, 'می‌فرسته') + 0.05, 'ارسال مستقیم', 620, 1035, 46, INK.r, {center: true});
	MAGNETS.push({kind: 'box', t0: c(2, 'براش') - 0.1, t1: c(2, 'می‌فرسته') + 0.6, path: ship.map(([x, y]) => [x + o.x, y + o.y - 10]), col: '#e08a1e'});
	ev(c(2, 'براش') - 0.1, 'magnet', 0.5);
	// formula
	b.T(c(2, 'سودِ') - 0.05, 'سودِ تو', 600, 1200, 66, INK.r, {center: true, dur: 0.45});
	b.T(c(2, 'فاصله') + 0.05, 'قیمت فروش - قیمت خرید', 600, 1305, 56, INK.k, {center: true, dur: 1.3});
	b.P(c(2, 'خریده') + 0.05, 0.45, INK.b, S.rect(150, 1120, 900, 235, {roughness: 1.1}), {w: 6});
}

// ---------- scene 3: niche ----------
{
	const o = CELLS[3], b = B(o.x, o.y);
	badge(b, st(3) - 0.02, c(3, 'یک') - 0.05, '۱');
	title(b, c(3, 'نیچ') - 0.1, 'انتخاب نیچ', 96);
	b.P(c(3, 'سه') - 0.12, 0.42, INK.k, S.circle(600, 545, 440));
	b.P(c(3, 'سه') + 0.32, 0.42, INK.b, S.circle(465, 775, 440));
	b.P(c(3, 'سه') + 0.76, 0.42, INK.k, S.circle(735, 775, 440));
	b.T(c(3, 'مشکلِ') - 0.05, 'مشکل واقعی', 600, 445, 48, INK.k, {center: true});
	b.T(c(3, 'آدم') - 0.05, 'تقاضا', 375, 830, 56, INK.b, {center: true, dur: 0.4});
	b.T(c(3, 'دنبالِ') - 0.05, '(دنبال راه‌حل)', 375, 885, 34, INK.b, {center: true, dur: 0.55});
	b.T(c(3, 'موضوعی') - 0.05, 'تخصص تو', 825, 840, 50, INK.k, {center: true});
	b.P(c(3, 'بلدی') - 0.2, 0.45, INK.r, cat(S.hatchCircle(600, 700, 125), S.circle(600, 700, 125, {roughness: 0.5})), {w: 6});
	b.P(c(3, 'بلدی') + 0.2, 0.3, INK.r, S.arrow([[600, 1110], [600, 790]], {roughness: 0.4}), {w: 8});
	b.T(c(3, 'بلدی') + 0.45, 'نیچ تو', 600, 1190, 66, INK.r, {center: true, dur: 0.45});
}

// ---------- scene 4: winning product ----------
{
	const o = CELLS[4], b = B(o.x, o.y);
	badge(b, st(4) - 0.02, c(4, 'دو') - 0.05, '۲');
	title(b, c(4, 'محصولِ') - 0.05, 'محصول برنده', 92);
	b.P(c(4, 'برنده') + 0.2, 0.35, INK.r, cat(S.rect(150, 300, 150, 110), S.rect(138, 268, 174, 34), S.line(225, 268, 225, 410), S.closed(star(345, 250, 26))), {w: 6});
	const rows = [
		{y: 520, txt: 'مشکلی رو حل کنه', a: c(4, 'مشکلی') - 0.1, k: c(4, 'کنه') + 0.05},
		{y: 690, txt: 'توی ویدیو چشم‌گیر باشه', a: c(4, 'توی') - 0.05, k: c(4, 'باشه')},
		{y: 860, txt: 'توی هر مغازه‌ای پیدا نشه', a: c(4, 'توی', 1) - 0.05, k: c(4, 'نشه')},
		{y: 1030, txt: 'حداقل ۳ برابر قیمت خرید', a: c(4, 'حداقل') - 0.05, k: c(4, 'بشه')},
	];
	rows.forEach((r) => {
		b.P(r.a - 0.22, 0.2, INK.k, S.rect(985, r.y - 52, 66, 66, {roughness: 0.7}), {w: 6});
		b.T(r.a, r.txt, 950, r.y, 52, INK.k, {dur: 0.75});
		b.P(r.k, 0.22, INK.g, S.check(1020, r.y - 22, 1.15), {w: 10, snd: 'tick'});
	});
	// 1x vs 3x bars
	b.P(c(4, 'قیمتِ') - 0.1, 0.3, INK.b, cat(S.rect(860, 1140, 120, 46), S.hatchRect(860, 1140, 120, 46, {hachureGap: 12})), {w: 5});
	b.T(c(4, 'خرید') - 0.05, 'خرید', 835, 1178, 40, INK.b, {dur: 0.3});
	b.P(c(4, 'فروخته') - 0.1, 0.4, INK.r, cat(S.rect(620, 1220, 360, 46), S.hatchRect(620, 1220, 360, 46, {hachureGap: 12})), {w: 5});
	b.T(c(4, 'فروخته') + 0.3, 'فروش', 595, 1258, 40, INK.r, {dur: 0.3});
}

// ---------- scene 5: supplier ----------
{
	const o = CELLS[5], b = B(o.x, o.y);
	badge(b, st(5) - 0.02, c(5, 'سه') - 0.05, '۳');
	title(b, c(5, 'تأمین') - 0.05, 'تأمین‌کننده', 92);
	b.T(c(5, 'قبل') - 0.05, 'قبل از فروش:', 985, 290, 46, INK.b, {dur: 0.5});
	b.P(c(5, 'خودت') - 0.1, 0.75, INK.k, cat(
		S.rect(470, 470, 240, 180),
		S.closed([[470, 470], [550, 410], [790, 410], [710, 470]]),
		S.closed([[710, 470], [790, 410], [790, 590], [710, 650]]),
		S.line(590, 470, 670, 410),
	));
	b.T(c(5, 'سفارش') + 0.05, 'نمونه', 590, 585, 56, INK.r, {center: true, dur: 0.4});
	// three checks
	b.P(c(5, 'کیفیت') - 0.1, 0.35, INK.k, S.closed(star(900, 860, 75)));
	b.T(c(5, 'کیفیت') + 0.25, 'کیفیت', 900, 1000, 48, INK.k, {center: true, dur: 0.35});
	b.P(c(5, 'بسته‌بندی') - 0.1, 0.4, INK.k, cat(S.rect(535, 805, 130, 110), S.line(600, 805, 600, 915), S.line(535, 840, 665, 840)));
	b.T(c(5, 'بسته‌بندی') + 0.3, 'بسته‌بندی', 600, 1000, 48, INK.k, {center: true, dur: 0.45});
	b.P(c(5, 'زمانِ') - 0.1, 0.45, INK.k, cat(S.circle(300, 860, 150), S.line(300, 860, 300, 805), S.line(300, 860, 340, 880)));
	b.T(c(5, 'ارسال') + 0.05, 'زمان ارسال', 300, 1000, 48, INK.k, {center: true, dur: 0.45});
	b.T(c(5, 'ارسال') + 0.5, 'زیر ۲ هفته', 300, 1065, 40, INK.g, {center: true, dur: 0.35});
	// magnifier
	b.P(c(5, 'چشمِ') - 0.15, 0.5, INK.b, cat(S.circle(735, 520, 190), S.line(800, 590, 880, 680, {roughness: 0.3})), {w: 10});
}

// ---------- scene 6: store page ----------
{
	const o = CELLS[6], b = B(o.x, o.y);
	badge(b, st(6) - 0.02, c(6, 'چهار') - 0.05, '۴');
	title(b, c(6, 'فروشگاه') - 0.05, 'فروشگاه', 96);
	b.T(c(6, 'صد') - 0.05, '۱۰۰ محصول', 300, 200, 50, INK.k, {center: true, dur: 0.45});
	b.P(c(6, 'نیست') - 0.1, 0.25, INK.r, S.line(160, 182, 440, 182, {roughness: 0.5}), {w: 9});
	b.T(c(6, 'صفحه'), '۱ صفحه‌ی قوی', 300, 290, 50, INK.g, {center: true, dur: 0.5});
	b.P(c(6, 'کافیه') - 0.15, 0.55, INK.k, cat(S.rect(140, 360, 380, 930, {roughness: 0.8}), S.line(285, 385, 375, 385)), {w: 7});
	const L = (t: number, txt: string, y: number, yy: number) => {
		b.T(t + 0.28, txt, 1085, y, 48, INK.b, {dur: 0.45});
		b.P(t + 0.05, 0.22, INK.b, S.arrow([[800, yy], [540, yy]], {roughness: 0.4, head: 26}), {w: 6});
	};
	b.P(c(6, 'تیترِ') - 0.1, 0.3, INK.k, cat(S.line(180, 430, 480, 430), S.line(180, 470, 390, 470)), {w: 12});
	L(c(6, 'تیترِ'), 'تیتر روشن', 465, 450);
	b.P(c(6, 'ویدیوی') - 0.1, 0.35, INK.k, cat(S.rect(175, 510, 310, 200), S.closed([[305, 570], [305, 650], [370, 610]])));
	L(c(6, 'ویدیوی'), 'ویدیوی واقعی', 625, 610);
	b.P(c(6, 'مزیت') - 0.1, 0.45, INK.g, cat(S.check(205, 765, 0.5), S.check(205, 815, 0.5), S.check(205, 865, 0.5)), {w: 6});
	b.P(c(6, 'مزیت') + 0.2, 0.3, INK.k, cat(S.line(245, 762, 470, 762), S.line(245, 812, 440, 812), S.line(245, 862, 455, 862)), {w: 5});
	L(c(6, 'مزیت'), 'مزیت‌ها', 830, 815);
	b.P(c(6, 'نظرِ') - 0.1, 0.5, INK.o, cat(...[0, 1, 2, 3, 4].map((k) => S.closed(star(200 + k * 52, 945, 22)))), {w: 5});
	L(c(6, 'نظرِ'), 'نظر مشتری', 965, 945);
	b.P(c(6, 'ضمانت') - 0.1, 0.35, INK.k, cat(S.path('M235,1025 L280,1040 L280,1080 Q280,1110 235,1125 Q190,1110 190,1080 L190,1040 Z', {roughness: 0.5}), S.line(310, 1075, 470, 1075)));
	L(c(6, 'ضمانت'), 'ضمانت', 1090, 1075);
	b.P(c(6, 'دکمه') - 0.1, 0.4, INK.r, cat(S.rect(180, 1165, 300, 80, {roughness: 0.6}), S.hatchRect(180, 1165, 300, 80, {hachureGap: 14})), {w: 6});
	b.T(c(6, 'خرید') - 0.1, 'خرید', 330, 1222, 46, INK.k, {center: true, dur: 0.3});
	L(c(6, 'دکمه'), 'دکمه‌ی خرید', 1225, 1205);
}

// ---------- scene 7: unit economics ----------
{
	const o = CELLS[7], b = B(o.x, o.y);
	badge(b, st(7) - 0.02, c(7, 'پنج') - 0.05, '۵');
	title(b, c(7, 'حساب') - 0.05, 'حساب‌وکتاب', 92);
	b.T(c(7, 'سی') - 0.15, 'قیمت فروش: ۳۰ دلار', 600, 330, 62, INK.b, {center: true, dur: 0.75});
	b.P(c(7, 'می‌فروشی') - 0.1, 0.45, INK.k, S.rect(120, 400, 960, 130, {roughness: 0.6}), {w: 7});
	const seg = (a: number, z: number, t: number, txt: string, row: number, col = INK.b) => {
		b.P(t - 0.1, 0.3, col, cat(S.line(z, 400, z, 530), S.hatchRect(z, 400, a - z, 130, {hachureGap: 14})), {w: 5});
		b.T(t + 0.15, txt, (a + z) / 2, row, 42, col, {center: true, dur: 0.35});
	};
	seg(1080, 792, c(7, 'جنس'), 'جنس ۹', 600);
	seg(792, 664, c(7, 'ارسال'), 'ارسال ۴', 665);
	seg(664, 600, c(7, 'کارمزد'), 'کارمزد ۲', 600);
	seg(600, 280, c(7, 'تبلیغ'), 'تبلیغ ۱۰', 665);
	seg(280, 120, c(7, 'پنج', 1) - 0.1, 'سود ۵', 600, INK.g);
	ev(c(7, 'پنج', 1) + 0.2, 'ding', 0.45);
	b.T(c(7, 'بمونه') - 0.1, 'سود هر فروش: ۵ دلار', 560, 805, 58, INK.g, {center: true, dur: 0.8});
	b.P(c(7, 'سالمه') - 0.05, 0.25, INK.g, S.check(985, 785, 1.4), {w: 11, snd: 'tick'});
	const neg = b.T(c(7, 'منفیه') - 0.2, 'اگه منفی شد...', 600, 990, 56, INK.r, {center: true, dur: 0.55});
	const nx = b.P(c(7, 'منفیه') + 0.3, 0.22, INK.r, S.cross(985, 970, 1.1), {w: 10});
	const er = {t0: c(7, 'قبل') - 0.05, dur: 0.65, pts: zig(260, 925, 1060, 1010, 4), w: 120};
	neg.erase = er;
	nx.erase = er;
	b.T(c(7, 'شروع') + 0.1, 'قیمت رو اصلاح کن', 600, 1150, 56, INK.b, {center: true, dur: 0.8});
}

// ---------- scene 8: marketing ----------
{
	const o = CELLS[8], b = B(o.x, o.y);
	badge(b, st(8) - 0.02, c(8, 'شش') - 0.05, '۶');
	title(b, c(8, 'بازاریابی') - 0.05, 'بازاریابی', 96);
	b.T(c(8, 'جایی') - 0.05, 'جایی که فروش ساخته می‌شه', 985, 280, 44, INK.b, {dur: 0.9});
	const xs = [1000, 800, 600, 400, 200];
	xs.forEach((x, k) => {
		b.P(c(8, 'سه') + k * 0.36, 0.32, INK.k, cat(S.rect(x - 70, 380, 140, 240, {roughness: 0.7}), S.closed([[x - 18, 470], [x - 18, 530], [x + 30, 500]])), {w: 6});
	});
	b.T(c(8, 'تست') - 0.05, '۵ ویدیوی تست', 600, 700, 44, INK.k, {center: true, dur: 0.5});
	[1, 3, 4].forEach((k, j) => b.P(c(8, 'بازنده') + j * 0.28, 0.22, INK.r, S.cross(xs[k], 500, 1.6), {w: 10}));
	b.T(c(8, 'خاموش') + 0.05, 'خاموش', 300, 760, 40, INK.r, {center: true, dur: 0.3});
	[0, 2].forEach((k, j) => b.P(c(8, 'برنده') - 0.2 + j * 0.3, 0.28, INK.g, S.ellipse(xs[k], 500, 190, 300, {roughness: 0.8}), {w: 8}));
	b.P(c(8, 'برنده') + 0.4, 0.35, INK.k, S.poly([[250, 840], [250, 1240], [960, 1240]], {roughness: 0.4}), {w: 7});
	b.P(c(8, 'بودجه') - 0.05, 0.55, INK.g, S.arrow([[275, 1200], [450, 1140], [600, 1060], [760, 950], [930, 850]], {roughness: 0.6}), {w: 10});
	b.T(c(8, 'بذار') - 0.1, 'بودجه روی برنده‌ها', 600, 1320, 50, INK.g, {center: true, dur: 0.7});
}

// ---------- scene 9: after the sale ----------
{
	const o = CELLS[9], b = B(o.x, o.y);
	badge(b, st(9) - 0.02, c(9, 'هفت') - 0.05, '۷');
	title(b, c(9, 'بعد') - 0.05, 'بعد از فروش', 94);
	b.P(c(9, 'کدِ') - 0.25, 0.45, INK.k, cat(
		S.rect(150, 380, 180, 110),
		S.poly([[330, 410], [390, 410], [420, 450], [420, 490], [330, 490]]),
		S.circle(195, 500, 46), S.circle(370, 500, 46),
	));
	b.T(c(9, 'رهگیری') - 0.1, 'کد رهگیری بفرست', 1050, 465, 52, INK.k, {dur: 0.7});
	b.P(c(9, 'زیرِ') - 0.15, 0.4, INK.b, S.circle(285, 680, 160), {w: 7});
	b.T(c(9, 'بیست') - 0.05, '۲۴', 285, 708, 66, INK.b, {center: true, font: NUM, weight: 800, dur: 0.3});
	b.T(c(9, 'ساعت') - 0.05, 'جواب زیر ۲۴ ساعت', 1050, 705, 52, INK.k, {dur: 0.7});
	b.P(c(9, 'مرجوعیِ') - 0.15, 0.4, INK.k, cat(S.arc(285, 920, 150, 150, -Math.PI * 0.9, Math.PI * 0.6, {roughness: 0.5}), S.poly([[240, 868], [212, 900], [254, 912]], {roughness: 0.4})), {w: 7});
	b.T(c(9, 'شفاف') - 0.1, 'مرجوعی شفاف', 1050, 945, 52, INK.k, {dur: 0.55});
	b.P(c(9, 'مشتریِ') - 0.1, 0.6, INK.k, stick(330, 1180, 0.85, true));
	b.P(c(9, 'راضی') - 0.05, 0.35, INK.r, S.path('M480,1015 C450,985 420,1020 480,1060 C540,1020 510,985 480,1015 Z', {roughness: 0.4}), {w: 7});
	b.T(c(9, 'تبلیغِ') - 0.1, 'مشتری راضی = تبلیغ مجانی', 700, 1180, 46, INK.r, {center: true, dur: 0.9});
}

// ---------- scene 10: ecosystem ----------
{
	const o = CELLS[10], b = B(o.x, o.y);
	badge(b, st(10) - 0.02, st(10) + 0.25, '', true);
	const mess = b.P(c(10, 'خیلی') - 0.05, 0.8, INK.k, cat(
		S.curve([[260, 470], [340, 360], [450, 520], [520, 380], [610, 540], [690, 370], [780, 520], [880, 400], [940, 500]], {roughness: 2.2}),
		S.curve([[300, 560], [420, 430], [560, 600], [700, 440], [860, 590]], {roughness: 2.4}),
	), {w: 6});
	const mt = b.T(c(10, 'دردسرها') - 0.05, 'دردسرها', 600, 660, 50, INK.r, {center: true, dur: 0.45});
	const er = {t0: c(10, 'حل') - 0.15, dur: 0.75, pts: zig(220, 330, 980, 690, 5), w: 130};
	mess.erase = er;
	mt.erase = er;
	title(b, c(10, 'اکوسیستمِ') - 0.05, 'اکوسیستم رفیعی', 78);
	const cards = [
		{t: c(10, 'تأمینِ') - 0.2, y: 830, col: INK.b, title: 'Rafiei Dropship', sub: 'تأمین محصول'},
		{t: c(10, 'فروشگاه') - 0.2, y: 1035, col: INK.r, title: 'Rafiei Store', sub: 'فروشگاه'},
		{t: c(10, 'پرداخت') - 0.2, y: 1240, col: INK.g, title: 'Rafiei Pay', sub: 'پرداخت'},
	];
	cards.forEach((k) => {
		MAGNETS.push({kind: 'card', t0: k.t, x: o.x + 600, y: o.y + k.y, col: k.col, title: k.title, sub: k.sub});
		ev(k.t + 0.18, 'magnet', 0.55);
	});
}

// ---------- scene 11: CTA (footer) ----------
{
	const b = B(0, 6250);
	const s = st(11);
	b.P(s + 0.0, 0.3, INK.k, S.line(1330, 330, 1330, 105), {w: 9});
	b.P(s + 0.3, 0.35, INK.r, cat(S.closed([[1330, 108], [1450, 140], [1330, 175]]), S.hatchPoly([[1330, 108], [1450, 140], [1330, 175]], {hachureGap: 10})), {w: 6});
	b.T(s + 0.6, 'اولین فروش', 1630, 230, 54, INK.k, {center: true, dur: 0.5});
	b.T(c(11, 'آموزشِ') - 0.05, 'آموزش رایگان', 1800, 470, 82, INK.b, {center: true, dur: 0.7});
	b.T(c(11, 'مزه') - 0.12, 'مزه بدون مرز', 1800, 660, 150, INK.k, {center: true, dur: 1.0});
	b.P(c(11, 'رو') - 0.05, 0.4, INK.r, S.curve([[1440, 710], [1800, 728], [2160, 706]], {roughness: 0.4}), {w: 10});
	b.P(c(11, 'کلمه') - 0.1, 0.55, INK.k, cat(S.rect(1470, 810, 660, 200, {roughness: 0.7}), S.poly([[1640, 1010], [1600, 1080], [1720, 1010]], {roughness: 0.5})), {w: 8});
	b.T(c(11, 'شروع') - 0.12, 'شروع', 1800, 955, 120, INK.r, {center: true, dur: 0.55});
	b.T(c(11, 'کامنت') - 0.1, 'کامنت کن', 1800, 1180, 72, INK.k, {center: true, dur: 0.5});
	b.P(c(11, 'کن') + 0.35, 0.45, INK.r, S.ellipse(1800, 915, 820, 330, {roughness: 1.1}), {w: 9});
	b.P(c(11, 'کن') + 0.82, 0.42, INK.r, S.ellipse(1805, 912, 860, 350, {roughness: 1.3}), {w: 7});
	ev(c(11, 'کن') + 1.45, 'cap', 0.6);
}

// ---------- camera ----------
export const CAM: Cam[] = (() => {
	const K: Cam[] = [];
	const k = (t: number, v: Cam) => K.push({...v, t});
	k(0, {...view(1), x: 1960, y: 690, z: 1.2});
	k(c(1, 'جنس'), {...view(1), x: 1800, y: 700, z: 1.12});
	k(c(1, 'دراپ') - 0.35, {...view(1), y: 700, z: 1.12});
	k(c(1, 'دراپ') + 0.6, {...view(1), y: 830, z: 0.98});
	k(c(1, 'بیا') - 0.1, {...view(1), y: 840, z: 0.97});
	k(c(1, 'تخته') + 0.5, {t: 0, x: 1880, y: 880, z: 0.8});
	let prev: Cam = {t: 0, x: 1880, y: 880, z: 0.8};
	for (let i = 2; i <= 10; i++) {
		const v = view(i);
		k(st(i) - 0.82, prev);
		k(st(i) - 0.4, {t: 0, x: (prev.x + v.x) / 2, y: (prev.y + v.y) / 2, z: Math.min(prev.z, v.z) * 0.74});
		k(st(i) + 0.08, v);
		prev = {...v, z: 0.99};
	}
	const s = st(11);
	k(s - 0.82, prev);
	k(s + 1.25, FULL);
	k(s + 2.35, {...FULL, z: FULL.z * 1.03});
	k(c(11, 'اگه') + 0.15, view(11));
	k(TOTAL, {...view(11), z: 1.0});
	return K;
})();

// ---------- captions ----------
export const CAPS: {t0: number; t1: number; text: string}[] = (() => {
	const out: {t0: number; t1: number; text: string}[] = [];
	SC.forEach((sc) => {
		let cur: Word[] = [];
		const flush = () => {
			if (!cur.length) return;
			out.push({t0: sc.start + cur[0].s - 0.05, t1: sc.start + cur[cur.length - 1].e + 0.25, text: cur.map((w) => w.t).join(' ')});
			cur = [];
		};
		sc.words.forEach((w) => {
			cur.push(w);
			const len = cur.map((x) => x.t).join(' ').length;
			if (/[،؛:.؟!]$/.test(w.t) || cur.length >= 5 || len > 26) flush();
		});
		flush();
	});
	for (let i = 0; i < out.length - 1; i++) out[i].t1 = Math.min(out[i].t1, out[i + 1].t0);
	return out;
})();
