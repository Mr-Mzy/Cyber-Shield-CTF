"""
tests/test_app.py
------------------
Automated checks using pytest and Flask's test client (fake requests,
no real server). Run them with:

    pytest

What is covered:
  - registration needs admin approval before login
  - the login / unlock / flag-submission flow
  - navbar rank, dashboard numbers, hint costs
  - admin: open any challenge, the three panel sections, user search
  - upgrading an old database that has no `status` column
"""

import os
import sqlite3
import sys

# Make sure Python can find the `app` package when running pytest
# from the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models import Challenge, Hint, Progress, Submission, User

PASSWORD = "Test1234!"
FLAG_CS01 = "CS{h1dd3n_1n_pl41n_s1ght}"


# --------------------------------------------------------------------
# Fixture: a fresh app with an in-memory database for EVERY test
# --------------------------------------------------------------------
@pytest.fixture
def client():
    """
    Builds an isolated app (in-memory SQLite, never your real database
    file), seeds the six challenges with their hints, and creates an
    approved admin account named "admin".

    config.py reads DATABASE_URL BEFORE create_app() runs, and the app
    connects to that URI immediately, so the variable must be set first.
    """
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    app = create_app()
    app.config["TESTING"] = True

    with app.app_context():
        db.create_all()
        from seed import CHALLENGES

        for c in CHALLENGES:
            ch = Challenge(
                code=c["code"], name=c["name"], category=c["category"],
                difficulty=c["difficulty"], scenario=c["scenario"],
                description=c["description"],
                flag_hash=generate_password_hash(c["flag"]),
                order_index=c["order_index"], file_path=c["file_path"],
                points=c["points"],
            )
            db.session.add(ch)
            db.session.flush()   # assigns ch.id so the hints below can point at it
            for i, text in enumerate(c["hints"]):
                db.session.add(Hint(challenge_id=ch.id, text=text, order_index=i, point_cost=10))

        db.session.add(
            User(username="admin", password_hash=generate_password_hash(PASSWORD),
                 is_admin=True, status="approved")
        )
        db.session.commit()

        with app.test_client() as test_client:
            yield test_client


# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------
def make_player(client, username, approved=True):
    """Registers through the real /register route, then (optionally) approves."""
    client.post("/register", data={"username": username, "password": PASSWORD})
    if approved:
        user = User.query.filter_by(username=username).first()
        user.status = "approved"
        db.session.commit()


def login(client, username):
    return client.post("/login", data={"username": username, "password": PASSWORD})


def logout(client):
    client.get("/logout")


def player_session(client, username):
    """Create an approved player, log them in, and open the dashboard
    (visiting the dashboard is what creates their Progress rows)."""
    make_player(client, username)
    login(client, username)
    client.get("/dashboard")


# ====================================================================
# Registration approval
# ====================================================================
def test_new_registration_is_pending_and_cannot_login(client):
    r = client.post("/register", data={"username": "newbie", "password": PASSWORD})
    assert r.status_code == 302                      # redirected to the login page

    assert User.query.filter_by(username="newbie").first().status == "pending"

    r = login(client, "newbie")
    assert r.status_code == 200                      # NOT redirected: login refused
    assert b"waiting for admin approval" in r.data
    assert client.get("/dashboard").status_code == 302   # still not signed in


def test_admin_approves_then_user_can_login(client):
    make_player(client, "newbie", approved=False)
    uid = User.query.filter_by(username="newbie").first().id

    login(client, "admin")
    r = client.post(f"/admin/requests/{uid}/approve")
    assert r.status_code == 302
    logout(client)

    r = login(client, "newbie")
    assert r.status_code == 302                      # login succeeded
    assert client.get("/dashboard").status_code == 200


def test_rejected_user_is_blocked_and_delete_frees_username(client):
    make_player(client, "nope", approved=False)
    uid = User.query.filter_by(username="nope").first().id

    login(client, "admin")
    client.post(f"/admin/requests/{uid}/reject")
    logout(client)

    r = login(client, "nope")
    assert b"declined" in r.data

    login(client, "admin")
    client.post(f"/admin/requests/{uid}/delete")
    logout(client)
    assert User.query.filter_by(username="nope").first() is None

    # the username can register again
    r = client.post("/register", data={"username": "nope", "password": PASSWORD})
    assert r.status_code == 302


def test_wrong_password_never_reveals_account_state(client):
    make_player(client, "ghost", approved=False)
    r = client.post("/login", data={"username": "ghost", "password": "wrong-password"})
    assert b"Invalid username or password" in r.data   # same message as any bad login


def test_pending_users_are_not_on_the_scoreboard(client):
    make_player(client, "waiting", approved=False)
    player_session(client, "active")
    html = client.get("/scoreboard").get_data(as_text=True)
    assert "active" in html and "waiting" not in html


# ====================================================================
# Player flow (unchanged behaviour)
# ====================================================================
def test_challenge_unlock_progression(client):
    player_session(client, "tester")

    assert client.get("/challenge/CS-02").status_code == 403    # locked at first

    r = client.post("/submit/CS-01", data={"flag": FLAG_CS01})
    assert r.get_json()["correct"] is True
    assert r.get_json()["unlocked_next"] == "CS-02"

    assert client.get("/challenge/CS-02").status_code == 200


def test_wrong_flag_does_not_unlock_next(client):
    player_session(client, "tester2")
    r = client.post("/submit/CS-01", data={"flag": "CS{wrong_guess}"})
    assert r.get_json()["correct"] is False
    assert client.get("/challenge/CS-02").status_code == 403


def test_navbar_shows_operator_and_rank_and_dashboard_stats(client):
    make_player(client, "alice")
    make_player(client, "bob")

    login(client, "bob")
    client.get("/dashboard")
    client.post("/submit/CS-01", data={"flag": FLAG_CS01})   # bob outranks alice
    logout(client)

    login(client, "alice")
    html = client.get("/dashboard").get_data(as_text=True)
    assert "OPERATOR:" in html and "alice" in html
    assert "RANK:" in html and "#2" in html
    assert "Challenges Completed" in html and "Score Progression" in html


def test_hint_text_is_not_in_page_until_revealed(client):
    player_session(client, "hinter")
    hint = Hint.query.filter_by(order_index=0).first()

    assert hint.text not in client.get("/challenge/CS-01").get_data(as_text=True)

    r = client.post(f"/hint/{hint.id}/reveal")
    assert r.get_json()["text"] == hint.text
    assert hint.text in client.get("/challenge/CS-01").get_data(as_text=True)


def test_hint_cost_is_deducted_once(client):
    player_session(client, "payer")
    client.post("/submit/CS-01", data={"flag": FLAG_CS01})          # +100

    h = Hint.query.join(Hint.challenge).filter_by(code="CS-02").first()
    assert client.post(f"/hint/{h.id}/reveal").get_json()["charged"] == h.point_cost

    html = client.get("/dashboard").get_data(as_text=True)
    assert "spent on hints" in html and "90" in html                # 100 - 10

    again = client.post(f"/hint/{h.id}/reveal").get_json()
    assert again["charged"] == 0 and again["already_revealed"] is True


def test_cannot_reveal_hint_for_locked_stage(client):
    player_session(client, "sneaky")
    locked = Hint.query.join(Hint.challenge).filter_by(code="CS-03").first()
    assert client.post(f"/hint/{locked.id}/reveal").status_code == 403


def test_challenges_page_and_nav_link(client):
    player_session(client, "nav")

    dash = client.get("/dashboard").get_data(as_text=True)
    assert "Investigation Case Files" not in dash
    assert 'href="/challenges"' in dash

    html = client.get("/challenges").get_data(as_text=True)
    assert "Hidden Message" in html and "LOCKED" in html

    logout(client)
    assert client.get("/challenges").status_code == 302


# ====================================================================
# Admin
# ====================================================================
def test_admin_can_open_any_challenge_download_and_use_hints(client):
    login(client, "admin")

    # every challenge opens, including the last one, with no progress at all
    for code in ["CS-01", "CS-03", "CS-06"]:
        assert client.get(f"/challenge/{code}").status_code == 200

    # file download on a locked stage (CS-03 ships a ciphertext file)
    assert client.get("/challenge/CS-03/file").status_code == 200

    # hints are free for the admin
    h = Hint.query.join(Hint.challenge).filter_by(code="CS-06").first()
    assert client.post(f"/hint/{h.id}/reveal").get_json()["charged"] == 0

    # the Challenges page shows no locked cards for the admin
    assert "LOCKED" not in client.get("/challenges").get_data(as_text=True)


def test_admin_flag_test_is_not_recorded(client):
    login(client, "admin")
    r = client.post("/submit/CS-04", data={"flag": "CS{1nput_v4l1d4t10n_m4tt3rs}"})
    assert r.get_json()["correct"] is True and r.get_json()["admin_preview"] is True
    assert Submission.query.count() == 0                   # nothing counted
    assert Progress.query.filter_by(solved=True).count() == 0


def test_regular_player_still_cannot_use_admin_pages(client):
    player_session(client, "plain")
    for url in ["/admin/", "/admin/requests", "/admin/stats", "/admin/logs"]:
        assert client.get(url).status_code == 403
    assert client.post("/admin/requests/approve-all").status_code == 403


def test_admin_panel_three_sections_render(client):
    make_player(client, "pendingguy", approved=False)
    player_session(client, "solver")
    client.post("/submit/CS-01", data={"flag": FLAG_CS01})
    logout(client)

    login(client, "admin")

    matrix = client.get("/admin/").get_data(as_text=True)
    assert "Active Challenge Matrix" in matrix and "Hidden Message" in matrix

    reqs = client.get("/admin/requests").get_data(as_text=True)
    assert "pendingguy" in reqs and "Approve" in reqs

    stats = client.get("/admin/stats").get_data(as_text=True)
    assert "Challenge Performance" in stats and "solver" in stats
    assert "pendingguy" not in stats                         # not approved => not a player yet


def test_admin_stats_search_by_username(client):
    for name in ["alice", "alina", "bob"]:
        make_player(client, name)
    login(client, "admin")

    html = client.get("/admin/stats?q=ali").get_data(as_text=True)
    assert "alice" in html and "alina" in html
    assert ">bob<" not in html                               # filtered out

    html = client.get("/admin/stats?q=ALICE").get_data(as_text=True)   # case-insensitive
    assert "alice" in html and "alina" not in html

    html = client.get("/admin/stats?q=zzz").get_data(as_text=True)
    assert "No players match" in html


def test_admin_user_detail_page(client):
    player_session(client, "detailed")
    client.post("/submit/CS-01", data={"flag": FLAG_CS01})
    uid = User.query.filter_by(username="detailed").first().id
    logout(client)

    login(client, "admin")
    r = client.get(f"/admin/users/{uid}")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "detailed" in html and "Stage by stage" in html and "solved" in html

    admin_id = User.query.filter_by(username="admin").first().id
    assert client.get(f"/admin/users/{admin_id}").status_code == 404   # no detail page for admins


# ====================================================================
# Upgrading an old database
# ====================================================================
def test_old_database_gets_status_column_and_existing_users_stay_approved(tmp_path):
    """
    Builds a database the way it looked BEFORE this feature (no `status`
    column), then starts the app on it. The column must be added and the
    existing player must stay approved, otherwise they would be locked out.
    """
    old_db = tmp_path / "old.db"
    conn = sqlite3.connect(old_db)
    conn.execute(
        'CREATE TABLE "user" (id INTEGER PRIMARY KEY, username VARCHAR(64) NOT NULL UNIQUE, '
        "password_hash VARCHAR(256) NOT NULL, is_admin BOOLEAN, created_at DATETIME)"
    )
    conn.execute(
        'INSERT INTO "user" (username, password_hash, is_admin) VALUES (?, ?, 0)',
        ("veteran", generate_password_hash(PASSWORD)),
    )
    conn.commit()
    conn.close()

    # config.py reads DATABASE_URL only ONCE (when it is first imported), so
    # changing the environment variable now would do nothing. Point the
    # Config class at the old database directly, and put it back afterwards.
    from config import Config

    previous = Config.SQLALCHEMY_DATABASE_URI
    Config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{old_db}"
    try:
        app = create_app()
        with app.app_context():
            veteran = User.query.filter_by(username="veteran").first()
            assert veteran.status == "approved"
            assert veteran.is_approved is True
    finally:
        Config.SQLALCHEMY_DATABASE_URI = previous