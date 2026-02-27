from __future__ import annotations

from sqlalchemy import Index, UniqueConstraint

from extensions import db


class User(db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)

    gmail_refresh_token_enc = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
        nullable=False,
    )


class ClassifiedMail(db.Model):
    __tablename__ = "classified_mail"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", name="fk_classified_mail_user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user = db.relationship(
        "User",
        backref=db.backref("mails", lazy=True, cascade="all, delete-orphan"),
    )

    gmail_message_id = db.Column(db.String(128), nullable=False)

    subject = db.Column(db.String(255))
    category = db.Column(db.String(50))
    spam_score = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())

    __table_args__ = (
        UniqueConstraint("user_id", "gmail_message_id", name="uq_user_gmail_message"),
        Index("ix_classified_mail_user_timestamp", "user_id", "timestamp"),
    )