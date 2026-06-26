from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from models import CreateSkillRequest, UpdateSkillRequest
from supabase_client import get_supabase
from uuid import UUID as _UUID

router = APIRouter(prefix="/skills", tags=["skills"])


def _validate_uuid(val: str | None, param: str) -> None:
    if val is None:
        return
    try:
        _UUID(val)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid UUID for {param}")


@router.get("")
def list_skills(user_id: str | None = None, db=Depends(get_supabase)):
    """When user_id is provided, return default + user-owned skills.
    When omitted, return only is_default=true skills to prevent cross-user exposure."""
    _validate_uuid(user_id, "user_id")
    if user_id:
        result = db.table("sg_skills").select("*").or_(f"is_default.eq.true,user_id.eq.{user_id}").execute()
    else:
        result = db.table("sg_skills").select("*").eq("is_default", True).execute()
    return result.data

@router.post("", status_code=201)
def create_skill(body: CreateSkillRequest, user_id: str, db=Depends(get_supabase)):
    """Create a user-owned skill. user_id is required to prevent orphan rows
    (user_id NULL + is_default False) that cannot be modified or deleted later."""
    _validate_uuid(user_id, "user_id")
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
def update_skill(skill_id: str, body: UpdateSkillRequest, user_id: str, db=Depends(get_supabase)):
    """Update a user-owned skill. user_id is required for ownership verification (IDOR prevention)."""
    _validate_uuid(user_id, "user_id")
    check = db.table("sg_skills").select("id, is_default, user_id").eq("id", skill_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Skill not found")
    skill = check.data[0]
    if skill.get("is_default") or skill.get("user_id") is None:
        raise HTTPException(status_code=403, detail="Cannot modify default skills")
    if str(skill.get("user_id")) != user_id:
        raise HTTPException(status_code=403, detail="Not your skill")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    result = db.table("sg_skills").update(updates).eq("id", skill_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Skill not found")
    return result.data[0]

@router.delete("/{skill_id}", status_code=204)
def delete_skill(skill_id: str, user_id: str, db=Depends(get_supabase)):
    """Delete a user-owned skill. user_id is required for ownership verification (IDOR prevention)."""
    _validate_uuid(user_id, "user_id")
    check = db.table("sg_skills").select("id, is_default, user_id").eq("id", skill_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Skill not found")
    skill = check.data[0]
    if skill.get("is_default") or skill.get("user_id") is None:
        raise HTTPException(status_code=403, detail="Cannot modify default skills")
    if str(skill.get("user_id")) != user_id:
        raise HTTPException(status_code=403, detail="Not your skill")
    db.table("sg_skills").delete().eq("id", skill_id).execute()
