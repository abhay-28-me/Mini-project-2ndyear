"""
database.py
-----------
SQLite database helper for storing user accounts
and enrollment metadata.
"""

import sqlite3
import os
import hashlib
import secrets

DB_PATH = os.path.join(os.path.dirname(__file__), "users", "users.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    UNIQUE NOT NULL,
            password_hash TEXT    NOT NULL,
            salt          TEXT    NOT NULL,
            enrolled      INTEGER DEFAULT 0,
            n_samples     INTEGER DEFAULT 0,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auth_logs (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            username       TEXT    NOT NULL,
            authenticated  INTEGER NOT NULL,
            confidence     REAL,
            failure_type   TEXT    DEFAULT NULL,
            timestamp      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Add failure_type column if upgrading from older schema
    try:
        cursor.execute("ALTER TABLE auth_logs ADD COLUMN failure_type TEXT DEFAULT NULL")
        conn.commit()
    except Exception:
        pass   # column already exists

    conn.commit()
    conn.close()


def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256((password + salt).encode()).hexdigest()
    return hashed, salt


def create_user(username, password):
    """Create a new user. Returns (success, message)."""
    conn = get_connection()
    try:
        hashed, salt = hash_password(password)
        conn.execute(
            "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
            (username, hashed, salt)
        )
        conn.commit()
        return True, "User created successfully."
    except sqlite3.IntegrityError:
        return False, "Username already exists."
    finally:
        conn.close()


def verify_password(username, password):
    """Verify a user's password."""
    conn = get_connection()
    row = conn.execute(
        "SELECT password_hash, salt FROM users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()

    if not row:
        return False

    hashed, _ = hash_password(password, row["salt"])
    return hashed == row["password_hash"]


def get_user(username):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def mark_enrolled(username, n_samples):
    conn = get_connection()
    conn.execute(
        "UPDATE users SET enrolled = 1, n_samples = ? WHERE username = ?",
        (n_samples, username)
    )
    conn.commit()
    conn.close()


def log_auth_attempt(username, authenticated, confidence, failure_type=None):
    conn = get_connection()
    conn.execute(
        "INSERT INTO auth_logs (username, authenticated, confidence, failure_type) VALUES (?, ?, ?, ?)",
        (username, int(authenticated), confidence, failure_type)
    )
    conn.commit()
    conn.close()


def delete_user(username):
    """Remove a user and their auth logs — used for registration rollback."""
    conn = get_connection()
    conn.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.execute("DELETE FROM auth_logs WHERE username = ?", (username,))
    conn.commit()
    conn.close()


def get_auth_history(username, limit=10):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM auth_logs WHERE username = ? ORDER BY timestamp DESC LIMIT ?",
        (username, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def is_locked_out(username):
    """
    Only locks out on PASSWORD failures — not keystroke failures.
    A legitimate user whose typing pattern varies won't get locked out.
    An imposter guessing passwords will.
    """
    conn = get_connection()
    recent_password_fails = conn.execute("""
        SELECT COUNT(*) FROM auth_logs
        WHERE username = ?
          AND authenticated = 0
          AND failure_type = 'password'
          AND timestamp > datetime('now', '-5 minutes')
    """, (username,)).fetchone()[0]
    conn.close()
    return recent_password_fails >= 5


def get_lockout_remaining(username):
    import datetime
    conn = get_connection()
    row  = conn.execute("""
        SELECT timestamp FROM auth_logs
        WHERE username = ?
          AND authenticated = 0
          AND failure_type = 'password'
        ORDER BY timestamp DESC
        LIMIT 1
    """, (username,)).fetchone()
    conn.close()

    if not row:
        return 0

    last_fail     = datetime.datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
    lockout_until = last_fail + datetime.timedelta(minutes=5)
    remaining     = (lockout_until - datetime.datetime.utcnow()).total_seconds()
    return max(0, int(remaining))


# Auto-initialize on import
init_db()