from uuid import uuid4

SKILL = {"name": "My Skill", "description": "test", "ai_prompt": "Extract X from transcript."}

def test_create_skill(client, mock_supabase):
    user_id = str(uuid4())
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": str(uuid4()), **SKILL, "is_default": False, "integration_actions": []}
    ]
    # user_id is now required
    response = client.post(f"/skills?user_id={user_id}", json=SKILL)
    assert response.status_code == 201
    assert response.json()["name"] == "My Skill"

def test_create_skill_missing_user_id_is_422(client, mock_supabase):
    """user_id is required for skill creation to prevent orphan rows."""
    response = client.post("/skills", json=SKILL)
    assert response.status_code == 422

def test_list_skills(client, mock_supabase):
    """Without user_id, only default skills are returned."""
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    response = client.get("/skills")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_delete_skill(client, mock_supabase):
    skill_id = str(uuid4())
    owner_id = str(uuid4())
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": skill_id, "is_default": False, "user_id": owner_id}
    ]
    mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value.data = []
    # user_id is now required; must match the skill's owner
    response = client.delete(f"/skills/{skill_id}?user_id={owner_id}")
    assert response.status_code == 204

def test_delete_skill_wrong_owner(client, mock_supabase):
    """Attempting to delete another user's skill returns 403."""
    skill_id = str(uuid4())
    owner_id = str(uuid4())
    other_id = str(uuid4())
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": skill_id, "is_default": False, "user_id": owner_id}
    ]
    response = client.delete(f"/skills/{skill_id}?user_id={other_id}")
    assert response.status_code == 403

def test_update_default_skill_forbidden(client, mock_supabase):
    user_id = str(uuid4())
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "skill-1", "is_default": True, "user_id": None}
    ]
    response = client.put(f"/skills/skill-1?user_id={user_id}", json={"name": "New Name"})
    assert response.status_code == 403

def test_delete_default_skill_forbidden(client, mock_supabase):
    user_id = str(uuid4())
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "skill-1", "is_default": True, "user_id": None}
    ]
    response = client.delete(f"/skills/skill-1?user_id={user_id}")
    assert response.status_code == 403

def test_list_skills_with_user_id(client, mock_supabase):
    valid_user_id = str(uuid4())
    mock_supabase.table.return_value.select.return_value.or_.return_value.execute.return_value.data = []
    response = client.get(f"/skills?user_id={valid_user_id}")
    assert response.status_code == 200


def test_list_skills_invalid_uuid(client, mock_supabase):
    response = client.get("/skills?user_id=not-a-uuid")
    assert response.status_code == 422
