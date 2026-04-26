# AutoHackFix

Analyze a **GitHub** repository with an LLM, get a **minimal code fix** for the highest-severity finding, run **light validation**, and **optionally open a pull request**—all behind a small **FastAPI** service and a **Next.js** UI.

The backend runs a **LangGraph** pipeline (ingest → detect → fix → validate → PR) so each stage is explicit and easy to extend.

---

## What it does

| Stage | Behavior |
|--------|----------|
| **Ingest** | Resolves `owner/repo` (or URL), reads repo metadata, lists root + common folders (`src`, `app`, …), fetches up to **12** text files (capped length per file). |
| **Detect** | LLM returns JSON: issues tied to **those paths only**. |
| **Fix** | One issue (highest severity): LLM returns **full replacement file** + explanation + confidence. |
| **Validate** | Ensures the output differs from the original, sanity-checks size, and for **`.py`** runs `ast.parse`. |
| **Pull request** | Optional: new branch `autohackfix/agent-*`, commit, open PR (needs a token with write access). |

The UI sends your **GitHub token** to **your** API only; the **OpenAI** key stays on the server.

---

## Stack

| Layer | Tech |
|--------|------|
| API | [FastAPI](https://fastapi.tiangolo.com/), [Pydantic](https://docs.pydantic.dev/) |
| Agent | [LangGraph](https://langchain-ai.github.io/langgraph/), [LangChain OpenAI](https://python.langchain.com/docs/integrations/chat/openai/) |
| HTTP client | [httpx](https://www.python-httpx.org/) → GitHub REST |
| UI | [Next.js](https://nextjs.org/) 16, React 19, [Tailwind CSS](https://tailwindcss.com/) 4, [Lucide](https://lucide.dev/) |

### Live deployment

| | URL |
|--|-----|
| UI (Vercel) | [https://autohackfix.vercel.app](https://autohackfix.vercel.app/) |
| API (Render) | [https://autohackfix.onrender.com](https://autohackfix.onrender.com) |

Production builds read **`NEXT_PUBLIC_API_URL`** from [`.env.production`](.env.production) so the browser calls the Render API. After changing URLs, redeploy both services. On Render, set **`CORS_ORIGINS`** if it is overridden in the dashboard (must include `https://autohackfix.vercel.app`).

---

## Prerequisites

- **Node.js** 20+
- **Python** 3.11+
- [OpenAI API key](https://platform.openai.com/api-keys) (server-side, in `backend/.env`)
- **GitHub personal access token** with access to the target repo (entered in the UI for local use)

---

## Quick start

### 1. Backend

From the `backend` directory (so `app` imports and `.env` resolve correctly):

```bash
cd backend
python -m venv .venv
```

**Windows (PowerShell)**

```powershell
.\.venv\Scripts\pip install -r requirements.txt
```

**macOS / Linux**

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env` from `backend/.env.example`, then set `OPENAI_API_KEY`:

```bash
cp .env.example .env
```

**Windows (PowerShell)** — still inside `backend/`: `Copy-Item .env.example .env`

Optional: `CORS_ORIGINS` (comma-separated), e.g. `http://localhost:3000,http://127.0.0.1:3000`.

Run the API:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Health: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- Analyze: `POST http://127.0.0.1:8000/api/analyze`

### 2. Frontend

From the **repository root**:

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

If the API is not on `http://127.0.0.1:8000`, copy `.env.local.example` to `.env.local` and set `NEXT_PUBLIC_API_URL`.

---

## API

### `POST /api/analyze`

**Body (JSON)**

| Field | Type | Description |
|--------|------|-------------|
| `repo` | string | `owner/repo` or `https://github.com/owner/repo` |
| `github_token` | string | PAT used for GitHub REST (read for scan; write for PR) |
| `create_pr` | boolean | If `true`, opens a real PR after validation |

**Response (JSON)** — main fields: `ok`, `owner`, `repo`, `default_branch`, `issues[]`, `target_path`, `fix_title`, `fix_explanation`, `new_content`, `confidence`, `validation_passed`, `validation_notes`, `pr_url`, `branch_name`, `stage_log[]`, `error`.

- HTTP **200** is returned for most outcomes; check **`ok`** and **`error`** for pipeline success vs failure.
- Missing server OpenAI key → **500** with a clear `detail` message.

### `GET /health`

Returns `{"status":"ok"}`.

---

## Deployment

### Environment variables

**API (`backend`)**

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | Server-side OpenAI key |
| `OPENAI_MODEL` | No | Default `gpt-4o-mini` |
| `CORS_ORIGINS` | Yes in prod | Comma-separated frontend origins, e.g. `https://myapp.vercel.app` |
| `APP_ENV` | No | Set `production` for extra response headers |
| `ROOT_PATH` | No | Path prefix behind a reverse proxy (no trailing slash) |
| `PORT` | Auto | Set by many hosts; Docker image defaults to `8000` |

**Frontend**

| Variable | When | Description |
|----------|------|-------------|
| `NEXT_PUBLIC_API_URL` | Build time | Public HTTPS URL of the API (no trailing slash). Inlined into the client bundle. |

Copy templates: `backend/.env.example` → `backend/.env`, `.env.local.example` → `.env.local`.

### Docker (API)

From `backend/`:

```bash
docker build -t autohackfix-api .
docker run --rm -p 8000:8000 --env-file .env -e APP_ENV=production autohackfix-api
```

Uses `PORT` if set (e.g. `-e PORT=8080`). Uvicorn listens on `0.0.0.0` with `--proxy-headers` for HTTPS behind a load balancer.

### Docker (frontend)

From the **repo root** (pass your real API URL):

```bash
docker build -t autohackfix-web --build-arg NEXT_PUBLIC_API_URL=https://api.example.com .
docker run --rm -p 3000:3000 autohackfix-web
```

### Docker Compose (full stack locally)

1. Create `backend/.env` with at least `OPENAI_API_KEY`.
2. From repo root:

```bash
docker compose up --build
```

UI: [http://127.0.0.1:3000](http://127.0.0.1:3000) · API: [http://127.0.0.1:8000](http://127.0.0.1:8000)

### Hosted examples

- **Frontend (Vercel)**: connect the repo root; set `NEXT_PUBLIC_API_URL` to your API’s public URL; deploy.
- **API (Railway, Fly.io, Render, Cloud Run, etc.)**: set **root directory** to `backend` (or use `backend/Dockerfile`), add secrets above, ensure `CORS_ORIGINS` matches the live frontend origin.
- **Render**: see `render.yaml` as a starting blueprint; ensure the web service gets `NEXT_PUBLIC_API_URL` at **image build** time if the platform supports build-time env.

### Production command (without Docker)

```bash
cd backend
pip install -r requirements.txt
APP_ENV=production uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
```

---

## GitHub token permissions

- **Read-only flow** (analyze + suggest fix in response): token must be able to **read** repository contents.
- **Open a PR**: token needs permission to **create refs** (branch), **push** file contents, and **open pull requests** (classic: `repo` for private; for public repos ensure scopes match your setup; fine-grained: **Contents** and **Pull requests** write access on that repository).

If you see **`403` — Resource not accessible by personal access token** on `create-a-reference`, the token cannot create branches on that repo—fix scopes or use a token from an account with push access.

---

## Project layout

```text
autohackfix/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI app, CORS, /health, /api/analyze
│   │   ├── config.py         # Settings from env / .env
│   │   ├── github_client.py  # GitHub REST helpers
│   │   └── agent/
│   │       └── graph.py      # LangGraph pipeline
│   ├── Dockerfile
│   ├── .env.example
│   ├── requirements.txt
│   └── .env                  # Local only; not committed
├── src/app/                  # Next.js App Router UI
├── Dockerfile                # Production Next (standalone)
├── docker-compose.yml
├── render.yaml               # Optional Render blueprint
├── .env.local.example
├── .env.production            # NEXT_PUBLIC_API_URL for Vercel builds
├── package.json
└── README.md
```

---

## Security

- **Local demos**: pasting a PAT into the UI sends it to **your** backend over your network; it is not stored in the browser by this app’s logic, but you should still treat PATs as secrets.
- **Production**: prefer a **GitHub App**, **OAuth**, or server-side stored credentials—never embed long-lived tokens in client bundles or public repos.
- Do **not** commit `backend/.env` or real keys.

---

## Troubleshooting

| Symptom | What to check |
|---------|----------------|
| UI says API unreachable | Backend running? Correct `NEXT_PUBLIC_API_URL`? Firewall? |
| `Issue detection could not parse model output` | Model returned non-JSON; backend parses fenced JSON—retry or switch model. |
| `403` when creating PR | PAT lacks write/ref permissions or SSO/org access. |
| Empty or tiny ingest | Repo layout may not match scanned paths; see `list_root_paths` / `select_text_files` in `github_client.py`. |

---

## Scripts (frontend)

| Command | Purpose |
|---------|---------|
| `npm run dev` | Development server |
| `npm run build` | Production build |
| `npm run start` | Run production server |

---

## Extending

Ideas that fit the current shape: deeper repo crawling, tests/CI as a validation step, embeddings or AST-aware context, GitHub App auth, multi-file patches, or human-in-the-loop approval before `node_pr`.

---

## License

Add a `LICENSE` file if you distribute or open-source this project.
