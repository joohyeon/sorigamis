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
