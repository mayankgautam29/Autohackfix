export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type Issue = {
  file_path: string;
  severity: string;
  title: string;
  description: string;
};

export type AnalyzeResult = {
  ok: boolean;
  owner: string;
  repo: string;
  default_branch: string;
  issues: Issue[];
  target_path: string;
  fix_title: string;
  fix_explanation: string;
  new_content: string;
  diff_text: string;
  diff_additions: number;
  diff_deletions: number;
  confidence: number;
  validation_passed: boolean;
  validation_notes: string;
  pr_url: string | null;
  branch_name: string | null;
  run_id: string | null;
  can_create_pr: boolean;
  ingest_from_cache: boolean;
  cache_backend: string;
  pr_blocked_reason: string | null;
  stage_log: string[];
  error: string | null;
};

export type AnalyzeParams = {
  repo: string;
  github_token: string;
  create_pr: boolean;
  use_cache: boolean;
  refresh_cache: boolean;
};

export function normalizeRepoKey(repo: string): string {
  return repo.trim().toLowerCase();
}

async function parseError(res: Response, data: unknown): Promise<string> {
  if (typeof data === "object" && data !== null && "detail" in data) {
    const detail = (data as { detail?: unknown }).detail;
    return typeof detail === "string" ? detail : JSON.stringify(detail ?? res.statusText);
  }
  return res.statusText;
}

export async function analyzeRepo(params: AnalyzeParams): Promise<AnalyzeResult> {
  const res = await fetch(`${API_BASE}/api/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  const data = (await res.json()) as AnalyzeResult & { detail?: unknown };
  if (!res.ok) {
    throw new Error(await parseError(res, data));
  }
  return data;
}

export async function createPrFromRun(runId: string, githubToken: string) {
  const res = await fetch(`${API_BASE}/api/create-pr`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: runId, github_token: githubToken }),
  });
  const data = (await res.json()) as {
    ok: boolean;
    pr_url?: string | null;
    branch_name?: string | null;
    error?: string | null;
    detail?: unknown;
  };
  if (!res.ok) {
    throw new Error(await parseError(res, data));
  }
  if (!data.ok || !data.pr_url) {
    throw new Error(data.error ?? "Could not open pull request.");
  }
  return data;
}
