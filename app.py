"""
app.py (Flask / Web version)
-----------------------------
Mobile-friendly web version of the AI Job Recommendation System.

This replaces the Tkinter desktop window with Flask routes + HTML
templates, so it can be opened from any phone or desktop browser
once deployed. Nothing about the underlying logic changes:

  - database.py        -> same SQLite storage layer (unchanged)
  - gemini_matcher.py   -> same Gemini AI engine (unchanged)
  - matcher.py          -> same TF-IDF fallback engine (unchanged)
  - region_utils.py     -> same PH/international grouping (unchanged)
  - resume_parser.py    -> same PDF/DOCX resume extraction (unchanged)

Run locally:
    pip install -r requirements.txt
    python app.py
    -> open http://127.0.0.1:5000 on your phone (same Wi-Fi) or PC

Deploy for real mobile access: see README_DEPLOY.md
"""

import os
from functools import wraps

from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

import database
from gemini_matcher import GeminiUnavailableError, gemini_extract_resume_profile, gemini_rank_listings
from matcher import rank_listings
from region_utils import split_and_rank_by_region
from resume_parser import build_skill_vocabulary, extract_resume_text, find_location_in_text, find_skills_in_text

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB resume upload limit

# Needed for Flask's signed session cookie (that's what keeps an
# applicant login in one browser separate from an admin login in
# another). Set a real SECRET_KEY env var before deploying for real --
# the fallback here is only for local testing.
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

database.init_db()

JOB_TYPES = ["Full-time", "Part-time", "Internship"]


@app.context_processor
def inject_unread_notifications():
    """Makes the unread notification count available in base.html on
    every page (for the badge next to 'My Dashboard'), without every
    route having to fetch and pass it explicitly."""
    if session.get("role") == "applicant" and session.get("user_id"):
        return {"unread_notifications": database.get_unread_notification_count(session["user_id"])}
    return {"unread_notifications": 0}


# ---------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------
def login_required(role=None):
    """Route decorator. With no args, just requires *someone* logged
    in. Pass role="applicant" or role="admin" to also require that
    specific account type (each browser keeps its own session, so an
    applicant logged in on a phone and an admin logged in on a laptop
    don't interfere with each other)."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                # request.full_path keeps query strings (e.g. ?from_match=5)
                # alive across the login redirect, so a selected match
                # survives having to log in first.
                next_path = request.full_path if request.query_string else request.path
                return redirect(url_for("login_page", next=next_path))
            if role and session.get("role") != role:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def _parse_resume_file(resume_file):
    """
    Shared helper: reads an uploaded resume file, extracts its text, and
    returns (skills_str, location_str, note). Tries Gemini first, falls
    back to local keyword/location matching if Gemini is unavailable.
    Raises ValueError for unsupported file types.
    """
    filename = secure_filename(resume_file.filename)
    file_bytes = resume_file.read()
    resume_text = extract_resume_text(filename, file_bytes)

    try:
        profile = gemini_extract_resume_profile(resume_text)
        skills_str = ", ".join(profile["skills"])
        location_str = profile["location"]
        note = "Skills and location detected from your resume via Gemini AI."
    except GeminiUnavailableError:
        listings = database.get_all_listings()
        vocabulary = build_skill_vocabulary(listings)
        extracted_skills = find_skills_in_text(resume_text, vocabulary)
        skills_str = ", ".join(extracted_skills)
        location_str = find_location_in_text(resume_text)
        note = "Gemini unavailable — skills and location detected via local keyword matching."

    return skills_str, location_str, note


# ---------------------------------------------------------------------
# Accounts: applicant registration/login + admin login (same form,
# different role) and logout. Sessions are per-browser, so an applicant
# signed in on one browser/device and an admin signed in on another
# never see each other's session.
# ---------------------------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register_page():
    if request.method == "GET":
        return render_template("register.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    confirm = request.form.get("confirm", "")
    security_question = request.form.get("security_question", "").strip()
    security_answer = request.form.get("security_answer", "").strip()

    if not username or not password or not security_question or not security_answer:
        return render_template("register.html", error="Please fill in all fields.", username=username)
    if password != confirm:
        return render_template("register.html", error="Passwords do not match.", username=username)
    if len(password) < 6:
        return render_template("register.html", error="Password must be at least 6 characters.", username=username)
    if database.get_user_by_username(username):
        return render_template("register.html", error="That username is already taken.", username=username)

    # Answer is normalized (lowercased/stripped) before hashing so a
    # later reset attempt isn't rejected over capitalization/spacing.
    answer_hash = generate_password_hash(security_answer.lower())
    user = database.create_user(
        username,
        generate_password_hash(password),
        role="applicant",
        security_question=security_question,
        security_answer_hash=answer_hash,
    )
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]
    return redirect(url_for("dashboard_page"))


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "GET":
        return render_template("login.html", next=request.args.get("next", ""))

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    next_url = request.form.get("next", "")

    user = database.get_user_by_username(username)
    if not user or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Invalid username or password.", username=username, next=next_url)

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]

    if next_url:
        return redirect(next_url)
    return redirect(url_for("admin_dashboard_page" if user["role"] == "admin" else "dashboard_page"))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ---------------------------------------------------------------------
# Forgot password -- self-serve reset using the security question the
# applicant set at registration. Two steps on one route: first look up
# the username and show their question, then verify the answer and
# accept a new password. (Usernames aren't secret -- there's no
# separate "forgot username" recovery, since forgetting your own
# chosen name isn't something a security-question flow can verify.)
# ---------------------------------------------------------------------
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password_page():
    if request.method == "GET":
        return render_template("forgot_password.html")

    stage = request.form.get("stage", "lookup")
    username = request.form.get("username", "").strip()

    if stage == "lookup":
        user = database.get_user_by_username(username)
        if not user or not user.get("security_question"):
            return render_template(
                "forgot_password.html",
                error="No account found with that username.",
                username=username,
            )
        return render_template(
            "forgot_password.html",
            username=username,
            security_question=user["security_question"],
        )

    # stage == "reset"
    answer = request.form.get("security_answer", "").strip()
    new_password = request.form.get("new_password", "")
    confirm = request.form.get("confirm", "")

    user = database.get_user_by_username(username)
    if not user or not user.get("security_answer_hash"):
        return render_template("forgot_password.html", error="No account found with that username.")

    if not check_password_hash(user["security_answer_hash"], answer.lower()):
        return render_template(
            "forgot_password.html",
            username=username,
            security_question=user["security_question"],
            error="That answer doesn't match what we have on file.",
        )
    if new_password != confirm:
        return render_template(
            "forgot_password.html",
            username=username,
            security_question=user["security_question"],
            error="Passwords do not match.",
        )
    if len(new_password) < 6:
        return render_template(
            "forgot_password.html",
            username=username,
            security_question=user["security_question"],
            error="Password must be at least 6 characters.",
        )

    database.update_user_password(user["id"], generate_password_hash(new_password))
    return render_template("login.html", success="Password reset. You can log in now.", username=username)


# ---------------------------------------------------------------------
# Tab 1: Find Your Matches -- now requires being logged in (as either
# applicant-only. Admins manage listings from /admin instead; they
# don't upload resumes or search for jobs, so this whole flow (and its
# nav tab) is hidden from them.
# ---------------------------------------------------------------------
@app.route("/", methods=["GET"])
@login_required()
def match_page():
    # An admin has no "Find Matches" flow of their own -- send them to
    # their dashboard instead of a 403, since landing on "/" (e.g. via
    # a bookmark or the site's root URL) is a normal thing to do, not
    # an access violation.
    if session.get("role") == "admin":
        return redirect(url_for("admin_dashboard_page"))
    return render_template("match.html", job_types=JOB_TYPES)


@app.route("/parse_resume", methods=["POST"])
@login_required(role="applicant")
def parse_resume_route():
    """
    Called via JS as soon as the user clicks "Parse Resume". Reads the
    uploaded file and returns detected skills/location as JSON, so the
    match form can auto-fill those fields for the user to review before
    searching -- without losing the selected file from the form.
    """
    resume_file = request.files.get("resume")
    if not resume_file or not resume_file.filename:
        return jsonify({"error": "Please choose a resume file first."}), 400

    try:
        skills_str, location_str, note = _parse_resume_file(resume_file)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if not skills_str:
        note = "No recognizable skills found in that resume. You can type them in manually."

    return jsonify({"skills": skills_str, "location": location_str, "note": note})


@app.route("/match", methods=["POST"])
@login_required(role="applicant")
def find_matches():
    typed_skills = request.form.get("skills", "").strip()
    typed_location = request.form.get("location", "").strip()
    resume_file = request.files.get("resume")

    applicant_skills = typed_skills
    applicant_location = typed_location
    resume_note = ""

    # If a resume was uploaded and the skills box is still empty (i.e.
    # the user didn't click "Parse Resume" first, or typed nothing),
    # extract skills/location from it automatically here too.
    if resume_file and resume_file.filename and not typed_skills:
        try:
            extracted_skills, extracted_location, resume_note = _parse_resume_file(resume_file)
        except ValueError as e:
            return render_template("match.html", job_types=JOB_TYPES, error=str(e),
                                    skills=typed_skills, location=typed_location)

        if extracted_skills:
            applicant_skills = extracted_skills
        if extracted_location and not typed_location:
            applicant_location = extracted_location

    if not applicant_skills:
        return render_template("match.html", job_types=JOB_TYPES,
                                error="Please upload a resume or enter your skills.",
                                skills=typed_skills, location=typed_location)

    listings = database.get_all_listings()

    try:
        ranked = gemini_rank_listings(applicant_skills, listings, applicant_location)
        engine_used = "Gemini AI"
    except GeminiUnavailableError:
        ranked = rank_listings(applicant_skills, listings)
        engine_used = "Local fallback (TF-IDF)"

    ph_matches, intl_matches = split_and_rank_by_region(ranked, applicant_location)

    return render_template(
        "results.html",
        skills=applicant_skills,
        location=applicant_location,
        engine_used=engine_used,
        resume_note=resume_note,
        ph_matches=ph_matches,
        intl_matches=intl_matches,
    )


# ---------------------------------------------------------------------
# Tab 2: Post a Listing (Applicant) -- requires an applicant login
# ---------------------------------------------------------------------
@app.route("/post", methods=["GET"])
@login_required(role="applicant")
def post_page():
    editing_id = request.args.get("edit")
    prefill_id = request.args.get("from_match")
    listing = None
    is_template = False

    if editing_id:
        listing = database.get_listing(int(editing_id))
        # An applicant can only edit their own listing, never someone else's.
        if not listing or listing.get("posted_by") != session["user_id"]:
            abort(403)
    elif prefill_id:
        # "Use This Match" on the results page: copy a matched listing's
        # title/company/type/location/skills into the form as a starting
        # point, but with no listing_id, so submitting creates a new
        # listing rather than editing the one that was matched.
        source = database.get_listing(int(prefill_id))
        if not source:
            abort(404)
        listing = {
            "title": source["title"],
            "company": source["company"],
            "type": source["type"],
            "location": source["location"],
            "skills": source["skills"],
        }
        is_template = True

    return render_template("post.html", job_types=JOB_TYPES, listing=listing, is_template=is_template)


@app.route("/post", methods=["POST"])
@login_required(role="applicant")
def submit_listing():
    from datetime import datetime

    editing_id = request.form.get("listing_id")
    data = {
        "title": request.form.get("title", "").strip(),
        "company": request.form.get("company", "").strip(),
        "type": request.form.get("type", "").strip(),
        "location": request.form.get("location", "").strip(),
        "skills": request.form.get("skills", "").strip(),
    }

    if not all(data.values()):
        listing = {**data, "id": editing_id} if editing_id else None
        return render_template("post.html", job_types=JOB_TYPES, listing=listing,
                                error="Please fill in all fields.")

    if editing_id:
        existing = database.get_listing(int(editing_id))
        if not existing or existing.get("posted_by") != session["user_id"]:
            abort(403)
        data["updated_at"] = datetime.now().strftime("%b %d, %Y %I:%M %p")   # ← bug
        database.update_listing(int(editing_id), data)
    else:
        data["posted_at"] = datetime.now().strftime("%b %d, %Y %I:%M %p")    # ← bug
        data["posted_by"] = session["user_id"]
        database.insert_listing(data)

    return redirect(url_for("dashboard_page"))


# ---------------------------------------------------------------------
# Tab 3: Applicant Dashboard -- each applicant only sees/manages their
# own listings, based on who's logged in in *this* browser.
# ---------------------------------------------------------------------
@app.route("/dashboard", methods=["GET"])
@login_required(role="applicant")
def dashboard_page():
    listings = database.get_listings_by_user(session["user_id"])
    notifications = database.get_notifications_by_user(session["user_id"])
    database.mark_notifications_read(session["user_id"])
    return render_template("dashboard.html", listings=listings, notifications=notifications)


@app.route("/dashboard/delete/<int:listing_id>", methods=["POST"])
@login_required(role="applicant")
def delete_listing_route(listing_id):
    listing = database.get_listing(listing_id)
    if not listing or listing.get("posted_by") != session["user_id"]:
        abort(403)
    database.delete_listing(listing_id)
    return redirect(url_for("dashboard_page"))


# ---------------------------------------------------------------------
# Tab 4: Admin Dashboard -- requires an admin login, kept completely
# separate from applicant accounts/sessions. Admins can see every
# listing posted by every applicant, approve one (marks the applicant
# as hired and sends them an in-app notification), or delete any
# listing outright.
# ---------------------------------------------------------------------
@app.route("/admin", methods=["GET"])
@login_required(role="admin")
def admin_dashboard_page():
    listings = database.get_all_listings()
    return render_template("admin_dashboard.html", listings=listings)


@app.route("/admin/approve/<int:listing_id>", methods=["POST"])
@login_required(role="admin")
def approve_listing_route(listing_id):
    from datetime import datetime as dt

    listing = database.get_listing(listing_id)
    if not listing:
        abort(404)

    start_date_raw = request.form.get("start_date", "").strip()
    if not start_date_raw:
        listings = database.get_all_listings()
        return render_template("admin_dashboard.html", listings=listings,
                                error="Please choose a start date before approving.")

    try:
        start_date_display = dt.strptime(start_date_raw, "%Y-%m-%d").strftime("%B %d, %Y")
    except ValueError:
        listings = database.get_all_listings()
        return render_template("admin_dashboard.html", listings=listings,
                                error="That start date doesn't look valid.")

    database.approve_listing(listing_id, start_date_display)
    if listing.get("posted_by"):
        database.create_notification(
            listing["posted_by"],
            f"You're hired! The admin approved your listing "
            f"\"{listing['title']}\" at {listing['company']}. "
            f"Your start date is {start_date_display}.",
        )
    return redirect(url_for("admin_dashboard_page"))


@app.route("/admin/delete/<int:listing_id>", methods=["POST"])
@login_required(role="admin")
def admin_delete_listing_route(listing_id):
    database.delete_listing(listing_id)
    return redirect(url_for("admin_dashboard_page"))


@app.errorhandler(403)
def forbidden(_e):
    return render_template("error.html", message="You don't have access to that page."), 403


if __name__ == "__main__":
    # host="0.0.0.0" so phones on the same Wi-Fi can reach it via your
    # computer's local IP (e.g. http://192.168.1.23:5000) during testing.
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
