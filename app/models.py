"""
app/models.py
-------------
This file defines the DATABASE TABLES as Python classes, using
SQLAlchemy's "ORM" (Object-Relational Mapper). Each class below
becomes a table; each class attribute becomes a column.

You never write raw SQL with this approach -- e.g. instead of
    SELECT * FROM user WHERE username = 'bob'
you write
    User.query.filter_by(username='bob').first()
and SQLAlchemy translates that into SQL for you.
"""

from datetime import datetime

from flask_login import UserMixin

from app import db

# UserMixin gives our User class the methods Flask-Login expects every
# "user" object to have (is_authenticated, is_active, get_id(), etc.)
# so we don't have to write them ourselves.


class User(db.Model, UserMixin):
    """One row per registered participant (or admin)."""

    id = db.Column(db.Integer, primary_key=True)

    # unique=True means the database itself will reject a duplicate
    # username -- an extra safety net beyond our own checks in auth.py.
    username = db.Column(db.String(64), unique=True, nullable=False)

    # We NEVER store the actual password. password_hash stores the
    # output of werkzeug's generate_password_hash(), a one-way hash.
    # Even if the database leaks, the real passwords aren't exposed.
    password_hash = db.Column(db.String(256), nullable=False)

    # Marks whether this account can see /admin pages.
    is_admin = db.Column(db.Boolean, default=False)

    # ------------------------------------------------------------------
    # status: the registration-approval state of this account.
    #   "pending"  -> just registered, waiting for an admin to decide
    #   "approved" -> allowed to log in
    #   "rejected" -> the admin declined the request
    # New sign-ups start as "pending" (set in auth.py). server_default
    # is what the database fills in for rows that exist WITHOUT a value
    # (accounts created before this feature) -- those are "approved",
    # so nobody who already had an account gets locked out.
    # ------------------------------------------------------------------
    status = db.Column(
        db.String(16), nullable=False, default="pending", server_default="approved"
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def is_approved(self):
        """True when an admin has approved this account."""
        return self.status == "approved"

    @property
    def is_active(self):
        """
        Flask-Login asks every user object "are you active?". We say
        yes only for approved accounts, so a pending or rejected
        account can never be logged in, even by mistake.
        """
        return self.is_approved


class Challenge(db.Model):
    """One row per CTF stage (CS-01 through CS-06)."""

    id = db.Column(db.Integer, primary_key=True)

    # Short human-readable code shown in the UI and used in URLs,
    # e.g. "CS-01". unique=True because two challenges can't share one.
    code = db.Column(db.String(16), unique=True, nullable=False)

    name = db.Column(db.String(128), nullable=False)          # "Hidden Message"
    category = db.Column(db.String(64), nullable=False)       # "Steganography"
    difficulty = db.Column(db.String(32), nullable=False)     # "Easy" / "Hard" / etc.

    scenario = db.Column(db.Text)        # the story/backstory text
    description = db.Column(db.Text, nullable=False)  # what the player must actually do

    # We store a HASH of the flag, never the flag itself in plaintext.
    # This means even someone with direct database access can't read
    # off the answers -- they'd have to actually solve the challenge.
    flag_hash = db.Column(db.String(256), nullable=False)

    # Controls stage order and unlock sequence: challenge with
    # order_index=0 unlocks first; solving it unlocks order_index=1, etc.
    order_index = db.Column(db.Integer, nullable=False)

    # Relative path INSIDE the challenges/ folder, e.g.
    # "cs01_hidden_message/employee_photo.jpg". Left as None (NULL)
    # for challenges that don't have a downloadable file (CS-02, CS-04,
    # CS-06 -- these are browser/service-based instead).
    file_path = db.Column(db.String(256))

    points = db.Column(db.Integer, default=100)

    # This creates a virtual attribute `challenge.hints` that
    # automatically fetches every Hint row whose challenge_id matches
    # this Challenge's id -- we never set it manually.
    hints = db.relationship(
        "Hint", backref="challenge", lazy=True, order_by="Hint.order_index"
    )


class Hint(db.Model):
    """One row per hint. A Challenge can have many Hints."""

    id = db.Column(db.Integer, primary_key=True)

    # ForeignKey links this row to a specific Challenge's id --
    # this is what makes `challenge.hints` (above) work.
    challenge_id = db.Column(db.Integer, db.ForeignKey("challenge.id"), nullable=False)

    text = db.Column(db.Text, nullable=False)
    order_index = db.Column(db.Integer, default=0)   # display order: 1st hint, 2nd hint...
    point_cost = db.Column(db.Integer, default=10)   # "cost" shown to the player if they reveal it


class HintReveal(db.Model):
    """One row each time a player pays to reveal a hint.

    This table is what makes hint costs real:
      - it remembers WHO revealed WHICH hint (so a hint is only paid
        for once, even if the player reopens the page), and
      - cost_paid stores the points taken off AT THAT MOMENT, so
        editing a hint's point_cost later never rewrites history.
    The player's score is: points from solved stages MINUS the sum of
    cost_paid over all their HintReveal rows (never below zero).
    """

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    hint_id = db.Column(db.Integer, db.ForeignKey("hint.id"), nullable=False)
    cost_paid = db.Column(db.Integer, default=0)
    revealed_at = db.Column(db.DateTime, default=datetime.utcnow)

    # A player can reveal a given hint only once: the database itself
    # refuses a duplicate (user_id, hint_id) pair.
    __table_args__ = (db.UniqueConstraint("user_id", "hint_id", name="uq_user_hint"),)


class Submission(db.Model):
    """One row EVERY TIME a player submits a flag -- correct or not.

    This is our audit trail: who tried what, and when.
    """

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey("challenge.id"), nullable=False)
    submitted_flag = db.Column(db.String(256))
    is_correct = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class Progress(db.Model):
    """One row per (user, challenge) pair -- tracks unlock/solve state.

    Every user gets one Progress row per challenge (created the first
    time they visit their dashboard -- see ensure_progress() in
    routes.py). This is how we know which stage each player is on.
    """

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey("challenge.id"), nullable=False)
    unlocked = db.Column(db.Boolean, default=False)   # can they currently access this stage?
    solved = db.Column(db.Boolean, default=False)     # have they submitted the correct flag?
    solved_at = db.Column(db.DateTime)


class LogEntry(db.Model):
    """One row per event we want to audit: logins, submissions, etc.

    This powers the /admin/logs page.
    """

    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(64))   # "login" / "logout" / "submission" / etc.

    # nullable=True because some events (a failed login with a typo'd
    # username) don't correspond to any real, known user.
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    detail = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)