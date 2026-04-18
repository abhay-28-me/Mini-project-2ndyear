"""
reset_user.py
-------------
Admin utility to completely remove a user from both the
database and the profiles folder in one command.

Usage:
    python reset_user.py abhay
    python reset_user.py abhay --list    # list all users instead
"""

import sys
import os
import sqlite3

DB_PATH      = os.path.join(os.path.dirname(__file__), "users", "users.db")
PROFILES_DIR = os.path.join(os.path.dirname(__file__), "users", "profiles")


def list_users():
    if not os.path.exists(DB_PATH):
        print("[WARN] Database not found.")
        return

    conn  = sqlite3.connect(DB_PATH)
    rows  = conn.execute("SELECT username, enrolled, n_samples, created_at FROM users").fetchall()
    conn.close()

    if not rows:
        print("No users registered yet.")
        return

    print(f"\n{'Username':<20} {'Enrolled':<10} {'Samples':<10} {'Created'}")
    print("-" * 60)
    for row in rows:
        profile_exists = os.path.exists(os.path.join(PROFILES_DIR, f"{row[0]}.pkl"))
        enrolled_str   = "✓" if row[1] else "✗"
        profile_str    = "✓" if profile_exists else "✗ (missing)"
        print(f"{row[0]:<20} {enrolled_str} / {profile_str:<10} {row[2]:<10} {row[3]}")
    print()


def reset_user(username):
    removed_db      = False
    removed_profile = False

    # 1. Remove from database
    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.execute("DELETE FROM auth_logs WHERE username = ?", (username,))
        conn.commit()
        conn.close()
        if cur.rowcount > 0:
            removed_db = True
            print(f"[DB]      Removed '{username}' from database.")
        else:
            print(f"[DB]      '{username}' not found in database.")
    else:
        print("[WARN] Database not found.")

    # 2. Remove profile .pkl
    safe         = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
    profile_path = os.path.join(PROFILES_DIR, f"{safe}.pkl")
    if os.path.exists(profile_path):
        os.remove(profile_path)
        removed_profile = True
        print(f"[Profile] Removed '{safe}.pkl' from profiles folder.")
    else:
        print(f"[Profile] No profile file found for '{username}'.")

    if removed_db or removed_profile:
        print(f"\n✅ '{username}' fully reset. They can now re-register.")
    else:
        print(f"\n⚠️  '{username}' was not found anywhere — nothing to remove.")


if __name__ == "__main__":
    if len(sys.argv) < 2 or "--list" in sys.argv:
        list_users()
    else:
        username = sys.argv[1].strip()
        print(f"\nResetting user: '{username}'")
        print("-" * 40)
        reset_user(username)