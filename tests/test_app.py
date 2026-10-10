"""
tests/test_app.py
------------------
A few basic sanity tests using pytest and Flask's built-in test client
(which lets us make fake requests without actually running a server).

Run with:
    pytest

This is intentionally small -- just enough to prove the core flow
(register -> login -> dashboard -> solve CS-01 -> CS-02 unlocks) keeps
working as you make changes. Add more tests here as you build out
CS-04/CS-06.
"""

import os
import sys

# Make sure Python can find the `app` package when running pytest
# from the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app import create_app, db


@pytest.fixture
def client():
    """
    A pytest "fixture": a reusable setup function. Any test function
    that takes `client` as an argument automatically gets a fresh,
    isolated Flask test client -- an in-memory SQLite database, so
    tests never touch your real database/cybershield.db file.

    IMPORTANT: config.py reads the DATABASE_URL environment variable
    BEFORE create_app() runs, and SQLAlchemy connects to that URI the
    moment db.init_app(app) executes inside create_app(). So we must
    set this env var BEFORE calling create_app() -- setting
    app.config["SQLALCHEMY_DATABASE_URI"] afterwards would be too late
    and the app would stay connected to your real database file.
    """
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    app = create_app()
    app.config["TESTING"] = True

    with app.app_context():
        db.create_all()
        # Import here to avoid touching the real seed.py's app instance
        from seed import CHALLENGES
        from app.models import Challenge, Hint
        from werkzeug.security import generate_password_hash

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
        db.session.commit()

    with app.test_client() as test_client:
        yield test_client


def test_register_and_login(client):
    r = client.post("/register", data={"username": "tester", "password": "Test1234!"})
    assert r.status_code == 302  # 302 = redirect after successful registration

    r = client.post("/login", data={"username": "tester", "password": "Test1234!"})
    assert r.status_code == 302  # redirect to dashboard after successful login


def test_challenge_unlock_progression(client):
    client.post("/register", data={"username": "tester", "password": "Test1234!"})
    client.post("/login", data={"username": "tester", "password": "Test1234!"})

    # Visiting /dashboard is what actually creates this user's Progress
    # rows (see ensure_progress() in app/routes.py) -- a real browser
    # would land here automatically after login redirects.
    client.get("/dashboard")

    # CS-02 should be locked before CS-01 is solved.
    r = client.get("/challenge/CS-02")
    assert r.status_code == 403

    # Submitting the correct CS-01 flag should unlock CS-02.
    r = client.post("/submit/CS-01", data={"flag": "CS{h1dd3n_1n_pl41n_s1ght}"})
    assert r.get_json()["correct"] is True
    assert r.get_json()["unlocked_next"] == "CS-02"

    r = client.get("/challenge/CS-02")
    assert r.status_code == 200


def test_wrong_flag_does_not_unlock_next(client):
    client.post("/register", data={"username": "tester2", "password": "Test1234!"})
    client.post("/login", data={"username": "tester2", "password": "Test1234!"})
    client.get("/dashboard")

    r = client.post("/submit/CS-01", data={"flag": "CS{wrong_guess}"})
    assert r.get_json()["correct"] is False

    r = client.get("/challenge/CS-02")
    assert r.status_code == 403


def test_navbar_shows_operator_and_rank_and_dashboard_stats(client):
    """
    The top-right navbar must show OPERATOR and RANK, and the dashboard's
    new analytics section must reflect a solved stage (score + rank change).
    """
    client.post("/register", data={"username": "alice", "password": "Test1234!"})
    client.post("/register", data={"username": "bob", "password": "Test1234!"})

    # bob logs in first and solves CS-01, so bob should outrank alice
    client.post("/login", data={"username": "bob", "password": "Test1234!"})
    client.get("/dashboard")
    client.post("/submit/CS-01", data={"flag": "CS{h1dd3n_1n_pl41n_s1ght}"})
    client.get("/logout")

    client.post("/login", data={"username": "alice", "password": "Test1234!"})
    html = client.get("/dashboard").get_data(as_text=True)
    assert "OPERATOR:" in html and "alice" in html
    assert "RANK:" in html and "#2" in html      # alice is 2nd of 2
    assert "Challenges Completed" in html and "Score Progression" in html


def _login_and_open(client, username):
    """Helper: register + log in + visit the dashboard (creates Progress rows)."""
    client.post("/register", data={"username": username, "password": "Test1234!"})
    client.post("/login", data={"username": username, "password": "Test1234!"})
    client.get("/dashboard")


def test_hint_text_is_not_in_page_until_revealed(client):
    from app.models import Hint
    _login_and_open(client, "hinter")

    hint = Hint.query.filter_by(order_index=0).first()
    page = client.get("/challenge/CS-01").get_data(as_text=True)
    assert hint.text not in page      # the secret must NOT be in the HTML source

    r = client.post(f"/hint/{hint.id}/reveal")
    assert r.get_json()["text"] == hint.text

    page = client.get("/challenge/CS-01").get_data(as_text=True)
    assert hint.text in page          # once paid for, it stays visible


def test_hint_cost_is_deducted_once_and_free_after_solving(client):
    from app.models import Hint
    _login_and_open(client, "payer")

    # earn 100 pts first (CS-01), then check the baseline score
    client.post("/submit/CS-01", data={"flag": "CS{h1dd3n_1n_pl41n_s1ght}"})
    assert "100" in client.get("/dashboard").get_data(as_text=True)

    # CS-02 is now unlocked; reveal one of its hints (cost 10)
    h = Hint.query.join(Hint.challenge).filter_by(code="CS-02").first()
    r = client.post(f"/hint/{h.id}/reveal")
    assert r.get_json()["charged"] == h.point_cost

    html = client.get("/dashboard").get_data(as_text=True)
    assert "spent on hints" in html and "90" in html   # 100 - 10

    # revealing the SAME hint again must not charge a second time
    r = client.post(f"/hint/{h.id}/reveal")
    assert r.get_json()["charged"] == 0 and r.get_json()["already_revealed"] is True
    assert "90" in client.get("/dashboard").get_data(as_text=True)


def test_cannot_reveal_hint_for_locked_stage(client):
    from app.models import Hint
    _login_and_open(client, "sneaky")

    locked = Hint.query.join(Hint.challenge).filter_by(code="CS-03").first()
    assert client.post(f"/hint/{locked.id}/reveal").status_code == 403


def test_challenges_page_and_nav_link(client):
    """Challenge cards now live on /challenges, not on the dashboard."""
    client.post("/register", data={"username": "nav", "password": "Test1234!"})
    client.post("/login", data={"username": "nav", "password": "Test1234!"})

    dash = client.get("/dashboard").get_data(as_text=True)
    assert "Investigation Case Files" not in dash       # removed from dashboard
    assert "Hidden Message" not in dash                 # no challenge cards there
    assert 'href="/challenges"' in dash and "Challenges</a>" in dash   # nav link exists

    page = client.get("/challenges")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Hidden Message" in html and "LOCKED" in html   # CS-01 open, others locked

    # must be login-protected
    client.get("/logout")
    assert client.get("/challenges").status_code == 302