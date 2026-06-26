from __future__ import annotations
import httpx


def post_slack(channel: str, text: str, token: str) -> None:
    try:
        response = httpx.post(
            "https://slack.com/api/chat.postMessage",
            json={"channel": channel, "text": text},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack error: {data.get('error')}")
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"post_slack failed: {exc}") from exc
