from __future__ import annotations

import base64
from email.header import decode_header, make_header

import requests


# =========================
# Auth helpers
# =========================
def _auth_headers(access_token: str) -> dict[str, str]:
    """Attach OAuth2 bearer token to every Gmail API request."""
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

    #  debug section
    if not resp.ok:
        print("Token exchange failed:")
        print("Status:", resp.status_code)
        print("Body:", resp.text)  # <-- THIS will say invalid_client/invalid_grant etc.

    resp.raise_for_status()
    return resp.json()["access_token"]


# =========================
# Message parsing helpers
# =========================
def _get_header(headers: list[dict], name: str) -> str:
    """
    Extract a header (like Subject) from Gmail's message headers list,
    and decode RFC2047 encoding safely.
    """
    for h in headers or []:
        if h.get("name", "").lower() == name.lower():
            raw = h.get("value", "")
            try:
                return str(make_header(decode_header(raw)))
            except Exception:
                return raw
    return ""


def _extract_sender(headers: list[dict]) -> str:
    # "From" header often looks like: 'Google <no-reply@google.com>'
    return _get_header(headers, "From") or ""


def _extract_plain_text(payload: dict) -> str:
    """
    Extract the first text/plain part from Gmail's nested MIME payload.
    Falls back to empty string if none exists.
    """
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


# =========================
# Gmail API: fetch messages
# =========================
def fetch_unread_emails_gmail_api(access_token: str, max_results: int = 25) -> list[dict]:
    """
    Fetch unread Gmail messages and return normalized dicts:

      {
        "id": gmail_message_id,
        "subject": str,
        "body": str,
        "sender": str,
        "labelIds": list[str]   <-- used to detect Promotions
      }
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

        # NOTE: labelIds includes CATEGORY_PROMOTIONS for Promotions tab messages
        label_ids = msg.get("labelIds") or []

        headers = (msg.get("payload") or {}).get("headers") or []
        subject = _get_header(headers, "Subject") or "No Subject"
        sender = _extract_sender(headers)
        body = _extract_plain_text(msg.get("payload") or {})

        emails_list.append(
            {
                "id": msg_id,
                "subject": subject,
                "body": body,
                "sender": sender,
                "labelIds": label_ids,
            }
        )

    return emails_list


# =========================
# Gmail API: mark as read
# =========================
def mark_as_read(access_token: str, gmail_message_id: str) -> None:
    """
    Remove the UNREAD label from a Gmail message.
    This prevents re-processing the same message on the next poll.
    """
    resp = requests.post(
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{gmail_message_id}/modify",
        headers={**_auth_headers(access_token), "Content-Type": "application/json"},
        json={"removeLabelIds": ["UNREAD"]},
        timeout=30,
    )
    resp.raise_for_status()