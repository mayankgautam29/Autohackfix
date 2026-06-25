import { normalizeRepoKey } from "./api";

export const scanKeys = {
  result: (repo: string) => ["scan", "result", normalizeRepoKey(repo)] as const,
};

export const CACHE_STALE_MS = 60 * 60 * 1000;
