from __future__ import annotations

import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split

# Make project root importable so "from preprocess import clean_text" works
BASE_DIR = Path(__file__).resolve().parent.parent  # project root (where app.py is)
sys.path.insert(0, str(BASE_DIR))

from preprocess import clean_text  # noqa: E402


DATA_PATH = BASE_DIR / "spam.csv"
MODEL_PATH = BASE_DIR / "spam_model.pkl"
VECTORIZER_PATH = BASE_DIR / "vectorizer.pkl"


def main() -> None:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Could not find dataset at: {DATA_PATH}")

    # Load dataset
    data = pd.read_csv(DATA_PATH, encoding="latin-1")

    # Expect columns: Category, Message
    required_cols = {"Category", "Message"}
    if not required_cols.issubset(set(data.columns)):
        raise ValueError(
            f"spam.csv must contain columns {required_cols}. Found: {set(data.columns)}"
        )

    data = data[["Category", "Message"]].copy()
    data.columns = ["label", "text"]

    # Convert labels
    data["label"] = data["label"].map({"spam": 1, "ham": 0})
    data = data.dropna(subset=["label", "text"]).copy()

    # Clean text
    data["clean_text"] = data["text"].apply(clean_text)

    # Split BEFORE vectorizer fit to avoid leakage
    X_train_text, X_test_text, y_train, y_test = train_test_split(
        data["clean_text"],
        data["label"],
        test_size=0.2,
        random_state=42,
        stratify=data["label"],
    )

    # Vectorization
    vectorizer = TfidfVectorizer(
        max_features=20000,
        ngram_range=(1, 2),
        min_df=2,
    )
    X_train = vectorizer.fit_transform(X_train_text)
    X_test = vectorizer.transform(X_test_text)

    # Train model (probability-capable)
    model = LogisticRegression(
        max_iter=2000,
        class_weight="balanced",
        solver="liblinear",  # reliable for small/medium text problems on Windows
    )
    model.fit(X_train, y_train)

    # Evaluate
    y_pred = model.predict(X_test)
    print("Confusion matrix:\n", confusion_matrix(y_test, y_pred))
    print("\nClassification report:\n", classification_report(y_test, y_pred, digits=4))

    # Save artifacts
    joblib.dump(model, MODEL_PATH)
    joblib.dump(vectorizer, VECTORIZER_PATH)

    print(f"\nSaved model to: {MODEL_PATH}")
    print(f"Saved vectorizer to: {VECTORIZER_PATH}")
    print("\nDone.")


if __name__ == "__main__":
    main()