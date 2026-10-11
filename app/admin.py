"""
app/admin.py
------------
The admin panel. Every route here is admin-only. It has three sections
(shown as tabs on the page) plus two extra pages:

    /admin                  Section 1  Active Challenge Matrix
    /admin/requests         Section 2  Registration Requests (approve / reject)
    /admin/stats            Section 3  Challenge Statistics (+ username search)
    /admin/users/<id>       one player's detailed progress (opened from section 3)
    /admin/logs             the system audit log (button on section 1)

This used to live inside routes.py. It moved into its own blueprint
because it grew: a blueprint is just a "mini app" of related routes
that app/__init__.py plugs in with the URL prefix "/admin".
"""

from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import Challenge, Hint, HintReveal, LogEntry, Progress, Submission, User
from app.routes import build_leaderboard

admin_bp = Blueprint("admin", __name__)


# ====================================================================
# Access control
# ====================================================================
def admin_required(view):
    """
    Decorator: put @admin_required under @admin_bp.route(...) to make a
    page admin-only. Not logged in -> sent to the login page.
    Logged in but not an admin -> 403 Forbidden.

    IMPORTANT: this check happens on the SERVER. Hiding the Admin link
    in the navbar is only cosmetic; this is the real protection.
    """

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return login_required(wrapped)


def approved_players():
    """Every approved, non-admin account -- the people actually playing."""
    return User.query.filter_by(is_admin=False, status="approved").all()


def percent(part, whole):
    """Whole-number percentage that never divides by zero."""
    return round(part / whole * 100) if whole else 0


# ====================================================================
# SECTION 1 -- Active Challenge Matrix
# ====================================================================
@admin_bp.route("/")
@admin_required
def matrix():
    """
    One row per challenge: how many players have it unlocked, how many
    solved it, how many attempts were made, and the completion rate.
    """
    challenges = Challenge.query.order_by(Challenge.order_index).all()
    players = approved_players()
    player_ids = [u.id for u in players]

    unlocked, solved, attempts = {}, {}, {}

    if player_ids:
        # Three grouped queries (one per number) instead of three
        # queries per challenge -- much faster as the data grows.
        for cid, n in (
            db.session.query(Progress.challenge_id, db.func.count(Progress.id))
            .filter(Progress.user_id.in_(player_ids), Progress.unlocked.is_(True))
            .group_by(Progress.challenge_id)
        ):
            unlocked[cid] = n

        for cid, n in (
            db.session.query(Progress.challenge_id, db.func.count(Progress.id))
            .filter(Progress.user_id.in_(player_ids), Progress.solved.is_(True))
            .group_by(Progress.challenge_id)
        ):
            solved[cid] = n

        for cid, n in (
            db.session.query(Submission.challenge_id, db.func.count(Submission.id))
            .filter(Submission.user_id.in_(player_ids))
            .group_by(Submission.challenge_id)
        ):
            attempts[cid] = n

    rows = []
    for ch in challenges:
        u, s = unlocked.get(ch.id, 0), solved.get(ch.id, 0)
        rows.append(
            {
                "challenge": ch,
                "unlocked": u,
                "solved": s,
                "attempts": attempts.get(ch.id, 0),
                "rate": percent(s, u),   # of the players who unlocked it, % who solved it
            }
        )

    return render_template(
        "admin_dashboard.html", rows=rows, player_count=len(players), active_tab="matrix"
    )


# ====================================================================
# SECTION 2 -- Registration Requests
# ====================================================================
@admin_bp.route("/requests")
@admin_required
def requests_page():
    """Lists accounts waiting for approval, plus ones that were rejected."""
    pending = (
        User.query.filter_by(is_admin=False, status="pending").order_by(User.created_at).all()
    )
    rejected = (
        User.query.filter_by(is_admin=False, status="rejected").order_by(User.created_at.desc()).all()
    )
    approved_count = User.query.filter_by(is_admin=False, status="approved").count()

    return render_template(
        "admin_requests.html",
        pending=pending,
        rejected=rejected,
        approved_count=approved_count,
        active_tab="requests",
    )


def get_player_or_404(user_id):
    """Fetch a user for an approve/reject action. Admin accounts are untouchable."""
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        abort(403)
    return user


@admin_bp.route("/requests/<int:user_id>/approve", methods=["POST"])
@admin_required
def approve_request(user_id):
    user = get_player_or_404(user_id)
    user.status = "approved"
    db.session.add(
        LogEntry(
            event_type="approve",
            user_id=current_user.id,
            detail=f"{current_user.username} approved '{user.username}'",
        )
    )
    db.session.commit()
    flash(f"{user.username} approved. They can log in now.", "success")
    return redirect(url_for("admin.requests_page"))


@admin_bp.route("/requests/<int:user_id>/reject", methods=["POST"])
@admin_required
def reject_request(user_id):
    user = get_player_or_404(user_id)
    user.status = "rejected"
    db.session.add(
        LogEntry(
            event_type="reject",
            user_id=current_user.id,
            detail=f"{current_user.username} rejected '{user.username}'",
        )
    )
    db.session.commit()
    flash(f"{user.username}'s request was rejected.", "error")
    return redirect(url_for("admin.requests_page"))


@admin_bp.route("/requests/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete_request(user_id):
    """
    Deletes a pending/rejected request so the username becomes free to
    register again. APPROVED players are never deleted here: they may
    already have scores, submissions and progress attached.
    """
    user = get_player_or_404(user_id)
    if user.status == "approved":
        abort(400)

    name = user.username
    db.session.delete(user)
    db.session.add(
        LogEntry(
            event_type="delete_request",
            user_id=current_user.id,
            detail=f"{current_user.username} deleted the request from '{name}'",
        )
    )
    db.session.commit()
    flash(f"Request from {name} deleted. That username can register again.", "success")
    return redirect(url_for("admin.requests_page"))


@admin_bp.route("/requests/approve-all", methods=["POST"])
@admin_required
def approve_all():
    """Approves every pending request in one click."""
    pending = User.query.filter_by(is_admin=False, status="pending").all()
    for user in pending:
        user.status = "approved"
    if pending:
        db.session.add(
            LogEntry(
                event_type="approve",
                user_id=current_user.id,
                detail=f"{current_user.username} approved {len(pending)} pending request(s)",
            )
        )
    db.session.commit()
    flash(f"{len(pending)} request(s) approved.", "success")
    return redirect(url_for("admin.requests_page"))


# ====================================================================
# SECTION 3 -- Challenge Statistics (with username search)
# ====================================================================
@admin_bp.route("/stats")
@admin_required
def statistics():
    """
    Three blocks of numbers:
      1. summary cards (players, solves, attempts, hints...)
      2. one row per challenge (how it is performing)
      3. one row per player (their progress), searchable by username
    """
    search = request.args.get("q", "").strip()
    sort = request.args.get("sort", "rank")

    challenges = Challenge.query.order_by(Challenge.order_index).all()
    players = {u.id: u for u in approved_players()}
    player_ids = list(players)

    # ---------- load everything we need in a few queries ----------
    progress_rows = (
        Progress.query.filter(Progress.user_id.in_(player_ids)).all() if player_ids else []
    )
    by_user = {}                       # {user_id: {challenge_id: Progress}}
    for p in progress_rows:
        by_user.setdefault(p.user_id, {})[p.challenge_id] = p

    attempts_by_challenge = {}
    if player_ids:
        for cid, n in (
            db.session.query(Submission.challenge_id, db.func.count(Submission.id))
            .filter(Submission.user_id.in_(player_ids))
            .group_by(Submission.challenge_id)
        ):
            attempts_by_challenge[cid] = n

    # which challenge does each hint belong to? (to count hints per challenge)
    hint_to_challenge = {h.id: h.challenge_id for h in Hint.query.all()}
    hints_by_user, hint_cost_by_user, hints_by_challenge = {}, {}, {}
    reveals = HintReveal.query.filter(HintReveal.user_id.in_(player_ids)).all() if player_ids else []
    for r in reveals:
        hints_by_user[r.user_id] = hints_by_user.get(r.user_id, 0) + 1
        hint_cost_by_user[r.user_id] = hint_cost_by_user.get(r.user_id, 0) + (r.cost_paid or 0)
        cid = hint_to_challenge.get(r.hint_id)
        hints_by_challenge[cid] = hints_by_challenge.get(cid, 0) + 1

    # ---------- per-challenge table ----------
    challenge_rows = []
    for ch in challenges:
        unlocked = solved = 0
        first = None                   # earliest solver of this challenge
        for uid, per_challenge in by_user.items():
            p = per_challenge.get(ch.id)
            if not p:
                continue
            if p.unlocked:
                unlocked += 1
            if p.solved:
                solved += 1
                if p.solved_at and (first is None or p.solved_at < first[1]):
                    first = (players[uid].username, p.solved_at)
        challenge_rows.append(
            {
                "challenge": ch,
                "unlocked": unlocked,
                "solved": solved,
                "rate": percent(solved, unlocked),
                "attempts": attempts_by_challenge.get(ch.id, 0),
                "hints": hints_by_challenge.get(ch.id, 0),
                "first": first,
            }
        )

    # ---------- per-player table ----------
    board = build_leaderboard()        # already ranked; points include hint costs
    player_rows = []
    for entry in board:
        uid = entry["user_id"]
        states = []
        for ch in challenges:
            p = by_user.get(uid, {}).get(ch.id)
            state = "solved" if p and p.solved else ("open" if p and p.unlocked else "locked")
            states.append({"code": ch.code, "name": ch.name, "state": state})
        player_rows.append(
            {
                **entry,
                "states": states,
                "pct": percent(entry["solved"], len(challenges)),
                "hints_used": hints_by_user.get(uid, 0),
                "hint_penalty": hint_cost_by_user.get(uid, 0),
            }
        )

    total_players = len(player_rows)

    # ---------- search by username (case-insensitive, partial match) ----------
    if search:
        player_rows = [r for r in player_rows if search.lower() in r["username"].lower()]

    # ---------- sorting ----------
    if sort == "name":
        player_rows.sort(key=lambda r: r["username"].lower())
    elif sort == "solved":
        player_rows.sort(key=lambda r: (-r["solved"], r["rank"]))
    elif sort == "recent":
        player_rows.sort(key=lambda r: (r["last_solve"] is None, -(r["last_solve"].timestamp() if r["last_solve"] else 0)))
    else:
        sort = "rank"                  # board is already in rank order

    # ---------- summary cards ----------
    total_solves = sum(r["solved"] for r in challenge_rows)
    summary = {
        "players": total_players,
        "pending": User.query.filter_by(is_admin=False, status="pending").count(),
        "solves": total_solves,
        "completion": percent(total_solves, total_players * len(challenges)),
        "attempts": sum(attempts_by_challenge.values()),
        "hints": len(reveals),
        "hint_points": sum(hint_cost_by_user.values()),
    }

    return render_template(
        "admin_stats.html",
        summary=summary,
        challenge_rows=challenge_rows,
        player_rows=player_rows,
        total_players=total_players,
        search=search,
        sort=sort,
        active_tab="stats",
    )


@admin_bp.route("/users/<int:user_id>")
@admin_required
def user_detail(user_id):
    """One player's challenge-by-challenge progress (opened from the stats table)."""
    user = User.query.get_or_404(user_id)
    if user.is_admin or not user.is_approved:
        abort(404)

    challenges = Challenge.query.order_by(Challenge.order_index).all()
    progress = {p.challenge_id: p for p in Progress.query.filter_by(user_id=user.id).all()}
    hint_to_challenge = {h.id: h.challenge_id for h in Hint.query.all()}

    attempts, wrong = {}, {}
    for sub in Submission.query.filter_by(user_id=user.id).all():
        attempts[sub.challenge_id] = attempts.get(sub.challenge_id, 0) + 1
        if not sub.is_correct:
            wrong[sub.challenge_id] = wrong.get(sub.challenge_id, 0) + 1

    hints, hint_cost = {}, {}
    for r in HintReveal.query.filter_by(user_id=user.id).all():
        cid = hint_to_challenge.get(r.hint_id)
        hints[cid] = hints.get(cid, 0) + 1
        hint_cost[cid] = hint_cost.get(cid, 0) + (r.cost_paid or 0)

    rows = []
    for ch in challenges:
        p = progress.get(ch.id)
        state = "solved" if p and p.solved else ("open" if p and p.unlocked else "locked")
        rows.append(
            {
                "challenge": ch,
                "state": state,
                "solved_at": p.solved_at if p and p.solved else None,
                "attempts": attempts.get(ch.id, 0),
                "wrong": wrong.get(ch.id, 0),
                "hints": hints.get(ch.id, 0),
                "hint_cost": hint_cost.get(ch.id, 0),
                "earned": ch.points if state == "solved" else 0,
            }
        )

    board = build_leaderboard()
    entry = next((r for r in board if r["user_id"] == user.id), None)

    recent = (
        LogEntry.query.filter_by(user_id=user.id).order_by(LogEntry.timestamp.desc()).limit(15).all()
    )

    return render_template(
        "admin_user.html",
        player=user,
        rows=rows,
        entry=entry,
        total_players=len(board),
        total_challenges=len(challenges),
        recent=recent,
        active_tab="stats",
    )


# ====================================================================
# System logs (button on Section 1)
# ====================================================================
@admin_bp.route("/logs")
@admin_required
def logs():
    """The most recent 300 audit-log entries."""
    entries = LogEntry.query.order_by(LogEntry.timestamp.desc()).limit(300).all()
    return render_template("admin_logs.html", entries=entries, active_tab=None)