# Sorigamis M2 Plan 1 (sg-pipeline) — Progress Ledger

Plan: docs/superpowers/plans/2026-06-26-hermes-pipeline-plan-series.md
Branch: m2-hermes-pipeline
Merge base: 92b5861

Tasks:
- Task 1: Project Scaffold + Supabase Schema — COMPLETE (commits 92b5861..49a060f, review clean; supabase db push applied from pipeline/)
- Task 2: FastAPI Skeleton + Health Endpoint — COMPLETE (commits 49a060f..269e578, review clean)
- Task 3: Jobs Router (Create + Status) — COMPLETE (commits 269e578..427bfad, review clean)
- Task 4: Skills & Modes CRUD Routers — COMPLETE (commits 427bfad..e9b1f6f, review clean)
- Task 5: Hermes sg-orchestrator Skill — COMPLETE (commits e9b1f6f..b184ab5, review clean)
- Task 6: Modal Workers (Whisper + Diarize) — COMPLETE (commits b184ab5..8c118b5, review clean)
- Task 7: Hermes Pipeline Tools (Drive, Supabase, FCM) — COMPLETE (commits 8c118b5..71c672f, review clean)
- Task 8: Integration Action Tools (Slack, Linear, Webhook) — COMPLETE (commits 71c672f..20ba7c3, review clean)
- Task 9: Hermes Session Runner — COMPLETE (commits 20ba7c3..02e0f07, review clean)
- Task 10: Fly.io Deploy + End-to-End Smoke Test — COMPLETE (commits 02e0f07..0b2291b, review clean)

Final whole-branch review: COMPLETE (HEAD 29ef315, 29 tests pass)
Fixed: Dockerfile/.dockerignore, maybe_single 404 guard, UUID injection, monitor status guard, mode ownership
Deferred to Plan 2: auth/JWT, Hermes→tools bridge (MCP or CLI), FCM device_token, secrets-in-argv
