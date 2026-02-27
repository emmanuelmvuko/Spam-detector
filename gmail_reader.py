from __future__ import annotations

import base64
from email.header import decode_header, make_header

import requests


def _auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def exchange_refresh_token_for_access_token(
    refresh_token: str, client_id: str, client_secret: str
) -> str:
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _get_header(headers: list[dict], name: str) -> str:
    for h in headers or []:
        if h.get("name", "").lower() == name.lower():
            raw = h.get("value", "")
            try:
                return str(make_header(decode_header(raw)))
            except Exception:
                return raw
    return ""


def _extract_plain_text(payload: dict) -> str:
    # Gmail messages are a nested MIME tree
    if not payload:
        return ""
    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {}) or {}

    if mime_type == "text/plain":
        data = body.get("data")
        if not data:
            return ""
        return base64.urlsafe_b64decode(data.encode("utf-8")).decode(errors="ignore")

    parts = payload.get("parts") or []
    for part in parts:
        txt = _extract_plain_text(part)
        if txt:
            return txt
    return ""


def fetch_unread_emails_gmail_api(access_token: str, max_results: int = 25) -> list[dict]:
    """
    Returns a list of dicts:
      { "id": gmail_message_id, "subject": str, "body": str }
    """
    list_resp = requests.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages",
        headers=_auth_headers(access_token),
        params={"q": "is:unread", "maxResults": max_results},
        timeout=30,
    )
    list_resp.raise_for_status()
    message_refs = list_resp.json().get("messages", []) or []

    emails_list: list[dict] = []
    for ref in message_refs:
        msg_id = ref["id"]
        msg_resp = requests.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}",
            headers=_auth_headers(access_token),
            params={"format": "full"},
            timeout=30,
        )
        msg_resp.raise_for_status()
        msg = msg_resp.json()

        headers = (msg.get("payload") or {}).get("headers") or []
        subject = _get_header(headers, "Subject") or "No Subject"
        body = _extract_plain_text(msg.get("payload") or {})

        emails_list.append({"id": msg_id, "subject": subject, "body": body})

    return emails_list


def mark_as_read(access_token: str, gmail_message_id: str) -> None:
    # Remove UNREAD label
    resp = requests.post(
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{gmail_message_id}/modify",
        headers={**_auth_headers(access_token), "Content-Type": "application/json"},
        json={"removeLabelIds": ["UNREAD"]},
        timeout=30,
    )
    resp.raise_for_status()