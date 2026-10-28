// Development only (import.meta.env.DEV): `localStorage.setItem('hermes:demo','1')` makes the Hermes pages run on this sample data, so the layout can be
// reviewed without a connected account. It is never part of a production build.
const now = Date.now();
const day = 86400000;
const agent = {
  answers: {}, competitors: [],
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
    { id: 'p1', status: 'proposed', engine: 'talking', title: 'چرا فروش دیجیتال از فیزیکی ساده‌تر است؟', hook: 'فروش فیزیکی یعنی انبار؛ فروش دیجیتال یعنی گوشی.', why: 'ادامه‌ی ریلز پرفروش قبلی با زاویه‌ی مقایسه', script: 'سلام. اگر فکر می‌کنی برای فروش باید انبار داشته باشی…', caption: 'کپشن نمونه', hashtags: ['#فروش', '#دیجیتال'], length_seconds: 35 },
    { id: 'p2', status: 'in_production', engine: 'explainer', conversation_id: 'demo', title: 'سه مرحله‌ی ساخت اولین محصول دیجیتال', hook: 'سه قدم تا اولین محصول.', why: 'قالب فهرستی که قبلاً جواب داده', script: '…', caption: '', hashtags: [], length_seconds: 40 },
  ],
  media: [{ id: 'm1', caption: '۳ اشتباه فروش آنلاین', likes: 1240, comments: 86 }, { id: 'm2', caption: 'معرفی دوره‌ی جدید', likes: 210, comments: 9 }],
  run: { status: 'done', step: null, error: null }, history: [], engines: {},
};
const posts = [{ id: 'a', status: 'scheduled', caption: 'ریلز چهارشنبه: مقایسه‌ی فروش', scheduled_at: new Date(now + 2 * day).toISOString() }, { id: 'b', status: 'draft', caption: 'پیش‌نویس کاروسل', scheduled_at: null }];
const account = { id: 'composio-instagram', username: 'sample.page', source: 'composio', followers: 12840 };
const routes = [
  [/^\/agent\/connection/, () => ({ connected: true })],
  [/^\/agent\/chat/, (body) => ({ reply: `درباره‌ی «${(body?.page?.title || 'این صفحه')}»: ${String(body?.page?.text || '').slice(0, 60) ? 'محتوای صفحه را دیدم و می‌توانم کمک کنم.' : 'صفحه خالی است.'}`, suggestions: ['یک ایده‌ی ریلز بده', 'تحلیل جدید'], action: null })],
  [/^\/agent\/run/, () => ({ status: 'started' })],
  [/^\/agent\/answer/, () => agent],
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
