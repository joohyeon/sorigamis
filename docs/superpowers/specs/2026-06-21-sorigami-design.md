# Sorigami — Mobile App Design Spec
**Date:** 2026-06-21  
**Status:** Approved

---

## 1. Overview

Sorigami is a cross-platform mobile app (Android + iOS) that records conversations and routes them through a server-side AI pipeline to produce transcripts, summaries, and action items. The app focuses on recording stability, metadata capture, Google Drive backup, and AI result retrieval. All AI computation runs on a backend server — the app is a thin client for capture and result display.

**Target users:** Fixli internal team initially; broader expansion to meeting-heavy teams later.

---

## 2. Architecture

### System Layers

```
┌─────────────────────────────────────────────────────┐
│                   Sorigami (Flutter)                 │
│                                                     │
│  UI Layer        Screens + Widgets (Riverpod)       │
│  Domain Layer    Use cases, entities, interfaces    │
│  Data Layer      Repositories, local DB, API client │
└──────────────┬──────────────────────┬───────────────┘
               │ Firebase Auth JWT     │ REST API
               ▼                       ▼
     ┌──────────────────┐   ┌─────────────────────┐
     │  Firebase Auth   │   │   Sorigami Backend  │
     │  (Google sign-in)│   │  (FastAPI / Node)   │
     └──────────────────┘   │                     │
                             │  POST /jobs         │
                             │  GET  /jobs/:id     │
                             │  GET  /jobs/:id/result│
                             │  PUT  /users/fcm-token│
                             └──────────┬──────────┘
                                        │
                             ┌──────────▼──────────┐
                             │   AI Pipeline       │
                             │  Whisper + Agents   │
                             │  (multi-agent)      │
                             └─────────────────────┘
```

### Key Decisions

- **Flutter + Riverpod** — async job polling fits provider pattern cleanly; avoids BLoC boilerplate
- **Clean architecture (3 layers)** — UI never touches API directly; repositories abstract local vs. remote
- **Drift (SQLite)** — offline-first local DB; recordings, metadata, and cached AI results survive offline
- **Firebase Auth only** — identity and JWT tokens; no other Firebase services
- **WorkManager** (Android) / **BGTaskScheduler** (iOS) — keeps uploads and polling alive in background
- **Google Drive OAuth** — separate credential from app auth, stored encrypted in local DB

---

## 3. Data Model

### Local Database (Drift/SQLite)

```
Recording
├── id                UUID (PK)
├── title             String
├── memo              String?
├── tags              List<String>
├── category          String?   ('meeting' | 'interview' | 'call' | 'note' | ...)
├── language          String    ('auto' | 'ko' | 'en' | ...)
├── modeId            UUID?     (FK → Mode, nullable = use default mode)
├── createdAt         DateTime
├── updatedAt         DateTime
├── audioFilePath     String    (local file path)
├── audioFormat       String    (m4a | wav | mp3)
├── audioDuration     Duration?
├── uploadStatus      Enum (none | queued | uploading | done | failed)
├── driveFileId       String?   (Google Drive file ID after upload)
├── jobId             String?   (AI pipeline job ID)
├── jobStatus         Enum (none | requested | processing | completed | failed)
└── jobError          String?

RecordingResult
├── id                UUID (PK)
├── recordingId       UUID (FK → Recording)
├── transcript        String              (always present, shared across skills)
├── skillResults      List<SkillResult>   (JSON)
└── receivedAt        DateTime

SkillResult (embedded JSON in RecordingResult)
├── skillId           UUID
├── skillName         String
└── output            String              (rendered text — summary, task list, etc.)

Skill
├── id                    UUID (PK)
├── name                  String        ('Action Items' | 'Decision Log' | ...)
├── description           String?
├── outputType            Enum (summary | tasks | both | custom)
├── focusArea             String?       ('action items' | 'decisions' | 'risks' | ...)
├── tone                  Enum (formal | casual | concise)
├── assigneeDetection     Bool
├── outputLanguage        String        ('auto' | 'ko' | 'en' | ...)
├── additionalInstructions String?      (free-text for power users)
└── createdAt             DateTime

Mode
├── id                UUID (PK)
├── name              String        ('Team Meeting' | 'Sales Call' | 'Standup' | ...)
├── icon              String        (emoji or icon key)
├── isDefault         Bool
└── createdAt         DateTime

ModeSkill  (Mode ↔ Skill many-to-many)
├── modeId            UUID (FK → Mode)
└── skillId           UUID (FK → Skill)

UserSettings
├── userId                String    (Firebase UID)
├── defaultLanguage       String
├── defaultCategory       String?
├── driveConnected        Bool
├── driveRefreshToken     String?   (encrypted via Flutter Secure Storage)
├── notificationsEnabled  Bool
└── fcmToken              String?
```

### Key Decisions

- `Recording` holds both upload state and AI job state — single source of truth per recording
- `RecordingResult` is separate and lazy-loaded — full transcripts can be large
- `driveRefreshToken` stored via Flutter Secure Storage — never in plain SQLite
- `skillResults` stored as JSON — allows multi-agent output format to evolve without schema migrations
- `category` is an optional free-form string with suggested values — user can leave blank
- `Mode` is the user-facing concept; `Skill` is the underlying capability — users configure Modes, not Skills directly in the recording flow

---

## 4. Skills & Modes System

### Concepts

- **Skill** — a reusable AI capability with structured settings (output type, focus, tone, assignee detection) plus an optional free-text `additionalInstructions` field for power users
- **Mode** — a named bundle of skills with an icon, shown as one-tap presets on the recording screen
- **Default mode** — one mode is marked default and pre-selected every time the app opens; user never has to tap anything for routine recordings

### UX Flow

```
RecordingsScreen (FAB tapped)
  └── RecordingInfoSheet
        ├── Mode selector (horizontal chip row — Team Meeting | Sales Call | Standup | + Custom)
        │     └── active mode persists from last session
        ├── [+ Custom] — opens skill multi-select for this recording only
        ├── Title (required)
        ├── Memo, tags, category, language (optional)
        └── [Start Recording]
```

- Default mode auto-applies — zero friction for 90% of use
- Active mode persists across sessions — repeat users never tap the selector
- [+ Custom] lets power users add/remove skills for one recording without changing their mode

### Skill configuration (structured + free-text)

Each skill has:
- **Structured fields**: output type, focus area, tone, assignee detection toggle, output language
- **Additional instructions** (optional free-text): e.g. "Always list blockers separately. Format tasks as checkboxes."

---

## 5. API Contract

### Authentication
All requests: `Authorization: Bearer <firebase_jwt>`  
Backend validates token against Firebase Auth public keys.

### Endpoints

```
# Job submission
POST /api/v1/jobs
Body: multipart/form-data
  - audio_file:       binary
  - recording_id:     UUID
  - language:         String    ('auto' | 'ko' | 'en' | ...)
  - audio_format:     String    (m4a | wav | mp3)
  - category:         String?
  - skills:           JSON array
    [
      {
        skill_id:                UUID,
        output_type:             "summary" | "tasks" | "both" | "custom",
        focus_area:              String?,
        tone:                    "formal" | "casual" | "concise",
        assignee_detection:      Bool,
        output_language:         String,
        additional_instructions: String?
      }
    ]
Response: { job_id: UUID, status: "requested" }

# Job status polling
GET /api/v1/jobs/:job_id
Response: {
  job_id:   UUID,
  status:   "requested" | "processing" | "completed" | "failed",
  error:    String?
}

# Fetch result (only when status = completed)
GET /api/v1/jobs/:job_id/result
Response: {
  transcript: String,
  skill_results: [
    { skill_id: UUID, skill_name: String, output: String }
  ]
}

# Register/update FCM token
PUT /api/v1/users/fcm-token
Body: { fcm_token: String }
Response: { ok: true }

# FCM push payload (backend → app, via Firebase)
{
  type:    "job_completed" | "job_failed",
  job_id:  UUID,
  error:   String?
}
```

### Polling Strategy

- Start polling 10s after job submission
- Interval: 15s while `processing`, 30s after 5 minutes elapsed
- Max attempts: 40 (≈ 20 min total coverage)
- On `job_completed` push received → cancel polling, fetch result immediately
- On app foreground → resume polling for any `processing` jobs

---

## 6. Screen Flow

```
Auth
└── SplashScreen → GoogleSignInScreen

Main (bottom nav: Recordings | Settings)
│
├── RecordingsScreen (list, search, filter by category/tag)
│   ├── NewRecordingScreen (FAB)
│   │   ├── RecordingInfoSheet  (mode selector, title, memo, tags, category, language)
│   │   └── RecordingControlScreen (start / pause / stop waveform UI)
│   │
│   └── RecordingDetailScreen
│       ├── InfoTab         (metadata, edit)
│       ├── UploadTab       (Drive status, upload/retry)
│       ├── AIProcessTab    (submit job, processing status, retry)
│       └── ResultTab       (transcript + one collapsible section per skill result, copy, share)
│
└── SettingsScreen
    ├── AccountSection          (Firebase user, sign out)
    ├── GoogleDriveSection      (connect/disconnect, target folder)
    ├── ModesSection
    │   ├── ModeListScreen      (all modes, set default)
    │   └── ModeEditScreen      (name, icon, skill multi-select)
    ├── SkillsSection
    │   ├── SkillListScreen     (all saved skills)
    │   └── SkillEditScreen     (structured fields + additional instructions)
    ├── DefaultsSection         (language, category)
    └── NotificationsSection    (toggle)
```

### Key UX Decisions

- **Persistent FAB** on RecordingsScreen — one tap to start recording
- **Mode chip row** in RecordingInfoSheet — one-tap context switch, active mode persists
- **RecordingsList** — minimal cards (title, date, duration, status badge); result preview not shown inline
- **ResultTab** — transcript at top, then one collapsible section per skill result
- **Offline state** — surfaced inline as "waiting for connection" chip; actions not hidden
- **RecordingDetailScreen tabs** — Upload and AI processing are explicit user-controlled steps

---

## 7. Error Handling & Offline Behaviour

### Upload Queue
- `WorkManager` job persists across app restarts and device reboots
- Exponential backoff: 30s → 2m → 10m → manual retry after 3 failures
- Drive token expiry handled silently via refresh; re-auth surfaced only if refresh fails

### AI Job Resilience
- Polling resumes on app foreground for any `processing` jobs
- Max attempts exhausted → job marked `failed` with "Timed out — tap to retry"
- Backend error messages passed through verbatim (internal users benefit from raw errors)

### Recording Safety
- Audio written to temp file during recording; moved to permanent path only on clean stop
- Temp file detected on next launch → offered as recoverable draft
- Background recording via foreground `Service` (Android) + persistent notification / `AVAudioSession` (iOS)

### Auth
- Firebase token refresh transparent via Dio interceptor — retries once on 401 before prompting re-login
- Sign-out clears local DB records for the user's UID; audio files on-device are preserved

---

## 8. Out of Scope for MVP

- Dropbox / OneDrive integration (Google Drive only)
- In-app audio playback of recordings
- Team / multi-user sharing of results
- Fixli orchestrator integration (future AX platform)
- iOS App Store / Google Play submission pipeline
