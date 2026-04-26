from __future__ import annotations

from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.requests import Request

from app.agent.graph import run_pipeline
from app.config import get_settings

load_dotenv()
_settings = get_settings()

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
    github_token: str = Field(..., min_length=8, description="GitHub PAT with repo scope")
    create_pr: bool = Field(False, description="If true, opens a real PR after validation")


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
    confidence: float = 0.0
    validation_passed: bool = False
    validation_notes: str = ""
    pr_url: str | None = None
    branch_name: str | None = None
    stage_log: list[str] = []
    error: str | None = None


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    """Render and uptime checks often hit `/` or `HEAD /`."""
    return {"service": "AutoHackFix API", "health": "/health"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(body: AnalyzeRequest) -> AnalyzeResponse:
    if not _settings.openai_api_key:
        raise HTTPException(
            status_code=500,
            detail="Server missing OPENAI_API_KEY. Add it to backend/.env",
        )

    state: dict[str, Any] = run_pipeline(
        body.repo,
        body.github_token,
        create_pr=body.create_pr,
        model=_settings.openai_model,
        openai_key=_settings.openai_api_key,
    )

    issues = [IssueOut(**i) for i in state.get("issues") or [] if isinstance(i, dict)]
    err = state.get("error")
    ok = not err

    return AnalyzeResponse(
        ok=ok,
        owner=state.get("owner") or "",
        repo=state.get("repo") or "",
        default_branch=state.get("default_branch") or "",
        issues=issues,
        target_path=state.get("target_path") or "",
        fix_title=state.get("fix_title") or "",
        fix_explanation=state.get("fix_explanation") or "",
        new_content=state.get("new_content") or "",
        confidence=float(state.get("confidence") or 0.0),
        validation_passed=bool(state.get("validation_passed")),
        validation_notes=state.get("validation_notes") or "",
        pr_url=state.get("pr_url"),
        branch_name=state.get("branch_name"),
        stage_log=list(state.get("stage_log") or []),
        error=err,
    )
