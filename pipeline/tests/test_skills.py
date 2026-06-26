from uuid import uuid4

SKILL = {"name": "My Skill", "description": "test", "ai_prompt": "Extract X from transcript."}

def test_create_skill(client, mock_supabase):
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": str(uuid4()), **SKILL, "is_default": False, "integration_actions": []}
    ]
    response = client.post("/skills", json=SKILL)
    assert response.status_code == 201
    assert response.json()["name"] == "My Skill"

def test_list_skills(client, mock_supabase):
    mock_supabase.table.return_value.select.return_value.execute.return_value.data = []
    response = client.get("/skills")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_delete_skill(client, mock_supabase):
    mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value.data = []
    response = client.delete(f"/skills/{uuid4()}")
    assert response.status_code == 204
