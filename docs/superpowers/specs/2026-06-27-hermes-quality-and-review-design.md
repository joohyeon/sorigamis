# Hermes — Quality Metrics & Skill Review Design
**Date:** 2026-06-27
**Status:** Approved
**Scope:** Three additions to the existing Hermes pipeline (M2): transcript quality reporting, quality surfaced in Results, and per-skill human-in-the-loop review before integration actions fire

---

## 1. Overview

This design adds three capabilities to the existing Hermes pipeline without restructuring it:

1. **Quality metrics** — after transcription, compute a quality summary (score + low-confidence segments + diarization mode) and store it on the job. Shown in the Flutter Results screen — informational, not a blocking gate.
2. **Per-skill review flag** — each skill can be marked `require_review: true`. When set, Hermes pauses after producing that skill's output and waits for user confirmation before firing its integration actions.
3. **`awaiting_skill_review` checkpoint** — new job status and checkpoint type, following the existing `awaiting_checkpoint` pattern exactly.

All three changes follow Approach A: enrich existing structures rather than add new tables or polling mechanisms.

---

## 2. Schema Changes

### `sg_jobs` — one new column

```sql
ALTER TABLE sg_jobs ADD COLUMN quality_json jsonb;
```

`quality_json` is nullable. Jobs that complete before this feature ships have `null` — the app renders no quality card in that case.

### `sg_skills` — one new column

```sql
ALTER TABLE sg_skills ADD COLUMN require_review bool NOT NULL DEFAULT false;
```

Default `false` preserves existing behavior — no skill is affected unless explicitly opted in.

---

## 3. Quality Metrics

### What is computed

After Stage 1 transcription, before utterances are written to Supabase, the orchestrator computes a `quality_summary` from the Whisper JSON output:

```json
{
  "transcript_score": "good",
  "avg_logprob": -0.42,
  "low_confidence_count": 3,
  "low_confidence_segments": [
    {"start_sec": 12.5, "end_sec": 18.2, "text": "...", "avg_logprob": -1.4}
  ],
  "diarization_degraded": false,
  "segment_count": 87,
  "duration_sec": 3421.0
}
```

**Score thresholds** (based on mean `avg_logprob` across all segments):
- `"good"` — avg ≥ −0.5
- `"fair"` — avg between −0.5 and −0.8
- `"poor"` — avg < −0.8

`low_confidence_segments` contains up to 10 segments where `avg_logprob < −1.0`, sorted worst-first.

`diarization_degraded` is `true` when the diarize worker fell back to single-speaker mode (i.e. any segment in the diarization output has `"degraded": true`).

### How it is written

The orchestrator computes quality as a Python one-liner that reads `/tmp/sg-job-<job_id>.transcript.json`, then writes it to `/tmp/sg-job-<job_id>.quality.json`. It then calls `update_job_status` with `extra={"quality_json": ...}` — no new tool required.

```python
# orchestrator computes quality (inline, after transcript JSON is written)
# NOTE: reads raw transcript file which uses 'start'/'end' keys (not yet normalized to start_sec/end_sec)
.venv/bin/python -c "
import json, sys
segs = json.load(open('/tmp/sg-job-<job_id>.transcript.json'))
probs = [s['avg_logprob'] for s in segs if 'avg_logprob' in s]
avg = sum(probs) / len(probs) if probs else 0.0
score = 'good' if avg >= -0.5 else ('fair' if avg >= -0.8 else 'poor')
low = sorted([s for s in segs if s.get('avg_logprob', 0) < -1.0], key=lambda s: s['avg_logprob'])[:10]
quality = {
    'transcript_score': score,
    'avg_logprob': round(avg, 4),
    'low_confidence_count': len([s for s in segs if s.get('avg_logprob', 0) < -1.0]),
    'low_confidence_segments': [{'start_sec': s['start'], 'end_sec': s['end'], 'text': s['text'], 'avg_logprob': s['avg_logprob']} for s in low],
    'diarization_degraded': False,   # updated after diarize stage
    'segment_count': len(segs),
}
json.dump(quality, open('/tmp/sg-job-<job_id>.quality.json', 'w'))
"
```

After diarization (Stage 2), the orchestrator checks if any diarization segment has `"degraded": true` and, if so, re-writes `quality_json` with `diarization_degraded: true`.

### Where it is shown

The Flutter Results screen reads `quality_json` from the job row and renders an expandable **Quality card** at the top of the results view:

- **Header:** transcript score chip ("Good / Fair / Poor") + diarization mode ("Multi-speaker" or "Single-speaker fallback")
- **Expandable body:** list of low-confidence segments, each showing timestamp range + text + logprob value, linked to the corresponding utterance in the transcript view

Quality is purely informational — it does not block any pipeline stage or require user action.

---

## 4. Per-Skill Review Flag

### Configuration

The `require_review` boolean is set per-skill in the Skill editor screen on mobile. A toggle — "Require review before actions fire" — is added to the skill edit form. Default: off.

The value is captured in the job context JSON at job-start time (already part of the `skills` array passed to `build_context`). In-flight jobs use the value captured at launch, not the current skill row.

### Behavior

| `require_review` | Behavior after skill extraction |
|---|---|
| `false` (default) | Flows directly to Stage 6 action checkpoints — no change from today |
| `true` | Orchestrator pauses at new Stage 5.5, waits for user confirmation, then proceeds to Stage 6 |

---

## 5. Stage 5.5 — Skill Review Checkpoint (conditional)

This stage runs between Stage 5 (skill extraction) and Stage 6 (integration actions), once per skill where `require_review == true`.

### Orchestrator steps

1. Set job status → `awaiting_skill_review`
2. Write checkpoint to `sg_jobs.checkpoint_json`:
   ```json
   {
     "type": "skill_review",
     "skill_name": "Action Items",
     "output_markdown": "...",
     "output_json": {...}
   }
   ```
3. Send FCM push: `"Review [skill name] before actions fire"`
4. **STOP and wait.** Poll `sg_jobs.status` every 5 seconds. Timeout after 30 minutes (treat as skip — do not fail the job).
5. On resume: read `checkpoint_json`.
   - If `{"skipped": true}` — skip all integration actions for this skill, continue to next skill.
   - Otherwise — proceed to Stage 6 for this skill's integration actions.

### New job status value

`awaiting_skill_review` is added to the state machine alongside existing `awaiting_plan_confirmation` and `awaiting_checkpoint`. The FastAPI `/jobs/{id}` endpoint already returns raw `status` — no endpoint changes needed.

### Updated state machine

```
submitted → analyzing → awaiting_plan_confirmation
  → executing → awaiting_checkpoint (speaker assignment)
  → executing → [per skill with require_review=true: awaiting_skill_review]*
  → executing → awaiting_checkpoint (action confirmation)
  → executing → … → complete | failed
```

---

## 6. Mobile App Changes

| Screen | Change |
|---|---|
| Skill editor | Add "Require review before actions fire" toggle |
| Results | Add expandable Quality card at top (reads `quality_json`) |
| Pipeline status handling | Handle `awaiting_skill_review` status — show skill result card with approve/skip |

No changes to Plan Confirmation, Speaker Checkpoint, Action Checkpoint, or recording flow.

---

## 7. Files to Change

| File | Change |
|---|---|
| `pipeline/hermes/skills/sg-orchestrator.md` | Add quality computation after Stage 1; add Stage 5.5 skill review checkpoint |
| `pipeline/hermes/context.py` | Pass `require_review` per skill in context JSON |
| Supabase migrations | `quality_json` on `sg_jobs`; `require_review` on `sg_skills` |
| Flutter skill editor screen | `require_review` toggle |
| Flutter results screen | Quality card |
| Flutter pipeline status handler | `awaiting_skill_review` state |

---

## 8. Out of Scope

- Quality metrics do not block pipeline progression
- No per-job override of `require_review` (set at the skill level, not at plan confirmation time)
- No reprocessing/retry triggered from the quality card
- Threshold values (`-0.5`, `-0.8`, `-1.0`) are hardcoded for now — not user-configurable
