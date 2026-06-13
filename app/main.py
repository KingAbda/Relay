"""Relay — Flask application. Trade skills, not money.
Security-hardened MVP with rating system, pilot vertical, and CSRF protection."""

import os
import re
import uuid
import secrets
import hashlib
from datetime import datetime, timedelta

import bleach
from flask import (
    Flask, render_template, request, redirect, url_for,
    make_response, abort, jsonify,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect, generate_csrf
from werkzeug.security import generate_password_hash, check_password_hash
from markupsafe import Markup
import enum

# ── App Setup ──────────────────────────────────────────

app = Flask(__name__)

# ── Security-first config ──────────────────────────────
_secret_key = os.environ.get("RELAY_SECRET_KEY")
if not _secret_key:
    _secret_key = secrets.token_hex(32)
    print("WARNING: Using auto-generated SECRET_KEY. Set RELAY_SECRET_KEY env var in production.")

app.config["SECRET_KEY"] = _secret_key
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///relay.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("RELAY_ENV") == "production"
app.config["PREFERRED_URL_SCHEME"] = "https" if os.environ.get("RELAY_ENV") == "production" else "http"
app.config["MAX_CONTENT_LENGTH"] = 1024 * 50

# ── Plugins ────────────────────────────────────────────
csrf = CSRFProtect(app)
from .database import db, init_db
init_db(app)

# ── Rate limiter ────────────────────────────────────────
limiter = Limiter(
    get_remote_address, app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=os.environ.get("RATE_LIMIT_STORAGE", "memory://"),
)

# ── Configuration Constants ────────────────────────────
SITE_NAME = "Relay"
CONTACT_EMAIL = os.environ.get("RELAY_CONTACT_EMAIL", "hello@joinrelay.co")
PILOT_VERTICAL = os.environ.get("RELAY_PILOT_VERTICAL", "all")
PILOT_VERTICAL_NAME = {
    "lifestyle": "Fitness & Wellness",
    "creative": "Creative",
    "finance": "Finance & Career",
    "all": "All Categories",
}.get(PILOT_VERTICAL, PILOT_VERTICAL.capitalize())

# ── Import models after db init ────────────────────────
from app.models import (
    User, UserSkill, UserWant, CreditAccount, CreditTransaction,
    Session, SessionReview, SkillCategory, SessionStatus, TransactionType,
)

# ── Auto-seed demo data (defined before use) ──────────
def _auto_seed_demo_data():
    """Auto-creates demo users & skills so the marketplace isn't empty on first launch."""
    if os.environ.get("RELAY_ENV") == "production":
        return  # never seed in production
    if User.query.count() > 1:
        return  # already has real users
    from werkzeug.security import generate_password_hash
    demo_accounts = [
        ("Alex Rivera", "alex@nyu.edu", "Pass1234"),
        ("Jordan Kim", "jordan@nyu.edu", "Pass1234"),
        ("Sam Patel", "sam@nyu.edu", "Pass1234"),
    ]
    demo_skills_pool = [
        ("Python for Beginners", "technical", "Learn variables, loops, and functions in 30 min. No experience needed.", 3),
        ("Weight Training 101", "lifestyle", "Proper form for squats, deadlifts, bench press. Bring gym clothes.", 4),
        ("Guitar Chords & Strumming", "creative", "Open chords and strumming patterns. I'll have a guitar ready.", 3),
        ("Budgeting for Students", "finance", "Build a student budget, understand credit scores, start investing small.", 4),
        ("Spanish Conversation", "languages", "Practice everyday conversation. Intermediate level welcome.", 3),
        ("Resume & Cover Letter Review", "academic", "I've helped 20+ classmates land internships. Let's fix your resume.", 5),
        ("Public Speaking 101", "social", "Overcome stage fright. Practice pitches in a safe space.", 3),
        ("HTML/CSS Basics", "technical", "Build your first personal site in 30 minutes. No coding experience needed.", 3),
        ("Meal Prep & Nutrition", "lifestyle", "Healthy meals under $50/week. I'll show you my system.", 4),
        ("Music Production (GarageBand)", "creative", "Beat-making from idea to export in one session.", 3),
        ("Calculus Tutoring", "academic", "Up to Calc II. Bring your problem set.", 4),
        ("Yoga & Flexibility", "lifestyle", "30 min flow for beginners. Bring a mat.", 3),
        ("Investing 101", "finance", "Stocks, ETFs, and Roth IRAs explained simply.", 3),
        ("Japanese Basics", "languages", "Hiragana, katakana, and simple phrases.", 3),
        ("Photoshop/Canva Design", "creative", "Social media graphics, flyers, and basic photo editing.", 4),
    ]
    for email, name, pw in demo_accounts:
        if get_user_by_email(email):
            continue
        user = User(
            email=email, password_hash=generate_password_hash(pw),
            full_name=name, email_verified=True, onboarded=True,
        )
        db.session.add(user)
        db.session.flush()
        db.session.add(CreditAccount(user_id=user.id, balance=5.0))
        import random
        assigned = random.sample(demo_skills_pool, 5)
        for sk_name, sk_cat, sk_desc, sk_prof in assigned:
            db.session.add(UserSkill(
                user_id=user.id, name=sk_name, category=sk_cat,
                description=sk_desc, proficiency=sk_prof,
            ))
        want = random.choice(demo_skills_pool)
        db.session.add(UserWant(
            user_id=user.id, name=want[0], category=want[1],
            description=f"I want to learn {want[0]}",
        ))
    if User.query.count() > 1:
        db.session.commit()
        print(f"🌟 Seeded {User.query.count()} demo users with skills for the marketplace.")

# ── Initialize DB tables ──────────────────────────────
with app.app_context():
    db.create_all()
    _auto_seed_demo_data()

# ── Gravatar helper ─────────────────────────────────
def gravatar_url(email, size=80):
    """Return Gravatar URL for an email address."""
    if not email:
        return ""
    hash = hashlib.md5(email.strip().lower().encode()).hexdigest()
    return f"https://www.gravatar.com/avatar/{hash}?s={size}&d=identicon&r=g"

# ══════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════

def sanitize(text, max_length=500):
    if not text:
        return ""
    return bleach.clean(text.strip(), tags=[], strip=True)[:max_length]

def validate_password(password):
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
            if user.account_locked_until and user.account_locked_until > datetime.utcnow():
                return None
            now = datetime.utcnow()
            if not user.last_active or (now - user.last_active) > timedelta(minutes=5):
                user.last_active = now
                db.session.commit()
            return user
    return None

def require_user():
    return current_user()

def require_onboarded():
    user = require_user()
    if not user:
        return None
    return "redirect_onboarding" if not user.onboarded else user

def add_credit_transaction(user_id, amount, tx_type, description="", related_user_id=None):
    tx = CreditTransaction(
        user_id=user_id, amount=amount,
        type=tx_type.value if isinstance(tx_type, TransactionType) else tx_type,
        description=description, related_user_id=related_user_id,
    )
    db.session.add(tx)
    account = CreditAccount.query.filter(CreditAccount.user_id == user_id).first()
    if account:
        account.balance += amount
    return tx

def get_pilot_categories():
    if PILOT_VERTICAL and PILOT_VERTICAL != "all":
        return [PILOT_VERTICAL]
    return [c.value for c in SkillCategory]

def get_available_skills_query():
    query = UserSkill.query.join(User).filter(
        User.onboarded == True, UserSkill.is_active == True,
    )
    if PILOT_VERTICAL and PILOT_VERTICAL != "all":
        query = query.filter(UserSkill.category == PILOT_VERTICAL)
    return query

# ── Email helper (console in dev, SendGrid in prod) ───
def send_email(to, subject, body):
    """Print to console in dev. In production, uses SendGrid."""
    print(f"\n{'='*50}")
    print(f"📧 TO: {to}")
    print(f"   SUBJECT: {subject}")
    print(f"{'='*50}")
    print(body)
    print(f"{'='*50}\n")
    try:
        # In production, try SendGrid
        if os.environ.get("RELAY_ENV") == "production" and os.environ.get("SENDGRID_API_KEY"):
            import sendgrid
            from sendgrid.helpers.mail import Mail
            sg = sendgrid.SendGridAPIClient(api_key=os.environ["SENDGRID_API_KEY"])
            msg = Mail(from_email="noreply@joinrelay.co", to_emails=to, subject=subject, plain_text_content=body)
            sg.send(msg)
    except Exception as e:
        print(f"⚠️ Email send failed (non-fatal): {e}")

@app.context_processor
def inject_globals():
    return {
        "site_name": SITE_NAME, "contact_email": CONTACT_EMAIL,
        "pilot_vertical": PILOT_VERTICAL, "pilot_vertical_name": PILOT_VERTICAL_NAME,
        "csrf_token": lambda: generate_csrf(),
    }

def jinja_capitalize(s):
    return s.replace("_", " ").title() if s else ""

def jinja_time_ago(dt):
    if not dt: return ""
    diff = datetime.utcnow() - dt
    if diff.days > 30: return f"{diff.days // 30}mo ago"
    if diff.days > 0: return f"{diff.days}d ago"
    if diff.seconds > 3600: return f"{diff.seconds // 3600}h ago"
    if diff.seconds > 60: return f"{diff.seconds // 60}m ago"
    return "just now"

def jinja_stars(rating):
    return ("★" * rating + "☆" * (5 - rating)) if rating else ""

def jinja_gravatar(email, size=80):
    return gravatar_url(email, size)

def jinja_avatar_url(email, size=80):
    return gravatar_url(email, size)

app.jinja_env.filters["capitalize"] = jinja_capitalize
app.jinja_env.filters["time_ago"] = jinja_time_ago
app.jinja_env.filters["stars"] = jinja_stars
app.jinja_env.globals["SkillCategory"] = SkillCategory
app.jinja_env.globals["SessionStatus"] = SessionStatus
app.jinja_env.globals["gravatar_url"] = jinja_gravatar

# ── Error handlers ─────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", user=current_user(), code=404, message="Page not found."), 404

@app.errorhandler(429)
def ratelimit_error(e):
    return render_template("error.html", user=current_user(), code=429, message="Too many requests. Please slow down."), 429

@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", user=current_user(), code=500, message="Something went wrong."), 500

# ── Security headers ──────────────────────────────────

@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; frame-src 'self' https://docs.google.com; "
        "connect-src 'self'"
    )
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    return response

# ══════════════════════════════════════════════════════════
#  ROUTES: SEED DATA (for cold-start demo)
# ══════════════════════════════════════════════════════════

@app.route("/seed-demo")
def seed_demo():
    """Seed sample skills so the browse page isn't empty."""
    user = require_user()
    if not user:
        return redirect(url_for("login"))
    existing = UserSkill.query.filter(UserSkill.user_id == user.id).count()
    if existing >= 3:
        return redirect(url_for("browse"))
    demo_skills = [
        ("Python for Beginners", "technical", "Learn variables, loops, and functions in 30 min. No experience needed."),
        ("Weight Training 101", "lifestyle", "Proper form for squats, deadlifts, bench press. Bring gym clothes."),
        ("Guitar Chords", "creative", "Open chords and strumming patterns. I'll have a guitar ready."),
        ("Budgeting & Finance", "finance", "Build a student budget, understand credit scores, start investing small."),
        ("Spanish Conversation", "languages", "Practice everyday conversation. Intermediate level welcome."),
        ("Resume Review", "academic", "I've helped 20+ classmates land internships. Let's fix your resume."),
        ("Public Speaking", "social", "Overcome stage fright. Practice pitches and presentations in a safe space."),
        ("Basic Web Dev", "technical", "HTML/CSS — build your first personal site in 30 minutes."),
        ("Meal Prep & Nutrition", "lifestyle", "Healthy meals under $50/week. I'll show you my system."),
        ("Music Production", "creative", "Beat-making in GarageBand. From idea to export in one session."),
    ]
    added = 0
    for name, cat, desc in demo_skills:
        if cat not in get_pilot_categories():
            continue
        exists = UserSkill.query.filter_by(user_id=user.id, name=name, is_active=True).first()
        if not exists:
            db.session.add(UserSkill(user_id=user.id, name=name, category=cat, description=desc, proficiency=4))
            added += 1
    if added:
        db.session.commit()
    return redirect(url_for("browse"))

# ══════════════════════════════════════════════════════════
#  ROUTES: AUTH
# ══════════════════════════════════════════════════════════

@app.route("/")
def home():
    user = current_user()
    total_users = User.query.count()
    total_sessions = Session.query.filter(Session.status == SessionStatus.COMPLETED.value).count()
    # Trending skills — most-booked skills from completed sessions
    trending = db.session.query(
        UserSkill.name, UserSkill.category,
        db.func.count(Session.id).label("count")
    ).join(Session, Session.skill_name == UserSkill.name).filter(
        Session.status == SessionStatus.COMPLETED.value
    ).group_by(UserSkill.name).order_by(db.func.count(Session.id).desc()).limit(4).all()
    if not trending:
        # Fallback: show skills from demo users
        demo_skills = UserSkill.query.filter(UserSkill.is_active == True).order_by(UserSkill.proficiency.desc()).limit(4).all()
        trending = [{"name": s.name, "category": s.category.value if hasattr(s.category, 'value') else s.category, "count": s.proficiency or 0} for s in demo_skills]
    else:
        trending = [{"name": r[0], "category": r[1].value if hasattr(r[1], 'value') else r[1], "count": r[2]} for r in trending]
    # A/B test variant
    variant = request.args.get("variant", "a")
    return render_template("index.html", user=user, total_users=total_users, total_sessions=total_sessions, trending=trending, variant=variant)

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html", user=None, error=None, ref=request.args.get("ref", ""))

    email = sanitize(request.form.get("email", "")).strip().lower()
    password = request.form.get("password", "")
    full_name = sanitize(request.form.get("full_name", "")).strip()
    referral_code = sanitize(request.form.get("ref", "")).strip()

    if not email.endswith(".edu") and os.environ.get("RELAY_ENV") == "production":
        return render_template("signup.html", user=None, ref=referral_code, error="Only .edu email addresses accepted.")
    if get_user_by_email(email):
        return render_template("signup.html", user=None, ref=referral_code, error="An account with this email already exists.")
    pw_errors = validate_password(password)
    if pw_errors:
        return render_template("signup.html", user=None, ref=referral_code, error=pw_errors[0])
    if not full_name or len(full_name) < 2:
        return render_template("signup.html", user=None, ref=referral_code, error="Please enter your full name.")

    referrer = get_user(referral_code) if referral_code else None
    user = User(
        email=email, password_hash=generate_password_hash(password),
        full_name=full_name, referred_by=referrer.id if referrer else None,
        verification_token=secrets.token_urlsafe(32),
    )
    db.session.add(user)
    db.session.flush()
    credit = CreditAccount(user_id=user.id, balance=3.0)
    db.session.add(credit)
    add_credit_transaction(user.id, 3.0, TransactionType.BONUS, "3 free credits to start!")
    if referrer:
        add_credit_transaction(referrer.id, 1.0, TransactionType.REFERRAL, f"You referred {full_name}!", related_user_id=user.id)
        add_credit_transaction(user.id, 1.0, TransactionType.REFERRAL, f"You joined through {referrer.full_name}!", related_user_id=referrer.id)
    db.session.commit()
    # Send verification email
    verify_link = url_for("verify_email", token=user.verification_token, _external=True)
    send_email(user.email, "Verify your Relay account",
        f"Hi {user.full_name.split()[0]},\n\n"
        f"Welcome to Relay! Click this link to verify your .edu email:\n{verify_link}\n\n"
        f"Your first 3 credits are waiting.\n\n- Relay Team")
    resp = make_response(redirect(url_for("onboarding")))
    resp.set_cookie("user_id", user.id, httponly=True, samesite="Lax", max_age=60*60*24*30)
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
        return render_template("login.html", user=None, error="Invalid email or password.")
    if user.account_locked_until and user.account_locked_until > datetime.utcnow():
        remaining = (user.account_locked_until - datetime.utcnow()).seconds // 60
        return render_template("login.html", user=None, error=f"Account locked. Try again in {remaining} minutes.")
    user.failed_login_attempts = 0
    user.account_locked_until = None
    db.session.commit()
    resp = make_response(redirect(url_for("dashboard")))
    resp.set_cookie("user_id", user.id, httponly=True, samesite="Lax", max_age=60*60*24*30)
    return resp

@app.route("/logout")
def logout():
    resp = make_response(redirect(url_for("home")))
    resp.delete_cookie("user_id")
    return resp

@app.route("/verify-email/<token>")
def verify_email(token):
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    if user.verification_token == token:
        user.email_verified = True
        user.verification_token = None
        db.session.commit()
        return render_template("error.html", user=user, code=200, message="Email verified!")
    return render_template("error.html", user=user, code=400, message="Invalid link."), 400

# ══════════════════════════════════════════════════════════
#  ROUTES: ONBOARDING
# ══════════════════════════════════════════════════════════

@app.route("/onboarding", methods=["GET", "POST"])
def onboarding():
    user = require_user()
    if not user:
        return redirect(url_for("login"))
    if user.onboarded:
        return redirect(url_for("dashboard"))
    if request.method == "GET":
        return render_template("onboarding.html", user=user, categories=get_pilot_categories(), error=None)

    teach_name = sanitize(request.form.get("teach_name", ""))
    teach_cat = sanitize(request.form.get("teach_category", ""))
    teach_desc = sanitize(request.form.get("teach_description", ""), 300)
    learn_name = sanitize(request.form.get("learn_name", ""))
    learn_cat = sanitize(request.form.get("learn_category", ""))
    learn_desc = sanitize(request.form.get("learn_description", ""), 300)

    if not teach_name or not learn_name:
        return render_template("onboarding.html", user=user, categories=get_pilot_categories(), error="Fill in both a skill to teach and a skill to learn.")
    if not teach_cat or not learn_cat:
        return render_template("onboarding.html", user=user, categories=get_pilot_categories(), error="Select a category for both skills.")
    valid_cats = get_pilot_categories()
    if teach_cat not in valid_cats or learn_cat not in valid_cats:
        abort(400)

    db.session.add(UserSkill(user_id=user.id, name=teach_name, category=teach_cat, description=teach_desc))
    db.session.add(UserWant(user_id=user.id, name=learn_name, category=learn_cat, description=learn_desc))
    user.onboarded = True
    db.session.commit()
    return redirect(url_for("dashboard"))

# ══════════════════════════════════════════════════════════
#  ROUTES: DASHBOARD
# ══════════════════════════════════════════════════════════

@app.route("/dashboard")
def dashboard():
    user = require_onboarded()
    if not user:
        return redirect(url_for("login"))
    if user == "redirect_onboarding":
        return redirect(url_for("onboarding"))

    my_skills = UserSkill.query.filter(UserSkill.user_id == user.id, UserSkill.is_active == True).order_by(UserSkill.created_at.desc()).all()
    my_wants = UserWant.query.filter(UserWant.user_id == user.id).all()
    credit = CreditAccount.query.filter(CreditAccount.user_id == user.id).first()

    sessions = Session.query.filter((Session.teacher_id == user.id) | (Session.learner_id == user.id)).order_by(Session.created_at.desc()).limit(10).all()
    enriched_sessions = []
    for s in sessions:
        teacher = get_user(s.teacher_id)
        learner = get_user(s.learner_id)
        other_name = learner.full_name if s.teacher_id == user.id else teacher.full_name
        my_review = SessionReview.query.filter_by(session_id=s.id, reviewer_id=user.id).first()
        teacher_rating = db.session.query(db.func.avg(SessionReview.rating)).filter(SessionReview.reviewee_id == s.teacher_id).scalar()
        enriched_sessions.append({
            "id": s.id, "skill_name": s.skill_name,
            "status": s.status.value if hasattr(s.status, 'value') else s.status,
            "other_name": other_name, "role": "teacher" if s.teacher_id == user.id else "learner",
            "created_at": s.created_at, "notes": s.notes, "scheduled_at": s.scheduled_at,
            "meet_link": getattr(s, 'meet_link', None),
            "my_review": my_review, "teacher_rating": round(teacher_rating, 1) if teacher_rating else None,
        })

    pending = Session.query.filter(Session.teacher_id == user.id, Session.status == SessionStatus.REQUESTED).order_by(Session.created_at.desc()).all()
    enriched_pending = []
    for s in pending:
        learner = get_user(s.learner_id)
        enriched_pending.append({"id": s.id, "skill_name": s.skill_name, "learner_username": learner.full_name.split()[0] if learner else "Someone", "notes": s.notes})

    transactions = CreditTransaction.query.filter(CreditTransaction.user_id == user.id).order_by(CreditTransaction.created_at.desc()).limit(10).all()
    ref_link = url_for("signup", ref=user.id, _external=True)

    return render_template("dashboard.html", user=user, my_skills=my_skills, my_wants=my_wants,
                           credit=credit, sessions=enriched_sessions, pending_requests=enriched_pending,
                           transactions=transactions, ref_link=ref_link, categories=get_pilot_categories())

@app.route("/browse")
def browse():
    user = require_user()
    category = request.args.get("category")
    q = sanitize(request.args.get("q", ""))
    if user:
        query = get_available_skills_query().filter(UserSkill.user_id != user.id)
        is_limited = False
    else:
        query = UserSkill.query.join(User).filter(User.onboarded == True, UserSkill.is_active == True)
        if PILOT_VERTICAL:
            query = query.filter(UserSkill.category == PILOT_VERTICAL)
        is_limited = True
    if category and category in get_pilot_categories():
        query = query.filter(UserSkill.category == category)
    if q:
        query = query.filter(UserSkill.name.ilike(f"%{q}%"))
    query = query.order_by(UserSkill.created_at.desc())
    if is_limited:
        query = query.limit(6)
    skills = query.all()
    # Enrich with session counts per teacher
    enriched_skills = []
    for s in skills:
        teacher_completed = Session.query.filter(
            Session.teacher_id == s.user_id,
            Session.status == SessionStatus.COMPLETED.value
        ).count()
        enriched_skills.append({
            "id": s.id, "name": s.name, "category": s.category,
            "description": s.description, "proficiency": s.proficiency,
            "user_id": s.user_id, "user_name": s.user.full_name,
            "user_email": s.user.email,
            "session_count": teacher_completed,
        })
    ref_link = url_for("signup", ref=user.id, _external=True) if user else None
    return render_template("browse.html", user=user, skills=enriched_skills, categories=get_pilot_categories(), selected_category=category, query=q, ref_link=ref_link)

# ══════════════════════════════════════════════════════════
#  ROUTES: WAITLIST
# ══════════════════════════════════════════════════════════

@app.route("/waitlist", methods=["POST"])
def waitlist():
    """Capture non-.edu emails for waitlist."""
    email = sanitize(request.form.get("email", "")).strip().lower()
    if not email or "@" not in email:
        return redirect(url_for("home"))
    import json, os
    wl_path = os.path.join(os.path.dirname(__file__), "..", "instance", "waitlist.json")
    try:
        waitlist_data = []
        if os.path.exists(wl_path):
            with open(wl_path) as f:
                waitlist_data = json.load(f)
        if email not in [w["email"] for w in waitlist_data]:
            waitlist_data.append({"email": email, "signed_up": datetime.utcnow().isoformat()})
            with open(wl_path, "w") as f:
                json.dump(waitlist_data, f, indent=2)
            send_email(email, "You're on the Relay waitlist!",
                f"Thanks for joining the Relay waitlist!\n\n"
                f"We'll let you know when Relay comes to your campus.\n\n"
                f"In the meantime, tell your friends: every referral = +1 credit at launch.\n\n- Relay Team")
    except Exception as e:
        print(f"⚠️ Waitlist save error: {e}")
    return redirect(url_for("home"))

# ══════════════════════════════════════════════════════════
#  ROUTES: SESSIONS
# ══════════════════════════════════════════════════════════

@app.route("/request-session/<skill_id>", methods=["GET", "POST"])
def request_session(skill_id):
    user = require_onboarded()
    if not user or user == "redirect_onboarding":
        return redirect(url_for("login"))
    skill = db.session.get(UserSkill, skill_id)
    if not skill:
        abort(404)
    if skill.user_id == user.id:
        return render_template("request_session.html", user=user, skill=skill, error="You can't request a session from yourself!", now=datetime.utcnow().strftime("%Y-%m-%dT%H:%M"))
    if request.method == "GET":
        return render_template("request_session.html", user=user, skill=skill, error=None, now=datetime.utcnow().strftime("%Y-%m-%dT%H:%M"))
    notes = sanitize(request.form.get("notes", ""), 500)
    scheduled_raw = request.form.get("scheduled_at", "")
    scheduled_at = None
    if scheduled_raw:
        try:
            scheduled_at = datetime.fromisoformat(scheduled_raw)
        except (ValueError, TypeError):
            pass
    credit = CreditAccount.query.filter(CreditAccount.user_id == user.id).first()
    if not credit or credit.balance < 1.0:
        return render_template("request_session.html", user=user, skill=skill, error="Not enough credits.", now=datetime.utcnow().strftime("%Y-%m-%dT%H:%M"))
    session = Session(teacher_id=skill.user_id, learner_id=user.id, skill_name=skill.name, notes=notes, scheduled_at=scheduled_at)
    db.session.add(session)
    add_credit_transaction(user.id, -1.0, TransactionType.SPEND, f"Hold: {skill.name}", related_user_id=skill.user_id)
    db.session.commit()
    return redirect(url_for("dashboard"))

@app.route("/accept-session/<session_id>")
def accept_session(session_id):
    user = require_user()
    if not user: return redirect(url_for("login"))
    session = db.session.get(Session, session_id)
    if not session or session.teacher_id != user.id or session.status != SessionStatus.REQUESTED:
        abort(404)
    session.status = SessionStatus.CONFIRMED
    # Auto-generate a Google Meet link
    meet_id = secrets.token_urlsafe(8)
    session.meet_link = f"https://meet.google.com/{meet_id}"
    db.session.commit()
    return redirect(url_for("dashboard"))

@app.route("/complete-session/<session_id>")
def complete_session(session_id):
    user = require_user()
    if not user: return redirect(url_for("login"))
    session = db.session.get(Session, session_id)
    if not session or (session.teacher_id != user.id and session.learner_id != user.id):
        abort(404)
    if session.status not in (SessionStatus.CONFIRMED, SessionStatus.REQUESTED):
        return redirect(url_for("dashboard"))
    session.status = SessionStatus.COMPLETED
    session.completed_at = datetime.utcnow()
    add_credit_transaction(session.teacher_id, 1.0, TransactionType.EARN, f"Taught {session.skill_name}", related_user_id=session.learner_id)
    db.session.commit()
    return redirect(url_for("dashboard"))

@app.route("/cancel-session/<session_id>")
def cancel_session(session_id):
    user = require_user()
    if not user: return redirect(url_for("login"))
    session = db.session.get(Session, session_id)
    if not session or (session.teacher_id != user.id and session.learner_id != user.id):
        abort(404)
    if session.status == SessionStatus.COMPLETED:
        return redirect(url_for("dashboard"))
    was_held = session.status == SessionStatus.REQUESTED
    session.status = SessionStatus.CANCELLED
    if was_held:
        add_credit_transaction(session.learner_id, 1.0, TransactionType.BONUS, f"Refund: {session.skill_name}", related_user_id=session.teacher_id)
    db.session.commit()
    return redirect(url_for("dashboard"))

# ══════════════════════════════════════════════════════════
#  ROUTES: REVIEWS
# ══════════════════════════════════════════════════════════

@app.route("/review-session/<session_id>", methods=["GET", "POST"])
def review_session(session_id):
    user = require_onboarded()
    if not user or user == "redirect_onboarding":
        return redirect(url_for("login"))
    session = db.session.get(Session, session_id)
    if not session or (session.teacher_id != user.id and session.learner_id != user.id):
        abort(404)
    if session.status != SessionStatus.COMPLETED:
        return redirect(url_for("dashboard"))
    if SessionReview.query.filter_by(session_id=session_id, reviewer_id=user.id).first():
        return redirect(url_for("dashboard"))
    reviewee_id = session.learner_id if session.teacher_id == user.id else session.teacher_id
    if request.method == "GET":
        return render_template("review_session.html", user=user, session=session, other=get_user(reviewee_id))
    rating = request.form.get("rating", type=int)
    review_text = sanitize(request.form.get("review", ""), 500)
    if not rating or rating < 1 or rating > 5:
        return render_template("review_session.html", user=user, session=session, error="Select a rating from 1 to 5.")
    db.session.add(SessionReview(session_id=session_id, reviewer_id=user.id, reviewee_id=reviewee_id, rating=rating, review=review_text))
    db.session.commit()
    return redirect(url_for("dashboard"))

# ══════════════════════════════════════════════════════════
#  ROUTES: ABOUT, LEGAL & HEALTH (before profile/param routes)
# ══════════════════════════════════════════════════════════

@app.route("/about")
def about():
    return render_template("about.html", user=current_user())

@app.route("/privacy")
def privacy():
    return render_template("privacy.html", user=current_user())

@app.route("/terms")
def terms():
    return render_template("terms.html", user=current_user())

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


# ══════════════════════════════════════════════════════════
#  ROUTES: PROFILE
# ══════════════════════════════════════════════════════════

@app.route("/profile/<user_id>")
def view_profile(user_id):
    current = current_user()
    profile = get_user(user_id)
    if not profile: abort(404)
    skills = UserSkill.query.filter(UserSkill.user_id == user_id, UserSkill.is_active == True).all()
    wants = UserWant.query.filter(UserWant.user_id == user_id).all()
    completed_count = Session.query.filter(
        ((Session.teacher_id == user_id) | (Session.learner_id == user_id)) & (Session.status == SessionStatus.COMPLETED)
    ).count()
    avg_rating = db.session.query(db.func.avg(SessionReview.rating)).filter(SessionReview.reviewee_id == user_id).scalar()
    recent = SessionReview.query.filter(SessionReview.reviewee_id == user_id).order_by(SessionReview.created_at.desc()).limit(5).all()
    enriched = [{"reviewer_name": (get_user(r.reviewer_id).full_name if get_user(r.reviewer_id) else "Someone"), "rating": r.rating, "review": r.review, "created_at": r.created_at} for r in recent]
    return render_template("profile.html", user=current, profile_user=profile, skills=skills, wants=wants,
                           completed_count=completed_count, avg_rating=round(avg_rating, 1) if avg_rating else None, recent_reviews=enriched)

# ══════════════════════════════════════════════════════════
#  ROUTES: SKILLS
# ══════════════════════════════════════════════════════════

@app.route("/add-skill", methods=["POST"])
def add_skill():
    user = require_user()
    if not user: return redirect(url_for("login"))
    name = sanitize(request.form.get("name", ""))
    category = sanitize(request.form.get("category", ""))
    description = sanitize(request.form.get("description", ""), 300)
    if name and category and category in get_pilot_categories():
        db.session.add(UserSkill(user_id=user.id, name=name, category=category, description=description))
        db.session.commit()
    return redirect(url_for("dashboard"))

@app.route("/remove-skill/<skill_id>")
def remove_skill(skill_id):
    user = require_user()
    if not user: return redirect(url_for("login"))
    skill = db.session.get(UserSkill, skill_id)
    if not skill or skill.user_id != user.id: abort(404)
    skill.is_active = False
    db.session.commit()
    return redirect(url_for("dashboard"))

# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    debug = os.environ.get("RELAY_ENV") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)
