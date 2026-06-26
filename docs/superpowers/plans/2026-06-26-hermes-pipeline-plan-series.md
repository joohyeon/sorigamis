# Sorigamis M2 — Hermes Pipeline Plan Series (Overview)

> **For agentic workers:** Each plan in this series is a standalone document. REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement each plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Milestone 2 of Sorigamis — the real AI pipeline server powered by Hermes as the intelligent orchestrator — as a sequence of independently-shippable plans, infrastructure-first.

**Why a series, not one plan:** M2 touches four loosely-coupled subsystems. Building them as separate plans keeps each one runnable and reviewable on its own.

## Build order

| Plan | Subsystem | Deliverable |
|------|-----------|-------------|
| **1** | **sg-pipeline backend** | FastAPI + Hermes + Modal workers running locally; full job lifecycle end-to-end |
| 2 | Flutter LivePipelineClient | Swap mock for live HTTP client; plan confirmation + checkpoint screens |
| 3 | Flutter Skills & Modes CRUD | Skills Library, Modes, Skill editor screens |
| 4 | Flutter Results & offline sync | Results screen, Drift sync on completion, offline access |

Each plan assumes the previous one merged to `main`. **Only Plan 1 is fully detailed below.** Ask for Plan 2+ when you finish the prior one.

---

# Plan 1 — sg-pipeline Backend (FastAPI + Hermes + Modal)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A FastAPI server running on Fly.io that accepts a recording job, spawns a Hermes agent session, transcribes audio from Google Drive using Modal/faster-whisper, diarizes speakers, proposes an execution plan for user confirmation, runs approved Skills, fires integration actions after checkpoint, and writes all results to Supabase.

**Architecture:** FastAPI wrapper (Fly.io, CPU-only) spawns one Hermes CLI session per job as a subprocess. Hermes loads `sg-orchestrator` skill and calls Modal for GPU work (Whisper + pyannote). Job state and results live in Supabase. FCM push notifies the Flutter app of status changes. Modal workers are deployed separately using `modal deploy`.

**Tech Stack:** Python 3.12, FastAPI, uv, Supabase (postgres + supabase-py), Hermes CLI (gemini-2.5-pro via GitHub Copilot), Modal (faster-whisper large-v3, pyannote.audio), google-api-python-client, firebase-admin (FCM), pytest, httpx (test client).

## Global Constraints

- All table names, tool names, and skill names use the `sg-` / `sg_` prefix (short for Sorigamis).
- Hermes model: `gemini-2.5-pro`, provider: `github-copilot`.
- Whisper: `faster-whisper==1.1.1`, model `large-v3`, `language=ko`, `compute_type=float16`, `device=cuda`, same params as `SoriNote/scripts/test_audio_locally.py`.
- Diarization: `pyannote.audio==3.3.2`, `num_speakers=2` default.
- All Supabase writes scoped by `job_id` — never write without it.
- TDD: failing test first, implementation second, verify pass, commit per task.
- Project lives in `pipeline/` subdirectory of the sorigamis repo.
- `uv` for dependency management (not pip directly).

## File Structure

```
pipeline/
  pyproject.toml              — uv project, deps
  .env.example                — required env vars
  fly.toml                    — Fly.io deploy config
  main.py                     — FastAPI app entry, mounts routers
  models.py                   — Pydantic request/response models
  supabase_client.py          — Supabase client singleton
  routers/
    jobs.py                   — POST /jobs, GET /jobs/{id}, confirm, checkpoint
    skills.py                 — CRUD /skills
    modes.py                  — CRUD /modes
  hermes/
    runner.py                 — spawn Hermes subprocess per job
    context.py                — build job context JSON injected into Hermes
    skills/
      sg-orchestrator.md      — master Hermes skill
      sg-skill-summary.md
      sg-skill-action-items.md
      sg-skill-decisions.md
      sg-skill-sentiment.md
  workers/
    whisper_worker.py         — Modal app: sg-whisper-transcribe
    diarize_worker.py         — Modal app: sg-diarize
  tools/
    sg_drive_download.py      — download audio from Google Drive
    sg_supabase_write.py      — write job state + results
    sg_notify_fcm.py          — FCM push notification
    sg_slack_post.py          — Slack integration action
    sg_linear_create.py       — Linear integration action
    sg_webhook_call.py        — generic webhook action
  supabase/
    migrations/
      20260626000000_sg_schema.sql   — all sg_* tables
  tests/
    conftest.py               — FastAPI test client, Supabase mock
    test_jobs.py              — job lifecycle API tests
    test_skills.py            — skills CRUD tests
    test_modes.py             — modes CRUD tests
    test_hermes_runner.py     — Hermes subprocess launch tests
    test_tools.py             — tool unit tests (mocked external calls)
```

---

## Task 1: Project Scaffold + Supabase Schema

**Files:**
- Create: `pipeline/pyproject.toml`
- Create: `pipeline/.env.example`
- Create: `pipeline/supabase/migrations/20260626000000_sg_schema.sql`

**Interfaces:**
- Produces: all `sg_*` tables in Supabase, ready for all subsequent tasks

- [ ] **Step 1: Create `pipeline/pyproject.toml`**

```toml
[project]
name = "sg-pipeline"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "supabase>=2.11",
  "google-api-python-client>=2.154",
  "google-auth>=2.36",
  "firebase-admin>=6.6",
  "httpx>=0.28",
  "pydantic>=2.10",
  "structlog>=25.0",
]

[dependency-groups]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.24",
  "pytest-httpx>=0.32",
  "anyio[trio]>=4.7",
]
```

- [ ] **Step 2: Install dependencies**

```bash
cd pipeline
uv sync
```

Expected: `pipeline/.venv/` created, all packages installed.

- [ ] **Step 3: Create `pipeline/.env.example`**

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
FCM_SERVER_KEY=your-fcm-server-key
MODAL_TOKEN_ID=your-modal-token-id
MODAL_TOKEN_SECRET=your-modal-token-secret
HERMES_MODEL=gemini-2.5-pro
HERMES_PROVIDER=github-copilot
```

- [ ] **Step 4: Write the Supabase migration**

Create `pipeline/supabase/migrations/20260626000000_sg_schema.sql`:

```sql
-- sg_skills: default (user_id IS NULL) and user-owned skills
create table sg_skills (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  name text not null,
  description text not null default '',
  ai_prompt text not null,
  integration_actions jsonb not null default '[]',
  is_default boolean not null default false,
  created_at timestamptz not null default now()
);

-- sg_modes: user-owned ordered bundles of skills
create table sg_modes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  skill_ids uuid[] not null default '{}',
  created_at timestamptz not null default now()
);

-- sg_jobs: one row per pipeline run
create table sg_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  mode_id uuid references sg_modes(id),
  drive_file_id text not null,
  status text not null default 'submitted',
  plan_json jsonb,
  checkpoint_json jsonb,
  error text,
  created_at timestamptz not null default now()
);

-- sg_speakers: detected speakers per job, confirmed by user at checkpoint
create table sg_speakers (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references sg_jobs(id) on delete cascade,
  label text not null,
  confirmed_name text,
  talk_time_pct float,
  created_at timestamptz not null default now()
);

-- sg_utterances: one row per Whisper segment, merged with diarization
create table sg_utterances (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references sg_jobs(id) on delete cascade,
  start_sec float not null,
  end_sec float not null,
  text text not null,
  speaker_id uuid references sg_speakers(id),
  confirmed_by_user boolean not null default false,
  avg_logprob float,
  created_at timestamptz not null default now()
);

-- sg_transcript_raw: full Whisper + pyannote output for debugging
create table sg_transcript_raw (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references sg_jobs(id) on delete cascade,
  whisper_json jsonb,
  diarize_json jsonb,
  created_at timestamptz not null default now()
);

-- sg_skill_results: one row per skill per job
create table sg_skill_results (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references sg_jobs(id) on delete cascade,
  skill_id uuid references sg_skills(id),
  skill_name text not null,
  output_json jsonb,
  output_markdown text,
  status text not null default 'pending',
  created_at timestamptz not null default now()
);

-- sg_action_logs: one row per integration action per job
create table sg_action_logs (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references sg_jobs(id) on delete cascade,
  skill_id uuid references sg_skills(id),
  action_type text not null,
  destination text,
  payload_json jsonb,
  status text not null default 'pending',
  fired_at timestamptz,
  error text,
  created_at timestamptz not null default now()
);

-- Seed default skills
insert into sg_skills (name, description, ai_prompt, is_default) values
  ('Summary', 'Concise meeting summary', 'Summarize the transcript into a clear, concise paragraph covering the main topics discussed.', true),
  ('Action Items', 'Extract tasks and owners', 'Extract all action items from the transcript. For each item return: text (the task), owner (speaker name if mentioned, else null). Return as JSON array: [{"text":"...","owner":"..."}]', true),
  ('Decisions', 'Key decisions made', 'List all decisions made during the conversation. Return as a JSON array of strings: ["Decision 1","Decision 2"]', true),
  ('Sentiment', 'Speaker tone analysis', 'Analyse the tone of each speaker. Return JSON: {"Speaker A": "positive|neutral|negative", "Speaker B": "positive|neutral|negative"}', true);
```

- [ ] **Step 5: Apply migration to Supabase**

```bash
# From the sorigamis repo root (where supabase CLI is configured)
supabase db push
```

Expected: Migration applied, all `sg_*` tables visible in Supabase dashboard.

- [ ] **Step 6: Commit**

```bash
git add pipeline/pyproject.toml pipeline/.env.example pipeline/supabase/migrations/
git commit -m "feat(pipeline): project scaffold and sg_* Supabase schema"
```

---

## Task 2: FastAPI Skeleton + Health Endpoint

**Files:**
- Create: `pipeline/main.py`
- Create: `pipeline/supabase_client.py`
- Create: `pipeline/models.py`
- Create: `pipeline/tests/conftest.py`
- Create: `pipeline/tests/test_health.py`

**Interfaces:**
- Produces:
  - `app` — FastAPI instance, imported by all router tests
  - `get_supabase()` — returns Supabase client, used in all routers
  - `GET /health` → `{"status": "ok"}`

- [ ] **Step 1: Write the failing test**

Create `pipeline/tests/conftest.py`:
```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

@pytest.fixture
def mock_supabase():
    return MagicMock()

@pytest.fixture
def client(mock_supabase):
    with patch("supabase_client.get_supabase", return_value=mock_supabase):
        from main import app
        return TestClient(app)
```

Create `pipeline/tests/test_health.py`:
```python
def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd pipeline
uv run pytest tests/test_health.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 3: Create `pipeline/supabase_client.py`**

```python
from __future__ import annotations
import os
from supabase import create_client, Client

_client: Client | None = None

def get_supabase() -> Client:
    global _client
    if _client is None:
        _client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        )
    return _client
```

- [ ] **Step 4: Create `pipeline/models.py`**

```python
from __future__ import annotations
from pydantic import BaseModel
from uuid import UUID
from typing import Any

class CreateJobRequest(BaseModel):
    drive_file_id: str
    mode_id: UUID
    user_id: UUID

class ConfirmJobRequest(BaseModel):
    approved_steps: list[str]
    per_step_overrides: dict[str, Any] = {}

class CheckpointRequest(BaseModel):
    data: dict[str, Any]

class CreateSkillRequest(BaseModel):
    name: str
    description: str = ""
    ai_prompt: str
    integration_actions: list[dict[str, Any]] = []

class UpdateSkillRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    ai_prompt: str | None = None
    integration_actions: list[dict[str, Any]] | None = None

class CreateModeRequest(BaseModel):
    name: str
    skill_ids: list[UUID]

class UpdateModeRequest(BaseModel):
    name: str | None = None
    skill_ids: list[UUID] | None = None
```

- [ ] **Step 5: Create `pipeline/main.py`**

```python
from __future__ import annotations
from fastapi import FastAPI

app = FastAPI(title="sg-pipeline")

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 6: Run test to verify it passes**

```bash
cd pipeline
uv run pytest tests/test_health.py -v
```

Expected: `PASSED`

- [ ] **Step 7: Verify server starts**

```bash
cd pipeline
uv run uvicorn main:app --reload --port 8080
```

Expected: `Uvicorn running on http://127.0.0.1:8080`. Hit `Ctrl+C` to stop.

- [ ] **Step 8: Commit**

```bash
git add pipeline/main.py pipeline/supabase_client.py pipeline/models.py pipeline/tests/
git commit -m "feat(pipeline): FastAPI skeleton + health endpoint + test client"
```

---

## Task 3: Jobs Router (Create + Status)

**Files:**
- Create: `pipeline/routers/jobs.py`
- Modify: `pipeline/main.py` — mount jobs router
- Create: `pipeline/tests/test_jobs.py`

**Interfaces:**
- Consumes: `CreateJobRequest`, `ConfirmJobRequest`, `CheckpointRequest` from `models.py`; `get_supabase()` from `supabase_client.py`
- Produces:
  - `POST /jobs` → `{"job_id": "<uuid>", "status": "submitted"}`
  - `GET /jobs/{id}` → `{"job_id": "...", "status": "...", "plan": null|{...}, "checkpoint": null|{...}}`

- [ ] **Step 1: Write the failing tests**

Create `pipeline/tests/test_jobs.py`:
```python
from uuid import uuid4
import pytest

JOB_PAYLOAD = {
    "drive_file_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs",
    "mode_id": str(uuid4()),
    "user_id": str(uuid4()),
}

def test_create_job(client, mock_supabase):
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": "abc-123", "status": "submitted"}
    ]
    response = client.post("/jobs", json=JOB_PAYLOAD)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "submitted"
    assert "job_id" in body

def test_get_job(client, mock_supabase):
    job_id = str(uuid4())
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": job_id,
        "status": "analyzing",
        "plan_json": None,
        "checkpoint_json": None,
    }
    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == job_id
    assert body["status"] == "analyzing"
    assert body["plan"] is None
    assert body["checkpoint"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd pipeline
uv run pytest tests/test_jobs.py -v
```

Expected: `FAILED` — 404 (route not found)

- [ ] **Step 3: Create `pipeline/routers/jobs.py`**

```python
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from uuid import uuid4
from models import CreateJobRequest, ConfirmJobRequest, CheckpointRequest
from supabase_client import get_supabase

router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.post("", status_code=201)
def create_job(body: CreateJobRequest, db=Depends(get_supabase)):
    result = db.table("sg_jobs").insert({
        "drive_file_id": body.drive_file_id,
        "mode_id": str(body.mode_id),
        "user_id": str(body.user_id),
        "status": "submitted",
    }).execute()
    row = result.data[0]
    return {"job_id": row["id"], "status": row["status"]}

@router.get("/{job_id}")
def get_job(job_id: str, db=Depends(get_supabase)):
    result = db.table("sg_jobs").select("*").eq("id", job_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Job not found")
    row = result.data
    return {
        "job_id": row["id"],
        "status": row["status"],
        "plan": row.get("plan_json"),
        "checkpoint": row.get("checkpoint_json"),
        "error": row.get("error"),
    }

@router.post("/{job_id}/confirm")
def confirm_job(job_id: str, body: ConfirmJobRequest, db=Depends(get_supabase)):
    db.table("sg_jobs").update({
        "status": "executing",
        "plan_json": {"approved_steps": body.approved_steps, "overrides": body.per_step_overrides},
    }).eq("id", job_id).execute()
    return {"job_id": job_id, "status": "executing"}

@router.post("/{job_id}/checkpoint")
def resolve_checkpoint(job_id: str, body: CheckpointRequest, db=Depends(get_supabase)):
    db.table("sg_jobs").update({
        "status": "executing",
        "checkpoint_json": body.data,
    }).eq("id", job_id).execute()
    return {"job_id": job_id, "status": "executing"}
```

- [ ] **Step 4: Mount router in `pipeline/main.py`**

```python
from __future__ import annotations
from fastapi import FastAPI
from routers import jobs

app = FastAPI(title="sg-pipeline")
app.include_router(jobs.router)

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd pipeline
uv run pytest tests/test_jobs.py tests/test_health.py -v
```

Expected: all `PASSED`

- [ ] **Step 6: Commit**

```bash
git add pipeline/routers/jobs.py pipeline/main.py pipeline/tests/test_jobs.py
git commit -m "feat(pipeline): jobs router — create, get, confirm, checkpoint"
```

---

## Task 4: Skills & Modes CRUD Routers

**Files:**
- Create: `pipeline/routers/skills.py`
- Create: `pipeline/routers/modes.py`
- Modify: `pipeline/main.py` — mount both routers
- Create: `pipeline/tests/test_skills.py`
- Create: `pipeline/tests/test_modes.py`

**Interfaces:**
- Consumes: `CreateSkillRequest`, `UpdateSkillRequest`, `CreateModeRequest`, `UpdateModeRequest` from `models.py`
- Produces:
  - `GET /skills` → `[{id, name, description, ai_prompt, integration_actions, is_default}]`
  - `POST /skills` → `{id, name, ...}`
  - `PUT /skills/{id}`, `DELETE /skills/{id}`
  - `GET /modes`, `POST /modes`, `PUT /modes/{id}`, `DELETE /modes/{id}`

- [ ] **Step 1: Write failing tests**

Create `pipeline/tests/test_skills.py`:
```python
from uuid import uuid4

SKILL = {"name": "My Skill", "description": "test", "ai_prompt": "Extract X from transcript."}

def test_create_skill(client, mock_supabase):
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": str(uuid4()), **SKILL, "is_default": False, "integration_actions": []}
    ]
    response = client.post("/skills", json=SKILL)
    assert response.status_code == 201
    assert response.json()["name"] == "My Skill"

def test_list_skills(client, mock_supabase):
    mock_supabase.table.return_value.select.return_value.execute.return_value.data = []
    response = client.get("/skills")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_delete_skill(client, mock_supabase):
    mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value.data = []
    response = client.delete(f"/skills/{uuid4()}")
    assert response.status_code == 204
```

Create `pipeline/tests/test_modes.py`:
```python
from uuid import uuid4

MODE = {"name": "My Mode", "skill_ids": [str(uuid4())]}

def test_create_mode(client, mock_supabase):
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": str(uuid4()), **MODE}
    ]
    response = client.post("/modes", json=MODE)
    assert response.status_code == 201
    assert response.json()["name"] == "My Mode"

def test_list_modes(client, mock_supabase):
    mock_supabase.table.return_value.select.return_value.execute.return_value.data = []
    response = client.get("/modes")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd pipeline
uv run pytest tests/test_skills.py tests/test_modes.py -v
```

Expected: `FAILED` — 404

- [ ] **Step 3: Create `pipeline/routers/skills.py`**

```python
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from models import CreateSkillRequest, UpdateSkillRequest
from supabase_client import get_supabase

router = APIRouter(prefix="/skills", tags=["skills"])

@router.get("")
def list_skills(user_id: str | None = None, db=Depends(get_supabase)):
    return db.table("sg_skills").select("*").execute().data

@router.post("", status_code=201)
def create_skill(body: CreateSkillRequest, user_id: str | None = None, db=Depends(get_supabase)):
    result = db.table("sg_skills").insert({
        "user_id": user_id,
        "name": body.name,
        "description": body.description,
        "ai_prompt": body.ai_prompt,
        "integration_actions": body.integration_actions,
        "is_default": False,
    }).execute()
    return result.data[0]

@router.put("/{skill_id}")
def update_skill(skill_id: str, body: UpdateSkillRequest, db=Depends(get_supabase)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    result = db.table("sg_skills").update(updates).eq("id", skill_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Skill not found")
    return result.data[0]

@router.delete("/{skill_id}", status_code=204)
def delete_skill(skill_id: str, db=Depends(get_supabase)):
    db.table("sg_skills").delete().eq("id", skill_id).execute()
```

- [ ] **Step 4: Create `pipeline/routers/modes.py`**

```python
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from models import CreateModeRequest, UpdateModeRequest
from supabase_client import get_supabase

router = APIRouter(prefix="/modes", tags=["modes"])

@router.get("")
def list_modes(user_id: str | None = None, db=Depends(get_supabase)):
    return db.table("sg_modes").select("*").execute().data

@router.post("", status_code=201)
def create_mode(body: CreateModeRequest, user_id: str | None = None, db=Depends(get_supabase)):
    result = db.table("sg_modes").insert({
        "user_id": user_id,
        "name": body.name,
        "skill_ids": [str(s) for s in body.skill_ids],
    }).execute()
    return result.data[0]

@router.put("/{mode_id}")
def update_mode(mode_id: str, body: UpdateModeRequest, db=Depends(get_supabase)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if "skill_ids" in updates:
        updates["skill_ids"] = [str(s) for s in updates["skill_ids"]]
    result = db.table("sg_modes").update(updates).eq("id", mode_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Mode not found")
    return result.data[0]

@router.delete("/{mode_id}", status_code=204)
def delete_mode(mode_id: str, db=Depends(get_supabase)):
    db.table("sg_modes").delete().eq("id", mode_id).execute()
```

- [ ] **Step 5: Mount routers in `pipeline/main.py`**

```python
from __future__ import annotations
from fastapi import FastAPI
from routers import jobs, skills, modes

app = FastAPI(title="sg-pipeline")
app.include_router(jobs.router)
app.include_router(skills.router)
app.include_router(modes.router)

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 6: Run all tests**

```bash
cd pipeline
uv run pytest tests/ -v
```

Expected: all `PASSED`

- [ ] **Step 7: Commit**

```bash
git add pipeline/routers/skills.py pipeline/routers/modes.py pipeline/main.py pipeline/tests/test_skills.py pipeline/tests/test_modes.py
git commit -m "feat(pipeline): skills and modes CRUD routers"
```

---

## Task 5: Hermes sg-orchestrator Skill

**Files:**
- Create: `pipeline/hermes/skills/sg-orchestrator.md`
- Create: `pipeline/hermes/skills/sg-skill-summary.md`
- Create: `pipeline/hermes/skills/sg-skill-action-items.md`
- Create: `pipeline/hermes/skills/sg-skill-decisions.md`
- Create: `pipeline/hermes/skills/sg-skill-sentiment.md`

**Interfaces:**
- Produces: Hermes skill files loaded via `-s` flag at job runtime; `sg-orchestrator` is the only skill explicitly loaded — it coordinates the rest

- [ ] **Step 1: Create `pipeline/hermes/skills/sg-orchestrator.md`**

```markdown
---
name: sg-orchestrator
description: Master orchestration skill for Sorigamis pipeline jobs. Coordinates transcription, diarization, skill extraction, and integration actions with user confirmation checkpoints.
---

# sg-orchestrator

You are the Sorigamis pipeline orchestrator. You receive a job context JSON and execute the full pipeline for one recording.

## Job Context

The job context is provided as JSON in your prompt. It contains:
- `job_id` — Supabase job ID (include in every write)
- `drive_file_id` — Google Drive file ID for the audio
- `mode_name` — the recording Mode (e.g. "Team Meeting")
- `skills` — array of `{skill_name, ai_prompt, integration_actions}` to run
- `supabase_url`, `supabase_service_role_key` — for state writes
- `fcm_server_key`, `fcm_device_token` — for push notifications

## Pipeline Stages

Execute these stages in order. Write job status to Supabase before and after each stage.

### Stage 1: Download & Transcribe
1. Set job status → `analyzing`
2. Download audio from Google Drive using `sg-drive-download`
3. Transcribe with `sg-whisper-transcribe` (language=ko, faster-whisper large-v3)
4. Write utterances to `sg_utterances` via `sg-supabase-write`
5. Write raw Whisper output to `sg_transcript_raw`

### Stage 2: Diarize
1. Run `sg-diarize` on the WAV file
2. Merge diarization with utterances — assign `speaker_id` to each utterance
3. Write speakers to `sg_speakers`, update utterances with `speaker_id`

### Stage 3: Propose Plan
1. Build a plan listing all approved stages: speaker assignment checkpoint, each skill by name, each integration action by destination
2. Set job status → `awaiting_plan_confirmation`
3. Write `plan_json` to `sg_jobs`
4. Send FCM push via `sg-notify-fcm` with title "Review your pipeline plan"
5. **STOP and wait.** Do not proceed until job status changes to `executing` (poll `sg_jobs` every 5s, timeout 30min)

### Stage 4: Speaker Checkpoint
1. Read `per_step_overrides` from confirmed `plan_json` — apply any user edits
2. Set job status → `awaiting_checkpoint`
3. Write checkpoint: `{"type": "speaker_assignment", "speakers": [{id, label, talk_time_pct}]}`
4. Send FCM push: "Assign speaker names"
5. **STOP and wait** for status → `executing`. Read `checkpoint_json` for confirmed names.
6. Update `sg_speakers.confirmed_name` for each speaker

### Stage 5: Skill Extraction
1. For each skill in the job's approved skills list:
   a. Build prompt: `{skill.ai_prompt}\n\nTranscript:\n{utterances_as_text_with_speaker_names}`
   b. Call the LLM (yourself) to generate the extraction
   c. Write result to `sg_skill_results` (status=complete, output_markdown + output_json)
2. Skills with no integration actions can run in parallel

### Stage 6: Integration Action Checkpoints
For each integration action in each skill:
1. Set job status → `awaiting_checkpoint`
2. Write checkpoint: `{"type": "action_confirmation", "action_type": "slack", "destination": "#meetings", "preview": "..."}`
3. Send FCM push: "Confirm action before sending"
4. **STOP and wait.** On resume, check if action was approved or skipped in `checkpoint_json`
5. If approved: call the appropriate tool (`sg-slack-post`, `sg-linear-create`, `sg-webhook-call`)
6. Write result to `sg_action_logs`

### Stage 7: Complete
1. Set job status → `complete`
2. Send FCM push: "Your results are ready"

## Error Handling
- If any stage fails, set job status → `failed`, write `error` field, send FCM push with error message
- Retry transient failures (network, Modal) up to 3 times before failing
- User can skip a checkpoint without failing the job (checkpoint_json will contain `{"skipped": true}`)
```

- [ ] **Step 2: Create `pipeline/hermes/skills/sg-skill-summary.md`**

```markdown
---
name: sg-skill-summary
description: Summarize a meeting transcript into a concise paragraph.
---

# sg-skill-summary

Given a speaker-attributed transcript, produce a concise summary paragraph covering the main topics discussed. Write in third person. Do not include action items or decisions — those are handled by other skills.
```

- [ ] **Step 3: Create `pipeline/hermes/skills/sg-skill-action-items.md`**

```markdown
---
name: sg-skill-action-items
description: Extract action items and owners from a transcript.
---

# sg-skill-action-items

Extract all action items from the transcript. For each item identify the task and the owner (speaker name if mentioned, null otherwise).

Return ONLY valid JSON — no prose, no markdown fences:
[{"text": "...", "owner": "..." or null}]
```

- [ ] **Step 4: Create `pipeline/hermes/skills/sg-skill-decisions.md`**

```markdown
---
name: sg-skill-decisions
description: Extract decisions made during a conversation.
---

# sg-skill-decisions

List all decisions made during the conversation. Return ONLY a JSON array of strings:
["Decision 1", "Decision 2"]
```

- [ ] **Step 5: Create `pipeline/hermes/skills/sg-skill-sentiment.md`**

```markdown
---
name: sg-skill-sentiment
description: Analyse the tone of each speaker in a conversation.
---

# sg-skill-sentiment

Analyse the overall tone of each speaker across the transcript. Return ONLY valid JSON:
{"Speaker A": "positive|neutral|negative", "Speaker B": "positive|neutral|negative"}
```

- [ ] **Step 6: Commit**

```bash
git add pipeline/hermes/skills/
git commit -m "feat(pipeline): Hermes sg-orchestrator and default skill files"
```

---

## Task 6: Modal Workers (Whisper + Diarize)

**Files:**
- Create: `pipeline/workers/whisper_worker.py`
- Create: `pipeline/workers/diarize_worker.py`
- Create: `pipeline/tests/test_tools.py`

**Interfaces:**
- Produces:
  - `transcribe(wav_path: str) -> list[dict]` — `[{start, end, text, avg_logprob}]`
  - `diarize(wav_path: str, num_speakers: int = 2) -> list[dict]` — `[{start, end, speaker}]`

- [ ] **Step 1: Write failing tool tests**

Create `pipeline/tests/test_tools.py`:
```python
from unittest.mock import patch, MagicMock

def test_transcribe_returns_segments():
    mock_segment = MagicMock()
    mock_segment.start = 0.0
    mock_segment.end = 2.5
    mock_segment.text = "안녕하세요"
    mock_segment.avg_logprob = -0.3

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([mock_segment], MagicMock(language="ko"))

    with patch("workers.whisper_worker.WhisperModel", return_value=mock_model):
        from workers.whisper_worker import transcribe
        result = transcribe("/tmp/test.wav")

    assert len(result) == 1
    assert result[0]["text"] == "안녕하세요"
    assert result[0]["start"] == 0.0
    assert result[0]["end"] == 2.5

def test_diarize_returns_speaker_segments():
    mock_pipeline = MagicMock()
    mock_turn = MagicMock()
    mock_turn.start = 0.0
    mock_turn.end = 3.0
    mock_pipeline.return_value.itertracks.return_value = [(mock_turn, None, "SPEAKER_00")]

    with patch("workers.diarize_worker.Pipeline.from_pretrained", return_value=mock_pipeline()):
        from workers.diarize_worker import diarize
        result = diarize("/tmp/test.wav")

    assert len(result) == 1
    assert result[0]["speaker"] == "A"
    assert result[0]["start"] == 0.0
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd pipeline
uv run pytest tests/test_tools.py -v
```

Expected: `FAILED` — `ModuleNotFoundError`

- [ ] **Step 3: Create `pipeline/workers/whisper_worker.py`**

```python
"""Modal GPU worker: faster-whisper large-v3 transcription."""
from __future__ import annotations
import modal

app = modal.App("sg-whisper")

image = (
    modal.Image.from_registry("nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04", add_python="3.12")
    .apt_install("ffmpeg")
    .pip_install("faster-whisper==1.1.1", "numpy<2.3")
)

models_volume = modal.Volume.from_name("sg-models", create_if_missing=True)

INITIAL_PROMPT = (
    "인터뷰에서 다음 용어가 등장할 수 있습니다: "
    "Analyzing Photos, not working, iCloud, Face ID, Live Text."
)

@app.function(
    image=image,
    gpu="T4",
    volumes={"/models": models_volume},
    timeout=600,
)
def transcribe(wav_path: str, language: str = "ko") -> list[dict]:
    from faster_whisper import WhisperModel
    model = WhisperModel(
        "large-v3",
        device="cuda",
        compute_type="float16",
        download_root="/models/faster-whisper",
    )
    segments, _ = model.transcribe(
        wav_path,
        language=language,
        task="transcribe",
        beam_size=5,
        best_of=5,
        temperature=0.0,
        condition_on_previous_text=False,
        initial_prompt=INITIAL_PROMPT if language == "ko" else None,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        word_timestamps=False,
    )
    return [
        {"start": s.start, "end": s.end, "text": s.text.strip(), "avg_logprob": s.avg_logprob}
        for s in segments
    ]
```

- [ ] **Step 4: Create `pipeline/workers/diarize_worker.py`**

```python
"""Modal GPU worker: pyannote.audio speaker diarization."""
from __future__ import annotations
import modal

app = modal.App("sg-diarize")

image = (
    modal.Image.from_registry("nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04", add_python="3.12")
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install(
        "torch==2.5.1", "torchaudio==2.5.1",
        "pyannote.audio==3.3.2", "speechbrain==1.0.2",
    )
)

models_volume = modal.Volume.from_name("sg-models", create_if_missing=True)
secrets = [modal.Secret.from_name("sg-huggingface")]  # HF_TOKEN for pyannote

_SPEAKER_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

@app.function(
    image=image,
    gpu="T4",
    volumes={"/models": models_volume},
    secrets=secrets,
    timeout=600,
)
def diarize(wav_path: str, num_speakers: int = 2) -> list[dict]:
    from pyannote.audio import Pipeline
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=True,
        cache_dir="/models/pyannote",
    )
    diarization = pipeline(wav_path, num_speakers=num_speakers)
    speaker_map: dict[str, str] = {}
    segments = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        if speaker not in speaker_map:
            speaker_map[speaker] = _SPEAKER_LABELS[len(speaker_map)]
        segments.append({
            "start": round(turn.start, 3),
            "end": round(turn.end, 3),
            "speaker": speaker_map[speaker],
        })
    return segments
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd pipeline
uv run pytest tests/test_tools.py -v
```

Expected: all `PASSED`

- [ ] **Step 6: Deploy Modal workers**

```bash
cd pipeline
modal deploy workers/whisper_worker.py
modal deploy workers/diarize_worker.py
```

Expected: both workers deployed, URLs printed.

- [ ] **Step 7: Commit**

```bash
git add pipeline/workers/
git commit -m "feat(pipeline): Modal Whisper and diarize workers"
```

---

## Task 7: Hermes Pipeline Tools (Drive, Supabase, FCM)

**Files:**
- Create: `pipeline/tools/sg_drive_download.py`
- Create: `pipeline/tools/sg_supabase_write.py`
- Create: `pipeline/tools/sg_notify_fcm.py`

**Interfaces:**
- Produces (each function called by Hermes via tool mechanism or imported by `hermes/runner.py`):
  - `download_audio(file_id: str, dest_path: str, creds_json: str) -> str` — returns `dest_path`
  - `update_job_status(job_id: str, status: str, supabase_url: str, key: str, extra: dict = {}) -> None`
  - `send_fcm(device_token: str, title: str, body: str, server_key: str) -> None`

- [ ] **Step 1: Write failing tests (added to `test_tools.py`)**

```python
def test_download_audio_calls_drive_api():
    import json
    from unittest.mock import patch, MagicMock
    mock_service = MagicMock()
    mock_service.files.return_value.get_media.return_value.execute.return_value = b"audio_bytes"

    with patch("tools.sg_drive_download.build", return_value=mock_service), \
         patch("builtins.open", MagicMock()), \
         patch("tools.sg_drive_download.MediaIoBaseDownload") as mock_dl:
        mock_dl.return_value.next_chunk.return_value = (MagicMock(progress=lambda: 1.0), True)
        from tools.sg_drive_download import download_audio
        result = download_audio("file123", "/tmp/audio.m4a", json.dumps({"type": "service_account"}))
    assert result == "/tmp/audio.m4a"

def test_update_job_status():
    from unittest.mock import patch, MagicMock
    mock_client = MagicMock()
    with patch("tools.sg_supabase_write.create_client", return_value=mock_client):
        from tools.sg_supabase_write import update_job_status
        update_job_status("job-1", "analyzing", "https://x.supabase.co", "key")
    mock_client.table.assert_called_with("sg_jobs")
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd pipeline
uv run pytest tests/test_tools.py -v -k "download or status"
```

Expected: `FAILED`

- [ ] **Step 3: Create `pipeline/tools/sg_drive_download.py`**

```python
from __future__ import annotations
import io, json
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.service_account import Credentials

def download_audio(file_id: str, dest_path: str, creds_json: str) -> str:
    creds = Credentials.from_service_account_info(
        json.loads(creds_json),
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    service = build("drive", "v3", credentials=creds)
    request = service.files().get_media(fileId=file_id)
    with open(dest_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    return dest_path
```

- [ ] **Step 4: Create `pipeline/tools/sg_supabase_write.py`**

```python
from __future__ import annotations
from supabase import create_client

def update_job_status(
    job_id: str,
    status: str,
    supabase_url: str,
    key: str,
    extra: dict | None = None,
) -> None:
    db = create_client(supabase_url, key)
    payload = {"status": status, **(extra or {})}
    db.table("sg_jobs").update(payload).eq("id", job_id).execute()

def write_utterances(job_id: str, utterances: list[dict], supabase_url: str, key: str) -> None:
    db = create_client(supabase_url, key)
    rows = [{"job_id": job_id, **u} for u in utterances]
    db.table("sg_utterances").insert(rows).execute()

def write_speakers(job_id: str, speakers: list[dict], supabase_url: str, key: str) -> None:
    db = create_client(supabase_url, key)
    rows = [{"job_id": job_id, **s} for s in speakers]
    db.table("sg_speakers").insert(rows).execute()

def write_skill_result(
    job_id: str, skill_id: str | None, skill_name: str,
    output_json: dict, output_markdown: str,
    supabase_url: str, key: str,
) -> None:
    db = create_client(supabase_url, key)
    db.table("sg_skill_results").insert({
        "job_id": job_id, "skill_id": skill_id, "skill_name": skill_name,
        "output_json": output_json, "output_markdown": output_markdown,
        "status": "complete",
    }).execute()

def write_action_log(
    job_id: str, skill_id: str | None, action_type: str,
    destination: str, payload: dict, status: str,
    supabase_url: str, key: str,
    fired_at: str | None = None, error: str | None = None,
) -> None:
    db = create_client(supabase_url, key)
    db.table("sg_action_logs").insert({
        "job_id": job_id, "skill_id": skill_id, "action_type": action_type,
        "destination": destination, "payload_json": payload,
        "status": status, "fired_at": fired_at, "error": error,
    }).execute()
```

- [ ] **Step 5: Create `pipeline/tools/sg_notify_fcm.py`**

```python
from __future__ import annotations
import httpx

FCM_URL = "https://fcm.googleapis.com/fcm/send"

def send_fcm(device_token: str, title: str, body: str, server_key: str) -> None:
    payload = {
        "to": device_token,
        "notification": {"title": title, "body": body},
        "data": {"title": title, "body": body},
    }
    headers = {"Authorization": f"key={server_key}", "Content-Type": "application/json"}
    response = httpx.post(FCM_URL, json=payload, headers=headers, timeout=10)
    response.raise_for_status()
```

- [ ] **Step 6: Run all tests**

```bash
cd pipeline
uv run pytest tests/ -v
```

Expected: all `PASSED`

- [ ] **Step 7: Commit**

```bash
git add pipeline/tools/sg_drive_download.py pipeline/tools/sg_supabase_write.py pipeline/tools/sg_notify_fcm.py pipeline/tests/test_tools.py
git commit -m "feat(pipeline): Drive download, Supabase write, and FCM notification tools"
```

---

## Task 8: Integration Action Tools (Slack, Linear, Webhook)

**Files:**
- Create: `pipeline/tools/sg_slack_post.py`
- Create: `pipeline/tools/sg_linear_create.py`
- Create: `pipeline/tools/sg_webhook_call.py`

**Interfaces:**
- Produces:
  - `post_slack(channel: str, text: str, token: str) -> None`
  - `create_linear_issue(title: str, description: str, team_id: str, api_key: str) -> str` — returns issue URL
  - `call_webhook(url: str, payload: dict) -> None`

- [ ] **Step 1: Write failing tests (append to `test_tools.py`)**

```python
def test_post_slack():
    from unittest.mock import patch
    import httpx
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        from tools.sg_slack_post import post_slack
        post_slack("#meetings", "Hello", "xoxb-token")
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert "slack.com" in str(call_kwargs)

def test_call_webhook():
    from unittest.mock import patch, MagicMock
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        from tools.sg_webhook_call import call_webhook
        call_webhook("https://example.com/hook", {"key": "value"})
    mock_post.assert_called_once_with(
        "https://example.com/hook",
        json={"key": "value"},
        timeout=15,
    )
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd pipeline
uv run pytest tests/test_tools.py -v -k "slack or webhook"
```

Expected: `FAILED`

- [ ] **Step 3: Create `pipeline/tools/sg_slack_post.py`**

```python
from __future__ import annotations
import httpx

def post_slack(channel: str, text: str, token: str) -> None:
    response = httpx.post(
        "https://slack.com/api/chat.postMessage",
        json={"channel": channel, "text": text},
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack error: {data.get('error')}")
```

- [ ] **Step 4: Create `pipeline/tools/sg_linear_create.py`**

```python
from __future__ import annotations
import httpx

_MUTATION = """
mutation CreateIssue($title: String!, $description: String, $teamId: String!) {
  issueCreate(input: {title: $title, description: $description, teamId: $teamId}) {
    success
    issue { url }
  }
}
"""

def create_linear_issue(title: str, description: str, team_id: str, api_key: str) -> str:
    response = httpx.post(
        "https://api.linear.app/graphql",
        json={"query": _MUTATION, "variables": {"title": title, "description": description, "teamId": team_id}},
        headers={"Authorization": api_key},
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    return data["data"]["issueCreate"]["issue"]["url"]
```

- [ ] **Step 5: Create `pipeline/tools/sg_webhook_call.py`**

```python
from __future__ import annotations
import httpx

def call_webhook(url: str, payload: dict) -> None:
    response = httpx.post(url, json=payload, timeout=15)
    response.raise_for_status()
```

- [ ] **Step 6: Run all tests**

```bash
cd pipeline
uv run pytest tests/ -v
```

Expected: all `PASSED`

- [ ] **Step 7: Commit**

```bash
git add pipeline/tools/sg_slack_post.py pipeline/tools/sg_linear_create.py pipeline/tools/sg_webhook_call.py
git commit -m "feat(pipeline): Slack, Linear, and webhook integration action tools"
```

---

## Task 9: Hermes Session Runner

**Files:**
- Create: `pipeline/hermes/context.py`
- Create: `pipeline/hermes/runner.py`
- Modify: `pipeline/routers/jobs.py` — call `launch_hermes` after job creation
- Create: `pipeline/tests/test_hermes_runner.py`

**Interfaces:**
- Consumes: job row from `sg_jobs`, skills from `sg_skills`, mode from `sg_modes`
- Produces:
  - `build_context(job: dict, mode: dict, skills: list[dict]) -> str` — JSON string
  - `launch_hermes(job_id: str, context_json: str) -> None` — spawns subprocess, non-blocking

- [ ] **Step 1: Write failing tests**

Create `pipeline/tests/test_hermes_runner.py`:
```python
import json
from unittest.mock import patch, MagicMock
from uuid import uuid4

def test_build_context_includes_required_fields():
    from hermes.context import build_context
    job = {"id": str(uuid4()), "drive_file_id": "abc123"}
    mode = {"id": str(uuid4()), "name": "Team Meeting"}
    skills = [{"skill_name": "Summary", "ai_prompt": "Summarize this."}]
    ctx = json.loads(build_context(job, mode, skills))
    assert ctx["job_id"] == job["id"]
    assert ctx["drive_file_id"] == "abc123"
    assert ctx["mode_name"] == "Team Meeting"
    assert len(ctx["skills"]) == 1

def test_launch_hermes_spawns_subprocess():
    from hermes.runner import launch_hermes
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock(pid=12345)
        launch_hermes("job-1", '{"job_id":"job-1"}')
    mock_popen.assert_called_once()
    cmd = mock_popen.call_args[0][0]
    assert "hermes" in cmd
    assert "-s" in cmd
    assert "sg-orchestrator" in cmd
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd pipeline
uv run pytest tests/test_hermes_runner.py -v
```

Expected: `FAILED`

- [ ] **Step 3: Create `pipeline/hermes/context.py`**

```python
from __future__ import annotations
import json
import os

def build_context(job: dict, mode: dict, skills: list[dict]) -> str:
    return json.dumps({
        "job_id": job["id"],
        "drive_file_id": job["drive_file_id"],
        "mode_name": mode.get("name", ""),
        "skills": skills,
        "supabase_url": os.environ["SUPABASE_URL"],
        "supabase_service_role_key": os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        "fcm_server_key": os.environ.get("FCM_SERVER_KEY", ""),
        "google_service_account_json": os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "{}"),
    })
```

- [ ] **Step 4: Create `pipeline/hermes/runner.py`**

```python
from __future__ import annotations
import os
import subprocess
from pathlib import Path

SKILLS_DIR = Path(__file__).parent / "skills"

def launch_hermes(job_id: str, context_json: str) -> None:
    """Spawn a Hermes session for one job. Non-blocking — runs in background."""
    cmd = [
        "hermes",
        "-z", context_json,
        "--provider", os.environ.get("HERMES_PROVIDER", "github-copilot"),
        "-m", os.environ.get("HERMES_MODEL", "gemini-2.5-pro"),
        "-s", f"sg-orchestrator",
        "--skills", str(SKILLS_DIR / "sg-orchestrator.md"),
        "--yolo",
        "--accept-hooks",
    ]
    subprocess.Popen(
        cmd,
        stdout=open(f"/tmp/sg-job-{job_id}.log", "w"),
        stderr=subprocess.STDOUT,
    )
```

- [ ] **Step 5: Wire into `pipeline/routers/jobs.py` — spawn Hermes after job creation**

Replace the `create_job` function:
```python
@router.post("", status_code=201)
def create_job(body: CreateJobRequest, db=Depends(get_supabase)):
    # Create job row
    result = db.table("sg_jobs").insert({
        "drive_file_id": body.drive_file_id,
        "mode_id": str(body.mode_id),
        "user_id": str(body.user_id),
        "status": "submitted",
    }).execute()
    row = result.data[0]
    job_id = row["id"]

    # Resolve mode + skills
    mode = db.table("sg_modes").select("*").eq("id", str(body.mode_id)).single().execute().data or {}
    skill_ids = mode.get("skill_ids", [])
    skills_data = []
    if skill_ids:
        skills_data = db.table("sg_skills").select("*").in_("id", skill_ids).execute().data or []

    skills = [
        {"skill_name": s["name"], "ai_prompt": s["ai_prompt"], "integration_actions": s.get("integration_actions", [])}
        for s in skills_data
    ]

    # Spawn Hermes (non-blocking)
    from hermes.context import build_context
    from hermes.runner import launch_hermes
    context_json = build_context(row, mode, skills)
    launch_hermes(job_id, context_json)

    return {"job_id": job_id, "status": row["status"]}
```

- [ ] **Step 6: Run all tests**

```bash
cd pipeline
uv run pytest tests/ -v
```

Expected: all `PASSED`

- [ ] **Step 7: Commit**

```bash
git add pipeline/hermes/context.py pipeline/hermes/runner.py pipeline/routers/jobs.py pipeline/tests/test_hermes_runner.py
git commit -m "feat(pipeline): Hermes session runner — spawns agent per job"
```

---

## Task 10: Fly.io Deploy + End-to-End Smoke Test

**Files:**
- Create: `pipeline/fly.toml`
- Create: `pipeline/Dockerfile`

**Interfaces:**
- Produces: `sg-pipeline` running on Fly.io, reachable at `https://sg-pipeline.fly.dev`

- [ ] **Step 1: Create `pipeline/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install uv
COPY pyproject.toml .
RUN uv sync --no-dev
COPY . .
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 2: Create `pipeline/fly.toml`**

```toml
app = "sg-pipeline"
primary_region = "nrt"

[build]

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 1

[env]
  HERMES_MODEL = "gemini-2.5-pro"
  HERMES_PROVIDER = "github-copilot"

[[vm]]
  memory = "2gb"
  cpu_kind = "shared"
  cpus = 1
```

- [ ] **Step 3: Set Fly.io secrets**

```bash
fly secrets set \
  SUPABASE_URL="..." \
  SUPABASE_SERVICE_ROLE_KEY="..." \
  GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}' \
  FCM_SERVER_KEY="..." \
  MODAL_TOKEN_ID="..." \
  MODAL_TOKEN_SECRET="..."
```

- [ ] **Step 4: Deploy**

```bash
cd pipeline
fly deploy
```

Expected: deployment succeeds, `https://sg-pipeline.fly.dev` reachable.

- [ ] **Step 5: Smoke test health endpoint**

```bash
curl https://sg-pipeline.fly.dev/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 6: End-to-end smoke test with a real audio file**

```bash
# Upload a test audio file to your Google Drive and note the file_id
# Then create a job via the API:
curl -X POST https://sg-pipeline.fly.dev/jobs \
  -H "Content-Type: application/json" \
  -d '{"drive_file_id":"YOUR_FILE_ID","mode_id":"YOUR_MODE_ID","user_id":"YOUR_USER_ID"}'
```

Expected: `{"job_id":"...","status":"submitted"}`. Check Supabase dashboard — status should move to `analyzing` within 30s, then `awaiting_plan_confirmation`.

- [ ] **Step 7: Commit**

```bash
git add pipeline/fly.toml pipeline/Dockerfile
git commit -m "feat(pipeline): Fly.io deploy config + Dockerfile"
```

---

## Summary

After completing all 10 tasks you will have:

- All `sg_*` Supabase tables with default skills seeded
- FastAPI server on Fly.io with full job lifecycle, skills, and modes CRUD
- Hermes `sg-orchestrator` skill coordinating the full pipeline
- Modal workers for Whisper (large-v3) and pyannote diarization
- Tools for Drive download, Supabase writes, FCM push, Slack, Linear, webhook
- End-to-end pipeline running in the cloud

**Next:** Ask for Plan 2 — Flutter `LivePipelineClient` swap and plan confirmation screens.
