import os
import sqlite3
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "data", "listings.db")

# Default admin account, only ever created once (the very first time the
# app runs and no admin exists yet). Override via environment variables
# so the real credentials never have to live in source control.
DEFAULT_ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Creates the listings/users tables if they don't exist yet, runs
    small migrations for older databases, and seeds sample data + a
    default admin account the very first time (empty tables only)."""
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)

    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('applicant', 'admin')),
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            type TEXT NOT NULL,
            location TEXT NOT NULL,
            skills TEXT NOT NULL,
            posted_at TEXT NOT NULL,
            updated_at TEXT,
            posted_by INTEGER REFERENCES users(id)
        )
        """
    )
    conn.commit()

    # Migration: older databases created before logins existed won't
    # have a posted_by column yet -- add it without losing existing data.
    existing_cols = [row[1] for row in conn.execute("PRAGMA table_info(listings)").fetchall()]
    if "posted_by" not in existing_cols:
        conn.execute("ALTER TABLE listings ADD COLUMN posted_by INTEGER REFERENCES users(id)")
        conn.commit()
    if "status" not in existing_cols:
        conn.execute("ALTER TABLE listings ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
        conn.commit()
    if "start_date" not in existing_cols:
        conn.execute("ALTER TABLE listings ADD COLUMN start_date TEXT")
        conn.commit()

    # Migration: security question/answer for self-serve password reset.
    existing_user_cols = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "security_question" not in existing_user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN security_question TEXT")
        conn.commit()
    if "security_answer_hash" not in existing_user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN security_answer_hash TEXT")
        conn.commit()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()

    # Migration: older databases created before read/unread tracking
    # existed won't have this column yet.
    existing_notif_cols = [row[1] for row in conn.execute("PRAGMA table_info(notifications)").fetchall()]
    if "is_read" not in existing_notif_cols:
        conn.execute("ALTER TABLE notifications ADD COLUMN is_read INTEGER NOT NULL DEFAULT 0")
        conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    if count == 0:
        _seed_sample_data(conn)

    admin_exists = conn.execute("SELECT 1 FROM users WHERE role = 'admin' LIMIT 1").fetchone()
    if not admin_exists:
        _seed_default_admin(conn)

    conn.close()


def _seed_default_admin(conn: sqlite3.Connection) -> None:
    """Creates one admin account on first run only. Change the password
    right away (or set ADMIN_USERNAME / ADMIN_PASSWORD before the first
    run) -- this default is meant for local/demo use only."""
    conn.execute(
        "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, 'admin', ?)",
        (
            DEFAULT_ADMIN_USERNAME,
            generate_password_hash(DEFAULT_ADMIN_PASSWORD),
            datetime.now().strftime("%b %d, %Y %I:%M %p"),
        ),
    )
    conn.commit()


def _seed_sample_data(conn: sqlite3.Connection) -> None:
    samples = [
        ("Web Development Intern", "BrightPath Solutions", "Internship", "Iloilo City",
         "HTML CSS JavaScript React frontend web development responsive design git"),
        ("Data Analyst Intern", "Insight Analytics PH", "Internship", "Remote",
         "python pandas excel data analysis sql visualization statistics reporting"),
        ("Junior Backend Developer", "NimbusTech", "Full-time", "Iloilo City",
         "python flask django rest api database sql backend development git"),
        ("IT Support Intern", "Janiuay Municipal Office", "Internship", "Janiuay, Iloilo",
         "troubleshooting hardware networking customer service windows technical support documentation"),
        ("Mobile App Developer Intern", "AppCraft Studios", "Internship", "Remote",
         "java kotlin android mobile development ui ux flutter dart git"),
        ("Machine Learning Intern", "DataForge AI", "Internship", "Remote",
         "python machine learning scikit-learn pandas numpy data preprocessing model training"),
        ("Graphic Design Intern", "Creative Hive Studio", "Internship", "Iloilo City",
         "photoshop illustrator canva graphic design branding layout creativity"),
        ("QA Testing Intern", "NimbusTech", "Internship", "Iloilo City",
         "software testing bug tracking manual testing test cases quality assurance documentation"),
        ("Remote Software Engineer Intern", "Global Nexus Tech (Singapore)", "Internship",
         "International, Remote (Asia-Pacific)",
         "python javascript react node api rest git agile remote collaboration"),
    ]

    base = datetime(2026, 8, 1, 9, 0)
    for i, (title, company, jtype, location, skills) in enumerate(samples):
        posted_at = (base + timedelta(days=i)).strftime("%b %d, %Y %I:%M %p")
        conn.execute(
            "INSERT INTO listings (title, company, type, location, skills, posted_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (title, company, jtype, location, skills, posted_at),
        )
    conn.commit()


_LISTINGS_WITH_AUTHOR = """
    SELECT listings.*, users.username AS posted_by_username
    FROM listings
    LEFT JOIN users ON users.id = listings.posted_by
"""


def get_all_listings() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(_LISTINGS_WITH_AUTHOR + " ORDER BY listings.id").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_listings_by_user(user_id: int) -> list[dict]:
    """Only the listings a given applicant posted -- used by the
    Applicant Dashboard so each logged-in user manages just their own."""
    conn = get_connection()
    rows = conn.execute(
        _LISTINGS_WITH_AUTHOR + " WHERE listings.posted_by = ? ORDER BY listings.id DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_listing(listing_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        _LISTINGS_WITH_AUTHOR + " WHERE listings.id = ?", (listing_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def insert_listing(data: dict) -> dict:
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO listings (title, company, type, location, skills, posted_at, posted_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (data["title"], data["company"], data["type"], data["location"],
         data["skills"], data["posted_at"], data.get("posted_by")),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return get_listing(new_id)


def update_listing(listing_id: int, data: dict) -> dict | None:
    conn = get_connection()
    cursor = conn.execute(
        "UPDATE listings SET title = ?, company = ?, type = ?, location = ?, "
        "skills = ?, updated_at = ? WHERE id = ?",
        (data["title"], data["company"], data["type"], data["location"],
         data["skills"], data["updated_at"], listing_id),
    )
    conn.commit()
    changed = cursor.rowcount
    conn.close()
    return get_listing(listing_id) if changed else None


def delete_listing(listing_id: int) -> bool:
    conn = get_connection()
    cursor = conn.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
    conn.commit()
    changed = cursor.rowcount
    conn.close()
    return changed > 0


def approve_listing(listing_id: int, start_date: str) -> dict | None:
    """Admin marks a listing's applicant as hired, with the date they're
    expected to start work (stored as-given, e.g. "2026-10-01")."""
    conn = get_connection()
    cursor = conn.execute(
        "UPDATE listings SET status = 'approved', start_date = ? WHERE id = ?",
        (start_date, listing_id),
    )
    conn.commit()
    changed = cursor.rowcount
    conn.close()
    return get_listing(listing_id) if changed else None


# ---------------------------------------------------------------------
# In-app notifications (e.g. "you're hired" messages from the admin)
# ---------------------------------------------------------------------
def create_notification(user_id: int, message: str) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO notifications (user_id, message, created_at, is_read) VALUES (?, ?, ?, 0)",
        (user_id, message, datetime.now().strftime("%b %d, %Y %I:%M %p")),
    )
    conn.commit()
    conn.close()


def get_notifications_by_user(user_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_unread_notification_count(user_id: int) -> int:
    """Powers the badge next to 'My Dashboard' in the nav bar."""
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0", (user_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else 0


def mark_notifications_read(user_id: int) -> None:
    """Called once the applicant actually views their Dashboard, so the
    unread badge clears after they've seen the message."""
    conn = get_connection()
    conn.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0", (user_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------
# User accounts (applicant + admin logins)
# ---------------------------------------------------------------------
def get_user_by_username(username: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_user(
    username: str,
    password_hash: str,
    role: str,
    security_question: str | None = None,
    security_answer_hash: str | None = None,
) -> dict:
    """Raises sqlite3.IntegrityError if the username is already taken
    (callers should check get_user_by_username first for a friendly
    error message, but this is the hard backstop). security_question /
    security_answer_hash power the self-serve "Forgot password" flow
    (see update_user_password below) -- optional so admin creation
    still works without them."""
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO users (username, password_hash, role, created_at, "
        "security_question, security_answer_hash) VALUES (?, ?, ?, ?, ?, ?)",
        (
            username,
            password_hash,
            role,
            datetime.now().strftime("%b %d, %Y %I:%M %p"),
            security_question,
            security_answer_hash,
        ),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return get_user_by_id(new_id)


def update_user_password(user_id: int, new_password_hash: str) -> None:
    """Used by the 'Forgot password' flow once the security answer has
    been verified, and could later be reused for a 'change password'
    settings page."""
    conn = get_connection()
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_password_hash, user_id))
    conn.commit()
    conn.close()
