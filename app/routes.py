"""
app/routes.py
-------------
Every route EXCEPT login/register/logout (those live in app/auth.py).
This includes: the landing page, the dashboard, individual challenge
pages, flag submission, the scoreboard, and the admin console.

Like auth.py, this is a Blueprint -- a "mini app" plugged into the
real Flask app inside app/__init__.py.
"""

from datetime import datetime, timedelta

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    render_template,
    request,
    send_from_directory,
)
from flask_login import current_user, login_required
from werkzeug.security import check_password_hash

from app import db
from app.models import Challenge, Hint, HintReveal, LogEntry, Progress, Submission, User

# "main" is this blueprint's name -> endpoints are "main.index",
# "main.dashboard", etc., used in url_for() calls and templates.
main_bp = Blueprint("main", __name__)


def ensure_progress(user):
    """
    Make sure the given user has a Progress row for EVERY challenge.

    We call this the first time a user visits their dashboard, rather
    than at registration time, so that adding a new challenge later
    (e.g. a CS-07) automatically works for existing users too.

    Only the very first challenge (order_index == 0) starts unlocked;
    every other one starts locked until the previous one is solved.
    """
    all_challenges = Challenge.query.order_by(Challenge.order_index).all()

    # Which challenge IDs does this user already have a Progress row for?
    existing_ids = {p.challenge_id for p in Progress.query.filter_by(user_id=user.id).all()}

    for i, ch in enumerate(all_challenges):
        if ch.id not in existing_ids:
            db.session.add(
                Progress(user_id=user.id, challenge_id=ch.id, unlocked=(i == 0))
            )

    db.session.commit()


# --------------------------------------------------------------------
# CATEGORY_ICONS: which Font Awesome icon to show next to each category
# in the dashboard's "Category Breakdown" card. Any category that isn't
# listed here just gets the default icon, so adding a new challenge
# category later will never crash anything.
# --------------------------------------------------------------------
CATEGORY_ICONS = {
    "Steganography": "fa-image",
    "OSINT / Reconnaissance": "fa-magnifying-glass",
    "Cryptography": "fa-lock",
    "Web Security": "fa-shield-halved",
    "Digital Forensics": "fa-fingerprint",
    "Linux / System Security": "fa-terminal",
}
DEFAULT_CATEGORY_ICON = "fa-layer-group"


def build_leaderboard():
    """
    Build the full ranking of every non-admin player.

    Returns a list of dicts, best player first:
        {"user_id", "username", "solved", "points", "last_solve", "rank"}

    Both the scoreboard page AND the navbar's "current rank" badge use
    this one function, so they can never disagree with each other.

    Ranking rule: more points wins; if points are tied, whoever reached
    their latest solve EARLIER wins (so being first to a score counts).
    """
    players = User.query.filter_by(is_admin=False).all()

    # Start every player at zero so people who haven't solved anything
    # still appear on the board.
    table = {
        u.id: {"user_id": u.id, "username": u.username,
               "solved": 0, "points": 0, "last_solve": None}
        for u in players
    }

    # ONE database query returns every solved stage together with the
    # points it is worth (a JOIN between Progress and Challenge).
    # Doing this in a single query is much faster than asking the
    # database a separate question for every player.
    solved_rows = (
        db.session.query(Progress.user_id, Challenge.points, Progress.solved_at)
        .join(Challenge, Challenge.id == Progress.challenge_id)
        .filter(Progress.solved.is_(True))
        .all()
    )

    for user_id, points, solved_at in solved_rows:
        entry = table.get(user_id)
        if entry is None:
            continue  # an admin account: admins are not ranked
        entry["solved"] += 1
        entry["points"] += points
        if solved_at and (entry["last_solve"] is None or solved_at > entry["last_solve"]):
            entry["last_solve"] = solved_at

    # Subtract what each player paid for hints. We add up cost_paid per
    # player in one grouped query, then take it off their points.
    # max(0, ...) means paying for hints can never push a score below zero.
    hint_costs = (
        db.session.query(HintReveal.user_id, db.func.sum(HintReveal.cost_paid))
        .group_by(HintReveal.user_id)
        .all()
    )
    for user_id, total_cost in hint_costs:
        entry = table.get(user_id)
        if entry is not None:
            entry["points"] = max(0, entry["points"] - (total_cost or 0))

    board = list(table.values())

    # Sort: highest points first; ties -> earliest last_solve first.
    # datetime.max is a stand-in for "never solved", pushing them down.
    board.sort(key=lambda row: (-row["points"], row["last_solve"] or datetime.max))

    for position, row in enumerate(board, start=1):
        row["rank"] = position

    return board


@main_bp.app_context_processor
def inject_navbar_info():
    """
    A "context processor" automatically adds extra variables to EVERY
    template, so base.html can show the player's current rank in the
    navbar without each route having to pass it in manually.

    Admins aren't ranked, so for them we add nothing (base.html shows
    an ADMIN badge instead).
    """
    if not current_user.is_authenticated or current_user.is_admin:
        return {}

    board = build_leaderboard()
    my_rank = next((r["rank"] for r in board if r["user_id"] == current_user.id), None)
    return {"nav_rank": my_rank, "nav_total_players": len(board)}


def build_dashboard_stats(user, all_challenges, progress_map):
    """
    Collects every number the dashboard's new analytics section needs:
    the two metric boxes, the score-progression chart, and the
    category-breakdown bars. Returned as one dict for the template.
    """
    by_id = {c.id: c for c in all_challenges}
    total_challenges = len(all_challenges)
    max_points = sum(c.points for c in all_challenges) or 1  # avoid dividing by zero

    # This player's solved stages, oldest solve first (needed for the chart).
    solved = sorted(
        (p for p in progress_map.values() if p.solved),
        key=lambda p: p.solved_at or datetime.min,
    )

    solved_points = sum(by_id[p.challenge_id].points for p in solved)

    # Every hint this player paid for (cost_paid is 0 for free reveals,
    # e.g. hints opened after the stage was already solved).
    reveals = HintReveal.query.filter_by(user_id=user.id).all()
    hint_penalty = sum(r.cost_paid or 0 for r in reveals)

    # Final score = solved points minus hint costs, never below zero.
    score = max(0, solved_points - hint_penalty)

    day_ago = datetime.utcnow() - timedelta(hours=24)
    solved_24h = sum(1 for p in solved if p.solved_at and p.solved_at >= day_ago)

    # ---------------- rank (None for admin accounts) ----------------
    board = build_leaderboard()
    rank = next((r["rank"] for r in board if r["user_id"] == user.id), None)

    # ---------------- score-progression chart -----------------------
    # The chart is an SVG drawn in a 500 x 200 coordinate box. We turn
    # "cumulative score after each solve" into (x, y) points:
    #   x: spread evenly from 0 (start) to 500 (latest solve)
    #   y: 195 = zero points (bottom), 20 = every point earned (top)
    def y_for(points):
        return 195 - (points / max_points) * 175

    # Chart events = every solve (+points) and every PAID hint (-points),
    # in the order they happened, so the line goes UP on a solve and
    # DOWN when a hint is bought.
    events = [(p.solved_at or datetime.min, by_id[p.challenge_id].points) for p in solved]
    events += [(r.revealed_at, -(r.cost_paid or 0)) for r in reveals if r.cost_paid]
    events.sort(key=lambda e: e[0])

    coords = [(0, y_for(0))]
    running = 0
    for i, (_when, delta) in enumerate(events, start=1):
        running += delta
        coords.append((500 * i / len(events), y_for(max(0, running))))

    if len(coords) == 1:                       # nothing happened yet: flat line
        coords.append((500, y_for(0)))

    line_path = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area_path = line_path + " L 500,200 L 0,200 Z"

    # The glowing dots are normal HTML elements positioned with
    # percentages (an SVG with preserveAspectRatio="none" would
    # squash circles into ovals), so convert coordinates to percents.
    dots = []
    if events:
        for x, y in coords[1:]:
            dots.append({"left": x / 500 * 100, "bottom": (200 - y) / 200 * 100})

    # ---------------- category breakdown bars -----------------------
    # Group challenges by category and count how many this player solved.
    categories = {}
    for c in all_challenges:
        entry = categories.setdefault(
            c.category,
            {"name": c.category, "total": 0, "solved": 0,
             "icon": CATEGORY_ICONS.get(c.category, DEFAULT_CATEGORY_ICON)},
        )
        entry["total"] += 1
        p = progress_map.get(c.id)
        if p and p.solved:
            entry["solved"] += 1

    category_list = list(categories.values())
    for entry in category_list:
        entry["pct"] = round(entry["solved"] / entry["total"] * 100)

    completion = round(len(solved) / total_challenges * 100) if total_challenges else 0

    return {
        "solved_count": len(solved),
        "total_challenges": total_challenges,
        "score": score,
        "hint_penalty": hint_penalty,
        "max_points": max_points,
        "solved_24h": solved_24h,
        "rank": rank,
        "total_players": len(board),
        "line_path": line_path,
        "area_path": area_path,
        "dots": dots,
        "categories": category_list,
        "completion": completion,
    }


@main_bp.route("/")
def index():
    """The public landing page -- no login required."""
    return render_template("index.html")


@main_bp.route("/dashboard")
@login_required
def dashboard():
    """
    The player's home screen: analytics only (metric boxes, score
    chart, category breakdown). The challenge cards live on their own
    page now -- see challenge_list() below.
    """
    ensure_progress(current_user)

    all_challenges = Challenge.query.order_by(Challenge.order_index).all()
    progress_map = {
        p.challenge_id: p for p in Progress.query.filter_by(user_id=current_user.id).all()
    }

    stats = build_dashboard_stats(current_user, all_challenges, progress_map)

    return render_template("dashboard.html", stats=stats)


@main_bp.route("/challenges")
@login_required
def challenge_list():
    """
    The "Challenges" page (nav link): every stage as a card that is
    locked, unlocked-but-unsolved, or solved for THIS player.
    """
    ensure_progress(current_user)

    all_challenges = Challenge.query.order_by(Challenge.order_index).all()

    # {challenge_id: Progress row}, so the template can look up each
    # card's state without a separate database query per card.
    progress_map = {
        p.challenge_id: p for p in Progress.query.filter_by(user_id=current_user.id).all()
    }

    return render_template("challenges.html", challenges=all_challenges, progress=progress_map)


@main_bp.route("/challenge/<code>")
@login_required
def detail(code):
    """
    Shows one challenge's scenario, description, hints, file download
    link (if any), and the flag submission box.

    <code> in the route captures whatever's in the URL, e.g. visiting
    /challenge/CS-01 calls this function with code="CS-01".
    """
    # first_or_404() automatically returns a proper 404 error page if
    # no Challenge with this code exists, instead of crashing.
    challenge = Challenge.query.filter_by(code=code).first_or_404()

    progress = Progress.query.filter_by(
        user_id=current_user.id, challenge_id=challenge.id
    ).first()

    # abort(403) = "Forbidden". This is the security check that stops
    # someone from just typing /challenge/CS-06 into the URL bar to
    # skip ahead before they've actually unlocked it.
    if not progress or not progress.unlocked:
        abort(403)

    # IDs of hints this player has already paid for. challenge.html shows
    # the text only for these; every other hint stays on the server until
    # it is requested through reveal_hint() below.
    revealed_ids = {
        r.hint_id for r in HintReveal.query.filter_by(user_id=current_user.id).all()
    }

    return render_template(
        "challenge.html", challenge=challenge, progress=progress, revealed_ids=revealed_ids
    )


@main_bp.route("/hint/<int:hint_id>/reveal", methods=["POST"])
@login_required
def reveal_hint(hint_id):
    """
    Reveals one hint and charges its point cost (once per player).

    Called by JavaScript in challenge.html when a hint button is
    clicked. The hint TEXT is only sent back here, after payment is
    recorded -- it is never in the page source beforehand.
    """
    hint = Hint.query.get_or_404(hint_id)
    challenge = hint.challenge   # the backref created by Challenge.hints

    # Same lock check as the challenge page: no peeking at hints for
    # stages you haven't unlocked yet.
    progress = Progress.query.filter_by(
        user_id=current_user.id, challenge_id=challenge.id
    ).first()
    if not progress or not progress.unlocked:
        abort(403)

    already = HintReveal.query.filter_by(user_id=current_user.id, hint_id=hint.id).first()

    if not already:
        # Hints on a stage you've ALREADY solved are free -- there is
        # nothing left to lose points on.
        cost = 0 if progress.solved else (hint.point_cost or 0)

        db.session.add(HintReveal(user_id=current_user.id, hint_id=hint.id, cost_paid=cost))
        db.session.add(
            LogEntry(
                event_type="hint",
                user_id=current_user.id,
                detail=f"{current_user.username} revealed a hint on {challenge.code} (-{cost} pts)",
            )
        )
        db.session.commit()
        charged = cost
    else:
        charged = 0   # already paid earlier, so no second charge

    return jsonify(text=hint.text, charged=charged, already_revealed=bool(already))


@main_bp.route("/challenge/<code>/file")
@login_required
def challenge_file(code):
    """
    Serves the downloadable file for a challenge (e.g. CS-01's image),
    read from the challenges/ folder on disk.
    """
    challenge = Challenge.query.filter_by(code=code).first_or_404()
    progress = Progress.query.filter_by(
        user_id=current_user.id, challenge_id=challenge.id
    ).first()

    # Same unlock check as detail() above -- and also make sure this
    # particular challenge actually HAS a file (CS-02/04/06 don't).
    if not progress or not progress.unlocked or not challenge.file_path:
        abort(403)

    # challenge.file_path looks like "cs01_hidden_message/employee_photo.jpg".
    # send_from_directory safely joins that onto CHALLENGES_FOLDER and
    # streams the file back -- and importantly, it protects against
    # "path traversal" tricks (e.g. someone requesting "../../config.py").
    return send_from_directory(
        current_app.config["CHALLENGES_FOLDER"], challenge.file_path, as_attachment=True
    )


@main_bp.route("/submit/<code>", methods=["POST"])
@login_required
def submit(code):
    """
    Receives a flag submission via JavaScript (fetch()) from
    challenge.html, checks it, records it, and unlocks the next
    stage if it's correct. Returns JSON, not a full HTML page.
    """
    challenge = Challenge.query.filter_by(code=code).first_or_404()
    progress = Progress.query.filter_by(
        user_id=current_user.id, challenge_id=challenge.id
    ).first()

    if not progress or not progress.unlocked:
        abort(403)

    submitted = request.form.get("flag", "").strip()

    # check_password_hash works for ANY hash made with
    # generate_password_hash -- we're reusing the same hashing
    # mechanism from auth.py to protect flags, not just passwords.
    # This means the correct flag is NEVER stored or compared in
    # plaintext anywhere in this file.
    is_correct = check_password_hash(challenge.flag_hash, submitted)

    # Log this attempt regardless of whether it was right or wrong --
    # this audit trail is what powers /admin and the per-challenge
    # attempt counts.
    db.session.add(
        Submission(
            user_id=current_user.id,
            challenge_id=challenge.id,
            submitted_flag=submitted,
            is_correct=is_correct,
        )
    )
    db.session.add(
        LogEntry(
            event_type="submission",
            user_id=current_user.id,
            detail=f"{current_user.username} -> {code}: {'correct' if is_correct else 'incorrect'}",
        )
    )

    # newly_unlocked_code lets the front-end show "CS-02 unlocked!"
    # immediately, without the player needing to refresh the page.
    newly_unlocked_code = None

    if is_correct and not progress.solved:
        progress.solved = True
        progress.solved_at = datetime.utcnow()

        # Find whichever challenge comes immediately after this one.
        next_challenge = Challenge.query.filter(
            Challenge.order_index == challenge.order_index + 1
        ).first()

        if next_challenge:
            next_progress = Progress.query.filter_by(
                user_id=current_user.id, challenge_id=next_challenge.id
            ).first()
            if next_progress and not next_progress.unlocked:
                next_progress.unlocked = True
                newly_unlocked_code = next_challenge.code

    db.session.commit()

    # jsonify() turns this Python dict into a JSON HTTP response --
    # the JavaScript in challenge.html reads this to decide what
    # message to show the player.
    return jsonify(correct=is_correct, unlocked_next=newly_unlocked_code)


@main_bp.route("/scoreboard")
@login_required
def scoreboard():
    """Ranks every non-admin user (see build_leaderboard() above for the rules)."""
    board = build_leaderboard()
    total_challenges = Challenge.query.count()
    return render_template("scoreboard.html", board=board, total_challenges=total_challenges)


# ============================================================================
# ADMIN ROUTES
# In a bigger project these would live in their own app/admin.py blueprint,
# but per the requested folder structure we keep everything non-auth in
# this one routes.py file.
# ============================================================================


def require_admin():
    """Small helper: abort with 403 unless the current user is an admin."""
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)


@main_bp.route("/admin")
@login_required
def admin_dashboard():
    """Shows solve/attempt counts per challenge, for admins only."""
    require_admin()

    all_challenges = Challenge.query.order_by(Challenge.order_index).all()
    stats = []
    for ch in all_challenges:
        solves = Progress.query.filter_by(challenge_id=ch.id, solved=True).count()
        attempts = Submission.query.filter_by(challenge_id=ch.id).count()
        stats.append({"challenge": ch, "solves": solves, "attempts": attempts})

    user_count = User.query.count()
    return render_template("admin_dashboard.html", stats=stats, user_count=user_count)


@main_bp.route("/admin/logs")
@login_required
def admin_logs():
    """Shows the most recent 300 audit-log entries, for admins only."""
    require_admin()
    entries = LogEntry.query.order_by(LogEntry.timestamp.desc()).limit(300).all()
    return render_template("admin_logs.html", entries=entries)