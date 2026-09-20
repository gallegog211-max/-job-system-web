import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash

# Render's free web-service tier has no persistent disk -- the old
# SQLite file (data/listings.db) got wiped every time the service
# spun down or redeployed, silently deleting every registered account
# and posted listing. This file now talks to a real, always-on
# Postgres database (Neon's free tier) instead, so data survives
# spin-downs, redeploys, and restarts exactly like a normal website.
#
# DATABASE_URL is set as an environment variable on Render (and in
# your local .env for testing) -- it is never hardcoded here.
DATABASE_URL = os.environ.get("DATABASE_URL")

# All timestamps are recorded in Philippine time (UTC+8) regardless of
# what timezone the hosting server itself runs in -- Render's servers
# run in UTC, which would otherwise make every "posted at" / "updated
# at" stamp look 8 hours off from the applicant's actual local time.
PH_TZ = ZoneInfo("Asia/Manila")


def ph_now_str() -> str:
    return datetime.now(PH_TZ).strftime("%b %d, %Y %I:%M %p")


# Default admin account, only ever created once (the very first time the
# app runs and no admin exists yet). Override via environment variables
# so the real credentials never have to live in source control.
DEFAULT_ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


def get_connection():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set. Add it as an environment variable "
            "(Render: Environment tab; local: your .env file) with the "
            "connection string from your Neon project."
        )
    # RealDictCursor makes every row behave like a dict already, so the
    # rest of this file's `dict(row)` calls keep working unchanged.
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def _exec(conn, sql, params=()):
    """Small helper so call sites read like the old sqlite3
    conn.execute(sql, params) shorthand, since psycopg2 requires an
    explicit cursor for every query."""
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur


def init_db() -> None:
    """Creates the listings/users/notifications tables if they don't
    exist yet, runs small migrations for older databases, and seeds
    sample data + a default admin account the very first time (empty
    tables only)."""
    conn = get_connection()

    _exec(conn, """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('applicant', 'admin')),
            created_at TEXT NOT NULL
        )
    """)
    _exec(conn, """
        CREATE TABLE IF NOT EXISTS listings (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            type TEXT NOT NULL,
            location TEXT NOT NULL,
            skills TEXT NOT NULL,
            posted_at TEXT NOT NULL,
            updated_at TEXT,
            posted_by INTEGER REFERENCES users(id)
        )
    """)
    _exec(conn, """
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()

    # Migrations: Postgres supports "ADD COLUMN IF NOT EXISTS" natively,
    # so unlike the old SQLite version this doesn't need to manually
    # check PRAGMA table_info first.
    _exec(conn, "ALTER TABLE listings ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active'")
    _exec(conn, "ALTER TABLE listings ADD COLUMN IF NOT EXISTS start_date TEXT")
    _exec(conn, "ALTER TABLE users ADD COLUMN IF NOT EXISTS security_question TEXT")
    _exec(conn, "ALTER TABLE users ADD COLUMN IF NOT EXISTS security_answer_hash TEXT")
    _exec(conn, "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS is_read INTEGER NOT NULL DEFAULT 0")
    conn.commit()

    count = _exec(conn, "SELECT COUNT(*) AS c FROM listings").fetchone()["c"]
    if count == 0:
        _seed_sample_data(conn)

    admin_exists = _exec(conn, "SELECT 1 FROM users WHERE role = 'admin' LIMIT 1").fetchone()
    if not admin_exists:
        _seed_default_admin(conn)

    conn.close()


def _seed_default_admin(conn) -> None:
    """Creates one admin account on first run only. Change the password
    right away (or set ADMIN_USERNAME / ADMIN_PASSWORD before the first
    run) -- this default is meant for local/demo use only."""
    _exec(
        conn,
        "INSERT INTO users (username, password_hash, role, created_at) VALUES (%s, %s, 'admin', %s)",
        (
            DEFAULT_ADMIN_USERNAME,
            generate_password_hash(DEFAULT_ADMIN_PASSWORD),
            ph_now_str(),
        ),
    )
    conn.commit()


def _seed_sample_data(conn) -> None:
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
        _exec(
            conn,
            "INSERT INTO listings (title, company, type, location, skills, posted_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
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
    rows = _exec(conn, _LISTINGS_WITH_AUTHOR + " ORDER BY listings.id").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_listings_by_user(user_id: int) -> list[dict]:
    """Only the listings a given applicant posted -- used by the
    Applicant Dashboard so each logged-in user manages just their own."""
    conn = get_connection()
    rows = _exec(
        conn,
        _LISTINGS_WITH_AUTHOR + " WHERE listings.posted_by = %s ORDER BY listings.id DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_listing(listing_id: int) -> dict | None:
    conn = get_connection()
    row = _exec(
        conn, _LISTINGS_WITH_AUTHOR + " WHERE listings.id = %s", (listing_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def insert_listing(data: dict) -> dict:
    conn = get_connection()
    cursor = _exec(
        conn,
        "INSERT INTO listings (title, company, type, location, skills, posted_at, posted_by) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (data["title"], data["company"], data["type"], data["location"],
         data["skills"], data["posted_at"], data.get("posted_by")),
    )
    new_id = cursor.fetchone()["id"]
    conn.commit()
    conn.close()
    return get_listing(new_id)


def update_listing(listing_id: int, data: dict) -> dict | None:
    conn = get_connection()
    cursor = _exec(
        conn,
        "UPDATE listings SET title = %s, company = %s, type = %s, location = %s, "
        "skills = %s, updated_at = %s WHERE id = %s",
        (data["title"], data["company"], data["type"], data["location"],
         data["skills"], data["updated_at"], listing_id),
    )
    changed = cursor.rowcount
    conn.commit()
    conn.close()
    return get_listing(listing_id) if changed else None


def delete_listing(listing_id: int) -> bool:
    conn = get_connection()
    cursor = _exec(conn, "DELETE FROM listings WHERE id = %s", (listing_id,))
    changed = cursor.rowcount
    conn.commit()
    conn.close()
    return changed > 0


def approve_listing(listing_id: int, start_date: str) -> dict | None:
    """Admin marks a listing's applicant as hired, with the date they're
    expected to start work (stored as-given, e.g. "2026-10-01")."""
    conn = get_connection()
    cursor = _exec(
        conn,
        "UPDATE listings SET status = 'approved', start_date = %s WHERE id = %s",
        (start_date, listing_id),
    )
    changed = cursor.rowcount
    conn.commit()
    conn.close()
    return get_listing(listing_id) if changed else None


# ---------------------------------------------------------------------
# In-app notifications (e.g. "you're hired" messages from the admin)
# ---------------------------------------------------------------------
def create_notification(user_id: int, message: str) -> None:
    conn = get_connection()
    _exec(
        conn,
        "INSERT INTO notifications (user_id, message, created_at, is_read) VALUES (%s, %s, %s, 0)",
        (user_id, message, ph_now_str()),
    )
    conn.commit()
    conn.close()


def get_notifications_by_user(user_id: int) -> list[dict]:
    conn = get_connection()
    rows = _exec(
        conn, "SELECT * FROM notifications WHERE user_id = %s ORDER BY id DESC", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_unread_notification_count(user_id: int) -> int:
    """Powers the badge next to 'My Dashboard' in the nav bar."""
    conn = get_connection()
    row = _exec(
        conn,
        "SELECT COUNT(*) AS c FROM notifications WHERE user_id = %s AND is_read = 0",
        (user_id,),
    ).fetchone()
    conn.close()
    return row["c"] if row else 0


def mark_notifications_read(user_id: int) -> None:
    """Called once the applicant actually views their Dashboard, so the
    unread badge clears after they've seen the message."""
    conn = get_connection()
    _exec(conn, "UPDATE notifications SET is_read = 1 WHERE user_id = %s AND is_read = 0", (user_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------
# User accounts (applicant + admin logins)
# ---------------------------------------------------------------------
def get_user_by_username(username: str) -> dict | None:
    conn = get_connection()
    row = _exec(
        conn, "SELECT * FROM users WHERE LOWER(username) = LOWER(%s)", (username,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_connection()
    row = _exec(conn, "SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_user(
    username: str,
    password_hash: str,
    role: str,
    security_question: str | None = None,
    security_answer_hash: str | None = None,
) -> dict:
    """Raises psycopg2.errors.UniqueViolation if the username is already
    taken (callers should check get_user_by_username first for a
    friendly error message, but this is the hard backstop).
    security_question / security_answer_hash power the self-serve
    "Forgot password" flow (see update_user_password below) -- optional
    so admin creation still works without them."""
    conn = get_connection()
    cursor = _exec(
        conn,
        "INSERT INTO users (username, password_hash, role, created_at, "
        "security_question, security_answer_hash) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (
            username,
            password_hash,
            role,
            ph_now_str(),
            security_question,
            security_answer_hash,
        ),
    )
    new_id = cursor.fetchone()["id"]
    conn.commit()
    conn.close()
    return get_user_by_id(new_id)


def update_user_password(user_id: int, new_password_hash: str) -> None:
    """Used by the 'Forgot password' flow once the security answer has
    been verified, and could later be reused for a 'change password'
    settings page."""
    conn = get_connection()
    _exec(conn, "UPDATE users SET password_hash = %s WHERE id = %s", (new_password_hash, user_id))
    conn.commit()
    conn.close()
