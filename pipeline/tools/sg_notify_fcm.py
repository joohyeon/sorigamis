from __future__ import annotations
import httpx

FCM_URL = "https://fcm.googleapis.com/fcm/send"


def send_fcm(device_token: str, title: str, body: str, server_key: str) -> None:
    payload = {
        "to": device_token,
        "notification": {"title": title, "body": body},
        "data": {"title": title, "body": body},
    }
    headers = {"Authorization": f"key={server_key}", "Content-Type": "application/json"}
    response = httpx.post(FCM_URL, json=payload, headers=headers, timeout=10)
    response.raise_for_status()
