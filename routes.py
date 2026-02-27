import secrets
from urllib.parse import urlencode

import requests
from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

from extensions import db
from crypto_utils import encrypt_token
from models import ClassifiedMail, User

bp = Blueprint("routes", __name__)


@bp.route("/")
def dashboard():
    history = ClassifiedMail.query.order_by(ClassifiedMail.id.desc()).limit(50).all()
    return render_template("dashboard.html", history=history)


@bp.route("/register", methods=["GET", "POST"])
def register():
    # Register just stores the email; OAuth connects Gmail later.
    if request.method == "POST":
        email_addr = request.form.get("email")

        if email_addr and not User.query.filter_by(email=email_addr).first():
            db.session.add(User(email=email_addr))
            db.session.commit()

        # After registering, send them to manage_accounts to click Connect Gmail
        return redirect(url_for("routes.manage_accounts"))

    return render_template("register.html")


@bp.route("/oauth/gmail/start/<int:user_id>")
def gmail_oauth_start(user_id: int):
    user = User.query.get_or_404(user_id)

    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state
    session["oauth_user_id"] = user.id
    
      # ✅ DEBUG PRINT
    print("GOOGLE_REDIRECT_URI =", current_app.config.get("GOOGLE_REDIRECT_URI"))

    params = {
        "client_id": current_app.config["GOOGLE_CLIENT_ID"],
        "redirect_uri": current_app.config["GOOGLE_REDIRECT_URI"],
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.modify",
        "access_type": "offline",
        "prompt": "consent",  # ensure refresh token is issued
        "state": state,
        "login_hint": user.email,
    }
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))


@bp.route("/oauth/gmail/callback")
def gmail_oauth_callback():
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

    user = User.query.get_or_404(user_id)
    user.gmail_refresh_token_enc = encrypt_token(
        refresh_token, current_app.config["TOKEN_ENCRYPTION_KEY"]
    )
    db.session.commit()

    return redirect(url_for("routes.manage_accounts"))


@bp.route("/manage_accounts")
def manage_accounts():
    users = User.query.all()
    return render_template("manage_accounts.html", users=users)


@bp.route("/delete_user/<int:user_id>", methods=["POST"])
def delete_user(user_id):
    user_to_delete = User.query.get_or_404(user_id)
    try:
        db.session.delete(user_to_delete)
        db.session.commit()
        return redirect(url_for("routes.manage_accounts"))
    except Exception as e:
        db.session.rollback()
        return f"There was a problem deleting that account: {e}"
       