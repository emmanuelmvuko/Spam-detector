"""
routes.py
=========
Flask routes (endpoints) for:
- Dashboard UI (filters, search, pagination)
- Promotions handling toggle (UI preference)
- "Clear dashboard data" (reset detected emails stored in app DB)
- Local-time display (EAT) while storing UTC in DB
- Account registration + OAuth connect flow
- Manage/remove accounts


"""

import secrets
from datetime import timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo  # Python 3.9+ built-in timezones

import requests
from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from crypto_utils import encrypt_token
from extensions import db
from models import ClassifiedMail, User

bp = Blueprint("routes", __name__)

# =============================================================================
# Dashboard settings / UX helpers
# =============================================================================

# Allowed categories for filtering in the dashboard.
# We include Promotions because we now support it as a first-class category.
ALLOWED_CATEGORIES = {"Spam", "Ham", "Promotions"}

# We will display times in EAT (Kenya/Uganda/Tanzania time).
# This keeps the UI consistent for our location even if DB stores UTC.
EAT_TZ = ZoneInfo("Africa/Nairobi")


def _get_promotions_as_ham_pref() -> bool:
    """
    Read the user's UI preference:
    - If True: dashboard will DISPLAY Promotions as Ham (UX choice).
    - If False: dashboard will display Promotions normally.

    NOTE:
    This does NOT change what the worker stores in the database.
    It only changes what the dashboard shows.
    """
    return bool(session.get("promotions_as_ham", False))


def _set_promotions_as_ham_pref(value: bool) -> None:
    """Persist the user's preference in their session cookie."""
    session["promotions_as_ham"] = bool(value)


def _display_category(db_category: str, promotions_as_ham: bool) -> str:
    """
    Decide what category label to show in the UI.
    - If user preference says "treat promotions as ham", show Ham.
    - Otherwise, show original category.
    """
    if promotions_as_ham and db_category == "Promotions":
        return "Ham"
    return db_category


def _to_eat(dt):
    """
    Convert a datetime to EAT for display.

    Why this exists:
    - SQLite often stores "naive" datetimes (no tzinfo).
    - Our worker stores UTC.
    - This function makes sure the dashboard always shows EAT (local time).
    """
    if not dt:
        return None

    # If naive datetime, assume it is UTC then convert.
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).astimezone(EAT_TZ)

    # If already tz-aware, just convert.
    return dt.astimezone(EAT_TZ)


# =============================================================================
# Dashboard (filters + search + pagination + last updated)
# =============================================================================

@bp.route("/")
def dashboard():
    """
    Dashboard page:
    - Server-side category filter (All/Spam/Ham/Promotions)
    - Subject search query
    - Pagination ("Load more")
    - Summary counts (for the whole DB, not just the current page)
    - Shows a "last updated" time based on latest ClassifiedMail timestamp
    - Adds display-friendly fields (display_category, display_timestamp)
    """

    # ----------------------------
    # Read query-string parameters
    # ----------------------------
    category = request.args.get("category", "All")  # All, Spam, Ham, Promotions
    q = (request.args.get("q") or "").strip()       # subject search
    page = int(request.args.get("page", "1"))       # pagination
    per_page = int(request.args.get("per_page", "25"))

    # Bound per_page to a safe range so the DB doesn't get hammered
    per_page = max(10, min(per_page, 100))

    # ----------------------------
    # Build base query
    # ----------------------------
    query = ClassifiedMail.query

    # Filter by category if requested and valid
    if category != "All":
        if category in ALLOWED_CATEGORIES:
            query = query.filter(ClassifiedMail.category == category)
        else:
            # If an invalid category is provided, fall back to All.
            category = "All"

    # Filter by subject search if provided
    if q:
        # SQLite ILIKE is supported via SQLAlchemy using .ilike
        query = query.filter(ClassifiedMail.subject.ilike(f"%{q}%"))

    # Sort newest first
    query = query.order_by(ClassifiedMail.id.desc())

    # ----------------------------
    # Pagination
    # ----------------------------
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    history = pagination.items

    # ----------------------------
    # Summary counts (whole DB)
    # These are shown in the dashboard UX cards.
    # ----------------------------
    total_count = ClassifiedMail.query.count()
    spam_count = ClassifiedMail.query.filter(ClassifiedMail.category == "Spam").count()
    ham_count = ClassifiedMail.query.filter(ClassifiedMail.category == "Ham").count()
    promotions_count = ClassifiedMail.query.filter(ClassifiedMail.category == "Promotions").count()

    # ----------------------------
    # "Last updated" time (heartbeat)
    # If the worker has inserted anything, we show latest timestamp.
    # Convert to EAT for display.
    # ----------------------------
    latest_mail = ClassifiedMail.query.order_by(ClassifiedMail.timestamp.desc()).first()
    last_updated = _to_eat(latest_mail.timestamp) if latest_mail else None

    # ----------------------------
    # Promotions-as-ham preference (UI-only)
    # ----------------------------
    promotions_as_ham = _get_promotions_as_ham_pref()

    # ----------------------------
    # Add display-only fields used by templates:
    # - display_category: respects promotions-as-ham toggle
    # - display_timestamp: shows EAT time in UI
    # ----------------------------
    for m in history:
        m.display_category = _display_category(m.category, promotions_as_ham)
        m.display_timestamp = _to_eat(m.timestamp)

    return render_template(
        "dashboard.html",
        history=history,

        # current filters
        category=category,
        q=q,
        page=page,
        per_page=per_page,

        # pagination info
        has_next=pagination.has_next,
        has_prev=pagination.has_prev,
        next_page=pagination.next_num if pagination.has_next else None,
        prev_page=pagination.prev_num if pagination.has_prev else None,

        # summary info
        total_count=total_count,
        spam_count=spam_count,
        ham_count=ham_count,
        promotions_count=promotions_count,
        last_updated=last_updated,

        # user preference
        promotions_as_ham=promotions_as_ham,
    )


@bp.route("/dashboard/clear", methods=["POST"])
def clear_dashboard_data():
    """
    Clears the app's stored classification history (classified_mail table).
    This is a "refresh everything" button for the dashboard.

    IMPORTANT:
    - This does NOT delete any Gmail emails.
    - It only deletes rows saved in your local SQLite database.

    Use cases:
    - You cleared your Gmail inbox but still see old entries.
    - You want to demo the system from a clean slate.
    """
    try:
        ClassifiedMail.query.delete()
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return f"Failed to clear dashboard data: {e}", 500

    return redirect(url_for("routes.dashboard"))


@bp.route("/preferences/promotions_as_ham", methods=["POST"])
def set_promotions_as_ham():
    """
    Toggle endpoint for the dashboard preference:
    - If checked: show Promotions items as Ham in the dashboard.
    - Stored in session, no DB changes.
    """
    enabled = request.form.get("enabled") == "on"
    _set_promotions_as_ham_pref(enabled)

    # Redirect back to dashboard, preserving current filters if possible
    return redirect(url_for("routes.dashboard", **request.args))


# =============================================================================
# Account registration + OAuth (Gmail connect)
# =============================================================================

@bp.route("/register", methods=["GET", "POST"])
def register():
    """
    Register page:
    - User enters email into our app DB
    - Then they connect Gmail via OAuth in Manage Accounts
    """
    if request.method == "POST":
        email_addr = (request.form.get("email") or "").strip()

        # Create user only if it doesn't already exist
        if email_addr and not User.query.filter_by(email=email_addr).first():
            db.session.add(User(email=email_addr))
            db.session.commit()

        return redirect(url_for("routes.manage_accounts"))

    return render_template("register.html")


@bp.route("/oauth/gmail/start/<int:user_id>")
def gmail_oauth_start(user_id: int):
    """
    Start the Gmail OAuth flow for a selected user.
    We store state + user_id in session to validate callback safely.
    """
    user = User.query.get_or_404(user_id)

    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state
    session["oauth_user_id"] = user.id

    # Scopes:
    # - gmail.readonly: read email content
    # - gmail.modify: remove UNREAD label after processing
    params = {
        "client_id": current_app.config["GOOGLE_CLIENT_ID"],
        "redirect_uri": current_app.config["GOOGLE_REDIRECT_URI"],
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.modify",
        "access_type": "offline",
        "prompt": "consent",  # ensures refresh token is returned
        "state": state,
        "login_hint": user.email,
    }
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))


@bp.route("/oauth/gmail/callback")
def gmail_oauth_callback():
    """
    OAuth callback:
    - Verify state (protects against CSRF)
    - Exchange code for tokens
    - Store refresh token encrypted in DB
    """
    if request.args.get("state") != session.get("oauth_state"):
        return "Invalid OAuth state", 400

    code = request.args.get("code")
    user_id = session.get("oauth_user_id")
    if not code or not user_id:
        return "Missing code or user context", 400

    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": current_app.config["GOOGLE_CLIENT_ID"],
        "client_secret": current_app.config["GOOGLE_CLIENT_SECRET"],
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": current_app.config["GOOGLE_REDIRECT_URI"],
    }
    resp = requests.post(token_url, data=data, timeout=30)
    resp.raise_for_status()
    token_payload = resp.json()

    refresh_token = token_payload.get("refresh_token")
    if not refresh_token:
        return (
            "No refresh_token received. Try again and ensure prompt=consent, access_type=offline.",
            400,
        )

    # Store encrypted refresh token
    user = User.query.get_or_404(user_id)
    user.gmail_refresh_token_enc = encrypt_token(
        refresh_token, current_app.config["TOKEN_ENCRYPTION_KEY"]
    )
    db.session.commit()

    return redirect(url_for("routes.manage_accounts"))


# =============================================================================
# Manage accounts + delete user
# =============================================================================

@bp.route("/manage_accounts")
def manage_accounts():
    """
    Manage Accounts page:
    - List all users registered in the app
    - Show whether Gmail is connected (refresh token exists)
    - Provide "Connect Gmail" link that starts OAuth
    - Provide remove button
    """
    users = User.query.all()
    return render_template("manage_accounts.html", users=users)


@bp.route("/delete_user/<int:user_id>", methods=["POST"])
def delete_user(user_id):
    """
    Remove a user and their associated mail history.
    Due to the DB relationship cascade, deleting a user also deletes their mails.
    """
    user_to_delete = User.query.get_or_404(user_id)
    try:
        db.session.delete(user_to_delete)
        db.session.commit()
        return redirect(url_for("routes.manage_accounts"))
    except Exception as e:
        db.session.rollback()
        return f"There was a problem deleting that account: {e}"