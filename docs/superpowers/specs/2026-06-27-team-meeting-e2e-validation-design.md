# Team Meeting E2E Validation Design
**Date:** 2026-06-27
**Status:** Approved
**Scope:** Local validation driver for the real Team Meeting Hermes pipeline, including real LLM skill execution and SMTP email delivery

---

## 1. Overview

This design adds a supported local end-to-end validation path for the Team Meeting scenario without using the mobile app. The validator drives the same public FastAPI contract that the app uses, keeps existing Supabase as the source of truth, lets Hermes run the real LLM skill extraction path, and can approve a real SMTP email action after the normal checkpoint flow.

The validator is not a replacement orchestrator. It acts as the local stand-in for the mobile client: it submits a job, polls status, answers confirmation checkpoints, prints progress, and writes a validation report.

---

## 2. Goals

- Validate a Google Drive audio file ID through the real FastAPI → Hermes → Supabase pipeline.
- Validate real Hermes/LLM outputs for the Team Meeting mode.
- Validate all expected checkpoints without using the mobile UI.
- Validate a real email integration action through SMTP when explicitly enabled.
- Produce an inspectable local report with job IDs, status timeline, checkpoints, skill outputs, action logs, and email delivery status.

---

## 3. Non-Goals

- No deterministic or mocked skill executor for this scenario.
- No local-only database/state replacement for Supabase.
- No generalized runner for every Mode yet.
- No mobile UI changes.
- No bulk attendee discovery from transcript; attendees are passed explicitly to the validator.

---

## 4. File Layout

The validation driver belongs under the test tree because it is a manual validation utility, not production runtime code:

```text
pipeline/
  tests/
    e2e/
      sg_validate_team_meeting.py
```

Runtime additions remain under runtime directories:

```text
pipeline/
  tools/
    sg_email_send.py
  hermes/
    skills/
      sg-orchestrator.md
```

Automated tests use the existing `pipeline/tests/test_*.py` pattern.

---

## 5. CLI Contract

The manual runner is invoked from `pipeline/`:

```bash
uv run python tests/e2e/sg_validate_team_meeting.py \
  --file-id <google_drive_audio_file_id> \
  --server-url http://localhost:8080 \
  --attendee alice@example.com \
  --attendee bob@example.com \
  --send-email \
  --out /tmp/sg-team-meeting-e2e.json
```

Arguments:

- `--file-id` — required Google Drive audio file ID.
- `--server-url` — FastAPI URL. Defaults to `http://localhost:8080`.
- `--env-file` — env file path. Defaults to `.env`.
- `--attendee` — repeatable email recipient.
- `--send-email` — required to approve real email action checkpoints.
- `--speaker` — optional repeatable mapping such as `A=Alice`, `B=Bob`.
- `--out` — local validation report path.

Required environment variables for all real pipeline runs:

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
GOOGLE_SERVICE_ACCOUNT_JSON
HERMES_PROVIDER
HERMES_MODEL
```

Required environment variables when `--send-email` is present:

```text
SMTP_HOST
SMTP_PORT
SMTP_USERNAME
SMTP_PASSWORD
SMTP_FROM
```

Optional:

```text
SMTP_USE_TLS
```

`SMTP_USE_TLS` defaults to `true`. A value of `false` disables STARTTLS for local SMTP test servers.

If `--send-email` is absent, the validator must not approve email action checkpoints. SMTP variables may be missing in that mode.

---

## 6. Data Flow

### 6.1 Preflight

The validator loads the env file, checks `GET /health`, validates required env vars, and verifies that at least one `--attendee` is present when `--send-email` is requested.

The validator should fail before submitting a job if credentials or required inputs are missing.

### 6.2 Team Meeting Setup

The validator ensures the existing Supabase project has the Team Meeting mode and expected skills:

- `Meeting Summary`
- `Action Items`
- `Decision Log`
- `Meeting Follow-up Email`

The Team Meeting mode is configured to include these skills in order.

For `user_id`, the validator follows the existing scratch runner behavior: use the first available Supabase auth user when one exists, otherwise create a confirmed test user through the Supabase admin API. The created user email should be clearly test-scoped.

The email-capable skill stores an integration action shaped like:

```json
{
  "type": "email",
  "destination": "meeting_attendees",
  "config": {
    "recipients": ["alice@example.com", "bob@example.com"],
    "subject": "Team Meeting follow-up"
  }
}
```

Skills that can trigger external actions should set `require_review: true`, so the real skill output is visible before actions fire.

### 6.3 Job Submission

The validator submits through FastAPI:

```http
POST /jobs
{
  "drive_file_id": "<file-id>",
  "mode_id": "<team-meeting-mode-id>",
  "user_id": "<test-or-existing-user-id>"
}
```

FastAPI remains responsible for creating the job row, resolving the Mode/Skills, building Hermes context, and launching Hermes.

### 6.4 Polling And Checkpoint Handling

The validator polls `GET /jobs/{job_id}` until a terminal state or timeout.

Handled statuses:

- `awaiting_plan_confirmation` — print the proposed plan and approve all Team Meeting steps.
- `awaiting_checkpoint` with `type=speaker_assignment` — submit speaker mappings from `--speaker` or stable placeholders such as `Participant A`.
- `awaiting_skill_review` — print the real Hermes skill output and approve it for this validation run.
- `awaiting_checkpoint` with `type=action_confirmation` and `action_type=email` — approve only when `--send-email` is present; otherwise skip/refuse.
- `awaiting_checkpoint` for non-email actions — skip by default in this Team Meeting validator.
- `complete` — fetch final results and write report.
- `failed` — fetch error, write report, exit non-zero.

### 6.5 Final Validation

At completion, the validator fetches `/jobs/{job_id}/results` and validates:

- expected Team Meeting skill result rows exist
- skill outputs are non-empty
- email action log exists
- when `--send-email` is set, email action status indicates successful send, such as `fired`

The local report includes:

- job ID
- Drive file ID
- mode ID and mode name
- status timeline
- handled checkpoints
- skill result summaries and raw output references
- action logs
- SMTP email recipients and subject
- final pass/fail summary

---

## 7. SMTP Email Tool

Add `pipeline/tools/sg_email_send.py` as the runtime email sender Hermes can call from Stage 6.

The tool reads SMTP configuration from env:

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM`
- `SMTP_USE_TLS` optional

Tool API:

```python
send_email(
    recipients: list[str],
    subject: str,
    body_markdown: str,
) -> dict
```

Behavior:

- sends a plain text email using the Markdown body as readable text
- authenticates with SMTP credentials from env
- returns recipients, subject, timestamp, and non-secret provider response details when available
- never returns or logs `SMTP_PASSWORD`
- raises clear errors for missing env, connection failure, auth failure, and send failure

---

## 8. Hermes Orchestrator Updates

Update `pipeline/hermes/skills/sg-orchestrator.md` Stage 6 to include email actions:

1. Build an action confirmation checkpoint for email:
   ```json
   {
     "type": "action_confirmation",
     "action_type": "email",
     "destination": "meeting_attendees",
     "preview": {
       "to": ["alice@example.com", "bob@example.com"],
       "subject": "Team Meeting follow-up",
       "body_markdown": "<Hermes-generated meeting follow-up body>"
     }
   }
   ```
2. Wait for confirmation like other external actions.
3. If approved, call `tools.sg_email_send.send_email(...)`.
4. Write `sg_action_logs` with `status="fired"` on success.
5. Write `sg_action_logs` with `status="failed"` and an error on failure.

The orchestrator must continue to use existing helper functions for Supabase writes.

---

## 9. Error Handling

The validator fails before job submission for missing required inputs or credentials.

During polling:

- failed job status exits non-zero and writes a report
- unknown checkpoint types are skipped with an explicit timeline entry
- email action checkpoints are refused unless `--send-email` is set
- polling has a clear timeout and reports the last known job state

The email tool:

- masks secrets from all error messages
- distinguishes missing config, connection/auth failure, and send failure
- lets Hermes decide whether to mark the action failed while allowing the overall job error behavior to follow the orchestrator rules

---

## 10. Testing Plan

Automated tests:

- `test_email_tool.py`
  - env loading
  - SMTP message construction
  - mocked `smtplib.SMTP` / `smtplib.SMTP_SSL`
  - auth and send failures
  - password never appears in return values or error text

- `test_team_meeting_validator.py`
  - env-file loading and preflight checks
  - Team Meeting seeding payloads against a mocked Supabase client
  - polling handlers for plan confirmation, speaker checkpoint, skill review, email action confirmation, complete, and failed
  - email action refusal when `--send-email` is absent
  - final report shape

- `test_hermes_runner.py`
  - orchestrator prompt includes email action instructions
  - orchestrator prompt mentions `sg_email_send`

Manual validation:

```bash
cd pipeline
uv run uvicorn main:app --port 8080
uv run python tests/e2e/sg_validate_team_meeting.py \
  --file-id <drive_file_id> \
  --server-url http://localhost:8080 \
  --attendee your-test-email@example.com \
  --send-email \
  --out /tmp/sg-team-meeting-e2e.json
```

Success criteria:

- Supabase job reaches `complete`
- all Team Meeting skill results are present
- real Hermes outputs are visible in the report
- email action log is written with successful status
- real email arrives at the configured attendee inbox
- report contains enough information to debug any failed stage

---

## 11. Open Decisions

No open decisions remain for the first implementation plan. Future generalization to other Modes is intentionally deferred until the Team Meeting validator proves stable.
