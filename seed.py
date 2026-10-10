"""
seed.py
-------
Run this ONCE after setting up the project (and again any time you
wipe database/cybershield.db) to populate the database with:
  - an admin account
  - the six CyberShield challenges (CS-01 .. CS-06)

Usage:
    python seed.py

IMPORTANT: the flags below are worked-example placeholders. Before
using this with real participants, change every value in the
CHALLENGES list, and rebuild the matching files in challenges/
to match your new flags.
"""

from app import create_app, db
from app.models import Challenge, Hint, User
from werkzeug.security import generate_password_hash

# Build an app instance just so we have database access -- we don't
# actually start the web server from this script.
app = create_app()

# --------------------------------------------------------------------
# One dict per challenge. file_path is relative to the challenges/
# folder (see CHALLENGES_FOLDER in config.py) -- e.g. "cs01_hidden_message/employee_photo.jpg".
# Challenges with no downloadable file (CS-02, CS-04, CS-06) use None.
# --------------------------------------------------------------------
CHALLENGES = [
    dict(
        code="CS-01",
        name="Hidden Message",
        category="Steganography",
        difficulty="Easy",
        order_index=0,
        points=100,
        scenario=(
            "An employee has submitted an ordinary company photograph as part of an "
            "internal investigation. The image appears normal, but the investigation "
            "team suspects information has been concealed inside it."
        ),
        description="Inspect the supplied image and recover the flag hidden inside it.",
        flag="CS{h1dd3n_1n_pl41n_s1ght}",
        file_path="cs01_hidden_message/employee_photo.jpg",
        hints=[
            "Information can exist inside a file without appearing in the visible image.",
            "Start by examining the file rather than only opening it as an image.",
            "Inspect the metadata and other non-visible information.",
        ],
    ),
    dict(
        code="CS-02",
        name="The Recon Trail",
        category="OSINT / Reconnaissance",
        difficulty="Easy",
        order_index=1,
        points=100,
        scenario=(
            "A clue recovered from the first stage references a fictional company "
            "department and a simulated employee profile."
        ),
        description="Correlate the simulated company information sources to find the next clue.",
        flag="CS{c0rr3l4t3_th3_clu3s}",
        file_path=None,
        hints=[
            "Do not assume the first matching record is the answer.",
            "Compare identifiers across the supplied information sources.",
            "Look for a repeated employee, department, document or system reference.",
        ],
    ),
    dict(
        code="CS-03",
        name="Broken Cipher",
        category="Cryptography",
        difficulty="Moderate",
        order_index=2,
        points=150,
        scenario=(
            "The reconnaissance trail produces an encrypted message believed to have "
            "been written by the suspected attacker."
        ),
        description="Decrypt the supplied ciphertext to recover the flag.",
        flag="CS{d0ubl3_l4y3r_d3c0d3d}",
        file_path="cs03_broken_cipher/ciphertext.txt",
        hints=[
            "Look closely at the character set used here -- only letters, digits, +, / and = padding at the end. That is a strong signal about the first layer.",
            "Decoding the first layer will not give you readable English yet -- a second, classical layer sits underneath it.",
            "The second layer is a simple alphabet shift. You do not need to guess the exact shift by hand -- let a brute-force tool try all of them at once.",
        ],
    ),
    dict(
        code="CS-04",
        name="Vulnerable Portal",
        category="Web Security",
        difficulty="Moderate",
        order_index=3,
        points=150,
        scenario=(
            "The decrypted message identifies an internal employee portal used by "
            "CyberShield Technologies."
        ),
        description="Explore the portal, identify the deliberate weakness, and access the protected page.",
        flag="CS{1nput_v4l1d4t10n_m4tt3rs}",
        file_path=None,
        hints=[
            "Pay attention to how the application processes user input.",
            "Compare normal requests with requests that change parameters.",
            "Investigate authentication, authorization and input validation behavior.",
        ],
    ),
    dict(
        code="CS-05",
        name="The Missing Evidence",
        category="Digital Forensics",
        difficulty="Moderate-Hard",
        order_index=4,
        points=200,
        scenario=(
            "CyberShield investigators discover that the attacker attempted to remove "
            "evidence from an employee workstation."
        ),
        description="Correlate the provided logs and recover the hidden/deleted evidence.",
        flag="CS{3v1d3nc3_r3c0v3r3d}",
        file_path="cs05_missing_evidence/evidence_package.zip",
        hints=[
            "Start by determining when the suspicious login occurred.",
            "Compare the authentication log with later access activity.",
            "Look for an artifact created or referenced immediately after the suspicious activity.",
        ],
    ),
    dict(
        code="CS-06",
        name="Compromised Server",
        category="Linux / System Security",
        difficulty="Hard",
        order_index=5,
        points=250,
        scenario=(
            "The forensic evidence identifies a Linux server used during the incident, "
            "configured with an intentional security weakness."
        ),
        description="Enumerate the system, find the privilege-escalation path, and capture the final flag.",
        flag="CS{pr1v1l3g3_b0und4ry_cr0ss3d}",
        file_path=None,
        hints=[
            "First determine which account and privilege level you currently have.",
            "Inspect users, processes, services and file permissions.",
            "Look for an intentionally misconfigured resource that crosses a privilege boundary.",
        ],
    ),
]


def seed():
    # app_context() is required any time we touch the database outside
    # of an actual web request -- it tells SQLAlchemy which app's
    # config (i.e. which database file) to use.
    with app.app_context():
        db.create_all()

        # Only create the admin account if one doesn't already exist --
        # this makes it safe to re-run seed.py without duplicating data.
        if not User.query.filter_by(username="admin").first():
            admin = User(
                username="admin",
                password_hash=generate_password_hash("ChangeMe123!"),
                is_admin=True,
            )
            db.session.add(admin)

        
        for c in CHALLENGES:
            ch = Challenge.query.filter_by(code=c["code"]).first()

            if ch is None:
                ch = Challenge(
                    code=c["code"],
                    name=c["name"],
                    category=c["category"],
                    difficulty=c["difficulty"],
                    scenario=c["scenario"],
                    description=c["description"],
                    flag_hash=generate_password_hash(c["flag"]),
                    order_index=c["order_index"],
                    file_path=c.get("file_path"),
                    points=c["points"],
                )
                db.session.add(ch)
                db.session.flush()
            else:
                ch.name = c["name"]
                ch.category = c["category"]
                ch.difficulty = c["difficulty"]
                ch.scenario = c["scenario"]
                ch.description = c["description"]
                ch.flag_hash = generate_password_hash(c["flag"])
                ch.order_index = c["order_index"]
                ch.file_path = c.get("file_path")
                ch.points = c["points"]

                Hint.query.filter_by(challenge_id=ch.id).delete(
                    synchronize_session=False
                )

            for i, hint_text in enumerate(c["hints"]):
                db.session.add(
                    Hint(
                        challenge_id=ch.id,
                        text=hint_text,
                        order_index=i,
                        point_cost=10,
                    )
                )

        db.session.commit()
        print("Challenges and hints updated successfully.")


if __name__ == "__main__":
    seed()
