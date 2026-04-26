"use client";

import {
  AlertCircle,
  AlertTriangle,
  ChevronRight,
  ExternalLink,
  FolderGit2,
  GitPullRequest,
  KeyRound,
  Loader2,
  ScrollText,
  Sparkles,
} from "lucide-react";
import { useMemo, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

type Issue = {
  file_path: string;
  severity: string;
  title: string;
  description: string;
};

type AnalyzeResult = {
  ok: boolean;
  owner: string;
  repo: string;
  default_branch: string;
  issues: Issue[];
  target_path: string;
  fix_title: string;
  fix_explanation: string;
  new_content: string;
  confidence: number;
  validation_passed: boolean;
  validation_notes: string;
  pr_url: string | null;
  branch_name: string | null;
  stage_log: string[];
  error: string | null;
};

function severityStyle(s: string) {
  const x = s.toLowerCase();
  if (x === "high") return "bg-rose-500/15 text-rose-300 ring-rose-500/25";
  if (x === "medium") return "bg-amber-500/12 text-amber-200 ring-amber-500/25";
  return "bg-zinc-500/15 text-zinc-300 ring-zinc-500/20";
}

export default function Home() {
  const [repo, setRepo] = useState("");
  const [token, setToken] = useState("");
  const [createPr, setCreatePr] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [clientError, setClientError] = useState<string | null>(null);

  const fullRepoLabel = useMemo(() => {
    if (!result?.owner) return "";
    return `${result.owner}/${result.repo}`;
  }, [result]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setClientError(null);
    setResult(null);
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repo: repo.trim(),
          github_token: token.trim(),
          create_pr: createPr,
        }),
      });
      const data = (await res.json()) as AnalyzeResult & { detail?: unknown };
      if (!res.ok) {
        const detail =
          typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail ?? res.statusText);
        setClientError(detail);
        return;
      }
      setResult(data);
    } catch (err) {
      setClientError(
        err instanceof Error
          ? `${err.message}. Is the API running at ${API_BASE}?`
          : "Request failed.",
      );
    } finally {
      setLoading(false);
    }
  }

  const logSteps = result?.stage_log ?? [];

  const inputClass =
    "w-full rounded-xl border border-[var(--border)] bg-[var(--bg)] px-4 py-3 text-[15px] text-[var(--text)] outline-none transition placeholder:text-[var(--faint)] focus:border-emerald-500/40 focus:ring-2 focus:ring-emerald-500/15";

  return (
    <div className="relative min-h-full overflow-x-hidden">
      <div
        className="pointer-events-none fixed inset-0 bg-[var(--bg)]"
        aria-hidden
      />
      <div
        className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_90%_60%_at_50%_-30%,var(--accent-glow),transparent_55%)]"
        aria-hidden
      />
      <div
        className="pointer-events-none fixed inset-0 bg-[linear-gradient(to_bottom,transparent_0%,var(--bg)_100%)] opacity-40"
        aria-hidden
      />
      <div
        className="pointer-events-none fixed inset-0 opacity-[0.035]"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
        }}
        aria-hidden
      />

      <div className="relative mx-auto max-w-2xl px-5 pb-24 pt-16 sm:px-6 sm:pt-24">
        <header className="mb-12 text-center sm:mb-14">
          <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--surface)] px-3 py-1 text-xs font-medium text-[var(--muted)]">
            <Sparkles className="size-3.5 text-emerald-400/90" strokeWidth={2} />
            Repo fix assistant
          </div>
          <h1 className="text-4xl font-semibold tracking-tight text-white sm:text-5xl">
            AutoHackFix
          </h1>
          <p className="mx-auto mt-4 max-w-md text-[15px] leading-relaxed text-[var(--muted)]">
            Scan a GitHub repo for clear issues, get a proposed patch, and optionally open a PR.
          </p>
        </header>

        <form
          onSubmit={onSubmit}
          className="rounded-2xl border border-[var(--border)] bg-[var(--surface)]/90 p-6 shadow-[0_0_0_1px_rgba(255,255,255,0.03)_inset,0_24px_48px_-12px_rgba(0,0,0,0.5)] backdrop-blur-sm sm:p-8"
        >
          <div className="space-y-5">
            <div>
              <label
                htmlFor="repo"
                className="mb-2 flex items-center gap-2 text-sm font-medium text-zinc-200"
              >
                <FolderGit2 className="size-4 text-[var(--faint)]" strokeWidth={2} />
                Repository
              </label>
              <input
                id="repo"
                className={inputClass}
                placeholder="owner/name or github.com/…"
                value={repo}
                onChange={(e) => setRepo(e.target.value)}
                autoComplete="off"
                required
              />
            </div>

            <div>
              <label
                htmlFor="token"
                className="mb-2 flex items-center gap-2 text-sm font-medium text-zinc-200"
              >
                <KeyRound className="size-4 text-[var(--faint)]" strokeWidth={2} />
                GitHub token
              </label>
              <input
                id="token"
                type="password"
                className={`${inputClass} font-mono text-sm`}
                placeholder="ghp_… or fine-grained PAT"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                autoComplete="off"
                required
              />
              <p className="mt-2 text-xs leading-relaxed text-[var(--faint)]">
                Sent to your API for this request only. Needs read access; PRs need write + PR scope.
              </p>
            </div>

            <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg)]/80 p-4 transition hover:border-zinc-700 hover:bg-[var(--surface-hover)]/50">
              <input
                type="checkbox"
                className="mt-1 size-4 rounded border-zinc-600 bg-zinc-900 text-emerald-500 focus:ring-emerald-500/30 focus:ring-offset-0"
                checked={createPr}
                onChange={(e) => setCreatePr(e.target.checked)}
              />
              <span className="text-sm leading-snug">
                <span className="flex items-center gap-2 font-medium text-zinc-100">
                  <GitPullRequest className="size-4 text-emerald-400/80" strokeWidth={2} />
                  Open a pull request
                </span>
                <span className="mt-1 block text-[var(--faint)]">
                  New branch, commit, and PR against the default branch.
                </span>
              </span>
            </label>

            <button
              type="submit"
              disabled={loading}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-500 px-4 py-3.5 text-[15px] font-semibold text-zinc-950 shadow-lg shadow-emerald-500/10 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? (
                <>
                  <Loader2 className="size-5 animate-spin" strokeWidth={2} />
                  Running…
                </>
              ) : (
                <>
                  Run analysis
                  <ChevronRight className="size-4 opacity-80" strokeWidth={2} />
                </>
              )}
            </button>
          </div>
        </form>

        <div className="mt-12 space-y-8">
          {clientError && (
            <div className="rounded-2xl border border-rose-500/25 bg-[var(--danger-bg)] px-5 py-4">
              <div className="flex gap-3">
                <AlertCircle className="mt-0.5 size-5 shrink-0 text-rose-400" strokeWidth={2} />
                <div className="min-w-0">
                  <p className="font-medium text-rose-100">Request failed</p>
                  <pre className="mt-2 whitespace-pre-wrap break-words font-mono text-xs text-rose-200/80">
                    {clientError}
                  </pre>
                </div>
              </div>
            </div>
          )}

          {result && (
            <>
              {!result.ok && result.error && (
                <div className="rounded-2xl border border-amber-500/25 bg-[var(--warn-bg)] px-5 py-4">
                  <div className="flex gap-3">
                    <AlertTriangle
                      className="mt-0.5 size-5 shrink-0 text-amber-400"
                      strokeWidth={2}
                    />
                    <div>
                      <p className="font-semibold text-amber-100">Stopped early</p>
                      <p className="mt-2 text-sm leading-relaxed text-amber-100/85">{result.error}</p>
                    </div>
                  </div>
                </div>
              )}

              {fullRepoLabel && (
                <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-2 text-center text-sm sm:justify-start sm:text-left">
                  <span className="font-mono font-medium text-white">{fullRepoLabel}</span>
                  {result.default_branch && (
                    <span className="text-[var(--faint)]">
                      <span className="text-zinc-600">·</span> {result.default_branch}
                    </span>
                  )}
                  {typeof result.confidence === "number" && result.confidence > 0 && (
                    <span className="rounded-md bg-[var(--accent-dim)] px-2 py-0.5 font-medium text-emerald-300/95">
                      {(result.confidence * 100).toFixed(0)}% confidence
                    </span>
                  )}
                </div>
              )}

              {result.issues.length > 0 && (
                <section>
                  <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--faint)]">
                    Findings
                  </h2>
                  <ul className="mt-4 space-y-3">
                    {result.issues.map((issue) => (
                      <li
                        key={`${issue.file_path}-${issue.title}`}
                        className="rounded-xl border border-[var(--border)] bg-[var(--surface)]/80 p-4 shadow-sm shadow-black/20"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span
                            className={`rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ring-1 ${severityStyle(issue.severity)}`}
                          >
                            {issue.severity}
                          </span>
                          <span className="font-mono text-xs text-[var(--muted)]">{issue.file_path}</span>
                        </div>
                        <p className="mt-2.5 font-medium text-zinc-100">{issue.title}</p>
                        <p className="mt-1.5 text-[15px] leading-relaxed text-[var(--muted)]">
                          {issue.description}
                        </p>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {result.fix_explanation && (
                <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface)]/80 p-6 shadow-sm shadow-black/25">
                  <h2 className="text-lg font-semibold text-white">
                    {result.fix_title || "Suggested change"}
                  </h2>
                  <p className="mt-4 whitespace-pre-wrap text-[15px] leading-relaxed text-[var(--muted)]">
                    {result.fix_explanation}
                  </p>
                  {result.validation_notes && (
                    <p className="mt-5 border-t border-[var(--border)] pt-5 text-sm text-[var(--muted)]">
                      <span className="font-medium text-zinc-300">Checks · </span>
                      {result.validation_notes}
                    </p>
                  )}
                </section>
              )}

              {result.new_content && result.target_path && (
                <details className="group rounded-2xl border border-[var(--border)] bg-[var(--surface)]/60 open:bg-[var(--surface)]/90">
                  <summary className="flex cursor-pointer list-none items-center gap-2 px-5 py-4 text-sm font-medium text-zinc-200 marker:content-none [&::-webkit-details-marker]:hidden">
                    <ChevronRight className="size-4 shrink-0 text-emerald-400/80 transition group-open:rotate-90" />
                    <span>
                      Full file{" "}
                      <span className="font-mono text-[13px] font-normal text-[var(--muted)]">
                        {result.target_path}
                      </span>
                    </span>
                  </summary>
                  <pre className="max-h-[min(26rem,60vh)] overflow-auto border-t border-[var(--border)] bg-[var(--bg-elevated)] p-4 font-mono text-[13px] leading-relaxed text-zinc-300">
                    {result.new_content}
                  </pre>
                </details>
              )}

              {result.pr_url && (
                <a
                  href={result.pr_url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center justify-between gap-4 rounded-2xl border border-emerald-500/35 bg-[var(--accent-dim)] px-5 py-4 text-emerald-200 transition hover:border-emerald-400/50 hover:bg-emerald-500/15"
                >
                  <span className="font-semibold">Open pull request</span>
                  <ExternalLink className="size-4 shrink-0 opacity-80" strokeWidth={2} />
                </a>
              )}

              {logSteps.length > 0 && (
                <details className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)]/50 px-4 py-3">
                  <summary className="flex cursor-pointer list-none items-center gap-2 font-medium text-zinc-400 marker:content-none [&::-webkit-details-marker]:hidden">
                    <ScrollText className="size-4" strokeWidth={2} />
                    Run log
                  </summary>
                  <ul className="mt-3 space-y-2 border-t border-[var(--border)] pt-3 font-mono text-xs text-[var(--muted)]">
                    {logSteps.map((line, i) => (
                      <li
                        key={`${i}-${line}`}
                        className="border-l-2 border-emerald-500/30 pl-3 text-zinc-400"
                      >
                        {line}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </>
          )}

          {!result && !clientError && !loading && (
            <p className="text-center text-sm text-[var(--faint)]">
              Results appear here after a successful run.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
