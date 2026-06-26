---
name: sg-skill-action-items
description: Extract action items and owners from a transcript.
---

# sg-skill-action-items

Extract all action items from the transcript. For each item identify the task and the owner (speaker name if mentioned, null otherwise).

Return ONLY valid JSON — no prose, no markdown fences:
[{"text": "...", "owner": "..." or null}]
