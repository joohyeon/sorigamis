from __future__ import annotations
import httpx

_MUTATION = """
mutation CreateIssue($title: String!, $description: String, $teamId: String!) {
  issueCreate(input: {title: $title, description: $description, teamId: $teamId}) {
    success
    issue { url }
  }
}
"""


def create_linear_issue(title: str, description: str, team_id: str, api_key: str) -> str:
    try:
        response = httpx.post(
            "https://api.linear.app/graphql",
            json={"query": _MUTATION, "variables": {"title": title, "description": description, "teamId": team_id}},
            headers={"Authorization": api_key},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        return data["data"]["issueCreate"]["issue"]["url"]
    except Exception as exc:
        raise RuntimeError(f"create_linear_issue failed: {exc}") from exc
