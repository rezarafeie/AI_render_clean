import { ensureFreshToken, getToken, handleUnauthorized } from '../auth';
import { demo, demoOn } from './hermesDemo';

const BASE = (import.meta.env.VITE_HERMES_API_URL || '/api/hermes').replace(/\/$/, '');

async function request(path, { method = 'GET', body, ...options } = {}) {
  if (demoOn()) return demo(path.split('?')[0], body);
  await ensureFreshToken();
  const token = getToken();
  if (!token) handleUnauthorized();
  const headers = { Authorization: `Bearer ${token}`, ...options.headers };
  if (body !== undefined && !(body instanceof FormData)) headers['Content-Type'] = 'application/json';
  let response;
  try {
    response = await fetch(`${BASE}${path}`, { ...options, method, headers, body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new Error('Hermes is unavailable. Check that its service is running.');
  }
  if (response.status === 401) handleUnauthorized();
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    const detail = data?.detail;
    const message = typeof detail === 'string' ? detail : detail?.code || `Hermes request failed (${response.status})`;
    throw new Error(message.replaceAll('_', ' ').toLowerCase());
  }
  return response.status === 204 ? null : response.json();
}

const query = (values = {}) => {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => { if (value !== undefined && value !== null && value !== '') params.set(key, value); });
  return params.size ? `?${params}` : '';
};

export const hermesApi = {
  getComposioSettings: (options) => request('/composio', options),
  setComposioEnabled: (enabled) => request('/composio', { method: 'PUT', body: { enabled } }),
  getComposioConnections: () => request('/composio/connections'),
  connectComposioApp: (application) => request('/composio/connect', { method: 'POST', body: { application } }),
  getInstagramSettings: () => request('/settings/instagram'),
  saveInstagramSettings: (credentials) => request('/settings/instagram', { method: 'POST', body: credentials }),
  deleteInstagramSettings: () => request('/settings/instagram', { method: 'DELETE' }),
  testInstagramConnection: () => request('/settings/instagram/test', { method: 'POST' }),
  getAgentConnection: () => request('/agent/connection'),
  chatAgent: (message, page, history) => request('/agent/chat', { method: 'POST', body: { message, page, history } }),
  getAgent: () => request('/agent'),
  runAgent: (steps, count = 4) => request('/agent/run', { method: 'POST', body: steps ? { steps, count } : { count } }),
  answerAgent: (key, value) => request('/agent/answer', { method: 'POST', body: { key, value } }),
  setProposalStatus: (id, status, conversationId) => request(`/agent/proposals/${id}`, { method: 'POST', body: { status, conversation_id: conversationId } }),
  askAgent: (skill, text, language = 'fa') => request('/agent/ask', { method: 'POST', body: { skill, text, language } }),
  getSkills: () => request('/skills'),
  getSkillAccount: () => request('/skills/account'),
  runSkill: (skill, text, language = 'fa', options = {}) => request(`/skills/${skill}`, { method: 'POST', body: { text, language, options } }),
  connectInstagram: () => request('/auth/connect', { method: 'POST' }),
  authCallback: (code, state) => request(`/auth/callback${query({ code, state })}`),
  refreshToken: (accountId) => request('/auth/refresh', { method: 'POST', body: { account_id: accountId } }),
  getAccounts: () => request('/auth/accounts'),
  createPost: (post) => request('/posts/', { method: 'POST', body: post }),
  getPosts: (filters) => request(`/posts/${query(filters)}`),
  getPost: (id) => request(`/posts/${encodeURIComponent(id)}`),
  updatePost: (id, post) => request(`/posts/${encodeURIComponent(id)}`, { method: 'PUT', body: post }),
  deletePost: (id) => request(`/posts/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  publishNow: (id) => request(`/posts/${encodeURIComponent(id)}/publish`, { method: 'POST' }),
  uploadMedia: (file) => { const body = new FormData(); body.append('file', file); return request('/posts/media', { method: 'POST', body }); },
  getSchedule: (filters) => request(`/schedule/${query(filters)}`),
  bulkSchedule: (items) => request('/schedule/bulk', { method: 'POST', body: { items } }),
  getAccountAnalytics: (accountId) => request(`/analytics/account/${encodeURIComponent(accountId)}`),
  getPostAnalytics: (accountId) => request(`/analytics/posts/${encodeURIComponent(accountId)}`),
  refreshAnalytics: (accountId) => request(`/analytics/refresh/${encodeURIComponent(accountId)}`, { method: 'POST' }),
  getBestTimes: (body) => request('/advisor/best-times', { method: 'POST', body }),
  getHashtags: (body) => request('/advisor/hashtags', { method: 'POST', body }),
  generateCaption: (body) => request('/advisor/caption', { method: 'POST', body }),
  getContentPlan: (body) => request('/advisor/content-plan', { method: 'POST', body }),
};

export default hermesApi;
