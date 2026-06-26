from __future__ import annotations
import httpx


def call_webhook(url: str, payload: dict) -> None:
    try:
        response = httpx.post(url, json=payload, timeout=15)
        response.raise_for_status()
    except Exception as exc:
        raise RuntimeError(f"call_webhook failed: {exc}") from exc
