import os
from pathlib import Path

import joblib
from flask import Flask

import preprocess
from extensions import db, migrate

BASE_DIR = Path(__file__).resolve().parent

model = None
vectorizer = None


def create_app():
    global model, vectorizer

    app = Flask(__name__)

    default_db_path = BASE_DIR / "classifier.db"
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL", f"sqlite:///{default_db_path.as_posix()}"
    )
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", " ")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    app.config["CHECK_INTERVAL_SECONDS"] = int(os.getenv("CHECK_INTERVAL_SECONDS", "40"))
    app.config["SPAM_THRESHOLD"] = float(os.getenv("SPAM_THRESHOLD", "0.5"))

    app.config["GOOGLE_CLIENT_ID"] = os.getenv("GOOGLE_CLIENT_ID", "")
    app.config["GOOGLE_CLIENT_SECRET"] = os.getenv("GOOGLE_CLIENT_SECRET", "")
    app.config["GOOGLE_REDIRECT_URI"] = os.getenv("GOOGLE_REDIRECT_URI", "")
    app.config["TOKEN_ENCRYPTION_KEY"] = os.getenv("TOKEN_ENCRYPTION_KEY", "")

    db.init_app(app)
    migrate.init_app(app, db)

    if model is None:
        model = joblib.load(BASE_DIR / "spam_model.pkl")
    if vectorizer is None:
        vectorizer = joblib.load(BASE_DIR / "vectorizer.pkl")

    import models  # noqa: F401

    from routes import bp as routes_bp
    app.register_blueprint(routes_bp)

    return app


def classify_text(text: str, spam_threshold: float) -> tuple[str, float]:
    clean = preprocess.clean_text(text)
    vec = vectorizer.transform([clean])
    proba_spam = float(model.predict_proba(vec)[0][1])
    category = "Spam" if proba_spam >= spam_threshold else "Ham"
    return category, proba_spam


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, use_reloader=False)