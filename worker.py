import logging
import re
import time
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.exc import IntegrityError

from app import classify_text, create_app
from crypto_utils import decrypt_token
from extensions import db
from gmail_reader import (
    exchange_refresh_token_for_access_token,
    fetch_unread_emails_gmail_api,
    mark_as_read,
)
from models import ClassifiedMail, User

logger = logging.getLogger(__name__)

# =========================
# Trusted sender allowlist (domain-based)
# =========================
TRUSTED_DOMAINS = {
    "google.com",
    "accounts.google.com",
    "microsoft.com",
    "amazon.com",
    "equitybank.co.ke",
    "kcbgroup.com",
    "icealion.co.ke",
    "icealion.com",  # covers unit-trusts@icealion.com
    "digitrust.co.ke",
    "safaricom.co.ke",
}

# =========================
# OTP heuristics (after allowlist, before ML)
# =========================
OTP_REGEX = re.compile(r"\b(\d{4,8})\b")  # common OTP lengths: 4-8 digits
OTP_KEYWORDS = (
    "one time password",
    "otp",
    "verification code",
    "security code",
    "authentication code",
    "login code",
    "sign-in code",
    "2-step verification",
    "two-step verification",
)


def looks_like_otp(subject: str, body: str) -> bool:
    text = f"{subject}\n{body}".lower()
    return bool(any(k in text for k in OTP_KEYWORDS) and OTP_REGEX.search(text))


def contains_url(subject: str, body: str) -> bool:
    """
    A simple phishing guard: if an OTP-like email contains a URL,
    we avoid auto-allowing it as Ham and let ML decide.
    """
    text = f"{subject}\n{body}".lower()
    return ("http://" in text) or ("https://" in text) or ("www." in text)


def extract_domain(sender: str) -> str:
    """
    Extract domain from sender header. Examples:
    - 'Google <no-reply@google.com>' -> 'google.com'
    - 'unit-trusts@icealion.com' -> 'icealion.com'

    Security note:
    We do NOT trust display names; we only use the actual email domain.
    """
    sender = (sender or "").strip().lower()

    # If it contains <...>, keep what's inside; otherwise keep as-is
    if "<" in sender and ">" in sender:
        sender = sender.split("<", 1)[1].split(">", 1)[0].strip()

    if "@" in sender:
        return sender.split("@", 1)[1].strip().lower().replace(">", "")
    return ""


# =========================
# Classification policy
# =========================
def categorize_email(
    app,
    sender: str,
    subject: str,
    body: str,
    gmail_label_ids: list[str],
) -> tuple[str, float | None]:
    """
    Decide the final category for the dashboard.

    Order of decision (layered, production-grade):
    1) Promotions label (CATEGORY_PROMOTIONS) -> Promotions
    2) Trusted sender domain allowlist -> Ham (skip ML)
    3) OTP heuristic (no URL) -> Ham (skip ML)
    4) ML classifier -> Spam/Ham (spam_score = probability of spam)

    Returns: (category, spam_score)
    """
    # 1) Promotions tab
    if "CATEGORY_PROMOTIONS" in (gmail_label_ids or []):
        return "Promotions", None

    # 2) Trusted domains (fast + high impact)
    domain = extract_domain(sender)
    if domain in TRUSTED_DOMAINS:
        return "Ham", 0.0

    # 3) OTP heuristic: allow only if it doesn't contain a URL
    if looks_like_otp(subject, body) and not contains_url(subject, body):
        return "Ham", 0.0

    # 4) ML classification
    spam_threshold = float(app.config.get("SPAM_THRESHOLD", 0.5))

    # Include sender + subject + body. Sender is extremely predictive.
    text = f"From: {sender}\nSubject: {subject}\n\n{body}".strip()

    category, spam_score = classify_text(text, spam_threshold)  # Spam/Ham + probability
    return category, spam_score


# =========================
# Single-user sync
# =========================
def sync_user(app, user: User) -> None:
    """
    Sync unread emails for a single connected Gmail user:
    - decrypt refresh token
    - get access token
    - fetch unread messages
    - categorize (Promotions via label OR allowlist/OTP OR ML)
    - store results in SQLite
    - mark each message as read
    """
    client_id = app.config.get("GOOGLE_CLIENT_ID", "")
    client_secret = app.config.get("GOOGLE_CLIENT_SECRET", "")
    token_key = app.config.get("TOKEN_ENCRYPTION_KEY", "")

    if not user.gmail_refresh_token_enc:
        logger.info("No refresh token for %s; skipping", user.email)
        return

    # Helpful config diagnostics (safe to print)
    logger.info("Config: GOOGLE_CLIENT_ID prefix=%s", (client_id or "")[:10])
    logger.info("Config: TOKEN_ENCRYPTION_KEY length=%s", len(token_key or ""))

    # 1) Gmail OAuth: refresh -> access token
    refresh_token = decrypt_token(user.gmail_refresh_token_enc, token_key)

    # Refresh token diagnostics (do NOT print the full token)
    logger.info(
        "Decrypted refresh token: prefix=%r len=%s",
        (refresh_token or "")[:3],
        len(refresh_token or ""),
    )

    try:
        access_token = exchange_refresh_token_for_access_token(
            refresh_token, client_id, client_secret
        )
    except Exception as ex:
        # If Google returns invalid_grant, user must reconnect Gmail.
        msg = str(ex)
        if "invalid_grant" in msg or "Token has been expired or revoked" in msg:
            logger.error(
                "Refresh token invalid for %s. Reconnect Gmail in Manage Accounts.",
                user.email,
            )
            return
        raise

    # 2) Fetch unread emails
    emails = fetch_unread_emails_gmail_api(access_token, max_results=25)
    logger.info("Fetched %d unread emails for %s", len(emails), user.email)

    inserted = 0
    for e in emails:
        gmail_message_id = e["id"]
        subject = e.get("subject", "") or "No Subject"
        body = e.get("body", "") or ""
        sender = e.get("sender", "") or ""
        label_ids = e.get("labelIds") or []

        # 3) Decide category (Promotions vs allowlist/OTP vs ML)
        category, spam_score = categorize_email(app, sender, subject, body, label_ids)

        # 4) Store in DB (Unique constraint prevents duplicates)
        row = ClassifiedMail(
            user_id=user.id,
            gmail_message_id=gmail_message_id,
            subject=subject,
            category=category,
            spam_score=spam_score,
            # Store as UTC so timestamps are consistent across machines
            timestamp=datetime.now(timezone.utc),
        )
        db.session.add(row)

        try:
            db.session.commit()
            inserted += 1
        except IntegrityError:
            # Already stored this gmail_message_id for this user
            db.session.rollback()
            logger.info(
                "Duplicate message skipped: %s (%s)", gmail_message_id, user.email
            )
        except Exception:
            db.session.rollback()
            raise

        # 5) Mark as read to avoid re-processing next run
        try:
            mark_as_read(access_token, gmail_message_id)
        except Exception as ex:
            logger.warning("Failed to mark as read (id=%s): %s", gmail_message_id, ex)

    logger.info("Inserted %d new rows for %s", inserted, user.email)


# =========================
# Multi-user sync entrypoint (scheduled)
# =========================
def sync_all_users(app) -> None:
    """
    Sync unread emails for all connected users.
    Runs inside Flask app context because it uses DB models and config.
    """
    with app.app_context():
        users = User.query.all()
        logger.info("Users in DB: %d", len(users))

        for u in users:
            logger.info(
                "User id=%s email=%s has_refresh_token=%s",
                u.id,
                u.email,
                bool(u.gmail_refresh_token_enc),
            )

        for u in users:
            if not u.gmail_refresh_token_enc:
                continue
            try:
                sync_user(app, u)
            except Exception:
                logger.exception("Sync failed for user id=%s email=%s", u.id, u.email)


# =========================
# Worker process main loop
# =========================
def main() -> None:
    """
    Start APScheduler and keep the worker alive indefinitely.
    """
    logging.basicConfig(level=logging.INFO)

    app = create_app()
    logger.info("DB URI: %s", app.config.get("SQLALCHEMY_DATABASE_URI"))

    interval = int(app.config.get("CHECK_INTERVAL_SECONDS", 40))

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=lambda: sync_all_users(app),
        trigger="interval",
        seconds=interval,
        # Make behavior nicer if a run overlaps: coalesce missed runs into one
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()

    logger.info("Worker started. Sync interval=%ss", interval)

    try:
        while True:
            time.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    main()