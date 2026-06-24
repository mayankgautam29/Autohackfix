from __future__ import annotations

from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.responses import Response

from app.agent.graph import run_pipeline
from app.config import get_settings
from app.diff_util import diff_line_stats, unified_diff_text
from app.rate_limit import RateLimiter, client_ip

load_dotenv()
_settings = get_settings()
_limiter = RateLimiter(_settings.rate_limit_requests, _settings.rate_limit_window_seconds)

app = FastAPI(
    title="AutoHackFix API",
    version="0.1.0",
    root_path=_settings.root_path.rstrip("/") if _settings.root_path else "",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    if _settings.app_env.lower() == "production":
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


class AnalyzeRequest(BaseModel):
    repo: str = Field(..., description="owner/repo or https://github.com/owner/repo")
    github_token: str = Field(
        "",
        description="Optional GitHub PAT. Required for private repos and PR creation.",
    )
    create_pr: bool = Field(False, description="If true, opens a real PR after validation")
    use_cache: bool = Field(
        True,
        description="Reuse cached repo snapshot when available (skips GitHub re-fetch on reruns).",
    )
    refresh_cache: bool = Field(
        False,
        description="Force a fresh GitHub scan and update the cache.",
    )


class IssueOut(BaseModel):
    file_path: str
    severity: str
    title: str
    description: str


class AnalyzeResponse(BaseModel):
    ok: bool
    owner: str = ""
    repo: str = ""
    default_branch: str = ""
    issues: list[IssueOut] = []
    target_path: str = ""
    fix_title: str = ""
    fix_explanation: str = ""
    new_content: str = ""
    diff_text: str = ""
    diff_additions: int = 0
    diff_deletions: int = 0
    confidence: float = 0.0
    validation_passed: bool = False
    validation_notes: str = ""
    pr_url: str | None = None
    branch_name: str | None = None
    ingest_from_cache: bool = False
    pr_blocked_reason: str | None = None
    stage_log: list[str] = []
    error: str | None = None


def _enforce_rate_limit(request: Request) -> None:
    ip = client_ip(
        request.headers.get("x-forwarded-for"),
        request.client.host if request.client else None,
    )
    allowed, retry_after = _limiter.check(ip)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    """Render and uptime checks often hit `/` or `HEAD /`."""
    return {"service": "AutoHackFix API", "health": "/health"}


@app.head("/", include_in_schema=False)
def root_head() -> Response:
    """Uptime monitors often use HEAD; FastAPI does not add it automatically for every GET."""
    return Response(status_code=200)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.head("/health", include_in_schema=False)
def health_head() -> Response:
    return Response(status_code=200)


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(body: AnalyzeRequest, request: Request) -> AnalyzeResponse:
    _enforce_rate_limit(request)

    if not _settings.openai_api_key:
        raise HTTPException(
            status_code=500,
            detail="Server missing OPENAI_API_KEY. Add it to backend/.env",
        )

    state: dict[str, Any] = run_pipeline(
        body.repo,
        body.github_token,
        create_pr=body.create_pr,
        use_cache=body.use_cache,
        refresh_cache=body.refresh_cache,
        cache_ttl_seconds=_settings.cache_ttl_seconds,
        model=_settings.openai_model,
        openai_key=_settings.openai_api_key,
    )

    issues = [IssueOut(**i) for i in state.get("issues") or [] if isinstance(i, dict)]
    err = state.get("error")
    ok = not err

    target_path = state.get("target_path") or ""
    old_content = (state.get("files_snapshot") or {}).get(target_path, "")
    new_content = state.get("new_content") or ""
    diff_text = ""
    diff_additions = 0
    diff_deletions = 0
    if target_path and new_content and old_content != new_content:
        diff_text = unified_diff_text(old_content, new_content, target_path)
        diff_additions, diff_deletions = diff_line_stats(diff_text)

    return AnalyzeResponse(
        ok=ok,
        owner=state.get("owner") or "",
        repo=state.get("repo") or "",
        default_branch=state.get("default_branch") or "",
        issues=issues,
        target_path=target_path,
        fix_title=state.get("fix_title") or "",
        fix_explanation=state.get("fix_explanation") or "",
        new_content=new_content,
        diff_text=diff_text,
        diff_additions=diff_additions,
        diff_deletions=diff_deletions,
        confidence=float(state.get("confidence") or 0.0),
        validation_passed=bool(state.get("validation_passed")),
        validation_notes=state.get("validation_notes") or "",
        pr_url=state.get("pr_url"),
        branch_name=state.get("branch_name"),
        ingest_from_cache=bool(state.get("ingest_from_cache")),
        pr_blocked_reason=state.get("pr_blocked_reason"),
        stage_log=list(state.get("stage_log") or []),
        error=err,
    )
