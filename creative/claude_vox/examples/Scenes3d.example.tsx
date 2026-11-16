// Craft reference for 3D Vox films (look clay_3d). Topic of this example only: «a developer's first app sale». Do not copy the topic, the texts or the sets.
// Every `at` is a cue of the scene's own line; every scene moves its camera on a word; the 2D title sits in the top zone over the 3D set.

// line: «یه برنامه‌نویسِ تنها، یه اپِ کوچیک ساخت… و شبِ اول، فقط سه نفر دانلودش کردن.»
const S01: React.FC = () => {
	const {c} = useS();
	return (
		<AbsoluteFill>
			<Stage3D look="clay" bg="linear-gradient(180deg,#F9E6D8 0%,#F0C9B3 100%)"
				cam={[{at: 0, pos: [0, 2.4, 7.2], look: [0, 1.5, 0], fov: 34}, {at: c('شبِ') - 0.2, pos: [3.2, 3.4, 5.6], look: [0.2, 1.3, 0], d: 1.6}]}>
				<Platform3 at={0} r={1.9} color="#FFFFFF" />
				<Phone3 at={0.15} pos={[0, 0.3, 0]} rot={-8} accent={RED} title="اپ من" cta="دانلود" s={1.15} />
				<Person3 at={c('سه') - 0.1} pos={[1.25, 0.3, 0.7]} color={TEAL} />
				<Person3 at={c('سه') + 0.05} pos={[1.55, 0.3, 0.1]} color={MUST} />
				<Person3 at={c('سه') + 0.2} pos={[0.95, 0.3, -0.4]} color={RED} />
				<Label3 at={c('دانلودش') - 0.1} pos={[1.25, 1.5, 0.2]} dx={-40} dy={-180} num={{to: 3, suffix: ' downloads', dur: 0.6}} size={56} />
			</Stage3D>
			<Abs x={540} y={330}><T size={104} weight={900}>شبِ اول</T></Abs>
		</AbsoluteFill>
	);
};

// line: «ولی هر بار که کسی خرید می‌کرد، سی درصدش اول به جیبِ فروشگاهِ اپ می‌رفت.»
const S02: React.FC = () => {
	const {c} = useS();
	return (
		<AbsoluteFill>
			<Stage3D look="clay" bg="linear-gradient(180deg,#DDEBFA 0%,#F4EEE6 100%)" orbit={0}
				cam={[{at: 0, pos: [0, 5.5, 6.5], look: [0, 0.6, 0], fov: 34}, {at: c('سی') - 0.3, pos: [-2.6, 3.2, 5.4], look: [0, 0.8, 0], d: 1.2}]}>
				<Donut3 at={c('خرید') - 0.15} values={[70, 30]} colors={[TEAL, RED]} r={1.25} h={0.4} pull={1} pullAt={c('سی')} />
				<Label3 at={c('سی') + 0.1} pos={[0.9, 0.8, -0.4]} dx={140} dy={-260} num={{to: 30, suffix: '%', dur: 0.7}} size={120} />
				<Label3 at={c('فروشگاهِ')} pos={[-0.6, 0.5, 0.6]} dx={-120} dy={240}>سهمِ فروشگاه</Label3>
			</Stage3D>
		</AbsoluteFill>
	);
};

// line: «امروز، همین بازار سالی بیش از صد میلیارد دلار برای سازنده‌ها پول جابه‌جا می‌کنه.»
const S03: React.FC = () => {
	const {c} = useS();
	return (
		<AbsoluteFill>
			<Stage3D look="clay" bg="linear-gradient(180deg,#E3F4EA 0%,#F7EFE0 100%)"
				cam={[{at: 0, pos: [4.5, 3.6, 7.5], look: [0, 1.4, 0]}, {at: c('صد') - 0.2, pos: [0.6, 1.6, 6.4], look: [0, 1.9, 0], d: 1.4}]}>
				<Bars3 at={c('بازار') - 0.1} dur={1.4} values={[10, 35, 70, 100]} labels={['2015', '2018', '2021', '2024']} prefix="$" suffix="B" h={2.6} w={0.5} gap={0.78} />
				<Coins3 at={c('پول') - 0.2} pos={[2.15, 0, 1.0]} n={7} dur={0.9} />
			</Stage3D>
			<Abs x={540} y={300}><T size={92} weight={900}>بازارِ اپ‌ها</T></Abs>
		</AbsoluteFill>
	);
};

// line: «و پولش از همه جای دنیا می‌آد؛ از استانبول تا سئول.»
const S04: React.FC = () => {
	const {c} = useS();
	return (
		<AbsoluteFill>
			<Stage3D look="clay" bg="radial-gradient(ellipse at 50% 45%,#FFFFFF 0%,#E7E0F5 80%)" orbit={0}
				cam={[{at: 0, pos: [0, 2.6, 8.5], look: [0, 1.7, 0]}, {at: c('سئول') - 0.4, pos: [0, 2.2, 6.8], look: [0, 1.75, 0], d: 1.5}]}>
				<Globe3 at={0} r={1.6} face="Turkey" spin3={5} fill={{Turkey: RED, 'South Korea': TEAL}}
					arcs={[['Turkey', 'United States of America', RED, c('استانبول')], ['South Korea', 'United States of America', TEAL, c('سئول')]]}
					pins={[['Turkey', RED, c('استانبول') - 0.1], ['South Korea', TEAL, c('سئول') - 0.1]]} />
			</Stage3D>
			<Enter at={c('دنیا') - 0.2} from="up" x={540} y={1560}><Label size={58}>از همه جای دنیا</Label></Enter>
		</AbsoluteFill>
	);
};
