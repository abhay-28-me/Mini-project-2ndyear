"""
enroll.py  (Z-SCORE ONLY — CLEAN & SIMPLE)
---------
Two-layer authentication with continuous learning.

┌─────────────────────────────────────────────────────────────────┐
│  LAYER 1 — Base Model Gate (IKDD-trained RF, trained once)      │
│    Checks: "Does this look like a human typing at all?"         │
│    → Rejects bots / random inputs immediately                   │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 2 — Personal Z-score Profile                             │
│    Checks: "Is this close to THIS user's enrolled pattern?"     │
│    → Compares each feature against enrolled mean ± std          │
│    → Updates automatically after every successful login         │
└─────────────────────────────────────────────────────────────────┘

ADAPTIVE THRESHOLD:
  Z-score threshold tightens automatically as more samples accumulate:
    0-15  samples → 2.5  (lenient, still learning)
    16-30 samples → 2.0
    31-50 samples → 1.8
    50+   samples → 1.5  (tight, well-trained)

CONTINUOUS LEARNING:
  After every successful login, update_profile():
    1. Adds the new genuine sample (rolling window of 100)
    2. Recomputes mean and std per feature
    3. Tightens the threshold automatically
"""

import os, sys, joblib
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from model.parse_ikdd import extract_features_from_raw

PROFILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "users", "profiles")
MODEL_DIR    = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH   = os.path.join(MODEL_DIR, "base_model.pkl")
SCALER_PATH  = os.path.join(MODEL_DIR, "scaler.pkl")
os.makedirs(PROFILES_DIR, exist_ok=True)

# ── Thresholds ─────────────────────────────────────────────────────────────────
BASE_THRESHOLD = 0.25
MIN_CONFIDENCE = 60.0

ADAPTIVE_THRESHOLDS = [
    (50, 1.5),
    (31, 1.8),
    (16, 2.0),
    (0,  2.5),
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_profile_path(username):
    safe = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
    return os.path.join(PROFILES_DIR, f"{safe}.pkl")


def _load_base_model():
    if os.path.exists(MODEL_PATH) and os.path.exists(SCALER_PATH):
        try:
            return joblib.load(MODEL_PATH), joblib.load(SCALER_PATH)
        except Exception as e:
            print(f"[WARN] Could not load base model: {e}")
    return None, None


def _adaptive_threshold(n_samples):
    for min_n, thresh in ADAPTIVE_THRESHOLDS:
        if n_samples >= min_n:
            return thresh
    return 2.5


# ── Enrollment ─────────────────────────────────────────────────────────────────

def enroll_user(username, timing_samples):
    """Build the initial profile from registration samples (min 5)."""
    if len(timing_samples) < 5:
        return {"success": False, "message": "Need at least 5 typing samples."}

    X         = np.array([extract_features_from_raw(s)[0] for s in timing_samples])
    n_samples = len(X)
    mean      = np.mean(X, axis=0)
    std       = np.std(X,  axis=0)
    std       = np.where(std < 1e-6, 1e-6, std)
    thresh    = _adaptive_threshold(n_samples)

    profile = {
        "username":    username,
        "mean":        mean,
        "std":         std,
        "n_samples":   n_samples,
        "X_enroll":    X,
        "threshold":   thresh,
        "base_thresh": BASE_THRESHOLD,
    }
    joblib.dump(profile, _get_profile_path(username))

    return {
        "success": True,
        "message": f"Enrolled with {n_samples} samples. Threshold={thresh}.",
    }


# ── Authentication ─────────────────────────────────────────────────────────────

def authenticate_user(username, timing_sample):
    """
    Two-layer authentication: base model gate + Z-score.
    Returns: authenticated, confidence, message, n_samples
    """
    profile_path = _get_profile_path(username)
    if not os.path.exists(profile_path):
        return {
            "authenticated": False,
            "confidence":    0.0,
            "message":       "User not enrolled. Please register first.",
        }

    profile = joblib.load(profile_path)
    feat    = extract_features_from_raw(timing_sample)[0]

    # ── Layer 1: Base model gate ───────────────────────────────────────────
    clf, base_scaler = _load_base_model()
    base_prob = 0.5

    if clf is not None:
        try:
            base_prob = float(
                clf.predict_proba(base_scaler.transform(feat.reshape(1, -1)))[0][1]
            )
        except Exception as e:
            print(f"[WARN] Base model error: {e}")

    if base_prob < profile.get("base_thresh", BASE_THRESHOLD):
        return {
            "authenticated": False,
            "confidence":    round(base_prob * 100, 1),
            "message":       "Authentication failed. Typing pattern not recognised.",
        }

    # ── Layer 2: Z-score ───────────────────────────────────────────────────
    mean   = profile["mean"]
    std    = profile["std"]
    thresh = profile.get("threshold", _adaptive_threshold(profile["n_samples"]))

    z_scores = np.abs((feat - mean) / std)
    avg_z    = float(np.mean(z_scores))

    authenticated = avg_z <= thresh

    # Confidence: avg_z=0 → 100%, avg_z=thresh → ~65%, avg_z=thresh*1.5 → ~33%
    profile_score = float(np.clip(1.0 - (avg_z / (thresh * 1.5)), 0, 1))
    confidence    = round(profile_score * 100, 1)

    # Minimum confidence gate
    if authenticated and confidence < MIN_CONFIDENCE:
        authenticated = False

    if authenticated:
        return {
            "authenticated": True,
            "confidence":    confidence,
            "message":       "Authentication successful! Welcome back.",
            "n_samples":     profile["n_samples"],
        }
    else:
        if confidence < MIN_CONFIDENCE:
            msg = "Authentication failed. Typing pattern did not match closely enough."
        else:
            msg = "Authentication failed. Typing rhythm is too different from your enrolled pattern."
        return {
            "authenticated": False,
            "confidence":    confidence,
            "message":       msg,
            "n_samples":     profile["n_samples"],
        }


# ── Continuous learning ────────────────────────────────────────────────────────

def update_profile(username, new_timing_sample):
    """
    Called after every successful login. Adds the new genuine sample,
    recomputes mean/std, and tightens threshold as data grows.
    """
    profile_path = _get_profile_path(username)
    if not os.path.exists(profile_path):
        return False

    profile  = joblib.load(profile_path)
    feat     = extract_features_from_raw(new_timing_sample)[0]

    X_enroll = np.vstack([profile["X_enroll"], feat])
    if len(X_enroll) > 100:
        X_enroll = X_enroll[-100:]
    n_samples = len(X_enroll)

    mean   = np.mean(X_enroll, axis=0)
    std    = np.std(X_enroll,  axis=0)
    std    = np.where(std < 1e-6, 1e-6, std)
    thresh = _adaptive_threshold(n_samples)

    profile.update({
        "mean":      mean,
        "std":       std,
        "n_samples": n_samples,
        "X_enroll":  X_enroll,
        "threshold": thresh,
    })
    joblib.dump(profile, profile_path)
    print(f"[CL] '{username}' updated: n={n_samples}, threshold={thresh}")
    return True


# ── Utility ────────────────────────────────────────────────────────────────────

def get_profile_status(username):
    """Returns learning progress for the dashboard."""
    profile_path = _get_profile_path(username)
    if not os.path.exists(profile_path):
        return None

    profile = joblib.load(profile_path)
    n       = profile["n_samples"]
    thresh  = profile.get("threshold", _adaptive_threshold(n))

    next_milestone = None
    for min_n, t in sorted(ADAPTIVE_THRESHOLDS, key=lambda x: x[0]):
        if n < min_n:
            next_milestone = (min_n, t)
            break

    return {
        "n_samples":       n,
        "threshold":       thresh,
        "method":          "Z-score",
        "next_threshold":  next_milestone[1] if next_milestone else thresh,
        "next_at":         next_milestone[0] if next_milestone else None,
        "samples_to_next": (next_milestone[0] - n) if next_milestone else 0,
    }


def user_exists(username):
    return os.path.exists(_get_profile_path(username))


def list_users():
    return sorted(
        f.replace(".pkl", "")
        for f in os.listdir(PROFILES_DIR)
        if f.endswith(".pkl")
    )