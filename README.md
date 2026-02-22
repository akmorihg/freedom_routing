# Freedom Routing

High-level multi-service system for:
- ingesting CSV datasets (tickets, managers, business units),
- running AI analysis on tickets,
- routing tickets to managers with heuristic balancing,
- querying data through a LangGraph NL2SQL chat interface.

## Project Structure (High Level)

- `backend/` - core FastAPI backend (CRUD, DB access, MinIO static files, Redis-backed caching).
- `ai_service/` - AI microservice (LLM analysis, CSV upload-to-DB orchestration, routing logic).
- `my-ui-app/` - main React dashboard UI (served by Nginx in Docker).
- `agent-chat-ui/` - LangGraph chat UI (Git submodule).
- `docker-compose.yml` - full local stack orchestration.
- `ARCHITECTURE_HIGH_LEVEL.md` - container/link architecture document.

## Submodule (Important)

`agent-chat-ui` is a git submodule (not a normal folder copy).  
After clone, initialize it before starting Docker:

```bash
git submodule update --init --recursive
```

If submodule code looks outdated after pulling:

```bash
git submodule update --remote --recursive
```

## Required `.env` Files

Docker Compose expects these files to exist:
- `backend/.env`
- `ai_service/.env`
- `agent-chat-ui/.env`

Do not commit real secrets to git.

### 1) `backend/.env`

Start from `backend/.env.example`:

```bash
cp backend/.env.example backend/.env
```

Minimum values for local Docker stack:

```env
DATABASE_URL=postgresql+psycopg://app_user:app_password@postgres:5432/app_db
REDIS_URL=redis://redis:6379/0

S3_URL=http://minio:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin123
S3_REGION_NAME=us-east-1
S3_BUCKET=static

OPENAI_API_KEY=YOUR_OPENAI_KEY
OPENAI_MODEL=gpt-5-mini

# Optional tuning (can be left empty or set defaults)
NL2SQL_MAX_ROWS=100
NL2SQL_ANALYTICS_MAX_ROWS=500
NL2SQL_MAX_CHART_POINTS=30
NL2SQL_CANDIDATE_TOP_K=4
NL2SQL_CANDIDATE_MAX_K=8
NL2SQL_CANDIDATE_RESULT_PREVIEW_ROWS=25
NL2SQL_CHART_BUCKET=static
NL2SQL_CHART_KEY_PREFIX=nl2sql/charts
NL2SQL_CHART_URL_EXPIRES_IN=86400
```

### 2) `ai_service/.env`

This repo currently does not include `ai_service/.env.example`, so create manually:

```env
OPENAI_API_KEY=YOUR_OPENAI_KEY
OPENAI_MODEL=gpt-4o-mini
OPENAI_TEMPERATURE=0.1

TASK_TIMEOUT_SECONDS=5.0
IMAGE_TASK_TIMEOUT_SECONDS=45.0
MAX_RETRIES=2
RETRY_BASE_DELAY=0.3

LOG_LEVEL=INFO
LOG_TEXT_MAX_CHARS=100

GOOGLE_MAPS_API_KEY=YOUR_GOOGLE_MAPS_KEY
BACKEND_URL=http://backend:8000
BATCH_MAX_CONCURRENCY=30
```

Notes:
- `OPENAI_API_KEY` is required for AI analysis endpoints.
- `GOOGLE_MAPS_API_KEY` is required for routing endpoint (`/routing/assign-from-db`).

### 3) `agent-chat-ui/.env`

Start from example:

```bash
cp agent-chat-ui/.env.example agent-chat-ui/.env
```

Local defaults:

```env
NEXT_PUBLIC_API_URL=http://localhost:2024
NEXT_PUBLIC_ASSISTANT_ID=agent
LANGSMITH_API_KEY=
```

## Main Commands

### Start (Build + Run + Migrate)

Option A (recommended, uses Makefile):

```bash
make start
```

This runs:
- `docker compose up --build -d`
- DB migrations in backend container (`alembic upgrade head`)

Option B (manual):

```bash
docker compose up --build -d
docker compose exec backend alembic -c infrastructure/db/migrations/alembic.ini upgrade head
```

### Stop

Option A:

```bash
make stop
```

Option B:

```bash
docker compose down --volumes
```

Warning: `--volumes` removes Postgres/Redis/MinIO persisted local data.

### Useful Operations

```bash
# See container status
docker compose ps

# Tail all logs
docker compose logs -f

# Tail one service
docker compose logs -f backend
docker compose logs -f ai-service
docker compose logs -f langchain-server
```

## Local URLs After Startup

- Main UI: `http://localhost:3001`
- Agent Chat UI: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- AI Service API: `http://localhost:8001`
- LangGraph server: `http://localhost:2024`
- PgAdmin: `http://localhost:5050`
- MinIO API: `http://localhost:9000`
- MinIO Console: `http://localhost:9001`

## One-Time Quick Start Checklist

1. `git submodule update --init --recursive`
2. Create/update `backend/.env`
3. Create/update `ai_service/.env`
4. Create/update `agent-chat-ui/.env`
5. `make start`
6. Open `http://localhost:3001` and `http://localhost:3000`
