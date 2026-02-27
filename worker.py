import logging
import time

from apscheduler.schedulers.background import BackgroundScheduler
from flask import current_app

import gmail_reader
from app import classify_text, create_app, db
from crypto_utils import decrypt_token
from models import ClassifiedMail, User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")


def sync_all_users():
    app = current_app._get_current_object()
    with app.app_context():
        users = User.query.all()
        for user in users:
            if not user.gmail_refresh_token_enc:
                continue

            try:
                refresh_token = decrypt_token(
                    user.gmail_refresh_token_enc, app.config["TOKEN_ENCRYPTION_KEY"]
                )
                access_token = gmail_reader.exchange_refresh_token_for_access_token(
                    refresh_token,
                    app.config["GOOGLE_CLIENT_ID"],
                    app.config["GOOGLE_CLIENT_SECRET"],
                )

                new_mails = gmail_reader.fetch_unread_emails_gmail_api(access_token)

                for mail in new_mails:
                    gmail_message_id = mail["id"]

                    # Dedup guard (DB unique constraint is the ultimate guard)
                    exists = ClassifiedMail.query.filter_by(
                        user_id=user.id, gmail_message_id=gmail_message_id
                    ).first()
                    if exists:
                        gmail_reader.mark_as_read(access_token, gmail_message_id)
                        continue

                    category, score = classify_text(
                        mail.get("body", ""), spam_threshold=app.config["SPAM_THRESHOLD"]
                    )
                    db.session.add(
                        ClassifiedMail(
                            user_id=user.id,
                            gmail_message_id=gmail_message_id,
                            subject=mail.get("subject", "No Subject"),
                            category=category,
                            spam_score=score,
                        )
                    )
                    db.session.commit()

                    gmail_reader.mark_as_read(access_token, gmail_message_id)

            except Exception:
                db.session.rollback()
                logger.exception("Failed syncing user %s", user.email)


def main():
    app = create_app()
    interval = app.config["CHECK_INTERVAL_SECONDS"]

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=lambda: sync_all_users(),
        trigger="interval",
        seconds=interval,
        id="sync_all_users",
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    logger.info("Worker started. Sync interval=%ss", interval)

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        scheduler.shutdown()


if __name__ == "__main__":
    main()