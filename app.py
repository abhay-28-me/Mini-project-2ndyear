"""
app.py
------
Main Flask application for Keystroke Dynamics Authentication.

Routes:
  GET  /              → Landing page
  GET  /register      → Registration page
  GET  /login         → Login page
  GET  /dashboard     → Dashboard (post-auth)
  POST /api/register  → Register user + enroll keystroke profile
  POST /api/login     → Authenticate user
  GET  /api/history   → Get auth history for a user
"""

import os
import sys

# Ensure model/ is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, jsonify, session, redirect, url_for

# Flask-Limiter is optional — works locally and on Render but may not be
# available on all platforms. Gracefully fall back to no rate limiting.
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    LIMITER_AVAILABLE = True
except ImportError:
    LIMITER_AVAILABLE = False
    print("[WARN] flask_limiter not available — rate limiting disabled.")
from database import (
    create_user, verify_password, get_user,
    mark_enrolled, log_auth_attempt, get_auth_history,
    is_locked_out, get_lockout_remaining
)
from model.enroll import enroll_user, authenticate_user, user_exists, update_profile

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "keystroke-auth-dev-secret-2024")

# ── Rate limiter ───────────────────────────────────────────────────────────────
if LIMITER_AVAILABLE:
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=[],
        storage_uri="memory://",
    )
else:
    # Dummy limiter that does nothing
    class _NoopLimiter:
        def limit(self, *args, **kwargs):
            def decorator(f): return f
            return decorator
    limiter = _NoopLimiter()


# ── Page routes ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register")
def register_page():
    return render_template("register.html")


@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if not session.get("authenticated"):
        return redirect(url_for("login_page"))
    return render_template("dashboard.html")


# ── API routes ─────────────────────────────────────────────────────────────────

@app.route("/api/check-username", methods=["POST"])
@limiter.limit("20 per minute")
def api_check_username():
    """
    Check if a username is available before the user starts enrollment.
    Body: { username }
    """
    data     = request.get_json()
    username = (data.get("username") or "").strip()

    if not username or len(username) < 3:
        return jsonify({"available": False, "message": "Username must be at least 3 characters."})

    if len(username) > 32:
        return jsonify({"available": False, "message": "Username must be 32 characters or fewer."})

    if not username.replace("_", "").replace("-", "").isalnum():
        return jsonify({"available": False, "message": "Only letters, numbers, - and _ allowed."})

    exists = get_user(username) is not None or user_exists(username)
    if exists:
        return jsonify({"available": False, "message": f'Username "{username}" is already taken. Please choose another.'})

    return jsonify({"available": True, "message": f'"{username}" is available!'})
@limiter.limit("5 per hour")   # max 5 registration attempts per IP per hour
def api_register():
    """
    Register a new user and enroll their keystroke profile.
    Body: { username, password, samples: [{dwell, flight}, ...] }
    """
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "Invalid request."}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "")
    samples  = data.get("samples", [])

    # Validate inputs
    if not username or len(username) < 3:
        return jsonify({"success": False, "message": "Username must be at least 3 characters."})

    if not password or len(password) < 4:
        return jsonify({"success": False, "message": "Password must be at least 4 characters."})

    if len(samples) < 5:
        return jsonify({"success": False, "message": "Need at least 5 keystroke samples."})

    # Create user in DB
    ok, msg = create_user(username, password)
    if not ok:
        return jsonify({"success": False, "message": msg})

    # Enroll keystroke profile
    result = enroll_user(username, samples)
    if not result["success"]:
        # Roll back — remove the DB entry so the username doesn't get stuck
        from database import delete_user
        delete_user(username)
        return jsonify(result)

    mark_enrolled(username, len(samples))

    return jsonify({
        "success": True,
        "message": f"Registered and enrolled with {len(samples)} samples!"
    })


@app.route("/api/login", methods=["POST"])
@limiter.limit("10 per minute")   # max 10 login attempts per IP per minute
def api_login():
    """
    Authenticate a user via password + keystroke dynamics.
    Body: { username, password, timing: {dwell, flight} }
    """
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "Invalid request."}), 400

    username   = data.get("username", "").strip()
    password   = data.get("password", "")
    timing     = data.get("timing", {})

    # Step 0: Check if account is locked out
    if is_locked_out(username):
        secs = get_lockout_remaining(username)
        mins = secs // 60
        return jsonify({
            "success": False,
            "message": f"Account temporarily locked due to too many failed attempts. "
                       f"Try again in {mins}m {secs % 60}s."
        })

    # Step 1: Verify password
    if not verify_password(username, password):
        log_auth_attempt(username, False, 0.0)
        return jsonify({"success": False, "message": "Incorrect username or password."})

    # Step 2: Check enrollment
    if not user_exists(username):
        return jsonify({"success": False, "message": "User not enrolled. Please register first."})

    # Step 3: Verify keystroke pattern
    result = authenticate_user(username, timing)
    log_auth_attempt(username, result["authenticated"], result["confidence"])

    if result["authenticated"]:
        # Set server-side session — dashboard is now gated on this
        session["user"]          = username
        session["authenticated"] = True
        session["confidence"]    = result["confidence"]
        update_profile(username, timing)
        return jsonify({
            "success":    True,
            "confidence": result["confidence"],
            "message":    result["message"]
        })
    else:
        return jsonify({
            "success": False,
            "message": result["message"] + f" (confidence: {result['confidence']}%)"
        })


@app.route("/api/history")
def api_history():
    """Return authentication history — only for the logged-in user."""
    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401
    username = session["user"]
    history  = get_auth_history(username, limit=10)
    return jsonify({"history": history})


@app.route("/api/me")
def api_me():
    """Return session data for the dashboard to use instead of URL params."""
    if not session.get("authenticated"):
        return jsonify({"authenticated": False}), 401
    return jsonify({
        "authenticated": True,
        "username":      session["user"],
        "confidence":    session.get("confidence", 0),
    })


@app.route("/api/status")
def api_status():
    """Return the continuous learning status for the logged-in user's profile."""
    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401
    from model.enroll import get_profile_status
    status = get_profile_status(session["user"])
    return jsonify(status or {})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    """Clear the session."""
    session.clear()
    return jsonify({"success": True})


# ── Run ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  KeyAuth running on http://localhost:{port}\n")
    app.run(debug=True, host="0.0.0.0", port=port)