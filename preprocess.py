import re

_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_EMAIL_RE = re.compile(r"\b[\w\.-]+@[\w\.-]+\.\w+\b")
_NON_WORD_RE = re.compile(r"[^a-z0-9\s]+")

def clean_text(text: str) -> str:
    if text is None:
        return ""

    text = str(text).lower()
    text = _URL_RE.sub(" url ", text)
    text = _EMAIL_RE.sub(" email ", text)
    text = re.sub(r"\d+", " number ", text)
    text = _NON_WORD_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text