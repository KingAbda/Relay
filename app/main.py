"""Relay — Flask application. Trade skills, not money."""

import os
import re
import uuid
from datetime import datetime, timedelta

import bleach
from flask import (
    Flask, render_template, request, redirect, url_for,
    make_response, abort,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import enum

# ── App Setup ──────────────────────────────────────────

app = Flask(__name__)

# Security configuration
app.config["SECRET_KEY"] = os.environ.get(
    "RELAY_SECRET_KEY",
    "replace-this-with-a-real-secret-in-production-abc123"
)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL",
    "sqlite:///relay.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["WTF_CSRF_ENABLED"] = True
app.config["MAX_CONTENT_LENGTH"] = 1024 * 50  # 50KB max form data

# Production security
if os.environ.get("RELAY_ENV") == "production":
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["PREFERRED_URL_SCHEME"] = "https"

db = SQLAlchemy(app)

# Rate limiter (memory-based; swap to Redis in production)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)


# ── Enums ──────────────────────────────────────────────

class SkillCategory(str, enum.Enum):
    CREATIVE = "creative"
    ACADEMIC = "academic"
    TECHNICAL = "technical"
    SOCIAL = "social"
    LIFESTYLE = "lifestyle"
    FINANCE = "finance"
    LANGUAGES = "languages"
    TRADES = "trades"
    OTHER = "other"


class SessionStatus(str, enum.Enum):
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class TransactionType(str, enum.Enum):
    EARN = "earn"
    SPEND = "spend"
    BONUS = "bonus"
    REFERRAL = "referral"
    EXPIRE = "expire"


# ── Models ─────────────────────────────────────────────

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = db.Column(db.String, unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String, nullable=False)
    full_name = db.Column(db.String, nullable=False)
    bio = db.Column(db.Text, default="")
    onboarded = db.Column(db.Boolean, default=False)
    referred_by = db.Column(db.String, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_active = db.Column(db.DateTime, default=datetime.utcnow)

    skills_taught = db.relationship("UserSkill", back_populates="user",
                                     foreign_keys="UserSkill.user_id")
    credit_account = db.relationship("CreditAccount", back_populates="user",
                                      uselist=False)


class UserSkill(db.Model):
    __tablename__ = "user_skills"
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String, nullable=False)
    category = db.Column(db.String, nullable=False)
    description = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", back_populates="skills_taught",
                            foreign_keys=[user_id])


class UserWant(db.Model):
    __tablename__ = "user_wants"
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String, nullable=False)
    category = db.Column(db.String, nullable=False)
    description = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CreditAccount(db.Model):
    __tablename__ = "credit_accounts"
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String, db.ForeignKey("users.id"), unique=True, nullable=False)
    balance = db.Column(db.Float, default=0.0)

    user = db.relationship("User", back_populates="credit_account")


class CreditTransaction(db.Model):
    __tablename__ = "credit_transactions"
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String, nullable=False)
    description = db.Column(db.String, default="")
    related_user_id = db.Column(db.String, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Session(db.Model):
    __tablename__ = "sessions"
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    teacher_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=False)
    learner_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=False)
    skill_name = db.Column(db.String, nullable=False)
    status = db.Column(db.String, default=SessionStatus.REQUESTED.value)
    notes = db.Column(db.Text, default="")
    scheduled_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ── Initialize DB ─────────────────────────────────────

with app.app_context():
    db.create_all()


# ── Helpers ────────────────────────────────────────────

def sanitize(text, max_length=500):
    """Strip HTML tags and limit length."""
    if not text:
        return ""
    cleaned = bleach.clean(text.strip(), tags=[], strip=True)
    return cleaned[:max_length]


def validate_password(password):
    """Enforce minimum password strength."""
    errors = []
    if len(password) < 8:
        errors.append("Password must be at least 8 characters.")
    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter.")
    if not re.search(r"[0-9]", password):
        errors.append("Password must contain at least one number.")
    return errors


def get_user(user_id):
    return db.session.get(User, user_id)


def get_user_by_email(email):
    return User.query.filter(User.email == email).first()


def current_user():
    user_id = request.cookies.get("user_id")
    if user_id:
        user = get_user(user_id)
        if user:
            # Update last active periodically
            now = datetime.utcnow()
            if not user.last_active or (now - user.last_active) > timedelta(minutes=5):
                user.last_active = now
                db.session.commit()
            return user
    return None


def require_user():
    user = current_user()
    if not user:
        return None
    return user


def require_onboarded():
    user = require_user()
    if not user:
        return None
    if not user.onboarded:
        return "redirect_onboarding"
    return user


def add_credit_transaction(user_id, amount, tx_type, description="", related_user_id=None):
    """Add a credit transaction and update the user's balance."""
    tx = CreditTransaction(
        user_id=user_id,
        amount=amount,
        type=tx_type.value if isinstance(tx_type, TransactionType) else tx_type,
        description=description,
        related_user_id=related_user_id,
    )
    db.session.add(tx)

    account = CreditAccount.query.filter(CreditAccount.user_id == user_id).first()
    if account:
        account.balance += amount

    return tx


def jinja_capitalize(s):
    return s.replace("_", " ").title() if s else ""


def jinja_time_ago(dt):
    if not dt:
        return ""
    diff = datetime.utcnow() - dt
    if diff.days > 30:
        return f"{diff.days // 30}mo ago"
    if diff.days > 0:
        return f"{diff.days}d ago"
    if diff.seconds > 3600:
        return f"{diff.seconds // 3600}h ago"
    if diff.seconds > 60:
        return f"{diff.seconds // 60}m ago"
    return "just now"


app.jinja_env.filters["capitalize"] = jinja_capitalize
app.jinja_env.filters["time_ago"] = jinja_time_ago
app.jinja_env.globals["SkillCategory"] = SkillCategory
app.jinja_env.globals["SessionStatus"] = SessionStatus


# ── Routes: Auth ───────────────────────────────────────

@app.route("/")
def home():
    user = current_user()
    total_users = User.query.count()
    total_sessions = Session.query.filter(Session.status == SessionStatus.COMPLETED.value).count()
    return render_template("index.html", user=user,
                           total_users=total_users,
                           total_sessions=total_sessions)


@app.route("/signup", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def signup():
    if request.method == "GET":
        ref = request.args.get("ref", "")
        return render_template("signup.html", user=None, error=None, ref=ref)

    email = sanitize(request.form.get("email", "")).strip().lower()
    password = request.form.get("password", "")
    full_name = sanitize(request.form.get("full_name", "")).strip()
    referral_code = sanitize(request.form.get("ref", "")).strip()

    # Validate .edu email
    if not email.endswith(".edu"):
        return render_template("signup.html", user=None, ref=referral_code,
                               error="Only .edu email addresses are accepted.")

    # Check existing
    if get_user_by_email(email):
        return render_template("signup.html", user=None, ref=referral_code,
                               error="An account with this email already exists.")

    # Validate password
    pw_errors = validate_password(password)
    if pw_errors:
        return render_template("signup.html", user=None, ref=referral_code,
                               error=pw_errors[0])

    # Validate name
    if not full_name or len(full_name) < 2:
        return render_template("signup.html", user=None, ref=referral_code,
                               error="Please enter your full name.")

    # Look up referrer
    referrer = None
    if referral_code:
        referrer = get_user(referral_code)

    # Create user
    user = User(
        email=email,
        password_hash=generate_password_hash(password),
        full_name=full_name,
        referred_by=referrer.id if referrer else None,
    )
    db.session.add(user)
    db.session.flush()

    # Signup bonus: 3 credits
    credit = CreditAccount(user_id=user.id, balance=3.0)
    db.session.add(credit)
    add_credit_transaction(user.id, 3.0, TransactionType.BONUS,
                           "Welcome to Relay! 3 free credits to start.")

    # Referral bonus (both get +1)
    if referrer:
        add_credit_transaction(referrer.id, 1.0, TransactionType.REFERRAL,
                               f"You referred {full_name}!", related_user_id=user.id)
        add_credit_transaction(user.id, 1.0, TransactionType.REFERRAL,
                               f"You joined through {referrer.full_name}!", related_user_id=referrer.id)

    db.session.commit()

    resp = make_response(redirect(url_for("onboarding")))
    resp.set_cookie("user_id", user.id, httponly=True, samesite="Lax",
                    max_age=60 * 60 * 24 * 30)  # 30 days
    return resp


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("20 per hour")
def login():
    if request.method == "GET":
        return render_template("login.html", user=None, error=None)

    email = sanitize(request.form.get("email", "")).strip().lower()
    password = request.form.get("password", "")

    user = get_user_by_email(email)
    if not user or not check_password_hash(user.password_hash, password):
        return render_template("login.html", user=None,
                               error="Invalid email or password.")

    resp = make_response(redirect(url_for("dashboard")))
    resp.set_cookie("user_id", user.id, httponly=True, samesite="Lax",
                    max_age=60 * 60 * 24 * 30)  # 30 days
    return resp


@app.route("/logout")
def logout():
    resp = make_response(redirect(url_for("home")))
    resp.delete_cookie("user_id")
    return resp


# ── Routes: Onboarding ─────────────────────────────────

@app.route("/onboarding", methods=["GET", "POST"])
def onboarding():
    user = require_user()
    if not user:
        return redirect(url_for("login"))
    if user.onboarded:
        return redirect(url_for("dashboard"))

    if request.method == "GET":
        return render_template("onboarding.html", user=user,
                               categories=[c.value for c in SkillCategory], error=None)

    teach_name = sanitize(request.form.get("teach_name", ""))
    teach_cat = sanitize(request.form.get("teach_category", ""))
    teach_desc = sanitize(request.form.get("teach_description", ""), 300)
    learn_name = sanitize(request.form.get("learn_name", ""))
    learn_cat = sanitize(request.form.get("learn_category", ""))
    learn_desc = sanitize(request.form.get("learn_description", ""), 300)

    if not teach_name or not learn_name:
        return render_template("onboarding.html", user=user,
                               categories=[c.value for c in SkillCategory],
                               error="Please fill in both a skill to teach and a skill to learn.")

    if not teach_cat or not learn_cat:
        return render_template("onboarding.html", user=user,
                               categories=[c.value for c in SkillCategory],
                               error="Please select a category for both skills.")

    # Validate categories
    valid_cats = [c.value for c in SkillCategory]
    if teach_cat not in valid_cats or learn_cat not in valid_cats:
        abort(400)

    skill = UserSkill(user_id=user.id, name=teach_name,
                       category=teach_cat, description=teach_desc)
    db.session.add(skill)

    want = UserWant(user_id=user.id, name=learn_name,
                     category=learn_cat, description=learn_desc)
    db.session.add(want)

    user.onboarded = True
    db.session.commit()

    return redirect(url_for("dashboard"))


# ── Routes: Dashboard ──────────────────────────────────

@app.route("/dashboard")
def dashboard():
    user = require_onboarded()
    if not user:
        return redirect(url_for("login"))
    if user == "redirect_onboarding":
        return redirect(url_for("onboarding"))

    my_skills = UserSkill.query.filter(UserSkill.user_id == user.id).order_by(UserSkill.created_at.desc()).all()
    my_wants = UserWant.query.filter(UserWant.user_id == user.id).all()
    credit = CreditAccount.query.filter(CreditAccount.user_id == user.id).first()

    # Sessions where user is teacher or learner
    sessions = (
        Session.query
        .filter((Session.teacher_id == user.id) | (Session.learner_id == user.id))
        .order_by(Session.created_at.desc())
        .limit(10)
        .all()
    )

    # Enrich sessions with names
    enriched_sessions = []
    for s in sessions:
        teacher = get_user(s.teacher_id)
        learner = get_user(s.learner_id)
        enriched_sessions.append({
            "id": s.id,
            "skill_name": s.skill_name,
            "status": s.status,
            "other_name": learner.full_name if s.teacher_id == user.id else teacher.full_name,
            "role": "teacher" if s.teacher_id == user.id else "learner",
            "created_at": s.created_at,
            "scheduled_at": s.scheduled_at,
            "notes": s.notes,
            "teacher_id": s.teacher_id,
            "learner_id": s.learner_id,
        })

    # Pending actions (sessions for teacher to accept/reject)
    pending_requests = (
        Session.query
        .filter(Session.teacher_id == user.id)
        .filter(Session.status == SessionStatus.REQUESTED.value)
        .order_by(Session.created_at.desc())
        .all()
    )

    transactions = (
        CreditTransaction.query
        .filter(CreditTransaction.user_id == user.id)
        .order_by(CreditTransaction.created_at.desc())
        .limit(10)
        .all()
    )

    # Referral link
    ref_link = url_for("signup", ref=user.id, _external=True)

    return render_template("dashboard.html", user=user,
                           my_skills=my_skills, my_wants=my_wants,
                           credit=credit, sessions=enriched_sessions,
                           pending_requests=pending_requests,
                           transactions=transactions,
                           ref_link=ref_link,
                           categories=[c.value for c in SkillCategory])


# ── Routes: Browse ─────────────────────────────────────

@app.route("/browse")
def browse():
    user = require_user()
    if not user:
        return redirect(url_for("login"))
    if not user.onboarded:
        return redirect(url_for("onboarding"))

    category = request.args.get("category")
    q = sanitize(request.args.get("q", ""))

    query = UserSkill.query.join(User).filter(User.onboarded == True)

    if category and category in [c.value for c in SkillCategory]:
        query = query.filter(UserSkill.category == category)
    if q:
        query = query.filter(UserSkill.name.ilike(f"%{q}%"))

    skills = query.order_by(UserSkill.created_at.desc()).all()

    return render_template("browse.html", user=user, skills=skills,
                           categories=[c.value for c in SkillCategory],
                           selected_category=category, query=q)


# ── Routes: Sessions ───────────────────────────────────

@app.route("/request-session/<skill_id>", methods=["GET", "POST"])
def request_session(skill_id):
    user = require_onboarded()
    if not user or user == "redirect_onboarding":
        return redirect(url_for("login"))

    skill = db.session.get(UserSkill, skill_id)
    if not skill:
        abort(404)

    # Prevent self-request
    if skill.user_id == user.id:
        return render_template("request_session.html", user=user, skill=skill,
                               error="You can't request a session from yourself!")

    if request.method == "GET":
        return render_template("request_session.html", user=user, skill=skill, error=None)

    notes = sanitize(request.form.get("notes", ""), 500)

    credit = CreditAccount.query.filter(CreditAccount.user_id == user.id).first()
    if not credit or credit.balance < 1.0:
        return render_template("request_session.html", user=user, skill=skill,
                               error="Not enough credits. You need at least 1 credit.")

    # Create session and hold 1 credit
    session = Session(
        teacher_id=skill.user_id,
        learner_id=user.id,
        skill_name=skill.name,
        notes=notes,
    )
    db.session.add(session)
    add_credit_transaction(user.id, -1.0, TransactionType.SPEND,
                           f"Session hold: {skill.name}",
                           related_user_id=skill.user_id)
    db.session.commit()

    return redirect(url_for("dashboard"))


@app.route("/accept-session/<session_id>")
def accept_session(session_id):
    user = require_user()
    if not user:
        return redirect(url_for("login"))

    session = db.session.get(Session, session_id)
    if not session or session.teacher_id != user.id:
        abort(404)

    if session.status != SessionStatus.REQUESTED.value:
        return redirect(url_for("dashboard"))

    session.status = SessionStatus.ACCEPTED.value
    db.session.commit()

    return redirect(url_for("dashboard"))


@app.route("/complete-session/<session_id>")
def complete_session(session_id):
    user = require_user()
    if not user:
        return redirect(url_for("login"))

    session = db.session.get(Session, session_id)
    if not session:
        abort(404)

    # Both teacher and learner can mark complete
    if session.teacher_id != user.id and session.learner_id != user.id:
        abort(404)

    if session.status not in (SessionStatus.ACCEPTED.value, SessionStatus.REQUESTED.value):
        return redirect(url_for("dashboard"))

    session.status = SessionStatus.COMPLETED.value
    session.completed_at = datetime.utcnow()

    # Release the held credit to the teacher
    add_credit_transaction(session.teacher_id, 1.0, TransactionType.EARN,
                           f"Taught {session.skill_name}",
                           related_user_id=session.learner_id)

    db.session.commit()

    return redirect(url_for("dashboard"))


@app.route("/cancel-session/<session_id>")
def cancel_session(session_id):
    user = require_user()
    if not user:
        return redirect(url_for("login"))

    session = db.session.get(Session, session_id)
    if not session:
        abort(404)

    # Both teacher and learner can cancel
    if session.teacher_id != user.id and session.learner_id != user.id:
        abort(404)

    if session.status == SessionStatus.COMPLETED.value:
        return redirect(url_for("dashboard"))

    was_held = session.status == SessionStatus.REQUESTED.value
    session.status = SessionStatus.CANCELLED.value

    # Refund the held credit if cancelled before completion
    if was_held:
        add_credit_transaction(session.learner_id, 1.0, TransactionType.BONUS,
                               f"Refund for cancelled session: {session.skill_name}",
                               related_user_id=session.teacher_id)

    db.session.commit()

    return redirect(url_for("dashboard"))


# ── Routes: Profile ────────────────────────────────────

@app.route("/profile/<user_id>")
def view_profile(user_id):
    current = current_user()
    profile = get_user(user_id)
    if not profile:
        abort(404)

    skills = UserSkill.query.filter(UserSkill.user_id == user_id).all()
    wants = UserWant.query.filter(UserWant.user_id == user_id).all()

    # Completed session count
    completed_count = Session.query.filter(
        ((Session.teacher_id == user_id) | (Session.learner_id == user_id)) &
        (Session.status == SessionStatus.COMPLETED.value)
    ).count()

    return render_template("profile.html", user=current,
                           profile_user=profile, skills=skills, wants=wants,
                           completed_count=completed_count)


# ── Routes: Skills ─────────────────────────────────────

@app.route("/add-skill", methods=["POST"])
def add_skill():
    user = require_user()
    if not user:
        return redirect(url_for("login"))

    name = sanitize(request.form.get("name", ""))
    category = sanitize(request.form.get("category", ""))
    description = sanitize(request.form.get("description", ""), 300)

    valid_cats = [c.value for c in SkillCategory]
    if name and category and category in valid_cats:
        skill = UserSkill(user_id=user.id, name=name,
                           category=category, description=description)
        db.session.add(skill)
        db.session.commit()

    return redirect(url_for("dashboard"))


# ── Routes: Legal ──────────────────────────────────────

@app.route("/privacy")
def privacy():
    user = current_user()
    return render_template("privacy.html", user=user)


@app.route("/terms")
def terms():
    user = current_user()
    return render_template("terms.html", user=user)


# ── Error handlers ─────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    user = current_user()
    return render_template("error.html", user=user, code=404,
                           message="Page not found."), 404


@app.errorhandler(429)
def ratelimit_error(e):
    user = current_user()
    return render_template("error.html", user=user, code=429,
                           message="Too many requests. Please slow down."), 429


@app.errorhandler(500)
def server_error(e):
    user = current_user()
    return render_template("error.html", user=user, code=500,
                           message="Something went wrong. We've been notified."), 500


# ── Run ──────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    debug = os.environ.get("RELAY_ENV") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug)
