// Development only (import.meta.env.DEV): `localStorage.setItem('hermes:demo','1')` makes the Hermes pages run on this sample data, so the layout can be
// reviewed without a connected account. It is never part of a production build.
const now = Date.now();
const day = 86400000;
const agent = {
  answers: {}, competitors: [], prefs: { talking_share: 50 },
  profile: { username: 'sample.page', followers: 12840, follows: 410, media_count: 187, ig_user_id: '1' },
  analysis: {
    at: new Date(now).toISOString(),
    profile: { score: 64, parts: [{ part: 'بیو', score: 5, note: 'کلی است و مخاطب را مشخص نمی‌کند', rewrite: 'آموزش فروش محصول دیجیتال، قدم‌به‌قدم' }, { part: 'هایلایت‌ها', score: 7, note: 'مرتب ولی بدون ترتیب فروش' }] },
    content: { top: [{ post: 'ریلز «۳ اشتباه فروش آنلاین»', why: 'هوک عددی و ادامه‌ی سریع' }], weak: [{ post: 'پست معرفی دوره', why: 'بدون هوک و خیلی طولانی' }], patterns: [], do_more: ['ریلزهای کوتاه آموزشی', 'قصه‌ی شخصی'], stop: ['پست‌های معرفی بدون هوک'] },
    strategy: { niche: 'فروش محصول دیجیتال', audience: 'کسب‌وکارهای کوچک مبتدی', pillars: ['آموزش', 'نتیجه‌ی مشتری', 'پشت‌صحنه'], format_mix: 'ریلز ۷۰٪، کاروسل ۳۰٪' },
    data_gaps: ['آمار ریچ و ذخیره در دسترس نیست'],
  },
  questions: [{ id: 'competitors', kind: 'handles', text: 'سه رقیب اصلی‌ات را با @ بنویس' }],
  proposals: [
    { id: 'p1', status: 'proposed', engine: 'talking', title: 'چرا فروش دیجیتال از فیزیکی ساده‌تر است؟', hook: 'فروش فیزیکی یعنی انبار؛ فروش دیجیتال یعنی گوشی.', why: 'ادامه‌ی ریلز پرفروش قبلی با زاویه‌ی مقایسه',
      script: 'فروش فیزیکی یعنی انبار؛ فروش دیجیتال یعنی گوشی.\nاگر فکر می‌کنی برای فروش باید انبار و پیک و موجودی داشته باشی، این ریلز را تا آخر ببین.\nمحصول دیجیتال یک‌بار ساخته می‌شود و هزار بار فروخته می‌شود. بدون هزینه‌ی ارسال، بدون موجودی.\nاگر می‌خواهی اولین محصول دیجیتالت را بسازی، زیر همین ریلز بنویس «شروع».',
      on_screen: ['انبار؟', 'گوشی', 'یک‌بار بساز'], shooting_tips: ['کادر نزدیک، نور از روبه‌رو', 'بعد از هوک نیم‌ثانیه مکث کن'], caption: 'کپشن نمونه', hashtags: ['#فروش', '#دیجیتال'], length_seconds: 35 },
    { id: 'p3', status: 'proposed', engine: 'explainer', title: 'روزی که انبارم را بستم', concept: 'داستان یک انبارِ پر که با یک فایل خالی شد؛ و چرا این بهترین تصمیم بود.',
      hook: 'تصویر انبار پر از کارتن با متن «۳۲۰ میلیون خوابیده».', why: 'روایت شخصی با تضاد بصری، قالبی که ذخیره و اشتراک می‌گیرد', style: 'تایپوگرافی درشت روی بافت کاغذ گرم، برش‌های سریع، اکشن‌های دستی', mood: 'تأمل‌برانگیز و امیدوار',
      music: 'پیانوی ملایم که در نیمه‌ی ویدیو به ضرب تند می‌رسد',
      scenes: [{ seconds: 3, visual: 'انبار پر از کارتن، دوربین عقب می‌رود', on_screen_text: '۳۲۰ میلیون خوابیده', narration: 'این انبار، سه‌صد و بیست میلیون سرمایه‌ی خوابیده بود.' },
        { seconds: 5, visual: 'کارتن‌ها یکی‌یکی محو می‌شوند', on_screen_text: 'و اگر خالی شود؟', narration: 'تا روزی که فهمیدم فروش واقعی به کارتن نیاز ندارد.' },
        { seconds: 6, visual: 'صفحه‌ی لپ‌تاپ با یک فایل ساده', on_screen_text: 'یک فایل', narration: 'یک فایل، هزار بار فروش، بدون یک روز موجودی.' }],
      script: 'این انبار، سه‌صد و بیست میلیون سرمایه‌ی خوابیده بود. تا روزی که فهمیدم فروش واقعی به کارتن نیاز ندارد.', cta: 'اگر می‌خواهی بدانی چطور شروع کنم، «انبار» را کامنت کن', caption: '', hashtags: [], length_seconds: 30 },
    { id: 'p2', status: 'in_production', engine: 'explainer', conversation_id: 'demo', title: 'سه مرحله‌ی ساخت اولین محصول دیجیتال', hook: 'سه قدم تا اولین محصول.', why: 'قالب فهرستی که قبلاً جواب داده', concept: 'سه گام ساده', style: 'اینفوگرافیک دست‌کشیده', mood: 'روشن', script: '…', caption: '', hashtags: [], length_seconds: 40 },
  ],
  media: [{ id: 'm1', caption: '۳ اشتباه فروش آنلاین', likes: 1240, comments: 86 }, { id: 'm2', caption: 'معرفی دوره‌ی جدید', likes: 210, comments: 9 }],
  run: { status: 'done', step: null, error: null }, history: [], engines: {},
};
const posts = [{ id: 'a', status: 'scheduled', caption: 'ریلز چهارشنبه: مقایسه‌ی فروش', scheduled_at: new Date(now + 2 * day).toISOString() }, { id: 'b', status: 'draft', caption: 'پیش‌نویس کاروسل', scheduled_at: null }];
const account = { id: 'composio-instagram', username: 'sample.page', source: 'composio', followers: 12840 };
const chats = [{ id: 'c1', title: 'ایده برای ریلز فروش', updated_at: new Date(now - day).toISOString(), created_at: new Date(now - day).toISOString(),
  messages: [{ role: 'user', text: 'یک ایده‌ی ریلز برای فروش بده', at: now - day }, { role: 'assistant', text: 'پیشنهاد من: مقایسه‌ی فروش فیزیکی و دیجیتال با هوک «انبار یا گوشی؟».', at: now - day, activity: [{ label: 'بررسی اطلاعات پیج و تحلیل ذخیره‌شده', tool: 'account' }], suggestions: ['متنش را بنویس'] }] }];
const routes = [
  [/^\/agent\/chats\/[^/]+\/messages/, (body) => ({ chat: { id: 'c1', title: 'گفتگو', updated_at: new Date().toISOString() }, reply: { role: 'assistant', text: `جواب نمونه به: ${String(body?.message || '').slice(0, 40)}`, at: Date.now(), activity: [{ label: 'خواندن محتوای صفحه‌ی باز', tool: 'page' }, { label: 'بررسی اطلاعات پیج و تحلیل ذخیره‌شده', tool: 'account' }], suggestions: ['ادامه بده'] } })],
  [/^\/agent\/chats\/[^/]+/, () => chats[0]],
  [/^\/agent\/chats/, () => ({ chats: chats.map(({ messages, ...c }) => c), ...chats[0], id: 'c1' })],
  [/^\/agent\/connection/, () => ({ connected: true })],
  [/^\/agent\/chat/, (body) => ({ reply: `درباره‌ی «${(body?.page?.title || 'این صفحه')}»: ${String(body?.page?.text || '').slice(0, 60) ? 'محتوای صفحه را دیدم و می‌توانم کمک کنم.' : 'صفحه خالی است.'}`, suggestions: ['یک ایده‌ی ریلز بده', 'تحلیل جدید'], activity: [{ label: 'خواندن محتوای صفحه‌ی باز', tool: 'page' }, { label: 'بررسی اطلاعات پیج و تحلیل ذخیره‌شده', tool: 'account' }], action: null })],
  [/^\/agent\/run/, () => ({ status: 'started' })],
  [/^\/agent\/answer/, () => agent],
  [/^\/agent\/prefs/, (body) => { agent.prefs = { talking_share: body.talking_share }; return agent; }],
  [/^\/agent\/proposals/, () => ({})],
  [/^\/agent/, () => agent],
  [/^\/auth\/accounts/, () => [account]],
  [/^\/analytics\/posts/, () => []],
  [/^\/analytics\//, () => ({ followers: 12840, follows: 410, media_count: 187 })],
  [/^\/posts/, () => posts],
  [/^\/scheduler|^\/schedule/, () => posts],
  [/^\/composio\/connections/, () => ({ applications: [{ application: 'instagram', name: 'Instagram', connected: true, status: 'ACTIVE' }] })],
  [/^\/composio/, () => ({ configured: true, enabled: true, applications: ['instagram'], external_actions_enabled: false })],
  [/^\/settings\/instagram/, () => ({ configured: false, instagram_user_id: null })],
  [/^\/skills\/account/, () => ({ connected: true, profile: account, recent_posts: agent.media })],
];
export async function demo(path, body) {
  await new Promise((resolve) => setTimeout(resolve, 350));            // show the "updating" state like a real request
  for (const [pattern, make] of routes) if (pattern.test(path)) return make(body);
  return {};
}
export const demoOn = () => import.meta.env.DEV && typeof localStorage !== 'undefined' && localStorage.getItem('hermes:demo') === '1';
