# AI Spam Classification System (Gmail UNREAD Inbox Monitor)

A **Flask** web application that connects to one or more **Gmail** accounts using **Google OAuth 2.0**, periodically fetches **UNREAD** emails using the **Gmail API**, classifies them using a **Logistic Regression** machine‑learning model, stores classification results in a local **SQLite** database, and displays results in a clean dashboard with filters, search, counts, and pagination.

> This project is designed for learning/demonstration and local use (localhost). If deploying publicly, review security considerations carefully.

---

## Key Features

- **Multi-account support**: Register multiple users and connect multiple Gmail accounts.
- **Secure OAuth connection**: Stores Gmail **refresh tokens encrypted** (Fernet).
- **Background worker**: Scheduled job runs every `CHECK_INTERVAL_SECONDS` (default: 40s).
- **UNREAD-only fetching**: Pulls emails matching Gmail search query `is:unread`.
- **Promotions support**: Detects Promotions via Gmail label `CATEGORY_PROMOTIONS`.
- **Layered classification policy**:
  - Promotions → Promotions
  - Trusted domain allowlist → Ham
  - OTP heuristic (no URL) → Ham
  - Logistic Regression → Spam/Ham with probability score
- **SQLite dashboard database**: Saves minimal fields needed for reporting.
- **Duplicate prevention**: Unique constraint on `(user_id, gmail_message_id)`.
- **Dashboard UX**:
  - Category filtering (All/Spam/Ham/Promotions)
  - Subject search
  - Pagination (“Load more”)
  - Summary counts + “Last updated” timestamp (displayed in EAT)

---

## Important Behavior (UNREAD-only note)

Because the worker fetches **UNREAD** emails only:

- If you click **Clear Dashboard Data**, the dashboard becomes empty (local DB history deleted).
- The dashboard will remain empty until **new UNREAD emails** arrive and the worker processes them.

This is expected system behavior.

---

## Tech Stack

- **Backend**: Flask
- **DB**: SQLite + SQLAlchemy
- **Migrations**: Flask-Migrate
- **Scheduler**: APScheduler
- **ML**: scikit-learn Logistic Regression + saved artifacts via joblib
- **Security**: cryptography (Fernet) encryption for refresh tokens
- **API**: Gmail API + Google OAuth 2.0
- **HTTP**: requests

---

## Requirements

- **Python**: 3.9+ recommended  
- **Google Cloud OAuth credentials** (Client ID + Client Secret)
- Gmail account(s) to connect (your account must allow OAuth consent)

---

## Dependencies (minimum versions)

```txt
Flask>=2.3
Flask-SQLAlchemy>=3.1
Flask-Migrate>=4.0

pandas>=2.0
scikit-learn>=1.3
joblib>=1.3

cryptography>=42.0
requests>=2.31
APScheduler>=3.10
```

---

## Project Structure

This repository contains a folder named:

- `Spam Detector/` → the actual Python project (web app + worker + model + templates)

Inside `Spam Detector/` you will typically find:

- `app.py` — Flask app factory + config + ML inference (`classify_text`)
- `routes.py` — Dashboard, registration, OAuth connect/callback, preferences, account management
- `worker.py` — Background scheduler + unread sync + classification + DB insert + mark-as-read
- `models.py` — SQLAlchemy models (`User`, `ClassifiedMail`) + constraints/indexes
- `crypto_utils.py` — Fernet encrypt/decrypt helpers for refresh tokens
- `gmail_reader.py` — Gmail API helpers (token exchange, fetch unread, parse subject/body/sender, mark as read)
- `preprocess.py` — text cleaning used by ML inference
- `spam.csv` — dataset used for training (if included)
- `model/train_model.py` — training script (if included)
- `templates/` — HTML templates (dashboard/register/manage accounts)
- `static/` — CSS, images (UI theme)
- `spam_model.pkl`, `vectorizer.pkl` — saved ML artifacts
- `classifier.db` — SQLite DB (created at runtime)
- `requirements.txt` — Python dependencies

---

## Setup (Windows)

Open Command Prompt / PowerShell:

```bat
cd "path\to\repo\Spam Detector"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

---

## Environment Variables

Create a `.env` (or set variables in your terminal) with at least:

```txt
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://127.0.0.1:5000/oauth/gmail/callback
TOKEN_ENCRYPTION_KEY=...  (Fernet key)
CHECK_INTERVAL_SECONDS=40
SPAM_THRESHOLD=0.5
DATABASE_URL=sqlite:///classifier.db   (optional; defaults to local classifier.db)
SECRET_KEY=...           (recommended)
```

### Generate `TOKEN_ENCRYPTION_KEY`
In Python:

```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```

Save the printed value as `TOKEN_ENCRYPTION_KEY`.

> Keep this key secret. If it changes, previously stored encrypted refresh tokens cannot be decrypted.

---

## Train / Retrain the Model (optional)

If your repository includes a training script:

```bat
python model\train_model.py
```

This should generate/update:
- `spam_model.pkl`
- `vectorizer.pkl`

---

## Run the Web App

From inside the `Spam Detector/` folder:

```bat
python app.py
```

Then open:

- http://127.0.0.1:5000

---

## Run the Worker (Background Email Sync)

In a second terminal:

```bat
run_worker.bat
```

Or directly:

```bat
python worker.py
```

The worker:
- decrypts each user’s refresh token,
- exchanges refresh→access token,
- fetches **UNREAD** emails,
- classifies + stores results,
- marks emails as read.

---

## How to Connect Gmail (OAuth 2.0)

1. Open the web app.
2. Click **Connect New Account** and register a user email (local DB).
3. Go to **Manage Accounts**.
4. Click **Connect Gmail** for that user.
5. Complete Google consent.

After connection, the worker will start processing UNREAD emails for that account.

---

## Database Records Saved (Minimal Fields)

The system stores only reporting fields in `ClassifiedMail`:

- `user_id`
- `gmail_message_id`
- `subject`
- `category` (Spam/Ham/Promotions)
- `spam_score` (Spam probability, when ML used)
- `timestamp`

> Email body is used during processing but is typically not stored in DB.

---

## Troubleshooting

### 1) `invalid_grant: Token has been expired or revoked`
- Reconnect Gmail for the affected user in **Manage Accounts**.
- Ensure your OAuth app is still valid and credentials are correct.
- If your OAuth consent is in **Testing**, refresh tokens may expire sooner; consider publishing or keeping test users updated.

### 2) SSL errors / network errors when calling Gmail API
- Check network stability (VPN/proxy/antivirus HTTPS scanning can cause TLS drops).
- Add retry logic in `gmail_reader.py` if needed.

### 3) Dashboard is empty after clearing
- Expected: dashboard history is deleted and worker fetches **UNREAD** only.
- Send a new email and keep it UNREAD, then wait for the worker interval.

---

## Security Notes (important)

- Refresh tokens are stored encrypted using Fernet, but **environment variables/secrets must be protected**.
- Do not commit `.env`, OAuth secrets, or encryption keys to GitHub.
- If deploying beyond localhost, add authentication and follow secure deployment practices.

---

## Next Improvements (ideas)

- Add “Backfill last N emails” option (read + unread) to repopulate after clearing.
- Add robust retry/backoff for Gmail API calls.
- Add user authentication (login) for the dashboard if deployed publicly.
- Add charts: spam rate over time, trend lines.
- Add feedback buttons (“Mark as Spam/Ham”) for continuous improvement and retraining.
- Add automated tests + CI workflow.

---