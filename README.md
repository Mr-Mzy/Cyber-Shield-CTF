# CyberShield CTF Platform

A custom-built Flask CTF control platform for the CyberShield six-stage
CTF Play Box, using the Flask "application factory" pattern.

## Project layout

```
CyberShield/
├── app/
│   ├── __init__.py     # application factory: create_app(), db, login_manager
│   ├── routes.py        # dashboard, challenge pages, submit, scoreboard, admin
│   ├── models.py          # database tables (User, Challenge, Hint, Submission, Progress, LogEntry)
│   ├── auth.py              # register / login / logout
│   ├── templates/             # Jinja2 HTML templates
│   └── static/                  # CSS + JS
│
├── challenges/                    # per-stage files (images, ciphertext, evidence, READMEs)
├── database/                        # cybershield.db lives here (created automatically)
├── tests/                              # pytest smoke tests
│
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── config.py                             # all settings in one place
└── run.py                                  # the file you actually execute
```

Every code file has inline comments explaining what it does and why —
that's intentional so you can learn the Flask patterns used here
(application factory, blueprints, SQLAlchemy models, password hashing)
before stripping the comments back out once it clicks.

## Quick start (Windows, VS Code, no Docker)

```powershell
cd CyberShield
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python seed.py        # creates database\cybershield.db, admin account, CS-01..CS-06
python run.py          # starts the server on http://127.0.0.1:5000
```

Default admin login after seeding: `admin` / `ChangeMe123!` — change
this before real use (there's no "change password" UI yet; update it
directly via a Python shell, or add a route for it).

## Running the tests

```powershell
pytest
```

This runs `tests/test_app.py`, which checks registration, login, and
that CS-02 stays locked until CS-01 is solved with the correct flag.

## Quick start (Docker)

```bash
cd CyberShield
docker compose up --build -d
docker compose exec ctf-platform python seed.py
```

Platform will be at `http://localhost:5000`.

## Before running this for real participants

1. **Replace every placeholder flag** in `seed.py` (the `CHALLENGES`
   list), and rebuild the matching files in `challenges/` to match.
   The current flags/files are worked examples: CS-01's image has the
   flag in EXIF metadata, CS-03 ships a real Caesar-cipher ciphertext,
   CS-05 has a small forensic evidence package.
2. **Change `SECRET_KEY`** (in `docker-compose.yml` or your environment).
3. **Change the seeded admin password.**
4. Build CS-04 and CS-06 as their own separate, isolated
   services/containers (see the README inside each of their folders
   under `challenges/`) — this platform should only show participants
   the connection info, not host the vulnerable service itself.
5. Turn off Flask debug mode (`debug=True` in `run.py`) for anything
   beyond local development.

## Extending

- Add a `/admin/reset/<code>` route to trigger a per-challenge reset script.
- Add a `HintReveal` table if you want a hint's point cost to actually
  deduct from that player's score (right now hints are informational only).
- Add rate limiting (e.g. Flask-Limiter) on `/submit/<code>` to slow
  down brute-force flag guessing.
