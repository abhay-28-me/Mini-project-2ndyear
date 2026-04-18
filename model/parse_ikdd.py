"""
parse_ikdd.py  (IMPROVED)
-------------
Parses IKDD .txt files and extracts a rich 30-feature vector.

Feature groups:
  1. Dwell stats        s  — 7 features
  2. Flight stats       (mean, std, min, max, median, p25, p75)  — 7 features
  3. Top-5 digraph means (most-used key pairs)                   — 5 features
  4. Top-5 digraph stds                                          — 5 features
  5. Derived / rhythm   (dwell/flight ratio, typing speed,f
                          dwell CV, flight CV, IQR dwell,
                          IQR flight)                            — 6 features
                                                          TOTAL = 30
"""

import os
import numpy as np

N_FEATURES = 30          # keep in sync with extract_features()
TOP_K_DIGRAPHS = 5       # how many most-used digraphs to include


# ── Parser ────────────────────────────────────────────────────────────────────

def parse_user_file(filepath):
    """
    Parse one IKDD user file.
    Returns dict:
      {
        "dwell":    [float, ...],          # all dwell values (key-code-0 rows)
        "flight":   [float, ...],          # all digraph values pooled
        "digraphs": { "A-B": [float,...] } # per-pair flight times
      }
    """
    all_dwell  = []
    all_flight = []
    digraphs   = {}

    try:
        with open(filepath, "r", errors="ignore") as f:
            for line in f:
                line = line.strip().rstrip("\r")
                if not line:
                    continue

                parts    = line.split(",")
                key_part = parts[0].strip()

                # Skip header (no dash in key descriptor)
                if "-" not in key_part:
                    continue

                dash_idx = key_part.rfind("-")
                y_code   = key_part[dash_idx + 1:]
                x_code   = key_part[:dash_idx]

                # Parse numeric values only
                values = []
                for v in parts[1:]:
                    v = v.strip()
                    if v:
                        try:
                            values.append(float(v))
                        except ValueError:
                            continue

                if not values:
                    continue

                if y_code == "0":
                    # Dwell row
                    all_dwell.extend(values)
                else:
                    # Digraph / flight row
                    all_flight.extend(values)
                    pair_key = f"{x_code}-{y_code}"
                    digraphs.setdefault(pair_key, []).extend(values)

    except Exception as e:
        print(f"[WARN] Could not parse {filepath}: {e}")
        return None

    if len(all_dwell) < 5:
        return None

    return {
        "dwell":    all_dwell,
        "flight":   all_flight,
        "digraphs": digraphs,
    }


# ── Feature extraction ────────────────────────────────────────────────────────

def _safe_stats(arr):
    """Return (mean, std, min, max, median, p25, p75) for a 1-D array."""
    if len(arr) == 0:
        return (0.0,) * 7
    a = np.array(arr, dtype=float)
    return (
        float(np.mean(a)),
        float(np.std(a)),
        float(np.min(a)),
        float(np.max(a)),
        float(np.median(a)),
        float(np.percentile(a, 25)),
        float(np.percentile(a, 75)),
    )


def extract_features(sample):
    """
    Build a 30-D feature vector from a parsed sample dict.
    """
    dwell    = sample.get("dwell",    [])
    flight   = sample.get("flight",  [])
    digraphs = sample.get("digraphs", {})

    # Group 1 — dwell stats (7)
    d_stats = _safe_stats(dwell)

    # Group 2 — flight stats (7)
    f_stats = _safe_stats(flight)

    # Group 3 & 4 — top-K digraph means + stds (5+5=10)
    # Sort digraphs by number of observations (most data = most reliable)
    sorted_pairs = sorted(digraphs.items(), key=lambda kv: len(kv[1]), reverse=True)
    dg_means = []
    dg_stds  = []
    for _, vals in sorted_pairs[:TOP_K_DIGRAPHS]:
        a = np.array(vals, dtype=float)
        dg_means.append(float(np.mean(a)))
        dg_stds.append(float(np.std(a)))
    # Pad if fewer than TOP_K digraphs present
    while len(dg_means) < TOP_K_DIGRAPHS:
        dg_means.append(0.0)
        dg_stds.append(0.0)

    # Group 5 — derived rhythm features (6)
    d_mean, d_std = d_stats[0], d_stats[1]
    f_mean, f_std = f_stats[0], f_stats[1]
    d_iqr = d_stats[6] - d_stats[5]   # p75 - p25 dwell
    f_iqr = f_stats[6] - f_stats[5]   # p75 - p25 flight

    dwell_cv  = d_std / (d_mean + 1e-6)     # coefficient of variation
    flight_cv = f_std / (f_mean + 1e-6)
    df_ratio  = d_mean / (f_mean + 1e-6)
    n_keys    = float(len(dwell))

    derived = [df_ratio, n_keys, dwell_cv, flight_cv, d_iqr, f_iqr]

    features = list(d_stats) + list(f_stats) + dg_means + dg_stds + derived
    assert len(features) == N_FEATURES, f"Expected {N_FEATURES} features, got {len(features)}"
    return np.array(features, dtype=float)


# ── Dataset loader ────────────────────────────────────────────────────────────

def load_ikdd_dataset(data_dir):
    """
    Load all IKDD .txt files from data_dir.
    Returns X (N×30), y (N,) labels, user_ids list.
    """
    X, y, user_ids = [], [], []

    if not os.path.exists(data_dir):
        print(f"[ERROR] Data directory not found: {data_dir}")
        return np.array([]), np.array([]), []

    files = [f for f in os.listdir(data_dir) if f.endswith(".txt")]
    if not files:
        print(f"[WARN] No .txt files found in {data_dir}")
        return np.array([]), np.array([]), []

    print(f"[INFO] Found {len(files)} user files in {data_dir}")

    for fname in sorted(files):
        user_id  = fname.replace(".txt", "")
        base_id  = user_id.split("_(")[0] if "_(" in user_id else user_id
        filepath = os.path.join(data_dir, fname)

        sample = parse_user_file(filepath)
        if sample is None:
            print(f"  -> Skipped {user_id} (no usable data)")
            continue

        feat = extract_features(sample)
        X.append(feat)
        y.append(base_id)

        if base_id not in user_ids:
            user_ids.append(base_id)

        print(f"  -> Loaded {user_id} | dwell={len(sample['dwell'])} "
              f"flight={len(sample['flight'])} digraphs={len(sample['digraphs'])}")

    return np.array(X), np.array(y), user_ids


# ── Live browser input ────────────────────────────────────────────────────────

def extract_features_from_raw(timing_data):
    """
    Extract features from live browser keystroke data.

    timing_data expected keys:
      "dwell"    : [int, ...]   milliseconds each key was held
      "flight"   : [int, ...]   milliseconds between key-up and next key-down
      "digraphs" : { "A-B": [int, ...] }  (optional, per-pair flight times)

    Returns numpy array shape (1, 30).
    """
    sample = {
        "dwell":    [float(v) for v in timing_data.get("dwell",  [])],
        "flight":   [float(v) for v in timing_data.get("flight", [])],
        "digraphs": {k: [float(x) for x in v]
                     for k, v in timing_data.get("digraphs", {}).items()},
    }
    return extract_features(sample).reshape(1, -1)