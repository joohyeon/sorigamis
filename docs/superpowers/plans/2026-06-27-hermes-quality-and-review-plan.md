# Hermes Quality Metrics & Skill Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add transcript quality reporting and per-skill human-in-the-loop review to the Hermes pipeline, storing quality metrics on `sg_jobs` and pausing before integration actions when a skill's `require_review` flag is set.

**Architecture:** A new `tools/sg_quality.py` module computes quality from Whisper segments; the orchestrator skill calls it after Stage 1 and writes `quality_json` to `sg_jobs`. A new `require_review` bool on `sg_skills` (propagated into context JSON via `routers/jobs.py`) triggers a new `awaiting_skill_review` checkpoint in Stage 5.5 of the orchestrator. On the Flutter side, a `requireReview` Drift column, a skill editor toggle, a quality card in Results, and handling for the new pipeline status complete the loop.

**Tech Stack:** Python 3.12, faster-whisper (quality signal: `avg_logprob`), Supabase (Postgres), Hermes orchestrator skill (Markdown), Flutter/Dart 3.12, Drift 2.18, Riverpod 2.5.

## Global Constraints

- Python: use `.venv/bin/python` for all pipeline commands; no new pip installs
- Hermes orchestrator calls tools as one-liner `-c "..."` subprocesses
- All Supabase writes go through `tools/sg_supabase_write.py` helpers — no hand-rolled REST calls
- Job status values must be lowercase strings matching the Supabase state machine
- Flutter: Drift schemaVersion bumped to 2; migration must use `addColumn` (not recreate table)
- Flutter: no new pub dependencies beyond what's in `pubspec.yaml`
- Quality score thresholds: `good` ≥ −0.5, `fair` ≥ −0.8, `poor` < −0.8; low-confidence threshold: < −1.0

---

## File Map

### Pipeline (Python)
| File | Action | Purpose |
|---|---|---|
| `pipeline/tools/sg_quality.py` | **Create** | `compute_quality()` and `with_diarization_degraded()` functions |
| `pipeline/hermes/skills/sg-orchestrator.md` | **Modify** | Add quality computation after Stage 1; add Stage 5.5 skill review checkpoint |
| `pipeline/routers/jobs.py` | **Modify** | Include `require_review` in each skill dict passed to `build_context` |
| `pipeline/tests/test_tools.py` | **Modify** | Add quality computation unit tests |
| `pipeline/tests/test_hermes_runner.py` | **Modify** | Add test that orchestrator prompt contains Stage 5.5 and quality instructions |
| `pipeline/tests/test_jobs.py` | **Modify** | Add test that `require_review` is forwarded in the skills context |

### Supabase Migrations (SQL — apply via Supabase dashboard or `supabase db push`)
| File | Action | Purpose |
|---|---|---|
| `supabase/migrations/20260627_quality_json.sql` | **Create** | Add `quality_json jsonb` to `sg_jobs` |
| `supabase/migrations/20260627_require_review.sql` | **Create** | Add `require_review bool NOT NULL DEFAULT false` to `sg_skills` |

### Flutter (Dart)
| File | Action | Purpose |
|---|---|---|
| `lib/data/db/database.dart` | **Modify** | Add `requireReview` BoolColumn to `Skills`; bump schemaVersion to 2; add migration |
| `lib/data/db/database.g.dart` | **Regenerate** | Run build_runner after schema change |
| `lib/data/db/daos/skill_dao.dart` | **Modify** | Add `updateRequireReview` method |
| `lib/data/db/daos/skill_dao.g.dart` | **Regenerate** | Run build_runner |
| `lib/core/enums.dart` | **Modify** | Add `awaitingSkillReview` to `JobStatus` enum |
| `lib/features/skills/skill_editor_screen.dart` | **Create** | Skill name + `require_review` toggle UI |
| `lib/core/router.dart` | **Modify** | Add `/skills/:id/edit` route |
| `lib/features/results/results_screen.dart` | **Create** | Results screen with expandable quality card |
| `lib/core/router.dart` | **Modify** | Add `/jobs/:id/results` route |
| `test/data/db/skill_dao_test.dart` | **Create** | Tests for `requireReview` column and DAO method |
| `test/features/skills/skill_editor_screen_test.dart` | **Create** | Widget test for the toggle |
| `test/features/results/results_screen_test.dart` | **Create** | Widget test for quality card rendering |

---

## Task 1: Supabase Migrations

**Files:**
- Create: `supabase/migrations/20260627_quality_json.sql`
- Create: `supabase/migrations/20260627_require_review.sql`

**Interfaces:**
- Produces: `sg_jobs.quality_json jsonb` column; `sg_skills.require_review bool` column — used by Tasks 2, 3, 4

- [ ] **Step 1: Create migrations directory if it doesn't exist**

```bash
mkdir -p /Users/hyeonjoo/VSCodeTestProjects/sorigamis/supabase/migrations
```

- [ ] **Step 2: Write the quality_json migration**

File: `supabase/migrations/20260627_quality_json.sql`
```sql
ALTER TABLE sg_jobs ADD COLUMN IF NOT EXISTS quality_json jsonb;
```

- [ ] **Step 3: Write the require_review migration**

File: `supabase/migrations/20260627_require_review.sql`
```sql
ALTER TABLE sg_skills ADD COLUMN IF NOT EXISTS require_review bool NOT NULL DEFAULT false;
```

- [ ] **Step 4: Apply migrations**

Via Supabase dashboard → SQL Editor, or:
```bash
# If supabase CLI is installed:
supabase db push
```

- [ ] **Step 5: Verify columns exist**

In Supabase dashboard, check `sg_jobs` has `quality_json` and `sg_skills` has `require_review`.

- [ ] **Step 6: Commit**

```bash
git add supabase/migrations/
git commit -m "feat: add quality_json to sg_jobs and require_review to sg_skills"
```

---

## Task 2: Quality Computation Module (`tools/sg_quality.py`)

**Files:**
- Create: `pipeline/tools/sg_quality.py`
- Modify: `pipeline/tests/test_tools.py`

**Interfaces:**
- Produces:
  - `compute_quality(segments: list[dict]) -> dict` — input: list of `{start, end, text, avg_logprob}` dicts; output: quality summary dict matching the spec schema
  - `with_diarization_degraded(quality: dict, degraded: bool) -> dict` — returns a new dict with `diarization_degraded` set

- [ ] **Step 1: Write the failing tests**

Append to `pipeline/tests/test_tools.py`:

```python
def test_compute_quality_good_score():
    from tools.sg_quality import compute_quality
    segments = [
        {"start": 0.0, "end": 2.0, "text": "hello", "avg_logprob": -0.3},
        {"start": 2.0, "end": 4.0, "text": "world", "avg_logprob": -0.4},
    ]
    q = compute_quality(segments)
    assert q["transcript_score"] == "good"
    assert q["avg_logprob"] == -0.35
    assert q["segment_count"] == 2
    assert q["low_confidence_count"] == 0
    assert q["low_confidence_segments"] == []
    assert q["diarization_degraded"] is False


def test_compute_quality_fair_score():
    from tools.sg_quality import compute_quality
    segments = [
        {"start": 0.0, "end": 2.0, "text": "a", "avg_logprob": -0.6},
        {"start": 2.0, "end": 4.0, "text": "b", "avg_logprob": -0.7},
    ]
    q = compute_quality(segments)
    assert q["transcript_score"] == "fair"


def test_compute_quality_poor_score():
    from tools.sg_quality import compute_quality
    segments = [
        {"start": 0.0, "end": 2.0, "text": "a", "avg_logprob": -0.9},
        {"start": 2.0, "end": 4.0, "text": "b", "avg_logprob": -0.85},
    ]
    q = compute_quality(segments)
    assert q["transcript_score"] == "poor"


def test_compute_quality_surfaces_low_confidence_segments():
    from tools.sg_quality import compute_quality
    segs = [{"start": float(i), "end": float(i+1), "text": f"t{i}", "avg_logprob": -1.5 - i * 0.1}
            for i in range(15)]
    q = compute_quality(segs)
    assert q["low_confidence_count"] == 15
    # Only up to 10 worst segments are returned, sorted worst-first
    assert len(q["low_confidence_segments"]) == 10
    assert q["low_confidence_segments"][0]["avg_logprob"] <= q["low_confidence_segments"][-1]["avg_logprob"]


def test_compute_quality_duration_from_last_segment_end():
    from tools.sg_quality import compute_quality
    segments = [
        {"start": 0.0, "end": 10.0, "text": "hi", "avg_logprob": -0.3},
        {"start": 10.0, "end": 25.5, "text": "bye", "avg_logprob": -0.4},
    ]
    q = compute_quality(segments)
    assert q["duration_sec"] == 25.5


def test_compute_quality_empty_segments():
    from tools.sg_quality import compute_quality
    q = compute_quality([])
    assert q["transcript_score"] == "good"
    assert q["avg_logprob"] == 0.0
    assert q["segment_count"] == 0
    assert q["duration_sec"] == 0.0


def test_with_diarization_degraded():
    from tools.sg_quality import compute_quality, with_diarization_degraded
    q = compute_quality([{"start": 0.0, "end": 1.0, "text": "hi", "avg_logprob": -0.3}])
    assert q["diarization_degraded"] is False
    updated = with_diarization_degraded(q, True)
    assert updated["diarization_degraded"] is True
    # Original not mutated
    assert q["diarization_degraded"] is False
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/hyeonjoo/VSCodeTestProjects/sorigamis/pipeline
.venv/bin/pytest tests/test_tools.py::test_compute_quality_good_score -v
```
Expected: `FAILED` — `ModuleNotFoundError: No module named 'tools.sg_quality'`

- [ ] **Step 3: Implement `pipeline/tools/sg_quality.py`**

```python
from __future__ import annotations


def compute_quality(segments: list[dict]) -> dict:
    probs = [s["avg_logprob"] for s in segments if "avg_logprob" in s]
    avg = round(sum(probs) / len(probs), 4) if probs else 0.0
    score = "good" if avg >= -0.5 else ("fair" if avg >= -0.8 else "poor")
    low = sorted(
        [s for s in segments if s.get("avg_logprob", 0.0) < -1.0],
        key=lambda s: s["avg_logprob"],
    )[:10]
    duration = max((s["end"] for s in segments), default=0.0)
    return {
        "transcript_score": score,
        "avg_logprob": avg,
        "low_confidence_count": sum(1 for s in segments if s.get("avg_logprob", 0.0) < -1.0),
        "low_confidence_segments": [
            {
                "start_sec": s["start"],
                "end_sec": s["end"],
                "text": s["text"],
                "avg_logprob": s["avg_logprob"],
            }
            for s in low
        ],
        "diarization_degraded": False,
        "segment_count": len(segments),
        "duration_sec": round(duration, 3),
    }


def with_diarization_degraded(quality: dict, degraded: bool) -> dict:
    return {**quality, "diarization_degraded": degraded}
```

- [ ] **Step 4: Run all new tests**

```bash
cd /Users/hyeonjoo/VSCodeTestProjects/sorigamis/pipeline
.venv/bin/pytest tests/test_tools.py -k "quality or diarization_degraded" -v
```
Expected: all 7 new tests PASS

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
.venv/bin/pytest tests/ -v
```
Expected: all existing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add pipeline/tools/sg_quality.py pipeline/tests/test_tools.py
git commit -m "feat: add sg_quality module for transcript quality computation"
```

---

## Task 3: Propagate `require_review` through Context

**Files:**
- Modify: `pipeline/routers/jobs.py` (line 45–48 — the `skills` list comprehension)
- Modify: `pipeline/tests/test_jobs.py`

**Interfaces:**
- Consumes: `sg_skills.require_review` (from Supabase, Task 1)
- Produces: `context_json.skills[*].require_review bool` — consumed by orchestrator in Task 4

- [ ] **Step 1: Write the failing test**

Open `pipeline/tests/test_jobs.py` and locate the existing `create_job` tests. Add this test:

```python
def test_create_job_forwards_require_review_to_context(client, mock_supabase):
    """require_review must travel from sg_skills into the Hermes context JSON."""
    import json
    from unittest.mock import patch, MagicMock

    job_row = {"id": "job-1", "status": "submitted"}
    mode_row = {"id": "mode-1", "name": "Team Meeting", "skill_ids": ["skill-1"]}
    skill_row = {
        "id": "skill-1",
        "name": "Summary",
        "ai_prompt": "Summarize.",
        "integration_actions": [],
        "require_review": True,
    }

    # Wire mock Supabase to return the rows above in sequence
    mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[job_row])
    mode_chain = (mock_supabase.table.return_value.select.return_value
                  .eq.return_value.maybe_single.return_value.execute)
    mode_chain.return_value = MagicMock(data=mode_row)
    skills_chain = (mock_supabase.table.return_value.select.return_value
                    .in_.return_value.execute)
    skills_chain.return_value = MagicMock(data=[skill_row])

    captured = {}

    def fake_launch(job_id, context_json):
        captured["context"] = json.loads(context_json)

    with patch("routers.jobs.launch_hermes", side_effect=fake_launch), \
         patch("routers.jobs.build_context", wraps=__import__("hermes.context", fromlist=["build_context"]).build_context):
        response = client.post("/jobs", json={
            "drive_file_id": "file-1",
            "mode_id": "mode-1",
            "user_id": "user-1",
        })

    assert response.status_code == 201
    skills_in_context = captured["context"]["skills"]
    assert skills_in_context[0]["require_review"] is True
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd /Users/hyeonjoo/VSCodeTestProjects/sorigamis/pipeline
.venv/bin/pytest tests/test_jobs.py::test_create_job_forwards_require_review_to_context -v
```
Expected: FAIL — `require_review` not present in context skills

- [ ] **Step 3: Update the skills list comprehension in `routers/jobs.py`**

Find lines 45–48:
```python
    skills = [
        {"skill_name": s["name"], "ai_prompt": s["ai_prompt"], "integration_actions": s.get("integration_actions", [])}
        for s in skills_data
    ]
```

Replace with:
```python
    skills = [
        {
            "skill_name": s["name"],
            "ai_prompt": s["ai_prompt"],
            "integration_actions": s.get("integration_actions", []),
            "require_review": bool(s.get("require_review", False)),
        }
        for s in skills_data
    ]
```

- [ ] **Step 4: Run the new test**

```bash
.venv/bin/pytest tests/test_jobs.py::test_create_job_forwards_require_review_to_context -v
```
Expected: PASS

- [ ] **Step 5: Run the full test suite**

```bash
.venv/bin/pytest tests/ -v
```
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add pipeline/routers/jobs.py pipeline/tests/test_jobs.py
git commit -m "feat: forward require_review from sg_skills into Hermes context JSON"
```

---

## Task 4: Update Orchestrator — Quality Computation + Stage 5.5

**Files:**
- Modify: `pipeline/hermes/skills/sg-orchestrator.md`
- Modify: `pipeline/tests/test_hermes_runner.py`

**Interfaces:**
- Consumes: `tools.sg_quality` (Task 2); `context.skills[*].require_review` (Task 3)
- Produces: `quality_json` written to `sg_jobs` after Stage 1 and Stage 2; `awaiting_skill_review` checkpoint after Stage 5 for skills with `require_review == true`

- [ ] **Step 1: Write the failing orchestrator prompt tests**

Append to `pipeline/tests/test_hermes_runner.py`:

```python
def test_orchestrator_prompt_contains_quality_computation():
    """The -z prompt must instruct Hermes to compute and write quality after transcription."""
    from hermes.runner import _build_prompt
    prompt = _build_prompt('{"job_id":"job-1"}')
    assert "sg_quality" in prompt
    assert "quality_json" in prompt


def test_orchestrator_prompt_contains_stage_55_skill_review():
    """The -z prompt must contain the Stage 5.5 skill review checkpoint instructions."""
    from hermes.runner import _build_prompt
    prompt = _build_prompt('{"job_id":"job-1"}')
    assert "awaiting_skill_review" in prompt
    assert "require_review" in prompt
    assert "Stage 5.5" in prompt
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd /Users/hyeonjoo/VSCodeTestProjects/sorigamis/pipeline
.venv/bin/pytest tests/test_hermes_runner.py::test_orchestrator_prompt_contains_quality_computation \
  tests/test_hermes_runner.py::test_orchestrator_prompt_contains_stage_55_skill_review -v
```
Expected: FAIL

- [ ] **Step 3: Update `pipeline/hermes/skills/sg-orchestrator.md`**

**3a — In Stage 1, after step 3 (transcription), add steps 4–6 (quality; the existing steps 4–5 become 7–8):**

Find the block starting with `### Stage 1: Download & Transcribe` and update the numbered steps so that after step 3 (transcription) you insert:

```markdown
4. Compute quality from the transcript and write it to `sg_jobs`:
   ```
   .venv/bin/python -c "
   import json
   from tools.sg_quality import compute_quality
   segs = json.load(open('/tmp/sg-job-<job_id>.transcript.json'))
   quality = compute_quality(segs)
   json.dump(quality, open('/tmp/sg-job-<job_id>.quality.json', 'w'))
   "
   ```
   Then write to Supabase:
   ```
   .venv/bin/python -c "
   import json
   from tools.sg_supabase_write import update_job_status
   quality = json.load(open('/tmp/sg-job-<job_id>.quality.json'))
   update_job_status('<job_id>', 'analyzing', extra={'quality_json': quality})
   "
   ```
5. Read `/tmp/sg-job-<job_id>.transcript.json` and write each segment as a row to
   `sg_utterances` (`job_id`, `start_sec`, `end_sec`, `text`, `avg_logprob`) via `sg-supabase-write`.
6. Write the full transcript JSON to `sg_transcript_raw`.
```

**3b — In Stage 2, after step 3 (write_speakers), add step 4 to update diarization degradation in quality_json:**

Find the block starting with `### Stage 2: Diarize` and after the existing steps add:

```markdown
5. Update `quality_json` with diarization degradation status:
   ```
   .venv/bin/python -c "
   import json
   from tools.sg_quality import with_diarization_degraded
   from tools.sg_supabase_write import update_job_status
   diarize_segs = json.load(open('/tmp/sg-job-<job_id>.speakers.json'))
   degraded = any(s.get('degraded') for s in diarize_segs)
   quality = json.load(open('/tmp/sg-job-<job_id>.quality.json'))
   quality = with_diarization_degraded(quality, degraded)
   json.dump(quality, open('/tmp/sg-job-<job_id>.quality.json', 'w'))
   update_job_status('<job_id>', 'analyzing', extra={'quality_json': quality})
   "
   ```
```

**3c — Add Stage 5.5 between Stage 5 and Stage 6:**

Insert the following section between `### Stage 5: Skill Extraction` and `### Stage 6: Integration Action Checkpoints`:

```markdown
### Stage 5.5: Skill Review Checkpoint (conditional)

For each skill in the approved skills list where `require_review == true`:
1. Set job status → `awaiting_skill_review` and write the skill result as a checkpoint:
   ```
   .venv/bin/python -c "
   import json
   from tools.sg_supabase_write import update_job_status
   checkpoint = {
       'type': 'skill_review',
       'skill_name': '<skill_name>',
       'output_markdown': '<output_markdown from sg_skill_results>',
       'output_json': <output_json from sg_skill_results>,
   }
   update_job_status('<job_id>', 'awaiting_skill_review', extra={'checkpoint_json': checkpoint})
   "
   ```
2. Send FCM push via `sg-notify-fcm` with title "Review [skill_name] before actions fire".
3. **STOP and wait.** Poll `sg_jobs.status` every 5s. Timeout after 30 minutes → treat as skip (do not fail the job).
4. On resume: read `checkpoint_json`.
   - If `{"skipped": true}` — skip all integration actions for this skill; continue to the next skill.
   - Otherwise — proceed to Stage 6 for this skill's integration actions.

Skills with `require_review == false` skip Stage 5.5 entirely and proceed directly to Stage 6.
```

- [ ] **Step 4: Run the new tests**

```bash
.venv/bin/pytest tests/test_hermes_runner.py::test_orchestrator_prompt_contains_quality_computation \
  tests/test_hermes_runner.py::test_orchestrator_prompt_contains_stage_55_skill_review -v
```
Expected: PASS

- [ ] **Step 5: Run the full test suite**

```bash
.venv/bin/pytest tests/ -v
```
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add pipeline/hermes/skills/sg-orchestrator.md pipeline/tests/test_hermes_runner.py
git commit -m "feat: add quality computation and Stage 5.5 skill review to orchestrator"
```

---

## Task 5: Flutter — Drift Schema Migration (`requireReview` column)

**Files:**
- Modify: `lib/data/db/database.dart`
- Modify: `lib/data/db/daos/skill_dao.dart`
- Regenerate: `lib/data/db/database.g.dart`, `lib/data/db/daos/skill_dao.g.dart`
- Create: `test/data/db/skill_dao_test.dart`

**Interfaces:**
- Produces: `Skill.requireReview bool` Dart field; `SkillDao.updateRequireReview(String id, bool value) Future<void>` — consumed by Task 6

- [ ] **Step 1: Write the failing Drift test**

Create `test/data/db/skill_dao_test.dart`:

```dart
import 'package:drift/drift.dart' hide isNull;
import 'package:flutter_test/flutter_test.dart';
import 'package:sorigamis/data/db/database.dart';
import '../../helpers/test_database.dart';

void main() {
  late AppDatabase db;
  setUp(() => db = newTestDatabase());
  tearDown(() => db.close());

  SkillsCompanion _skill(String id, String name) => SkillsCompanion.insert(
        id: id,
        name: name,
        createdAt: DateTime(2026, 1, 1),
      );

  test('requireReview defaults to false on insert', () async {
    await db.skillDao.insertSkill(_skill('s1', 'Summary'));
    final skills = await db.skillDao.watchAllSkills().first;
    expect(skills.first.requireReview, isFalse);
  });

  test('updateRequireReview sets the flag', () async {
    await db.skillDao.insertSkill(_skill('s1', 'Summary'));
    await db.skillDao.updateRequireReview('s1', true);
    final skills = await db.skillDao.watchAllSkills().first;
    expect(skills.first.requireReview, isTrue);
  });
}
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /Users/hyeonjoo/VSCodeTestProjects/sorigamis
flutter test test/data/db/skill_dao_test.dart
```
Expected: compile error — `requireReview` not found on `Skill`

- [ ] **Step 3: Add `requireReview` column to `Skills` table in `database.dart`**

In `lib/data/db/database.dart`, inside the `Skills` class, add after `additionalInstructions`:

```dart
  BoolColumn get requireReview =>
      boolean().withDefault(const Constant(false))();
```

Then bump `schemaVersion` to 2 and add a migration callback on `AppDatabase`:

```dart
  @override
  int get schemaVersion => 2;

  @override
  MigrationStrategy get migration => MigrationStrategy(
        onCreate: (m) => m.createAll(),
        onUpgrade: (m, from, to) async {
          if (from < 2) {
            await m.addColumn(skills, skills.requireReview);
          }
        },
      );
```

- [ ] **Step 4: Add `updateRequireReview` to `SkillDao`**

In `lib/data/db/daos/skill_dao.dart`, add:

```dart
  Future<void> updateRequireReview(String id, bool value) async {
    await (update(skills)..where((s) => s.id.equals(id)))
        .write(SkillsCompanion(requireReview: Value(value)));
  }
```

- [ ] **Step 5: Regenerate Drift code**

```bash
cd /Users/hyeonjoo/VSCodeTestProjects/sorigamis
dart run build_runner build --delete-conflicting-outputs
```
Expected: `database.g.dart` and `skill_dao.g.dart` regenerated successfully

- [ ] **Step 6: Run the new Drift tests**

```bash
flutter test test/data/db/skill_dao_test.dart
```
Expected: both tests PASS

- [ ] **Step 7: Run the full Flutter test suite**

```bash
flutter test
```
Expected: all tests PASS

- [ ] **Step 8: Commit**

```bash
git add lib/data/db/database.dart lib/data/db/database.g.dart \
        lib/data/db/daos/skill_dao.dart lib/data/db/daos/skill_dao.g.dart \
        test/data/db/skill_dao_test.dart
git commit -m "feat: add requireReview column to Skills Drift table (schema v2)"
```

---

## Task 6: Flutter — Skill Editor Screen with `require_review` Toggle

**Files:**
- Create: `lib/features/skills/skill_editor_screen.dart`
- Modify: `lib/core/router.dart`
- Create: `test/features/skills/skill_editor_screen_test.dart`

**Interfaces:**
- Consumes: `SkillDao.updateRequireReview` (Task 5); `skillDaoProvider` (from `providers.dart`)
- Produces: `/skills/:id/edit` route that renders a toggle saving to Drift

- [ ] **Step 1: Write the failing widget test**

Create `test/features/skills/skill_editor_screen_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:drift/native.dart';
import 'package:sorigamis/data/db/database.dart';
import 'package:sorigamis/features/skills/skill_editor_screen.dart';
import 'package:sorigamis/providers/providers.dart';

AppDatabase _db() => AppDatabase(NativeDatabase.memory());

Widget _wrap(AppDatabase db, String skillId) => ProviderScope(
      overrides: [databaseProvider.overrideWithValue(db)],
      child: MaterialApp(
        home: SkillEditorScreen(skillId: skillId),
      ),
    );

void main() {
  testWidgets('shows require review toggle defaulting to off', (tester) async {
    final db = _db();
    await db.skillDao.insertSkill(SkillsCompanion.insert(
      id: 's1',
      name: 'Summary',
      createdAt: DateTime(2026, 1, 1),
    ));
    await tester.pumpWidget(_wrap(db, 's1'));
    await tester.pumpAndSettle();

    expect(find.text('Require review before actions fire'), findsOneWidget);
    final toggle = tester.widget<Switch>(find.byType(Switch));
    expect(toggle.value, isFalse);
    await db.close();
  });

  testWidgets('toggling require_review saves to Drift', (tester) async {
    final db = _db();
    await db.skillDao.insertSkill(SkillsCompanion.insert(
      id: 's1',
      name: 'Summary',
      createdAt: DateTime(2026, 1, 1),
    ));
    await tester.pumpWidget(_wrap(db, 's1'));
    await tester.pumpAndSettle();

    await tester.tap(find.byType(Switch));
    await tester.pumpAndSettle();

    final skills = await db.skillDao.watchAllSkills().first;
    expect(skills.first.requireReview, isTrue);
    await db.close();
  });
}
```

- [ ] **Step 2: Run to confirm failure**

```bash
flutter test test/features/skills/skill_editor_screen_test.dart
```
Expected: compile error — `SkillEditorScreen` not found

- [ ] **Step 3: Create `lib/features/skills/skill_editor_screen.dart`**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../data/db/database.dart';
import '../../providers/providers.dart';

class SkillEditorScreen extends ConsumerStatefulWidget {
  const SkillEditorScreen({super.key, required this.skillId});
  final String skillId;

  @override
  ConsumerState<SkillEditorScreen> createState() => _SkillEditorScreenState();
}

class _SkillEditorScreenState extends ConsumerState<SkillEditorScreen> {
  Skill? _skill;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final dao = ref.read(skillDaoProvider);
    final all = await dao.watchAllSkills().first;
    final match = all.where((s) => s.id == widget.skillId).firstOrNull;
    if (mounted) setState(() => _skill = match);
  }

  Future<void> _toggleRequireReview(bool value) async {
    await ref.read(skillDaoProvider).updateRequireReview(widget.skillId, value);
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    final skill = _skill;
    if (skill == null) return const Scaffold(body: Center(child: CircularProgressIndicator()));
    return Scaffold(
      appBar: AppBar(title: Text(skill.name)),
      body: ListView(
        children: [
          SwitchListTile(
            title: const Text('Require review before actions fire'),
            subtitle: const Text('Hermes will pause and show you results before sending to Slack, Linear, or webhooks.'),
            value: skill.requireReview,
            onChanged: _toggleRequireReview,
          ),
        ],
      ),
    );
  }
}
```

- [ ] **Step 4: Add the route to `router.dart`**

In `lib/core/router.dart`:

```dart
import 'package:go_router/go_router.dart';
import '../features/recordings/recordings_screen.dart';
import '../features/skills/skill_editor_screen.dart';

final appRouter = GoRouter(
  routes: [
    GoRoute(path: '/', builder: (context, state) => const RecordingsScreen()),
    GoRoute(
      path: '/skills/:id/edit',
      builder: (context, state) =>
          SkillEditorScreen(skillId: state.pathParameters['id']!),
    ),
  ],
);
```

- [ ] **Step 5: Run the new widget tests**

```bash
flutter test test/features/skills/skill_editor_screen_test.dart
```
Expected: both tests PASS

- [ ] **Step 6: Run the full Flutter test suite**

```bash
flutter test
```
Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add lib/features/skills/skill_editor_screen.dart \
        lib/core/router.dart \
        test/features/skills/skill_editor_screen_test.dart
git commit -m "feat: add skill editor screen with require_review toggle"
```

---

## Task 7: Flutter — `awaitingSkillReview` Pipeline Status

**Files:**
- Modify: `lib/core/enums.dart`
- Create: `lib/features/pipeline/skill_review_screen.dart`
- Modify: `lib/core/router.dart`
- Create: `test/features/pipeline/skill_review_screen_test.dart`

**Interfaces:**
- Consumes: `GET /jobs/{id}` returns `{"status": "awaiting_skill_review", "checkpoint": {"type": "skill_review", "skill_name": "...", "output_markdown": "..."}}` 
- Produces: `POST /jobs/{id}/checkpoint` with `{"data": {}}` (approve) or `{"data": {"skipped": true}}` (skip)

> **Note:** This task assumes a `LivePipelineClient` and FCM deep-link routing are in place (M2 mobile). The screen and route are built here; wiring to FCM push and the real API client is a separate M2 task.

- [ ] **Step 1: Add `awaitingSkillReview` to `JobStatus` enum**

In `lib/core/enums.dart`, update:
```dart
/// AI pipeline job lifecycle for a recording.
enum JobStatus { none, requested, processing, awaitingSkillReview, completed, failed }
```

- [ ] **Step 2: Write the failing widget test**

Create `test/features/pipeline/skill_review_screen_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sorigamis/features/pipeline/skill_review_screen.dart';

Widget _wrap(Map<String, dynamic> checkpoint, {
  void Function()? onApprove,
  void Function()? onSkip,
}) =>
    MaterialApp(
      home: SkillReviewScreen(
        checkpoint: checkpoint,
        onApprove: onApprove ?? () {},
        onSkip: onSkip ?? () {},
      ),
    );

void main() {
  testWidgets('displays skill name and output', (tester) async {
    await tester.pumpWidget(_wrap({
      'skill_name': 'Action Items',
      'output_markdown': '- Buy milk\n- Call John',
    }));
    expect(find.text('Review: Action Items'), findsOneWidget);
    expect(find.textContaining('Buy milk'), findsOneWidget);
  });

  testWidgets('approve button calls onApprove', (tester) async {
    var approved = false;
    await tester.pumpWidget(_wrap(
      {'skill_name': 'Summary', 'output_markdown': 'A short summary.'},
      onApprove: () => approved = true,
    ));
    await tester.tap(find.text('Approve & Continue'));
    await tester.pump();
    expect(approved, isTrue);
  });

  testWidgets('skip button calls onSkip', (tester) async {
    var skipped = false;
    await tester.pumpWidget(_wrap(
      {'skill_name': 'Summary', 'output_markdown': 'A short summary.'},
      onSkip: () => skipped = true,
    ));
    await tester.tap(find.text('Skip'));
    await tester.pump();
    expect(skipped, isTrue);
  });
}
```

- [ ] **Step 3: Run to confirm failure**

```bash
flutter test test/features/pipeline/skill_review_screen_test.dart
```
Expected: compile error — `SkillReviewScreen` not found

- [ ] **Step 4: Create `lib/features/pipeline/skill_review_screen.dart`**

```dart
import 'package:flutter/material.dart';

class SkillReviewScreen extends StatelessWidget {
  const SkillReviewScreen({
    super.key,
    required this.checkpoint,
    required this.onApprove,
    required this.onSkip,
  });

  final Map<String, dynamic> checkpoint;
  final VoidCallback onApprove;
  final VoidCallback onSkip;

  @override
  Widget build(BuildContext context) {
    final skillName = checkpoint['skill_name'] as String? ?? '';
    final markdown = checkpoint['output_markdown'] as String? ?? '';
    return Scaffold(
      appBar: AppBar(title: Text('Review: $skillName')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(child: SingleChildScrollView(child: Text(markdown))),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: onSkip,
                    child: const Text('Skip'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton(
                    onPressed: onApprove,
                    child: const Text('Approve & Continue'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
```

- [ ] **Step 5: Add the route to `router.dart`**

```dart
import '../features/pipeline/skill_review_screen.dart';

// Inside appRouter routes list, add:
GoRoute(
  path: '/jobs/:id/skill-review',
  builder: (context, state) {
    final checkpoint = state.extra as Map<String, dynamic>? ?? {};
    return SkillReviewScreen(
      checkpoint: checkpoint,
      onApprove: () => context.pop(),   // caller wires real API call
      onSkip: () => context.pop(),
    );
  },
),
```

- [ ] **Step 6: Run the new tests**

```bash
flutter test test/features/pipeline/skill_review_screen_test.dart
```
Expected: all 3 tests PASS

- [ ] **Step 7: Run the full Flutter test suite**

```bash
flutter test
```
Expected: all tests PASS

- [ ] **Step 8: Commit**

```bash
git add lib/core/enums.dart \
        lib/features/pipeline/skill_review_screen.dart \
        lib/core/router.dart \
        test/features/pipeline/skill_review_screen_test.dart
git commit -m "feat: add SkillReviewScreen and awaitingSkillReview job status"
```

---

## Task 8: Flutter — Results Screen Quality Card

**Files:**
- Create: `lib/features/results/results_screen.dart`
- Modify: `lib/core/router.dart`
- Create: `test/features/results/results_screen_test.dart`

**Interfaces:**
- Consumes: `quality_json` map (passed as route `extra`) matching the spec schema: `{transcript_score: String, avg_logprob: double, low_confidence_count: int, low_confidence_segments: List, diarization_degraded: bool, segment_count: int, duration_sec: double}`
- Produces: `/jobs/:id/results` route rendering a quality card and skill results list

- [ ] **Step 1: Write the failing widget test**

Create `test/features/results/results_screen_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sorigamis/features/results/results_screen.dart';

final _goodQuality = {
  'transcript_score': 'good',
  'avg_logprob': -0.42,
  'low_confidence_count': 0,
  'low_confidence_segments': <Map<String, dynamic>>[],
  'diarization_degraded': false,
  'segment_count': 87,
  'duration_sec': 3421.0,
};

final _poorQuality = {
  'transcript_score': 'poor',
  'avg_logprob': -0.95,
  'low_confidence_count': 3,
  'low_confidence_segments': [
    {'start_sec': 10.0, 'end_sec': 12.0, 'text': 'unclear speech', 'avg_logprob': -1.6},
  ],
  'diarization_degraded': true,
  'segment_count': 20,
  'duration_sec': 600.0,
};

Widget _wrap(Map<String, dynamic> quality, {List<Map<String, dynamic>> skillResults = const []}) =>
    MaterialApp(
      home: ResultsScreen(qualityJson: quality, skillResults: skillResults),
    );

void main() {
  testWidgets('shows Good quality chip', (tester) async {
    await tester.pumpWidget(_wrap(_goodQuality));
    expect(find.text('Good'), findsOneWidget);
    expect(find.text('Multi-speaker'), findsOneWidget);
  });

  testWidgets('shows Poor quality chip with diarization warning', (tester) async {
    await tester.pumpWidget(_wrap(_poorQuality));
    expect(find.text('Poor'), findsOneWidget);
    expect(find.text('Single-speaker fallback'), findsOneWidget);
  });

  testWidgets('expands to show low confidence segments', (tester) async {
    await tester.pumpWidget(_wrap(_poorQuality));
    await tester.tap(find.text('3 low-confidence segments'));
    await tester.pumpAndSettle();
    expect(find.textContaining('unclear speech'), findsOneWidget);
  });

  testWidgets('shows no low confidence section when count is 0', (tester) async {
    await tester.pumpWidget(_wrap(_goodQuality));
    expect(find.text('0 low-confidence segments'), findsNothing);
  });
}
```

- [ ] **Step 2: Run to confirm failure**

```bash
flutter test test/features/results/results_screen_test.dart
```
Expected: compile error — `ResultsScreen` not found

- [ ] **Step 3: Create `lib/features/results/results_screen.dart`**

```dart
import 'package:flutter/material.dart';

class ResultsScreen extends StatelessWidget {
  const ResultsScreen({
    super.key,
    required this.qualityJson,
    this.skillResults = const [],
  });

  final Map<String, dynamic> qualityJson;
  final List<Map<String, dynamic>> skillResults;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Results')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _QualityCard(quality: qualityJson),
          const SizedBox(height: 16),
          ...skillResults.map((r) => Card(
                child: ListTile(
                  title: Text(r['skill_name'] as String? ?? ''),
                  subtitle: Text(r['output_markdown'] as String? ?? ''),
                ),
              )),
        ],
      ),
    );
  }
}

class _QualityCard extends StatefulWidget {
  const _QualityCard({required this.quality});
  final Map<String, dynamic> quality;

  @override
  State<_QualityCard> createState() => _QualityCardState();
}

class _QualityCardState extends State<_QualityCard> {
  bool _expanded = false;

  Color _scoreColor(String score) => switch (score) {
        'good' => Colors.green,
        'fair' => Colors.orange,
        _ => Colors.red,
      };

  String _scoreLabel(String score) => switch (score) {
        'good' => 'Good',
        'fair' => 'Fair',
        _ => 'Poor',
      };

  @override
  Widget build(BuildContext context) {
    final score = widget.quality['transcript_score'] as String? ?? 'good';
    final degraded = widget.quality['diarization_degraded'] as bool? ?? false;
    final lowCount = widget.quality['low_confidence_count'] as int? ?? 0;
    final lowSegs = (widget.quality['low_confidence_segments'] as List?)
            ?.cast<Map<String, dynamic>>() ??
        [];

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Chip(
                label: Text(_scoreLabel(score)),
                backgroundColor: _scoreColor(score).withOpacity(0.15),
                labelStyle: TextStyle(color: _scoreColor(score), fontWeight: FontWeight.bold),
              ),
              const SizedBox(width: 8),
              Text(degraded ? 'Single-speaker fallback' : 'Multi-speaker',
                  style: Theme.of(context).textTheme.bodySmall),
            ]),
            if (lowCount > 0) ...[
              const SizedBox(height: 8),
              GestureDetector(
                onTap: () => setState(() => _expanded = !_expanded),
                child: Text(
                  '$lowCount low-confidence segment${lowCount == 1 ? '' : 's'}',
                  style: TextStyle(color: Colors.orange[700], decoration: TextDecoration.underline),
                ),
              ),
              if (_expanded)
                ...lowSegs.map((s) => Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(
                        '${s['text']} (${s['avg_logprob']})',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    )),
            ],
          ],
        ),
      ),
    );
  }
}
```

- [ ] **Step 4: Add the route to `router.dart`**

```dart
import '../features/results/results_screen.dart';

// Inside appRouter routes list, add:
GoRoute(
  path: '/jobs/:id/results',
  builder: (context, state) {
    final extra = state.extra as Map<String, dynamic>? ?? {};
    return ResultsScreen(
      qualityJson: (extra['quality_json'] as Map<String, dynamic>?) ?? {},
      skillResults: (extra['skill_results'] as List?)?.cast<Map<String, dynamic>>() ?? [],
    );
  },
),
```

- [ ] **Step 5: Run the new widget tests**

```bash
flutter test test/features/results/results_screen_test.dart
```
Expected: all 4 tests PASS

- [ ] **Step 6: Run the full Flutter test suite**

```bash
flutter test
```
Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add lib/features/results/results_screen.dart \
        lib/core/router.dart \
        test/features/results/results_screen_test.dart
git commit -m "feat: add ResultsScreen with expandable transcript quality card"
```

---

## Self-Review Checklist

- [x] **Spec coverage:**
  - Quality metrics (score, low-confidence segments, diarization flag) → Tasks 2, 4
  - `require_review` flag on `sg_skills` → Tasks 1, 3, 5
  - `awaiting_skill_review` checkpoint → Tasks 4, 7
  - Flutter skill editor toggle → Task 6
  - Flutter Results quality card → Task 8
  - Supabase migrations → Task 1
  - `quality_json` written after Stage 1 and updated after Stage 2 → Task 4

- [x] **Placeholder scan:** All steps contain concrete code. No TBD/TODO.

- [x] **Type consistency:**
  - `compute_quality(segments: list[dict]) -> dict` defined in Task 2, called in Task 4 ✓
  - `with_diarization_degraded(quality: dict, degraded: bool) -> dict` defined in Task 2, called in Task 4 ✓
  - `SkillDao.updateRequireReview(String id, bool value)` defined in Task 5, consumed in Task 6 ✓
  - `SkillReviewScreen(checkpoint, onApprove, onSkip)` defined in Task 7 ✓
  - `ResultsScreen(qualityJson, skillResults)` defined in Task 8 ✓
