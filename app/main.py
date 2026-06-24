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
    make_response, abort, jsonify, session,
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
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("RELAY_ENV") == "production"
app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///relay.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["PREFERRED_URL_SCHEME"] = "https" if os.environ.get("RELAY_ENV") == "production" else "http"
app.config["MAX_CONTENT_LENGTH"] = 1024 * 50

# ── Cache bust version for static assets ───────────────
import hashlib
_CACHE_BUST = hashlib.md5(str(datetime.utcnow().timestamp()).encode()).hexdigest()[:8]

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

# ── Feature flags ─────────────────────────────────────
# Variable pricing: when True, every skill costs exactly 1 credit (old behavior)
RELAY_FLAT_RATE = os.environ.get("RELAY_FLAT_RATE", "false").lower() == "true"
# Max credit cost a teacher can set per session
RELAY_MAX_CREDIT_COST = int(os.environ.get("RELAY_MAX_CREDIT_COST", "4"))
# Starter credits for new verified users
RELAY_STARTER_CREDITS = int(os.environ.get("RELAY_STARTER_CREDITS", "3"))
# Supply-only mode: when True, only users with at least one listing can book
RELAY_SUPPLY_ONLY_MODE = os.environ.get("RELAY_SUPPLY_ONLY_MODE", "false").lower() == "true"
# Monetization enabled: when True, show top-up and membership UI
RELAY_MONETIZATION_ENABLED = os.environ.get("RELAY_MONETIZATION_ENABLED", "false").lower() == "true"

# ── Import models after db init ────────────────────────
from app.models import (
    User, UserSkill, UserWant, CreditAccount, CreditTransaction,
    Session, SessionReview, SkillCategory, SessionStatus, TransactionType,
    WaitlistEntry, PasswordResetToken, SkillRequest, SessionSeries,
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
    for name, email, pw in demo_accounts:
        if get_user_by_email(email):
            continue
        user = User(
            email=email, password_hash=generate_password_hash(pw, method='pbkdf2:sha256'),
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

# Seed demo data after helper definitions are available.
with app.app_context():
    _auto_seed_demo_data()

def current_user():
    user_id = session.get("user_id")
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

def send_email(to, subject, body):
    '''Print to console in dev, SendGrid in prod.'''
    try:
        safe_body = body.replace('\n', ' | ') if body else ''
        print(f'[EMAIL] To: {to} | Subj: {subject} | {safe_body[:200]}')
    except Exception:
        pass
    try:
        if os.environ.get('RELAY_ENV') == 'production' and os.environ.get('SENDGRID_API_KEY'):
            import sendgrid
            from sendgrid.helpers.mail import Mail
            sg = sendgrid.SendGridAPIClient(api_key=os.environ['SENDGRID_API_KEY'])
            msg = Mail(from_email='noreply@joinrelay.co', to_emails=to, subject=subject, plain_text_content=body)
            sg.send(msg)
    except Exception as e:
        print(f'Email send failed (non-fatal): {e}')

@app.context_processor
def inject_globals():
    return {
        "site_name": SITE_NAME, "contact_email": CONTACT_EMAIL,
        "pilot_vertical": PILOT_VERTICAL, "pilot_vertical_name": PILOT_VERTICAL_NAME,
        "csrf_token": lambda: generate_csrf(),
        "cache_bust": _CACHE_BUST,
        "relay_flat_rate": RELAY_FLAT_RATE,
        "relay_max_credit_cost": RELAY_MAX_CREDIT_COST,
        "relay_monetization_enabled": RELAY_MONETIZATION_ENABLED,
        "relay_starter_credits": RELAY_STARTER_CREDITS,
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
        "img-src 'self' data: https://www.gravatar.com https://*.gravatar.com; frame-src 'self' https://docs.google.com; "
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
        email=email, password_hash=generate_password_hash(password, method='pbkdf2:sha256'),
        full_name=full_name, referred_by=referrer.id if referrer else None,
        verification_token=secrets.token_urlsafe(32),
    )
    db.session.add(user)
    db.session.flush()
    credit = CreditAccount(user_id=user.id, balance=float(RELAY_STARTER_CREDITS))
    db.session.add(credit)
    add_credit_transaction(user.id, float(RELAY_STARTER_CREDITS), TransactionType.BONUS, f"{RELAY_STARTER_CREDITS} free credits to start!")
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
    session["user_id"] = user.id
    session.permanent = True
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
    session["user_id"] = user.id
    session.permanent = True
    return resp

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    resp = make_response(redirect(url_for("home")))
    resp.delete_cookie("session")
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


# ── Password reset flow ────────────────────────────────

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "GET":
        return render_template("forgot_password.html", user=None, error=None, sent=False)
    email = sanitize(request.form.get("email", "")).strip().lower()
    user = get_user_by_email(email)
    if user:
        import secrets
        token = secrets.token_urlsafe(48)
        expires = datetime.utcnow() + timedelta(hours=1)
        db.session.add(PasswordResetToken(user_id=user.id, token=token, expires_at=expires))
        db.session.commit()
        reset_link = url_for("reset_password", token=token, _external=True)
        send_email(user.email, "Reset your Relay password",
            f"Hi {user.full_name.split()[0]},\n\n"
            f"Click this link to reset your password (expires in 1 hour):\n{reset_link}\n\n"
            f"If you didn't request this, ignore this email.\n\n- Relay Team")
    return render_template("forgot_password.html", user=None, error=None, sent=True)


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    reset = PasswordResetToken.query.filter_by(token=token, used=False).first()
    if not reset or reset.expires_at < datetime.utcnow():
        return render_template("error.html", user=None, code=400, message="This reset link has expired or is invalid."), 400
    if request.method == "GET":
        return render_template("reset_password.html", token=token, error=None)
    password = request.form.get("password", "")
    pw_errors = validate_password(password)
    if pw_errors:
        return render_template("reset_password.html", token=token, error=pw_errors[0])
    user = get_user(reset.user_id)
    if not user:
        return render_template("error.html", user=None, code=404, message="User not found."), 404
    user.password_hash = generate_password_hash(password)
    reset.used = True
    db.session.commit()
    return redirect(url_for("login"))


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
                           transactions=transactions, ref_link=ref_link, categories=get_pilot_categories(),
                           relay_flat_rate=RELAY_FLAT_RATE, relay_max_credit_cost=RELAY_MAX_CREDIT_COST,
                           relay_monetization_enabled=RELAY_MONETIZATION_ENABLED)

@app.route("/browse")
def browse():
    user = current_user()
    category = request.args.get("category")
    q = sanitize(request.args.get("q", ""))
    query = UserSkill.query.join(User).filter(
        User.onboarded == True, UserSkill.is_active == True,
    )
    if user:
        query = query.filter(UserSkill.user_id != user.id)
    if PILOT_VERTICAL and PILOT_VERTICAL != "all":
        query = query.filter(UserSkill.category == PILOT_VERTICAL)
    if category and category in get_pilot_categories():
        query = query.filter(UserSkill.category == category)
    if q:
        query = query.filter(UserSkill.name.ilike(f"%{q}%"))
    skills = query.order_by(UserSkill.created_at.desc()).all()
    # Sort: highest proficiency/rating first, then most recent
    def sort_key(s):
        # Calculate average rating for this teacher
        avg_rating = db.session.query(db.func.avg(SessionReview.rating)).filter(SessionReview.reviewee_id == s.user_id).scalar() or 0
        return (avg_rating, s.proficiency, s.created_at.timestamp())
    skills.sort(key=sort_key, reverse=True)
    total_skills = len(skills)
    total_users = User.query.count()
    if not user:
        return render_template("browse.html", user=None, skills=skills[:8],
                               categories=get_pilot_categories(), selected_category=category, query=q,
                               total_skills=min(total_skills, 8), total_users=total_users, ref_link=None,
                               preview_mode=True)
    ref_link = url_for("signup", ref=user.id, _external=True)
    return render_template("browse.html", user=user, skills=skills,
                           categories=get_pilot_categories(), selected_category=category, query=q,
                           total_skills=total_skills, total_users=total_users, ref_link=ref_link)

# ══════════════════════════════════════════════════════════
#  ROUTES: WAITLIST
# ══════════════════════════════════════════════════════════

@app.route("/waitlist", methods=["POST"])
def waitlist():
    """Capture non-.edu emails for waitlist."""
    email = sanitize(request.form.get("email", "")).strip().lower()
    if not email or "@" not in email:
        return redirect(url_for("home"))
    existing = WaitlistEntry.query.filter(WaitlistEntry.email == email).first()
    if not existing:
        entry = WaitlistEntry(email=email)
        db.session.add(entry)
        db.session.commit()
        send_email(email, "You're on the Relay waitlist!",
            f"Thanks for joining the Relay waitlist!\n\n"
            f"We'll let you know when Relay comes to your campus.\n\n"
            f"In the meantime, tell your friends: every referral = +1 credit at launch.\n\n- Relay Team")
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
    
    # Supply-only mode check: only users with at least one listing can book
    if RELAY_SUPPLY_ONLY_MODE:
        user_listings = UserSkill.query.filter(UserSkill.user_id == user.id, UserSkill.is_active == True).count()
        if user_listings == 0:
            return render_template("request_session.html", user=user, skill=skill, error="You need to publish a skill listing before you can book sessions. Add a skill from your dashboard first!", now=datetime.utcnow().strftime("%Y-%m-%dT%H:%M"))

    # Determine credit cost — flat rate forces 1 (applied at charge time, not just creation)
    credit_cost = 1 if RELAY_FLAT_RATE else (skill.credit_cost or 1)
    
    if request.method == "GET":
        return render_template("request_session.html", user=user, skill=skill, credit_cost=credit_cost, error=None, now=datetime.utcnow().strftime("%Y-%m-%dT%H:%M"))
    
    notes = sanitize(request.form.get("notes", ""), 500)
    scheduled_raw = request.form.get("scheduled_at", "")
    scheduled_at = None
    if scheduled_raw:
        try:
            scheduled_at = datetime.fromisoformat(scheduled_raw)
        except (ValueError, TypeError):
            pass
    # Atomic balance check with row lock to prevent race conditions
    credit = CreditAccount.query.filter(CreditAccount.user_id == user.id).with_for_update().first()
    if not credit or credit.balance < credit_cost:
        return render_template("request_session.html", user=user, skill=skill, credit_cost=credit_cost, error=f"Not enough credits. This session costs {credit_cost} credit(s).", now=datetime.utcnow().strftime("%Y-%m-%dT%H:%M"))
    credit.balance -= credit_cost  # debit immediately, refund on cancel
    session = Session(teacher_id=skill.user_id, learner_id=user.id, skill_name=skill.name, notes=notes, scheduled_at=scheduled_at)
    db.session.add(session)
    add_credit_transaction(user.id, -credit_cost, TransactionType.SPEND, f"Hold: {skill.name}", related_user_id=skill.user_id)
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
    # Track completed sessions for good-student badging
    teacher = get_user(session.teacher_id)
    learner = get_user(session.learner_id)
    if teacher:
        teacher.completed_sessions_count = (teacher.completed_sessions_count or 0) + 1
    if learner:
        learner.completed_sessions_count = (learner.completed_sessions_count or 0) + 1
    # Determine credit cost — flat rate forces 1
    credit_cost = 1 if RELAY_FLAT_RATE else 1  # default fallback
    # Try to find the skill listing to get its credit_cost
    skill = UserSkill.query.filter(UserSkill.user_id == session.teacher_id, UserSkill.name == session.skill_name, UserSkill.is_active == True).first()
    if skill and not RELAY_FLAT_RATE:
        credit_cost = skill.credit_cost or 1
    add_credit_transaction(session.teacher_id, credit_cost, TransactionType.EARN, f"Taught {session.skill_name}", related_user_id=session.learner_id)
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
        # Refund the actual credit cost, not hardcoded 1
        credit_cost = 1
        skill = UserSkill.query.filter(UserSkill.user_id == session.teacher_id, UserSkill.name == session.skill_name, UserSkill.is_active == True).first()
        if skill and not RELAY_FLAT_RATE:
            credit_cost = skill.credit_cost or 1
        # Restore the learner's balance
        credit = CreditAccount.query.filter(CreditAccount.user_id == session.learner_id).with_for_update().first()
        if credit:
            credit.balance += credit_cost
        add_credit_transaction(session.learner_id, credit_cost, TransactionType.REFUND, f"Refund: {session.skill_name}", related_user_id=session.teacher_id)
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


@app.route("/edit-profile", methods=["GET", "POST"])
def edit_profile():
    user = require_user()
    if not user:
        return redirect(url_for("login"))
    if request.method == "GET":
        return render_template("edit_profile.html", user=user, error=None)
    user.full_name = sanitize(request.form.get("full_name", ""))
    user.bio = sanitize(request.form.get("bio", ""), 500)
    user.school = sanitize(request.form.get("school", ""))
    user.major = sanitize(request.form.get("major", ""))
    user.graduation_year = sanitize(request.form.get("graduation_year", ""))
    profile_photo = request.form.get("profile_photo", "").strip()
    if profile_photo:
        user.profile_photo = profile_photo
    db.session.commit()
    return redirect(url_for("view_profile", user_id=user.id))

# ── Add send verification code route ──
import random

@app.route("/send-verification-code", methods=["POST"])
def send_verification_code():
    user = require_user()
    if not user:
        return redirect(url_for("login"))
    code = str(random.randint(100000, 999999))
    user.verification_code = code
    user.verification_code_sent_at = datetime.utcnow()
    body = f"Your Relay .edu verification code is: {code}\n\nEnter this code on the verification page to confirm your student status.\n\n- Relay Team"
    send_email(user.email, "Your Relay verification code", body)
    db.session.commit()
    return render_template("verify_edu.html", user=user, error=None, message="Verification code sent to your email!")

@app.route("/verify-edu", methods=["GET", "POST"])
def verify_edu():
    user = require_user()
    if not user:
        return redirect(url_for("login"))
    if request.method == "GET":
        return render_template("verify_edu.html", user=user, error=None, message=None)
    code = sanitize(request.form.get("code", ""))
    if user.verification_code and user.verification_code == code:
        user.edu_verified = True
        user.verification_code = None
        db.session.commit()
        return redirect(url_for("dashboard"))
    return render_template("verify_edu.html", user=user, error="Invalid code. Try again.", message=None)

# ── Add proof video route ──
@app.route("/proof-video", methods=["GET", "POST"])
def proof_video():
    user = require_user()
    if not user:
        return redirect(url_for("login"))
    if request.method == "GET":
        return render_template("proof_video.html", user=user, error=None)
    url = sanitize(request.form.get("video_url", ""))
    if url and ("youtube.com" in url or "youtu.be" in url or "vimeo.com" in url or url.startswith("http")):
        user.has_proof_video = True
        user.proof_video_url = url
        # Give content credits for uploading proof
        user.content_credit_balance = (user.content_credit_balance or 0) + 1
        add_credit_transaction(user.id, 1.0, TransactionType.BONUS, "Bonus credit for sharing proof of skill!")
        db.session.commit()
        return redirect(url_for("dashboard"))
    return render_template("proof_video.html", user=user, error="Please provide a valid video URL (YouTube, Vimeo, etc.)")

# ── Student ambassador signup ──
@app.route("/become-ambassador", methods=["POST"])
def become_ambassador():
    user = require_user()
    if not user:
        return redirect(url_for("login"))
    user.is_ambassador = True
    add_credit_transaction(user.id, 2.0, TransactionType.BONUS, "Welcome to the Relay Student Ambassador program!")
    db.session.commit()
    return redirect(url_for("dashboard"))

# ══════════════════════════════════════════════════════════
#  ROUTES: MONETIZATION (stubs — no real payments)
# ══════════════════════════════════════════════════════════

@app.route("/top-up")
def top_up():
    user = require_user()
    if not user: return redirect(url_for("login"))
    if not RELAY_MONETIZATION_ENABLED:
        return redirect(url_for("dashboard"))
    return render_template("topup.html", user=user, relay_monetization_enabled=RELAY_MONETIZATION_ENABLED)

@app.route("/top-up", methods=["POST"])
def top_up_post():
    user = require_user()
    if not user: return redirect(url_for("login"))
    if not RELAY_MONETIZATION_ENABLED:
        return redirect(url_for("dashboard"))
    amount = request.form.get("amount", 0, type=int)
    if amount < 1 or amount > 100:
        return render_template("topup.html", user=user, error="Invalid amount. Choose 1–100 credits.", relay_monetization_enabled=RELAY_MONETIZATION_ENABLED)
    # TODO: integrate payment provider (Stripe Checkout, Lemon Squeezy, etc.)
    # For now, add credits directly as a demo — remove this in production
    credit = CreditAccount.query.filter(CreditAccount.user_id == user.id).first()
    if credit:
        credit.balance += float(amount)
        add_credit_transaction(user.id, float(amount), TransactionType.TOPUP, f"Credit top-up: {amount} credits")
        db.session.commit()
    return redirect(url_for("dashboard"))

@app.route("/membership")
def membership():
    user = require_user()
    if not user: return redirect(url_for("login"))
    if not RELAY_MONETIZATION_ENABLED:
        return redirect(url_for("dashboard"))
    return render_template("membership.html", user=user, is_member=user.is_member, relay_monetization_enabled=RELAY_MONETIZATION_ENABLED)

@app.route("/membership/join", methods=["POST"])
def membership_join():
    user = require_user()
    if not user: return redirect(url_for("login"))
    if not RELAY_MONETIZATION_ENABLED:
        return redirect(url_for("dashboard"))
    # TODO: integrate payment provider for membership billing
    user.is_member = True
    user.member_since = datetime.utcnow()
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

@app.route("/safety")
def safety():
    return render_template("safety.html", user=current_user())


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
#  ROUTES: SKILL REQUESTS (demand aggregation)
# ══════════════════════════════════════════════════════════

@app.route("/requests")
def browse_requests():
    user = current_user()
    category = request.args.get("category")
    query = SkillRequest.query.filter(SkillRequest.status == "open")
    if user:
        query = query.filter(SkillRequest.user_id != user.id)
    if category and category in get_pilot_categories():
        query = query.filter(SkillRequest.category == category)
    requests = query.order_by(SkillRequest.created_at.desc()).all()
    return render_template("requests.html", user=user, requests=requests, categories=get_pilot_categories())

@app.route("/add-request", methods=["POST"])
def add_request():
    user = require_user()
    if not user: return redirect(url_for("login"))
    name = sanitize(request.form.get("name", ""))
    category = sanitize(request.form.get("category", ""))
    description = sanitize(request.form.get("description", ""), 300)
    max_credits = request.form.get("max_credits", 1, type=int)
    max_credits = max(1, min(max_credits, RELAY_MAX_CREDIT_COST))
    if name and category and category in get_pilot_categories():
        db.session.add(SkillRequest(user_id=user.id, name=name, category=category, description=description, max_credits=max_credits))
        db.session.commit()
    return redirect(url_for("browse_requests"))

@app.route("/claim-request/<request_id>", methods=["POST"])
def claim_request(request_id):
    user = require_onboarded()
    if not user or user == "redirect_onboarding":
        return redirect(url_for("login"))
    req = db.session.get(SkillRequest, request_id)
    if not req or req.status != "open" or req.user_id == user.id:
        abort(404)
    # Supply-only mode check
    if RELAY_SUPPLY_ONLY_MODE:
        user_listings = UserSkill.query.filter(UserSkill.user_id == user.id, UserSkill.is_active == True).count()
        if user_listings == 0:
            return redirect(url_for("browse_requests"))
    req.status = "claimed"
    req.claimed_by = user.id
    # Auto-create a session so the claim→booking→credit path is wired end to end
    # Use the request's max_credits as the credit cost
    credit_cost = 1 if RELAY_FLAT_RATE else min(req.max_credits or 1, RELAY_MAX_CREDIT_COST)
    # Check if learner has enough credits (with row lock)
    learner_credit = CreditAccount.query.filter(CreditAccount.user_id == req.user_id).with_for_update().first()
    if learner_credit and learner_credit.balance >= credit_cost:
        learner_credit.balance -= credit_cost
        add_credit_transaction(req.user_id, -credit_cost, TransactionType.SPEND, f"Hold: {req.name} (claimed by {user.full_name})", related_user_id=user.id)
    session = Session(teacher_id=user.id, learner_id=req.user_id, skill_name=req.name, notes=f"Claimed from request: {req.name}")
    db.session.add(session)
    db.session.commit()
    return redirect(url_for("browse_requests"))

# ══════════════════════════════════════════════════════════
#  ROUTES: SKILLS (updated with credit_cost)
# ══════════════════════════════════════════════════════════

@app.route("/add-skill", methods=["POST"])
def add_skill():
    user = require_user()
    if not user: return redirect(url_for("login"))
    name = sanitize(request.form.get("name", ""))
    category = sanitize(request.form.get("category", ""))
    description = sanitize(request.form.get("description", ""), 300)
    # credit_cost: only used when RELAY_FLAT_RATE is False
    credit_cost = request.form.get("credit_cost", 1, type=int)
    credit_cost = max(1, min(credit_cost, RELAY_MAX_CREDIT_COST))
    if name and category and category in get_pilot_categories():
        db.session.add(UserSkill(user_id=user.id, name=name, category=category, description=description, credit_cost=credit_cost))
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
