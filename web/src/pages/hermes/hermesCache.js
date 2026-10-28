// Stale-while-revalidate for the Hermes pages: the last answer is shown at once (memory, then localStorage), the request runs in the
// background, and the new answer replaces the old one. `refreshing` tells the page to show an "updating" state instead of a blank spinner.
import { useCallback, useEffect, useRef, useState } from 'react';
import { getToken } from '../../auth';

const memory = new Map();

function owner() {
  try { return JSON.parse(atob((getToken() || '').split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).sub || 'u'; } catch { return 'u'; }
}
const storageKey = (key) => `hermes:v1:${owner()}:${key}`;

function read(key) {
  const k = storageKey(key);
  if (memory.has(k)) return memory.get(k);
  try { const raw = JSON.parse(localStorage.getItem(k) || 'null'); if (raw) { memory.set(k, raw); return raw; } } catch { /* storage may be unavailable */ }
  return null;
}
function write(key, data) {
  const entry = { data, at: Date.now() };
  memory.set(storageKey(key), entry);
  try { localStorage.setItem(storageKey(key), JSON.stringify(entry)); } catch { /* quota or private mode: memory still works */ }
  return entry;
}

export function writeCache(key, data) { return write(key, data); }
export function peekCache(key) { return read(key)?.data ?? null; }

export function useHermesData(key, fetcher, { every = 0, enabled = true } = {}) {
  const first = read(key);
  const [data, setData] = useState(first?.data ?? null);
  const [at, setAt] = useState(first?.at ?? null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const alive = useRef(true);
  const run = useRef(fetcher);
  run.current = fetcher;
  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const next = await run.current();
      const entry = write(key, next);
      if (alive.current) { setData(next); setAt(entry.at); setError(''); }
      return next;
    } catch (e) {
      if (alive.current) setError(e?.message || 'Could not update');
      return null;
    } finally { if (alive.current) setRefreshing(false); }
  }, [key]);
  useEffect(() => {
    alive.current = true;
    const cached = read(key);
    setData(cached?.data ?? null); setAt(cached?.at ?? null);
    if (!enabled) return () => { alive.current = false; };
    void load();
    const timer = every ? setInterval(() => { void load(); }, every) : null;
    return () => { alive.current = false; if (timer) clearInterval(timer); };
  }, [key, enabled, every, load]);
  return { data, loading: data === null && refreshing, refreshing, error, at, reload: load };
}
