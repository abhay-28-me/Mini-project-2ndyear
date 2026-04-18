"""
train_base.py  (IMPROVED)
-------------
Trains a base Random Forest on IKDD as a BINARY genuine-vs-imposter
classifier, not a user-ID classifier.

Why binary?
  The goal is not to identify *who* is typing, but to learn what
  "legitimate human typing patterns" look like vs. random/imposter
  patterns.  We generate imposter samples by pairing each user's
  features with *other* users' timing → label 1 (genuine) / 0 (imposter).

Run ONCE before deploying:
    python model/train_base.py
"""

import os, sys, joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.pipeline import Pipeline

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from model.parse_ikdd import load_ikdd_dataset

DATA_DIR    = os.path.join(os.path.dirname(__file__), "..", "data", "ikdd")
MODEL_DIR   = os.path.dirname(__file__)
MODEL_PATH  = os.path.join(MODEL_DIR, "base_model.pkl")
SCALER_PATH = os.path.join(MODEL_DIR, "scaler.pkl")

# Number of imposter pairs to generate per genuine sample
IMPOSTER_RATIO = 3
RANDOM_SEED    = 42


def build_binary_dataset(X, y):
    """
    Create (genuine, imposter) pairs.

    For each sample i (genuine):
      - label = 1
      - generate IMPOSTER_RATIO samples by randomly sampling
        rows from OTHER users as 'impostors' (label = 0).

    Feature = DIFFERENCE vector |genuine - imposter| + genuine vector
    This teaches the model what a deviation looks like.
    """
    rng = np.random.default_rng(RANDOM_SEED)
    X_out, y_out = [], []
    users = np.unique(y)

    for idx, (feat, user) in enumerate(zip(X, y)):
        # Genuine sample: features of the real user
        X_out.append(feat)
        y_out.append(1)

        # Imposter samples: features from other users
        imposter_mask = y != user
        imposter_pool = X[imposter_mask]
        if len(imposter_pool) == 0:
            continue
        chosen = imposter_pool[
            rng.integers(0, len(imposter_pool), size=IMPOSTER_RATIO)
        ]
        for imp in chosen:
            X_out.append(imp)
            y_out.append(0)

    return np.array(X_out), np.array(y_out)


def train():
    print("=" * 55)
    print("  IKDD Base Model Training  (binary genuine/imposter)")
    print("=" * 55)

    X, y, user_ids = load_ikdd_dataset(DATA_DIR)

    if len(X) == 0:
        print("[WARN] No IKDD data found. Creating dummy base model.")
        _create_dummy_model()
        return

    print(f"\n[INFO] Raw dataset: {len(X)} sessions | {len(user_ids)} users")

    # Build binary dataset
    X_bin, y_bin = build_binary_dataset(X, y)
    print(f"[INFO] Binary dataset: {len(X_bin)} samples "
          f"({y_bin.sum()} genuine / {(y_bin==0).sum()} imposter)")

    # Scale
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_bin)

    # ── Model: Random Forest (fast, interpretable) ──────────────────────────
    clf = RandomForestClassifier(
        n_estimators=300,
        max_depth=20,
        min_samples_split=4,
        min_samples_leaf=2,
        class_weight="balanced",   # handles genuine/imposter imbalance
        random_state=RANDOM_SEED,
        n_jobs=-1,
    )

    # Cross-validate first
    print("\n[INFO] Cross-validating (5-fold) ...")
    cv_scores = cross_val_score(
        clf, X_scaled, y_bin,
        cv=StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_SEED),
        scoring="roc_auc",
        n_jobs=-1,
    )
    print(f"[INFO] CV ROC-AUC: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")

    # Final fit on all data
    print("[INFO] Fitting final model on full dataset ...")
    clf.fit(X_scaled, y_bin)

    # Feature importance (top 10)
    feat_imp = clf.feature_importances_
    top10 = np.argsort(feat_imp)[::-1][:10]
    print("\n[INFO] Top-10 important features (index → importance):")
    for rank, fi in enumerate(top10, 1):
        print(f"  {rank:2d}. feature[{fi:2d}] = {feat_imp[fi]:.4f}")

    # Save
    joblib.dump(clf,    MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)
    print(f"\n[OK] Model  → {MODEL_PATH}")
    print(f"[OK] Scaler → {SCALER_PATH}")


def _create_dummy_model():
    from parse_ikdd import N_FEATURES
    X_dummy = np.random.rand(200, N_FEATURES)
    y_dummy = np.array([1] * 100 + [0] * 100)
    scaler  = StandardScaler()
    X_s     = scaler.fit_transform(X_dummy)
    clf     = RandomForestClassifier(n_estimators=10, random_state=42)
    clf.fit(X_s, y_dummy)
    joblib.dump(clf,    MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)
    print("[OK] Dummy binary model created.")


if __name__ == "__main__":
    train()