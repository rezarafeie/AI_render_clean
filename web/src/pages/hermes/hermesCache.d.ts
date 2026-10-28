export function writeCache(key: string, data: unknown): { data: unknown; at: number };
export function peekCache(key: string): unknown;
export function useHermesData<T = any>(key: string, fetcher: () => Promise<T>, options?: { every?: number; enabled?: boolean }): {
  data: T | null; loading: boolean; refreshing: boolean; error: string; at: number | null; reload: () => Promise<T | null>;
};
