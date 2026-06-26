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
