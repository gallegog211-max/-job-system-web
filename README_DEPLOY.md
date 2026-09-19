# Deploying the AI Job Recommendation System to Mobile

Tkinter (the original desktop version) can't run on a phone — there's no
Tkinter runtime for iOS/Android. This folder is a **Flask web version**
of the exact same system: same database, same Gemini/TF-IDF matching,
same PH/international grouping. Running it as a website is what makes
it openable on a phone.

## 0. Logins (new)

The app now has real accounts:

- **Applicants** self-register at `/register`, then log in at `/login`.
  Each applicant only sees and can edit/delete their own listings on
  the Applicant Dashboard — other applicants' listings are hidden from
  them there.
- **Admin** logs in at the same `/login` form and is routed to the
  read-only Admin Dashboard (`/admin`), which lists every listing from
  every applicant.
- Logins are ordinary Flask sessions (a cookie per browser), so an
  applicant signed in on their phone and an admin signed in on a
  laptop are completely independent — logging out of one never touches
  the other.

**Set these before running for real:**

```bash
SECRET_KEY=some-long-random-string       # signs the session cookie
ADMIN_USERNAME=your_admin_name           # only used the very first run
ADMIN_PASSWORD=a-strong-password         # only used the very first run
```

If you don't set `ADMIN_USERNAME`/`ADMIN_PASSWORD`, the app creates a
default account (`admin` / `admin123`) the first time it starts —
fine for a quick local demo, but log in and you'll want to know that
password isn't a secret. There's no "change password" screen yet; to
reset it, delete `data/listings.db` and set env vars before the next
first run (this also wipes existing listings/applicant accounts, so
only do it before you have real data).

**Also:** the `.env` file in this project bundle already has a real
`GEMINI_API_KEY` value in it. Treat any key that's been shared this
way as compromised — rotate it in Google AI Studio and put the new one
in your own untracked `.env` (it's already in `.gitignore`, so it
won't get committed, but a key that's already been shared elsewhere
should still be replaced).

## 1. Test it locally first

```bash
cd job_system_web
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env .env          # then paste your GEMINI_API_KEY inside
python app.py
```

Open `http://127.0.0.1:5000` on your computer. **`127.0.0.1` and
`192.168.x.x` addresses only work on your own computer/Wi-Fi — they're
not reachable from another network, and never from "around the world."**
That's expected at this stage; it's what the deploy step below fixes.

To test on your **own
phone** while still on your computer (same Wi-Fi, before deploying
anywhere):

1. Find your computer's local IP (Windows: `ipconfig`, Mac/Linux: `ifconfig`
   or `ip addr`) — something like `192.168.1.23`.
2. On your phone's browser, go to `http://192.168.1.23:5000`.
3. Both devices must be on the same Wi-Fi network.

This only works while your computer is on and running the app — it's for
testing, not real deployment.

## 2. Deploy for real (free options) — this is what makes it open on any
##    phone (iOS/Android) or PC, anywhere in the world, over the internet

Any of these gives you a real `https://...` URL that opens on any phone,
anywhere, without your computer needing to be on. Once deployed this way,
it works worldwide — the mobile-responsive design already built into
`static/style.css` means it'll look right on any phone browser too.

### Option A — Render (recommended, simplest)

1. Push this folder to a GitHub repo.
2. Go to [render.com](https://render.com) → New → Web Service → connect
   your repo.
3. **Name the service** something short and memorable, e.g. `findingjob`
   — this becomes part of your URL.
4. Build command: `pip install -r requirements.txt`
   Start command: `gunicorn app:app`
5. Under Environment, add `GEMINI_API_KEY`, `SECRET_KEY`, and (optionally)
   `ADMIN_USERNAME`/`ADMIN_PASSWORD`.
6. Deploy. Render gives you a URL like
   `https://findingjob.onrender.com` — that opens on any phone or PC,
   anywhere with internet, once deployed. Bookmark it (or add it to your
   phone's home screen) instead of typing an IP address.

### Option B — Railway

1. Push to GitHub, then [railway.app](https://railway.app) → New Project
   → Deploy from GitHub repo.
2. Railway auto-detects the `Procfile` (`web: gunicorn app:app`).
3. Add `GEMINI_API_KEY` under Variables.
4. Deploy → open the generated URL.

### Option C — PythonAnywhere

Good if you want a free option with no credit card and don't mind a bit
more manual setup (upload files directly, configure a WSGI file pointing
at `app.app`). See PythonAnywhere's Flask quickstart docs.

### A real custom domain (a link that's *exactly* "findingjob", with no
### ".onrender.com" on the end)

A browser address needs a registered domain with a suffix — plain
`http://findingjob` (no `.com`/`.app`/etc.) isn't something any browser
or the internet's naming system (DNS) can resolve; it's not a valid
public web address no matter how it's hosted. To get something like
`https://findingjob.com` or `https://findingjob.app`:

1. Buy the domain from a registrar (Namecheap, Squarespace Domains,
   etc.) — typically $10–20/year depending on the suffix. Check whether
   `findingjob.com` is available; if not, a suffix like `.app` or `.dev`
   is often cheaper and just as short.
2. In the registrar's DNS settings, add a CNAME record pointing your
   domain at the Render URL from Option A (e.g. `findingjob.onrender.com`).
3. In Render's dashboard, under your service → Settings → Custom Domain,
   add the same domain and follow its verification steps.

This is the only way to get an address without a provider suffix —
there's no free way to claim a bare word as a public web address.

## 3. A note on the database

`database.py` uses SQLite, a single file (`data/listings.db`). This is
fine for a capstone demo, but on some free hosts (Render's free tier
included) the filesystem resets on every redeploy, so listings you add
won't persist permanently. For a class demo this usually doesn't matter;
if it does, swap SQLite for a hosted Postgres database later (mentioned
as a stretch goal in the original README).

## 4. What changed vs. the desktop version

| Desktop (Tkinter)              | Web (Flask)                          |
|---------------------------------|----------------------------------------|
| `app.py` opens a native window  | `app.py` runs a Flask server           |
| Runs only on the machine it's on| Opens from any browser, any device     |
| No install needed for the user  | User just visits a URL                 |
| N/A                              | `templates/` + `static/style.css` for UI |

`database.py`, `gemini_matcher.py`, `matcher.py`, `region_utils.py`, and
`resume_parser.py` are byte-for-byte unchanged — only the UI layer moved
from Tkinter widgets to HTML pages.
