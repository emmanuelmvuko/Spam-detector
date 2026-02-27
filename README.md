# Spam Detector (Gmail Inbox Monitor)

A Flask web app that connects to one or more Gmail accounts (via IMAP), monitors unread emails, and classifies them as **Spam** or **Ham** using a machine‑learning model.

## Features
- Connect multiple Gmail accounts (stores them in a local SQLite database)
- Background monitoring: checks for **unread** messages periodically
- Classifies each email and displays results in a dashboard
- Training script to retrain the model on the included dataset (`spam.csv`)

---

## Project structure (important)
This repository contains a folder named:

- `Spam Detector/` → the actual Python project (app + model + templates)

Inside `Spam Detector/` you will find:
- `app.py` — Flask application
- `gmail_reader.py` — IMAP email fetching
- `preprocess.py` — text cleaning
- `spam.csv` — training dataset
- `model/train_model.py` — training script
- `templates/` — HTML templates
- `spam_model.pkl`, `vectorizer.pkl` — saved ML artifacts
- `requirements.txt` — Python dependencies

---

## Requirements
- Python 3.9+ recommended
- A Gmail account with **2‑Step Verification enabled** and a **Gmail App Password** (IMAP)

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

## Train / Retrain the model
From inside the `Spam Detector/` folder:

```bat
python model\train_model.py
```

This will generate/update:
- `spam_model.pkl`
- `vectorizer.pkl`

---

## Run the web app
From inside the `Spam Detector/` folder:

```bat
python app.py
```

Then open:
- http://127.0.0.1:5000

---

## Connect a Gmail account (App Password)
For Gmail IMAP access, **do not use your normal password**.

1. Enable 2‑Step Verification in your Google account
2. Create an **App Password** (16 characters)
3. In the web app, click **Connect New Account**
4. Enter:
   - Gmail address (example@gmail.com)
   - The generated App Password

The app will monitor unread emails and classify them.

---

## Notes / Limitations
- The app uses IMAP and requires Gmail IMAP access.
- The SQLite database is local (`classifier.db`).
- **Security warning:** the app password handling should be improved (encrypt at rest). Do not deploy this as‑is to a public server without securing credentials.

---

## Troubleshooting
### 1) “Authentication failed”
- Ensure you are using an **App Password**, not your normal password.
- Confirm IMAP access is enabled in Gmail settings (if applicable).
- Confirm 2‑Step Verification is enabled before creating App Password.

### 2) It classifies the same email repeatedly
- Ensure `gmail_reader.py` marks processed emails as **Seen** after classification.

---

## Next improvements (planned)
- Encrypt stored app passwords
- Add duplicate protection using message UID
- Add confidence score display (Spam probability)
- Add JSON API endpoint for predictions
- Add tests + CI (GitHub Actions)