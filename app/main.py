"""Relay — Flask application. Trade skills, not money.
Security-hardened MVP with rating system, pilot vertical, and CSRF protection."""

import os
import re
import uuid
import secrets
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import bleach
import click
from email_validator import EmailNotValidError, validate_email
from flask import (
    Flask, render_template, request, redirect, url_for,
    make_response, abort, jsonify, session, g, has_request_context,
)
from flask_limiter import Limiter
from flask_migrate import Migrate
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect, generate_csrf
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy import text as sql_text
from sqlalchemy.exc import IntegrityError

from .database import db, init_db, normalize_database_url
from .email_service import EmailDeliveryError, send_transactional_email
from .ledger import InsufficientCredits, LedgerError, LedgerService
from .policies import APPROVED_PUBLIC_LOCATIONS, validate_meeting_details, validate_trial_topic
from .session_service import SessionStateMachine
from .trial_config import load_trial_config


def utc_now():
    """Return naive UTC for database columns without utcnow deprecations."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_trial_schedule(value: str) -> datetime:
    """Parse an unambiguous America/New_York wall time into naive UTC."""
    requested_local = datetime.fromisoformat(value)
    if requested_local.tzinfo is not None:
        raise ValueError("Schedule must be a local wall time")
    eastern = ZoneInfo("America/New_York")
    utc_zone = ZoneInfo("UTC")
    candidates = []
    for fold in (0, 1):
        aware = requested_local.replace(tzinfo=eastern, fold=fold)
        as_utc = aware.astimezone(utc_zone)
        round_trip = as_utc.astimezone(eastern).replace(tzinfo=None)
        if round_trip == requested_local:
            candidates.append(as_utc)
    distinct = {candidate for candidate in candidates}
    if len(distinct) != 1:
        raise ValueError("Schedule is nonexistent or ambiguous in America/New_York")
    return distinct.pop().replace(tzinfo=None)


def trial_schedule_input_min() -> str:
    """Return the earliest selectable wall time in the trial's displayed timezone."""
    now_aware_utc = utc_now().replace(tzinfo=timezone.utc)
    return (
        now_aware_utc.astimezone(ZoneInfo("America/New_York")) + timedelta(hours=1)
    ).strftime("%Y-%m-%dT%H:%M")

# ── App Setup ──────────────────────────────────────────

app = Flask(__name__)
TRIAL = load_trial_config()


def configure_proxy_boundary(application, trial_config):
    """Trust only the explicitly configured count for each forwarded header."""
    if any((
        trial_config.proxy_x_for,
        trial_config.proxy_x_proto,
        trial_config.proxy_x_host,
    )):
        application.wsgi_app = ProxyFix(
            application.wsgi_app,
            x_for=trial_config.proxy_x_for,
            x_proto=trial_config.proxy_x_proto,
            x_host=trial_config.proxy_x_host,
            x_port=0,
            x_prefix=0,
        )


configure_proxy_boundary(app, TRIAL)

# ── Security-first config ──────────────────────────────
_secret_key = os.environ.get("RELAY_SECRET_KEY")
if not _secret_key:
    if TRIAL.is_deployed:
        raise RuntimeError("RELAY_SECRET_KEY is required in production")
    _secret_key = secrets.token_hex(32)

app.config["SECRET_KEY"] = _secret_key
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = TRIAL.is_deployed
app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)
_database_url = normalize_database_url(os.environ.get("DATABASE_URL"))
if TRIAL.is_deployed and not _database_url:
    raise RuntimeError("DATABASE_URL is required in production")
app.config["SQLALCHEMY_DATABASE_URI"] = _database_url or "sqlite:///relay.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["PREFERRED_URL_SCHEME"] = "https" if TRIAL.is_deployed else "http"
app.config["MAX_CONTENT_LENGTH"] = 1024 * 50
app.config["TRUSTED_HOSTS"] = list(TRIAL.trusted_hosts) if TRIAL.is_deployed else None
app.config["RELAY_PUBLIC_URL"] = TRIAL.public_url
app.config["RELAY_EMAIL_BACKEND"] = TRIAL.email_backend

# ── Cache bust version for static assets ───────────────
_CACHE_BUST = hashlib.md5(str(utc_now().timestamp()).encode()).hexdigest()[:8]

# ── Plugins ────────────────────────────────────────────
csrf = CSRFProtect(app)
init_db(app)
migrate = Migrate(
    app,
    db,
    compare_type=True,
    render_as_batch=True,
)

# ── Rate limiter ────────────────────────────────────────
_rate_limit_storage = os.environ.get("RATE_LIMIT_STORAGE", "memory://")
if TRIAL.is_deployed and _rate_limit_storage == "memory://":
    raise RuntimeError("RATE_LIMIT_STORAGE must use shared storage in production")
_rate_limit_storage_options = (
    {"socket_connect_timeout": 1, "socket_timeout": 1}
    if _rate_limit_storage.startswith(("redis://", "rediss://"))
    else None
)
limiter = Limiter(
    get_remote_address, app=app,
    default_limits=[],
    storage_uri=_rate_limit_storage,
    storage_options=_rate_limit_storage_options,
)


def authenticated_limit_key() -> str:
    """Scope protected-route limits to one signed-in account, not a campus IP."""
    user_id = session.get("user_id")
    return f"account:{user_id}" if user_id else f"ip:{get_remote_address()}"


def submitted_email_limit_key() -> str:
    """Rate-limit an auth identity without retaining its address in limiter keys."""
    normalized = request.form.get("email", "").strip().lower()
    return f"email:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}"

# ── Configuration Constants ────────────────────────────
SITE_NAME = "Relay"
CONTACT_EMAIL = os.environ.get("RELAY_CONTACT_EMAIL", "hello@joinrelay.co")
PILOT_VERTICAL = TRIAL.category
PILOT_VERTICAL_NAME = TRIAL.category_name

# ── Feature flags ─────────────────────────────────────
# The controlled trial has one price and intentionally excludes unfinished breadth.
RELAY_FLAT_RATE = True
RELAY_MAX_CREDIT_COST = TRIAL.credit_cost
RELAY_STARTER_CREDITS = TRIAL.starter_credits
RELAY_SUPPLY_ONLY_MODE = False
RELAY_MONETIZATION_ENABLED = False

# ── Import models after db init ────────────────────────
from app.models import (
    User, UserSkill, UserWant, CreditAccount, CreditTransaction,
    Session, SessionReview, SkillCategory, SessionStatus, TransactionType,
    PasswordResetToken, EmailDelivery, ConsentAcceptance,
    UserBlock, SafetyReport, SessionDispute, ModerationAction,
)

CURRENT_CONSENT_VERSIONS = {
    "terms": "2026-07-13-draft",
    "privacy": "2026-07-13-draft",
    "age_eligibility": "2026-07-13-draft",
    "code_of_conduct": "2026-07-13-draft",
    "safety_rules": "2026-07-13-draft",
}
DATABASE_SCHEMA_REVISION = "20260713_01"

# ── Auto-seed demo data (defined before use) ──────────
# ── Initialize DB tables ──────────────────────────────

# ── Gravatar helper ─────────────────────────────────
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


def hash_secret(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def missing_current_consents(user):
    accepted = {
        (row.document, row.version)
        for row in ConsentAcceptance.query.filter_by(user_id=user.id).all()
    }
    return [
        document
        for document, version in CURRENT_CONSENT_VERSIONS.items()
        if (document, version) not in accepted
    ]


def record_current_consents(user):
    existing = {
        (row.document, row.version)
        for row in ConsentAcceptance.query.filter_by(user_id=user.id).all()
    }
    for document, version in CURRENT_CONSENT_VERSIONS.items():
        if (document, version) not in existing:
            db.session.add(
                ConsentAcceptance(user_id=user.id, document=document, version=version)
            )

# Seed demo data after helper definitions are available.

def current_user():
    user_id = session.get("user_id")
    if user_id:
        user = get_user(user_id)
        if user:
            if user.account_status != "active":
                session.clear()
                return None
            if session.get("session_version") != user.session_version:
                session.clear()
                return None
            if user.account_locked_until and user.account_locked_until > utc_now():
                return None
            now = utc_now()
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
    if not user.email_verified:
        return "redirect_verification"
    if missing_current_consents(user):
        return "redirect_consent"
    return "redirect_onboarding" if not user.onboarded else user


def require_verified_user():
    user = require_user()
    if not user or not user.email_verified or missing_current_consents(user):
        return None
    return user


def require_moderator():
    user = require_verified_user()
    if not user or user.role not in {"moderator", "admin"}:
        return None
    return user


def users_are_blocked(first_user_id, second_user_id):
    return UserBlock.query.filter(
        ((UserBlock.blocker_id == first_user_id) & (UserBlock.blocked_id == second_user_id))
        | ((UserBlock.blocker_id == second_user_id) & (UserBlock.blocked_id == first_user_id))
    ).first() is not None

def get_pilot_categories():
    return [PILOT_VERTICAL]

def get_available_skills_query():
    query = UserSkill.query.join(User).filter(
        User.onboarded == True,
        User.email_verified == True,
        User.account_status == "active",
        UserSkill.is_active == True,
    )
    if PILOT_VERTICAL and PILOT_VERTICAL != "all":
        query = query.filter(UserSkill.category == PILOT_VERTICAL)
    return query

def absolute_url(endpoint, **values):
    if has_request_context():
        relative = url_for(endpoint, **values)
    else:
        # Scheduled CLI jobs have an application context but no request context.
        # Build only the relative route here; the configured canonical origin below
        # remains the sole authority for externally delivered links.
        with app.test_request_context("/"):
            relative = url_for(endpoint, **values)
    return urljoin(f"{app.config['RELAY_PUBLIC_URL']}/", relative.lstrip("/"))


def send_email(user, subject, body, *, message_type, source_id):
    """Deliver one transactional message and persist a secret-free outcome record."""
    idempotency_key = f"{message_type}:{source_id}:{user.id}"
    delivery = EmailDelivery.query.filter_by(
        idempotency_key=idempotency_key
    ).with_for_update().first()
    if delivery and delivery.status == "delivered":
        return
    if not delivery:
        delivery = EmailDelivery(
            recipient_user_id=user.id,
            message_type=message_type,
            source_id=source_id,
            idempotency_key=idempotency_key,
            attempts=0,
        )
        db.session.add(delivery)
        try:
            db.session.flush()
        except IntegrityError:
            # A competing worker created the same source-recipient delivery first.
            db.session.rollback()
            delivery = EmailDelivery.query.filter_by(
                idempotency_key=idempotency_key
            ).with_for_update().one()
            if delivery.status == "delivered":
                return
    delivery.attempts += 1
    delivery.last_attempt_at = utc_now()
    try:
        send_transactional_email(app, to=user.email, subject=subject, body=body)
    except EmailDeliveryError:
        delivery.status = "failed"
        delivery.failure_code = "provider_rejected"
        db.session.commit()
        raise
    delivery.status = "delivered"
    delivery.failure_code = ""
    delivery.delivered_at = utc_now()
    db.session.commit()


def send_session_notifications(recipients, *, booked, message_type, subject):
    """Send minimal session mail after the state transaction; return failure count."""
    details_url = absolute_url("session_details", session_id=booked.id)
    body = (
        f"A Relay session update is available. Sign in to review the private details:\n"
        f"{details_url}\n\n- Relay Team"
    )
    failures = 0
    for recipient in recipients:
        if not recipient or recipient.account_status != "active":
            continue
        try:
            send_email(
                recipient,
                subject,
                body,
                message_type=message_type,
                source_id=booked.id,
            )
        except EmailDeliveryError:
            failures += 1
    return failures


def notification_failure_response(user):
    return render_template(
        "error.html",
        user=user,
        code=202,
        message=(
            "The session change was saved, but Relay could not deliver one or more notifications. "
            "The update is visible in the dashboard; contact support if either participant needs help."
        ),
    ), 202

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
        "trial_participant_mode": TRIAL.participant_mode,
    }

def jinja_capitalize(s):
    return s.replace("_", " ").title() if s else ""

def jinja_time_ago(dt):
    if not dt: return ""
    diff = utc_now() - dt
    if diff.days > 30: return f"{diff.days // 30}mo ago"
    if diff.days > 0: return f"{diff.days}d ago"
    if diff.seconds > 3600: return f"{diff.seconds // 3600}h ago"
    if diff.seconds > 60: return f"{diff.seconds // 60}m ago"
    return "just now"

def jinja_stars(rating):
    return ("★" * rating + "☆" * (5 - rating)) if rating else ""


def jinja_trial_time(dt):
    if not dt:
        return "Not scheduled"
    utc_value = dt.replace(tzinfo=ZoneInfo("UTC")) if dt.tzinfo is None else dt
    local = utc_value.astimezone(ZoneInfo("America/New_York"))
    return local.strftime("%a, %b %#d at %#I:%M %p %Z")

app.jinja_env.filters["capitalize"] = jinja_capitalize
app.jinja_env.filters["time_ago"] = jinja_time_ago
app.jinja_env.filters["stars"] = jinja_stars
app.jinja_env.filters["trial_time"] = jinja_trial_time
app.jinja_env.globals["SkillCategory"] = SkillCategory
app.jinja_env.globals["SessionStatus"] = SessionStatus

# ── Error handlers ─────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", user=current_user(), code=404, message="Page not found."), 404

@app.errorhandler(429)
def ratelimit_error(e):
    return render_template("error.html", user=current_user(), code=429, message="Too many requests. Please slow down."), 429

@app.errorhandler(500)
def server_error(e):
    app.logger.error(json.dumps({
        "event": "unhandled_error",
        "request_id": g.get("request_id"),
        "endpoint": request.endpoint or "unmatched",
    }, separators=(",", ":")), exc_info=True)
    # Do not query user/session state here; the original failure may be a database outage.
    return render_template("error.html", user=None, code=500, message="Something went wrong."), 500

# ── Security headers ──────────────────────────────────

@app.before_request
def begin_request():
    g.request_id = str(uuid.uuid4())
    g.request_started = time.monotonic()

@app.after_request
def add_security_headers(response):
    response.headers["X-Request-ID"] = g.get("request_id", str(uuid.uuid4()))
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    )
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    app.logger.info(json.dumps({
        "event": "http_request",
        "request_id": g.get("request_id"),
        "endpoint": request.endpoint or "unmatched",
        "method": request.method,
        "status": response.status_code,
        "duration_ms": round((time.monotonic() - g.get("request_started", time.monotonic())) * 1000, 1),
    }, separators=(",", ":")))
    return response

# ══════════════════════════════════════════════════════════
#  INTENTIONALLY UNAVAILABLE LEGACY ROUTES
# ══════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════
#  ROUTES: AUTH
# ══════════════════════════════════════════════════════════

@app.route("/")
def home():
    user = current_user()
    return render_template("index.html", user=user)

@app.route("/signup", methods=["GET", "POST"])
@limiter.limit("60 per hour")
def signup():
    if request.method == "GET":
        return render_template("signup.html", user=None, error=None, ref=request.args.get("ref", ""))

    email = sanitize(request.form.get("email", "")).strip().lower()
    password = request.form.get("password", "")
    full_name = sanitize(request.form.get("full_name", "")).strip()
    required_acceptances = (
        "accept_terms", "accept_privacy", "confirm_age",
        "accept_conduct", "accept_safety",
    )
    if any(request.form.get(field) != "yes" for field in required_acceptances):
        return render_template(
            "signup.html", user=None, ref="",
            error="Accept each current trial policy and confirm you are at least 18."
        ), 400
    try:
        validated = validate_email(email, check_deliverability=False)
        email = validated.normalized.lower()
        email_domain = validated.domain.lower()
    except EmailNotValidError:
        return render_template("signup.html", user=None, ref="", error="Enter a valid institutional email address.")
    if not TRIAL.email_domain_allowed(email_domain):
        return render_template("signup.html", user=None, ref="", error="This controlled trial is limited to invited NYU email addresses.")
    if not TRIAL.email_is_invited(email):
        return render_template("signup.html", user=None, ref="", error="This email is not on the controlled-trial invite list.")
    if get_user_by_email(email):
        return render_template("signup.html", user=None, ref="", error="An account with this email already exists.")
    pw_errors = validate_password(password)
    if pw_errors:
        return render_template("signup.html", user=None, ref="", error=pw_errors[0])
    if not full_name or len(full_name) < 2:
        return render_template("signup.html", user=None, ref="", error="Please enter your full name.")
    verification_secret = secrets.token_urlsafe(32)
    now = utc_now()
    user = User(
        email=email, password_hash=generate_password_hash(password, method='pbkdf2:sha256'),
        full_name=full_name,
        verification_token_hash=hash_secret(verification_secret),
        verification_expires_at=now + timedelta(hours=1),
        verification_sent_at=now,
    )
    db.session.add(user)
    db.session.flush()
    credit = CreditAccount(user_id=user.id, balance=0)
    db.session.add(credit)
    record_current_consents(user)
    db.session.commit()
    session.clear()
    session["user_id"] = user.id
    session["session_version"] = user.session_version
    session.permanent = True
    verify_link = absolute_url("verify_email", token=verification_secret)
    try:
        send_email(user, "Verify your Relay account",
            f"Hi {user.full_name.split()[0]},\n\n"
            f"Open this link to verify your invited NYU email:\n{verify_link}\n\n"
            f"After verification, {RELAY_STARTER_CREDITS} starter credits will be added to your account.\n\n- Relay Team",
            message_type="verification", source_id=user.verification_token_hash)
    except EmailDeliveryError:
        return render_template(
            "error.html", user=user, code=503,
            message="Your account was created, but Relay could not deliver the verification email. Try resending it later or contact support."
        ), 503
    return redirect(url_for("verify_edu"))

@app.route("/login", methods=["GET", "POST"])
@limiter.limit("120 per minute")
@limiter.limit(
    "10 per 15 minutes",
    key_func=submitted_email_limit_key,
    methods=["POST"],
)
def login():
    if request.method == "GET":
        return render_template("login.html", user=None, error=None)
    email = sanitize(request.form.get("email", "")).strip().lower()
    password = request.form.get("password", "")
    user = get_user_by_email(email)
    if (
        user
        and user.account_status == "active"
        and user.account_locked_until
        and user.account_locked_until > utc_now()
    ):
        remaining = max(1, int((user.account_locked_until - utc_now()).total_seconds() // 60))
        return render_template("login.html", user=None, error=f"Account locked. Try again in {remaining} minutes."), 429
    if (
        not user
        or user.account_status != "active"
        or not check_password_hash(user.password_hash, password)
    ):
        if user and user.account_status == "active":
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= 5:
                user.account_locked_until = utc_now() + timedelta(minutes=15)
            db.session.commit()
        return render_template("login.html", user=None, error="Invalid email or password.")
    user.failed_login_attempts = 0
    user.account_locked_until = None
    db.session.commit()
    session.clear()
    session["user_id"] = user.id
    session["session_version"] = user.session_version
    session.permanent = True
    return redirect(url_for("dashboard"))

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    resp = make_response(redirect(url_for("home")))
    resp.delete_cookie("session")
    return resp

@app.route("/verify-email/<token>")
@limiter.limit("120 per minute")
def verify_email(token):
    token_hash = hash_secret(token)
    user = User.query.filter_by(verification_token_hash=token_hash).first()
    if user and user.verification_expires_at and user.verification_expires_at >= utc_now():
        user.email_verified = True
        user.edu_verified = True
        user.verification_token_hash = None
        user.verification_expires_at = None
        LedgerService.grant_starter(user, RELAY_STARTER_CREDITS)
        db.session.commit()
        session.clear()
        session["user_id"] = user.id
        session["session_version"] = user.session_version
        session.permanent = True
        return redirect(url_for("onboarding" if not user.onboarded else "dashboard"))
    return render_template("error.html", user=user, code=400, message="Invalid link."), 400


# ── Password reset flow ────────────────────────────────

@app.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("120 per hour")
@limiter.limit("5 per hour", key_func=submitted_email_limit_key, methods=["POST"])
def forgot_password():
    if request.method == "GET":
        return render_template("forgot_password.html", user=None, error=None, sent=False)
    email = sanitize(request.form.get("email", "")).strip().lower()
    user = get_user_by_email(email)
    if user:
        import secrets
        token = secrets.token_urlsafe(48)
        expires = utc_now() + timedelta(hours=1)
        reset = PasswordResetToken(user_id=user.id, token_hash=hash_secret(token), expires_at=expires)
        db.session.add(reset)
        db.session.commit()
        reset_link = absolute_url("reset_password", token=token)
        try:
            send_email(user, "Reset your Relay password",
                f"Hi {user.full_name.split()[0]},\n\n"
                f"Open this link to reset your password (expires in 1 hour):\n{reset_link}\n\n"
                f"If you didn't request this, ignore this email.\n\n- Relay Team",
                message_type="password_reset", source_id=reset.id)
        except EmailDeliveryError:
            app.logger.warning(json.dumps({
                "event": "password_reset_delivery_failed",
                "request_id": g.get("request_id"),
            }, separators=(",", ":")))
    return render_template("forgot_password.html", user=None, error=None, sent=True)


@app.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit("60 per hour")
def reset_password(token):
    reset = PasswordResetToken.query.filter_by(token_hash=hash_secret(token), used=False).first()
    if not reset or reset.expires_at < utc_now():
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
    user.session_version += 1
    PasswordResetToken.query.filter_by(user_id=user.id, used=False).update({"used": True})
    db.session.commit()
    session.clear()
    return redirect(url_for("login"))


# ══════════════════════════════════════════════════════════
#  ROUTES: ONBOARDING
# ══════════════════════════════════════════════════════════

@app.route("/consent", methods=["GET", "POST"])
@limiter.limit("30 per hour", key_func=authenticated_limit_key, methods=["POST"])
def consent():
    user = require_user()
    if not user:
        return redirect(url_for("login"))
    if not user.email_verified:
        return redirect(url_for("verify_edu"))
    missing = missing_current_consents(user)
    if not missing:
        return redirect(url_for("dashboard" if user.onboarded else "onboarding"))
    if request.method == "GET":
        return render_template(
            "consent.html", user=user, error=None,
            policy_versions=CURRENT_CONSENT_VERSIONS,
        )
    required_acceptances = (
        "accept_terms", "accept_privacy", "confirm_age",
        "accept_conduct", "accept_safety",
    )
    if any(request.form.get(field) != "yes" for field in required_acceptances):
        return render_template(
            "consent.html", user=user,
            error="Accept each current trial policy and confirm you are at least 18.",
            policy_versions=CURRENT_CONSENT_VERSIONS,
        ), 400
    record_current_consents(user)
    db.session.commit()
    return redirect(url_for("dashboard" if user.onboarded else "onboarding"))

@app.route("/onboarding", methods=["GET", "POST"])
@limiter.limit("30 per hour", key_func=authenticated_limit_key, methods=["POST"])
def onboarding():
    user = require_user()
    if not user:
        return redirect(url_for("login"))
    if not user.email_verified:
        return redirect(url_for("verify_edu"))
    if missing_current_consents(user):
        return redirect(url_for("consent"))
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
    topic_error = validate_trial_topic(teach_name, teach_desc)
    topic_error = topic_error or validate_trial_topic(learn_name, learn_desc)
    if topic_error:
        return render_template(
            "onboarding.html", user=user, categories=get_pilot_categories(), error=topic_error
        ), 400

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
    if user == "redirect_verification":
        return redirect(url_for("verify_edu"))
    if user == "redirect_consent":
        return redirect(url_for("consent"))
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
            "teacher_completed": s.teacher_completed, "learner_completed": s.learner_completed,
        })

    pending = Session.query.filter(Session.teacher_id == user.id, Session.status == SessionStatus.REQUESTED).order_by(Session.created_at.desc()).all()
    enriched_pending = []
    for s in pending:
        learner = get_user(s.learner_id)
        enriched_pending.append({
            "id": s.id,
            "skill_name": s.skill_name,
            "learner_username": learner.full_name.split()[0] if learner else "Someone",
            "notes": s.notes,
            "scheduled_at": s.scheduled_at,
        })

    transactions = CreditTransaction.query.filter(CreditTransaction.user_id == user.id).order_by(CreditTransaction.created_at.desc()).limit(10).all()
    ref_link = None

    return render_template("dashboard.html", user=user, my_skills=my_skills, my_wants=my_wants,
                           credit=credit, sessions=enriched_sessions, pending_requests=enriched_pending,
                           transactions=transactions, ref_link=ref_link, categories=get_pilot_categories(),
                           relay_flat_rate=RELAY_FLAT_RATE, relay_max_credit_cost=RELAY_MAX_CREDIT_COST,
                           relay_monetization_enabled=RELAY_MONETIZATION_ENABLED,
                           approved_public_locations=APPROVED_PUBLIC_LOCATIONS)

@app.route("/browse")
def browse():
    user = current_user()
    verified_user = user if user and user.email_verified and not missing_current_consents(user) else None
    category = request.args.get("category")
    q = sanitize(request.args.get("q", ""))
    query = UserSkill.query.join(User).filter(
        User.onboarded == True,
        User.email_verified == True,
        User.account_status == "active",
        UserSkill.is_active == True,
    )
    if verified_user:
        query = query.filter(UserSkill.user_id != verified_user.id)
        blocked_ids = {
            block.blocked_id for block in UserBlock.query.filter_by(blocker_id=verified_user.id).all()
        } | {
            block.blocker_id for block in UserBlock.query.filter_by(blocked_id=verified_user.id).all()
        }
        if blocked_ids:
            query = query.filter(~UserSkill.user_id.in_(blocked_ids))
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
    if not verified_user:
        return render_template("browse.html", user=user, skills=skills[:8],
                               categories=get_pilot_categories(), selected_category=category, query=q,
                               total_skills=min(total_skills, 8), total_users=total_users, ref_link=None,
                               preview_mode=True)
    return render_template("browse.html", user=verified_user, skills=skills,
                           categories=get_pilot_categories(), selected_category=category, query=q,
                           total_skills=total_skills, total_users=total_users, ref_link=None,
                           preview_mode=False)

# ══════════════════════════════════════════════════════════
#  ROUTES: WAITLIST
# ══════════════════════════════════════════════════════════

@app.route("/waitlist", methods=["POST"])
def waitlist():
    abort(404)

# ══════════════════════════════════════════════════════════
#  ROUTES: SESSIONS
# ══════════════════════════════════════════════════════════

@app.route("/request-session/<skill_id>", methods=["GET", "POST"])
@limiter.limit("30 per hour", key_func=authenticated_limit_key, methods=["POST"])
def request_session(skill_id):
    user = require_onboarded()
    if not user:
        return redirect(url_for("login"))
    if user == "redirect_verification":
        return redirect(url_for("verify_edu"))
    if user == "redirect_consent":
        return redirect(url_for("consent"))
    if user == "redirect_onboarding":
        return redirect(url_for("onboarding"))
    skill = db.session.get(UserSkill, skill_id)
    teacher = get_user(skill.user_id) if skill else None
    if (
        not skill or not skill.is_active or skill.category != SkillCategory(PILOT_VERTICAL)
        or not teacher or not teacher.onboarded or not teacher.email_verified
        or teacher.account_status != "active"
    ):
        abort(404)
    if skill.user_id == user.id:
        return render_template("request_session.html", user=user, skill=skill, error="You can't request a session from yourself!", now=trial_schedule_input_min())
    if users_are_blocked(user.id, skill.user_id):
        abort(404)
    
    # Supply-only mode check: only users with at least one listing can book
    if RELAY_SUPPLY_ONLY_MODE:
        user_listings = UserSkill.query.filter(UserSkill.user_id == user.id, UserSkill.is_active == True).count()
        if user_listings == 0:
            return render_template("request_session.html", user=user, skill=skill, error="You need to publish a skill listing before you can book sessions. Add a skill from your dashboard first!", now=trial_schedule_input_min())

    credit_cost = TRIAL.credit_cost
    
    if request.method == "GET":
        return render_template("request_session.html", user=user, skill=skill, credit_cost=credit_cost, error=None, now=trial_schedule_input_min())
    
    notes = sanitize(request.form.get("notes", ""), 500)
    scheduled_raw = request.form.get("scheduled_at", "")
    try:
        scheduled_at = parse_trial_schedule(scheduled_raw)
    except (ValueError, TypeError):
        return render_template(
            "request_session.html", user=user, skill=skill, credit_cost=credit_cost,
            error="Choose an unambiguous valid date and time in America/New_York.",
            now=trial_schedule_input_min()
        ), 400
    now_utc = utc_now()
    if scheduled_at <= now_utc + timedelta(hours=1) or scheduled_at > now_utc + timedelta(days=30):
        return render_template(
            "request_session.html", user=user, skill=skill, credit_cost=credit_cost,
            error="Choose a time at least one hour and no more than 30 days from now.",
            now=trial_schedule_input_min()
        ), 400
    # Atomic balance check with row lock to prevent race conditions
    credit = CreditAccount.query.filter(CreditAccount.user_id == user.id).with_for_update().first()
    if not credit or credit.balance < credit_cost:
        return render_template("request_session.html", user=user, skill=skill, credit_cost=credit_cost, error=f"Not enough credits. This session costs {credit_cost} credit(s).", now=trial_schedule_input_min())
    booked_session = Session(teacher_id=skill.user_id, learner_id=user.id, skill_name=skill.name, notes=notes, scheduled_at=scheduled_at, amount_charged=credit_cost)
    db.session.add(booked_session)
    db.session.flush()
    try:
        LedgerService.hold_for_session(booked_session, actor_user_id=user.id)
    except InsufficientCredits:
        db.session.rollback()
        return render_template(
            "request_session.html", user=user, skill=skill, credit_cost=credit_cost,
            error=f"Not enough credits. This session costs {credit_cost} credit.",
            now=trial_schedule_input_min()
        ), 409
    db.session.commit()
    if send_session_notifications(
        [teacher],
        booked=booked_session,
        message_type="session_requested",
        subject="New Relay session request",
    ):
        return notification_failure_response(user)
    return redirect(url_for("dashboard"))

@app.route("/accept-session/<session_id>", methods=["POST"])
@limiter.limit("60 per hour", key_func=authenticated_limit_key)
def accept_session(session_id):
    user = require_onboarded()
    if not user:
        return redirect(url_for("login"))
    if user == "redirect_verification":
        return redirect(url_for("verify_edu"))
    if user == "redirect_consent":
        return redirect(url_for("consent"))
    if user == "redirect_onboarding":
        return redirect(url_for("onboarding"))
    session = Session.query.filter_by(id=session_id).with_for_update().first()
    if not session or session.teacher_id != user.id or session.status != SessionStatus.REQUESTED:
        abort(404)
    if users_are_blocked(session.teacher_id, session.learner_id):
        abort(404)
    meeting_value, meeting_error = validate_meeting_details(
        request.form.get("meeting_type", ""), request.form.get("meeting_details", "")
    )
    if meeting_error or not session.scheduled_at:
        return render_template(
            "error.html", user=user, code=400,
            message=meeting_error or "The request needs a valid schedule before acceptance."
        ), 400
    SessionStateMachine.transition(session, SessionStatus.CONFIRMED)
    session.meet_link = meeting_value
    db.session.commit()
    if send_session_notifications(
        [get_user(session.learner_id)],
        booked=session,
        message_type="session_accepted",
        subject="Relay session accepted",
    ):
        return notification_failure_response(user)
    return redirect(url_for("dashboard"))

@app.route("/complete-session/<session_id>", methods=["POST"])
@limiter.limit("60 per hour", key_func=authenticated_limit_key)
def complete_session(session_id):
    user = require_onboarded()
    if not user:
        return redirect(url_for("login"))
    if user == "redirect_verification":
        return redirect(url_for("verify_edu"))
    if user == "redirect_consent":
        return redirect(url_for("consent"))
    if user == "redirect_onboarding":
        return redirect(url_for("onboarding"))
    session = Session.query.filter_by(id=session_id).with_for_update().first()
    if not session or (session.teacher_id != user.id and session.learner_id != user.id):
        abort(404)
    if users_are_blocked(session.teacher_id, session.learner_id):
        abort(404)
    if session.status != SessionStatus.CONFIRMED:
        return redirect(url_for("dashboard"))
    changed, settled = SessionStateMachine.confirm_completion(session, user.id)
    if not changed:
        return redirect(url_for("dashboard"))
    if settled:
        session.completed_at = utc_now()
        teacher = get_user(session.teacher_id)
        learner = get_user(session.learner_id)
        if teacher:
            teacher.completed_sessions_count = (teacher.completed_sessions_count or 0) + 1
        if learner:
            learner.completed_sessions_count = (learner.completed_sessions_count or 0) + 1
        LedgerService.payout_session(session, actor_user_id=user.id)

    db.session.commit()
    if settled and send_session_notifications(
        [get_user(session.teacher_id), get_user(session.learner_id)],
        booked=session,
        message_type="session_completed",
        subject="Relay session completed",
    ):
        return notification_failure_response(user)
    return redirect(url_for("dashboard"))

@app.route("/cancel-session/<session_id>", methods=["POST"])
@limiter.limit("60 per hour", key_func=authenticated_limit_key)
def cancel_session(session_id):
    user = require_onboarded()
    if not user:
        return redirect(url_for("login"))
    if user == "redirect_verification":
        return redirect(url_for("verify_edu"))
    if user == "redirect_consent":
        return redirect(url_for("consent"))
    if user == "redirect_onboarding":
        return redirect(url_for("onboarding"))
    session = Session.query.filter_by(id=session_id).with_for_update().first()
    if not session or (session.teacher_id != user.id and session.learner_id != user.id):
        abort(404)
    if session.status == SessionStatus.CANCELLED:
        return redirect(url_for("dashboard"))
    if session.status not in {SessionStatus.REQUESTED, SessionStatus.CONFIRMED}:
        return render_template(
            "error.html", user=user, code=409,
            message="This session now requires moderator resolution rather than cancellation."
        ), 409
    SessionStateMachine.transition(session, SessionStatus.CANCELLED)
    LedgerService.refund_session(
        session, actor_user_id=user.id,
        reason=f"Controlled-trial cancellation refund: {session.skill_name}",
    )
    db.session.commit()
    other_id = session.learner_id if user.id == session.teacher_id else session.teacher_id
    if send_session_notifications(
        [get_user(other_id)],
        booked=session,
        message_type="session_cancelled",
        subject="Relay session cancelled",
    ):
        return notification_failure_response(user)
    return redirect(url_for("dashboard"))


@app.route("/session/<session_id>")
def session_details(session_id):
    user = require_onboarded()
    if not user:
        return redirect(url_for("login"))
    if user == "redirect_verification":
        return redirect(url_for("verify_edu"))
    if user == "redirect_consent":
        return redirect(url_for("consent"))
    if user == "redirect_onboarding":
        return redirect(url_for("onboarding"))
    booked = db.session.get(Session, session_id)
    if not booked or user.id not in {booked.teacher_id, booked.learner_id}:
        abort(404)
    other_user_id = booked.learner_id if user.id == booked.teacher_id else booked.teacher_id
    blocked = users_are_blocked(booked.teacher_id, booked.learner_id)
    dispute = SessionDispute.query.filter_by(session_id=booked.id).first()
    return render_template(
        "session_details.html",
        user=user,
        booked=booked,
        teacher=get_user(booked.teacher_id),
        learner=get_user(booked.learner_id),
        other=get_user(other_user_id),
        blocked=blocked,
        dispute=dispute,
    )


@app.route("/block-user/<blocked_user_id>", methods=["POST"])
@limiter.limit("20 per hour", key_func=authenticated_limit_key)
def block_user(blocked_user_id):
    user = require_verified_user()
    if not user:
        return redirect(url_for("login"))
    blocked_user = get_user(blocked_user_id)
    reason = sanitize(request.form.get("reason", ""), 300)
    if not blocked_user or blocked_user.id == user.id or not reason:
        abort(400)
    existing = UserBlock.query.filter_by(blocker_id=user.id, blocked_id=blocked_user.id).first()
    if not existing:
        db.session.add(UserBlock(blocker_id=user.id, blocked_id=blocked_user.id, reason=reason))

    active_sessions = Session.query.filter(
        (
            ((Session.teacher_id == user.id) & (Session.learner_id == blocked_user.id))
            | ((Session.teacher_id == blocked_user.id) & (Session.learner_id == user.id))
        ),
        Session.status.in_([SessionStatus.REQUESTED, SessionStatus.CONFIRMED]),
    ).with_for_update().all()
    for booked in active_sessions:
        SessionStateMachine.transition(booked, SessionStatus.CANCELLED)
        booked.cancellation_reason = "Interaction blocked by a participant"
        LedgerService.refund_session(
            booked, actor_user_id=user.id,
            reason=f"Block safety refund: {booked.skill_name}",
        )
    db.session.commit()
    return redirect(url_for("dashboard"))


@app.route("/report-user/<reported_user_id>", methods=["POST"])
@limiter.limit("10 per hour", key_func=authenticated_limit_key)
def report_user(reported_user_id):
    user = require_verified_user()
    if not user:
        return redirect(url_for("login"))
    reported = get_user(reported_user_id)
    category = sanitize(request.form.get("category", ""), 32)
    description = sanitize(request.form.get("description", ""), 1000)
    session_id = sanitize(request.form.get("session_id", "")) or None
    allowed_categories = {"safety", "harassment", "fraud", "prohibited_content", "privacy", "other"}
    if not reported or reported.id == user.id or category not in allowed_categories or not description:
        abort(400)
    if session_id:
        booked = db.session.get(Session, session_id)
        if (
            not booked or user.id not in {booked.teacher_id, booked.learner_id}
            or reported.id not in {booked.teacher_id, booked.learner_id}
        ):
            abort(400)
    db.session.add(SafetyReport(
        reporter_id=user.id,
        reported_user_id=reported.id,
        session_id=session_id,
        category=category,
        description=description,
    ))
    db.session.commit()
    return redirect(url_for("session_details", session_id=session_id) if session_id else url_for("dashboard"))


@app.route("/dispute-session/<session_id>", methods=["POST"])
@limiter.limit("10 per hour", key_func=authenticated_limit_key)
def dispute_session(session_id):
    user = require_verified_user()
    if not user:
        return redirect(url_for("login"))
    booked = Session.query.filter_by(id=session_id).with_for_update().first()
    reason = sanitize(request.form.get("reason", ""), 1000)
    if not booked or user.id not in {booked.teacher_id, booked.learner_id} or not reason:
        abort(400)
    if booked.status not in {SessionStatus.CONFIRMED, SessionStatus.COMPLETED, SessionStatus.NO_SHOW}:
        return render_template("error.html", user=user, code=409, message="This session cannot enter dispute from its current state."), 409
    prior_status = booked.status.value if hasattr(booked.status, "value") else booked.status
    existing = SessionDispute.query.filter_by(session_id=booked.id).first()
    if not existing:
        db.session.add(SessionDispute(
            session_id=booked.id,
            opened_by_id=user.id,
            reason=reason,
            resolution=f"pending_from:{prior_status}",
        ))
    elif not existing.resolution:
        existing.resolution = f"pending_from:{prior_status}"
    SessionStateMachine.transition(booked, SessionStatus.DISPUTED)
    db.session.commit()
    other_id = booked.learner_id if user.id == booked.teacher_id else booked.teacher_id
    if send_session_notifications(
        [get_user(other_id)],
        booked=booked,
        message_type="session_dispute_opened",
        subject="Relay session needs moderator review",
    ):
        return notification_failure_response(user)
    return redirect(url_for("session_details", session_id=booked.id))


@app.route("/no-show/<session_id>", methods=["POST"])
@limiter.limit("10 per hour", key_func=authenticated_limit_key)
def mark_no_show(session_id):
    user = require_verified_user()
    if not user:
        return redirect(url_for("login"))
    booked = Session.query.filter_by(id=session_id).with_for_update().first()
    if not booked or user.id not in {booked.teacher_id, booked.learner_id}:
        abort(404)
    if (
        booked.status != SessionStatus.CONFIRMED
        or not booked.scheduled_at
        or booked.scheduled_at > utc_now() - timedelta(minutes=15)
    ):
        return render_template("error.html", user=user, code=409, message="A no-show can be reported only after the scheduled grace period."), 409
    reason = sanitize(request.form.get("reason", ""), 1000) or "Participant did not attend after the 15-minute grace period."
    SessionStateMachine.transition(booked, SessionStatus.NO_SHOW)
    if not SessionDispute.query.filter_by(session_id=booked.id).first():
        db.session.add(SessionDispute(session_id=booked.id, opened_by_id=user.id, reason=reason))
    db.session.commit()
    other_id = booked.learner_id if user.id == booked.teacher_id else booked.teacher_id
    if send_session_notifications(
        [get_user(other_id)],
        booked=booked,
        message_type="session_no_show_opened",
        subject="Relay session needs moderator review",
    ):
        return notification_failure_response(user)
    return redirect(url_for("session_details", session_id=booked.id))


@app.route("/moderator")
def moderator_queue():
    user = require_moderator()
    if not user:
        abort(404)
    reports = SafetyReport.query.filter(SafetyReport.status.in_(["open", "reviewing"])).order_by(SafetyReport.created_at).all()
    disputes = SessionDispute.query.filter_by(status="open").order_by(SessionDispute.created_at).all()
    dispute_sessions = {
        d.id: Session.query.get(d.session_id) for d in disputes
    }
    actions = ModerationAction.query.order_by(ModerationAction.created_at.desc()).limit(50).all()
    return render_template(
        "moderator_queue.html", user=user, reports=reports, disputes=disputes,
        dispute_sessions=dispute_sessions,
        actions=actions, get_user=get_user,
    )


@app.route("/moderator/resolve/<item_type>/<item_id>", methods=["POST"])
@limiter.limit("120 per hour", key_func=authenticated_limit_key)
def moderator_resolve(item_type, item_id):
    moderator = require_moderator()
    if not moderator:
        abort(404)
    action_type = sanitize(request.form.get("action_type", ""), 32)
    reason = sanitize(request.form.get("reason", ""), 500)
    evidence_notes = sanitize(request.form.get("evidence_notes", ""), 1500)
    allowed_actions = {"dismiss", "suspend", "remove_listings", "refund_hold", "reverse_completed"}
    if action_type not in allowed_actions or not reason or not evidence_notes:
        abort(400)

    report = SafetyReport.query.filter_by(id=item_id).with_for_update().first() if item_type == "report" else None
    dispute = SessionDispute.query.filter_by(id=item_id).with_for_update().first() if item_type == "dispute" else None
    if not report and not dispute:
        abort(404)
    if dispute and action_type not in {"dismiss", "refund_hold", "reverse_completed"}:
        abort(400)
    if report and report.status not in {"open", "reviewing"}:
        return render_template(
            "error.html", user=moderator, code=409,
            message="This safety report has already been resolved. No action was recorded."
        ), 409
    if dispute and dispute.status != "open":
        return render_template(
            "error.html", user=moderator, code=409,
            message="This dispute has already been resolved. No action was recorded."
        ), 409
    session_id = dispute.session_id if dispute else report.session_id
    booked = (
        Session.query.filter_by(id=session_id).with_for_update().first()
        if session_id else None
    )
    requested_target = sanitize(request.form.get("target_user_id", ""))
    target_user_id = report.reported_user_id if report else requested_target
    if dispute and (
        not booked or target_user_id not in {booked.teacher_id, booked.learner_id}
    ):
        abort(400)
    target = get_user(target_user_id) if target_user_id else None

    reversal_source_id = f"{booked.id}:completed_settlement" if booked else ""
    if action_type == "reverse_completed" and (
        not booked
        or CreditTransaction.query.filter_by(
            type=TransactionType.REVERSAL.value,
            source_type="session_reversal",
            source_id=reversal_source_id,
        ).first()
    ):
        return render_template(
            "error.html", user=moderator, code=409,
            message="This completed settlement has already been reversed. No action was recorded."
        ), 409
    if action_type == "refund_hold" and (
        not booked or booked.status == SessionStatus.CANCELLED
    ):
        return render_template(
            "error.html", user=moderator, code=409,
            message="This held credit has already been resolved. No action was recorded."
        ), 409

    action = ModerationAction(
        moderator_id=moderator.id,
        target_user_id=target_user_id or None,
        report_id=report.id if report else None,
        dispute_id=dispute.id if dispute else None,
        session_id=booked.id if booked else None,
        action_type=action_type,
        reason=reason,
        evidence_notes=evidence_notes,
    )
    db.session.add(action)
    db.session.flush()
    try:
        if action_type == "dismiss" and dispute and booked.status == SessionStatus.DISPUTED:
            prior_value = (
                dispute.resolution.removeprefix("pending_from:")
                if dispute.resolution.startswith("pending_from:")
                else (SessionStatus.COMPLETED.value if booked.completed_at else SessionStatus.CONFIRMED.value)
            )
            try:
                prior_status = SessionStatus(prior_value)
            except ValueError:
                abort(409)
            if prior_status not in {
                SessionStatus.CONFIRMED,
                SessionStatus.COMPLETED,
                SessionStatus.NO_SHOW,
            }:
                abort(409)
            SessionStateMachine.transition(booked, prior_status)
        elif action_type == "suspend":
            if (
                not target or target.id == moderator.id or target.role == "admin"
                or (target.role == "moderator" and moderator.role != "admin")
            ):
                abort(400)
            target.account_status = "suspended"
            target.session_version += 1
            PasswordResetToken.query.filter_by(user_id=target.id, used=False).update({"used": True})
            UserSkill.query.filter_by(user_id=target.id, is_active=True).update({"is_active": False})
            active_sessions = Session.query.filter(
                ((Session.teacher_id == target.id) | (Session.learner_id == target.id)),
                Session.status.in_([SessionStatus.REQUESTED, SessionStatus.CONFIRMED]),
            ).with_for_update().all()
            for active_session in active_sessions:
                LedgerService.refund_session(
                    active_session,
                    actor_user_id=moderator.id,
                    reason="Safety suspension refund",
                )
                SessionStateMachine.transition(active_session, SessionStatus.CANCELLED)
                active_session.cancellation_reason = "Participant suspended by moderator"
        elif action_type == "remove_listings":
            if not target:
                abort(400)
            UserSkill.query.filter_by(user_id=target.id, is_active=True).update({"is_active": False})
        elif action_type == "refund_hold":
            if not booked or booked.completed_at:
                abort(400)
            LedgerService.refund_session(booked, actor_user_id=moderator.id, reason=reason)
            SessionStateMachine.transition(booked, SessionStatus.CANCELLED)
            booked.cancellation_reason = reason
        elif action_type == "reverse_completed":
            if not booked or not booked.completed_at:
                abort(400)
            LedgerService.reverse_completed_session(
                booked,
                actor_user_id=moderator.id,
                reason=reason,
            )
            SessionStateMachine.transition(booked, SessionStatus.CANCELLED)
            booked.cancellation_reason = reason
    except (InsufficientCredits, LedgerError):
        db.session.rollback()
        return render_template(
            "error.html", user=moderator, code=409,
            message="The settlement is inconsistent or the reversal would create a negative balance. No moderation or ledger change was committed."
        ), 409

    now = utc_now()
    if report:
        report.status = "dismissed" if action_type == "dismiss" else "resolved"
        report.resolved_at = now
    if dispute:
        dispute.status = "dismissed" if action_type == "dismiss" else "resolved"
        dispute.resolution = reason
        dispute.resolved_at = now
    db.session.commit()
    if dispute and booked and send_session_notifications(
        [get_user(booked.teacher_id), get_user(booked.learner_id)],
        booked=booked,
        message_type="session_dispute_resolved",
        subject="Relay moderator review completed",
    ):
        return notification_failure_response(moderator)
    return redirect(url_for("moderator_queue"))

# ══════════════════════════════════════════════════════════
#  ROUTES: SESSION TIMEOUT / JANITOR
# ══════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════
#  ROUTES: REVIEWS
# ══════════════════════════════════════════════════════════

@app.route("/review-session/<session_id>", methods=["GET", "POST"])
@limiter.limit("30 per hour", key_func=authenticated_limit_key, methods=["POST"])
def review_session(session_id):
    user = require_onboarded()
    if not user:
        return redirect(url_for("login"))
    if user == "redirect_verification":
        return redirect(url_for("verify_edu"))
    if user == "redirect_consent":
        return redirect(url_for("consent"))
    if user == "redirect_onboarding":
        return redirect(url_for("onboarding"))
    session = Session.query.filter_by(id=session_id).with_for_update().first()
    if not session or (session.teacher_id != user.id and session.learner_id != user.id):
        abort(404)
    if users_are_blocked(session.teacher_id, session.learner_id):
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
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if SessionReview.query.filter_by(session_id=session_id, reviewer_id=user.id).first():
            return redirect(url_for("dashboard"))
        raise
    return redirect(url_for("dashboard"))


@app.route("/edit-profile", methods=["GET", "POST"])
@limiter.limit("30 per hour", key_func=authenticated_limit_key, methods=["POST"])
def edit_profile():
    user = require_verified_user()
    if not user:
        return redirect(url_for("verify_edu" if current_user() else "login"))
    if request.method == "GET":
        return render_template("edit_profile.html", user=user, error=None)
    user.full_name = sanitize(request.form.get("full_name", ""))
    user.bio = sanitize(request.form.get("bio", ""), 500)
    user.school = sanitize(request.form.get("school", ""))
    user.major = sanitize(request.form.get("major", ""))
    user.graduation_year = sanitize(request.form.get("graduation_year", ""))
    db.session.commit()
    return redirect(url_for("view_profile", user_id=user.id))


@app.route("/account/export")
@limiter.limit("10 per hour", key_func=authenticated_limit_key)
def export_account():
    user = require_verified_user()
    if not user:
        return redirect(url_for("login"))
    sessions = Session.query.filter(
        (Session.teacher_id == user.id) | (Session.learner_id == user.id)
    ).order_by(Session.created_at).all()
    payload = {
        "exported_at": utc_now().isoformat() + "Z",
        "account": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "bio": user.bio,
            "school": user.school,
            "major": user.major,
            "graduation_year": user.graduation_year,
            "created_at": user.created_at.isoformat() + "Z",
            "email_verified": user.email_verified,
            "account_status": user.account_status,
            "role": user.role,
        },
        "consents": [
            {"document": row.document, "version": row.version, "accepted_at": row.accepted_at.isoformat() + "Z"}
            for row in ConsentAcceptance.query.filter_by(user_id=user.id).order_by(ConsentAcceptance.accepted_at).all()
        ],
        "skills": [
            {"name": row.name, "category": str(row.category), "description": row.description, "active": row.is_active}
            for row in UserSkill.query.filter_by(user_id=user.id).all()
        ],
        "learning_interests": [
            {"name": row.name, "category": str(row.category), "description": row.description}
            for row in UserWant.query.filter_by(user_id=user.id).all()
        ],
        "sessions": [
            {
                "id": row.id,
                "teacher_id": row.teacher_id,
                "learner_id": row.learner_id,
                "skill_name": row.skill_name,
                "status": row.status.value if hasattr(row.status, "value") else row.status,
                "scheduled_at": row.scheduled_at.isoformat() + "Z" if row.scheduled_at else None,
                "completed_at": row.completed_at.isoformat() + "Z" if row.completed_at else None,
                "notes": row.notes,
                "meeting_details": row.meet_link,
                "cancellation_reason": row.cancellation_reason,
            }
            for row in sessions
        ],
        "credit_ledger": [
            {
                "id": row.id,
                "amount": row.amount,
                "type": row.type,
                "reason": row.description,
                "source_type": row.source_type,
                "source_id": row.source_id,
                "created_at": row.created_at.isoformat() + "Z",
            }
            for row in CreditTransaction.query.filter_by(user_id=user.id).order_by(CreditTransaction.created_at).all()
        ],
        "reports_submitted": [
            {
                "id": row.id,
                "reported_user_id": row.reported_user_id,
                "session_id": row.session_id,
                "category": row.category,
                "description": row.description,
                "status": row.status,
                "created_at": row.created_at.isoformat() + "Z",
                "resolved_at": row.resolved_at.isoformat() + "Z" if row.resolved_at else None,
            }
            for row in SafetyReport.query.filter_by(reporter_id=user.id).order_by(SafetyReport.created_at).all()
        ],
        "blocks_created": [
            {
                "id": row.id,
                "blocked_user_id": row.blocked_id,
                "reason": row.reason,
                "created_at": row.created_at.isoformat() + "Z",
            }
            for row in UserBlock.query.filter_by(blocker_id=user.id).order_by(UserBlock.created_at).all()
        ],
        "disputes_opened": [
            {
                "id": row.id,
                "session_id": row.session_id,
                "reason": row.reason,
                "status": row.status,
                "resolution": row.resolution,
                "created_at": row.created_at.isoformat() + "Z",
                "resolved_at": row.resolved_at.isoformat() + "Z" if row.resolved_at else None,
            }
            for row in SessionDispute.query.filter_by(opened_by_id=user.id).order_by(SessionDispute.created_at).all()
        ],
        "reviews_authored": [
            {
                "id": row.id,
                "session_id": row.session_id,
                "reviewee_id": row.reviewee_id,
                "rating": row.rating,
                "review": row.review,
                "created_at": row.created_at.isoformat() + "Z",
            }
            for row in SessionReview.query.filter_by(reviewer_id=user.id).order_by(SessionReview.created_at).all()
        ],
        "email_delivery_outcomes": [
            {
                "id": row.id,
                "message_type": row.message_type,
                "source_id": row.source_id,
                "status": row.status,
                "attempts": row.attempts,
                "failure_code": row.failure_code,
                "created_at": row.created_at.isoformat() + "Z",
                "last_attempt_at": row.last_attempt_at.isoformat() + "Z" if row.last_attempt_at else None,
                "delivered_at": row.delivered_at.isoformat() + "Z" if row.delivered_at else None,
            }
            for row in EmailDelivery.query.filter_by(recipient_user_id=user.id).order_by(EmailDelivery.created_at).all()
        ],
        "moderation_outcomes": [
            {
                "id": row.id,
                "session_id": row.session_id,
                "action_type": row.action_type,
                "reason": row.reason,
                "created_at": row.created_at.isoformat() + "Z",
            }
            for row in ModerationAction.query.filter_by(target_user_id=user.id).order_by(ModerationAction.created_at).all()
        ],
    }
    response = jsonify(payload)
    response.headers["Content-Disposition"] = 'attachment; filename="relay-account-export.json"'
    return response


@app.route("/account/delete", methods=["POST"])
@limiter.limit("5 per day", key_func=authenticated_limit_key)
def delete_account():
    user = require_verified_user()
    if not user:
        return redirect(url_for("login"))
    password = request.form.get("password", "")
    confirmation = request.form.get("confirmation", "")
    if confirmation != "DELETE" or not check_password_hash(user.password_hash, password):
        return render_template(
            "error.html", user=user, code=400,
            message="Account deletion requires your current password and the exact confirmation DELETE."
        ), 400

    active_sessions = Session.query.filter(
        ((Session.teacher_id == user.id) | (Session.learner_id == user.id)),
        Session.status.in_([SessionStatus.REQUESTED, SessionStatus.CONFIRMED]),
    ).with_for_update().all()
    cancellation_recipients = []
    for booked in active_sessions:
        LedgerService.refund_session(
            booked,
            actor_user_id=user.id,
            reason="Account closure refund",
        )
        SessionStateMachine.transition(booked, SessionStatus.CANCELLED)
        booked.cancellation_reason = "Participant closed their account"
        other_id = booked.learner_id if user.id == booked.teacher_id else booked.teacher_id
        cancellation_recipients.append((booked, get_user(other_id)))

    opaque_suffix = uuid.uuid4().hex
    user.email = f"deleted-{opaque_suffix}@deleted.invalid"
    user.full_name = "Deleted participant"
    user.bio = ""
    user.avatar_url = ""
    user.profile_photo = ""
    user.school = ""
    user.major = ""
    user.graduation_year = ""
    user.password_hash = generate_password_hash(secrets.token_urlsafe(48))
    user.email_verified = False
    user.edu_verified = False
    user.onboarded = False
    user.account_status = "deleted"
    user.session_version += 1
    user.verification_token_hash = None
    user.verification_expires_at = None
    PasswordResetToken.query.filter_by(user_id=user.id, used=False).update({"used": True})
    UserSkill.query.filter_by(user_id=user.id, is_active=True).update({"is_active": False})
    UserWant.query.filter_by(user_id=user.id).delete()
    UserBlock.query.filter(
        (UserBlock.blocker_id == user.id) | (UserBlock.blocked_id == user.id)
    ).delete(synchronize_session=False)
    db.session.commit()
    session.clear()
    delivery_failures = 0
    for booked, recipient in cancellation_recipients:
        delivery_failures += send_session_notifications(
            [recipient],
            booked=booked,
            message_type="session_cancelled",
            subject="Relay session cancelled",
        )
    if delivery_failures:
        return render_template(
            "error.html",
            user=None,
            code=202,
            message=(
                "Your account was closed, but Relay could not deliver one or more "
                "session-cancellation notifications. Contact support if another "
                "participant needs help."
            ),
        ), 202
    return redirect(url_for("home"))

@app.route("/resend-verification", methods=["POST"])
@limiter.limit("10 per hour", key_func=authenticated_limit_key)
def resend_verification():
    user = require_user()
    if not user:
        return redirect(url_for("login"))
    if user.email_verified:
        return redirect(url_for("dashboard" if user.onboarded else "onboarding"))
    now = utc_now()
    if user.verification_sent_at and user.verification_sent_at > now - timedelta(minutes=5):
        return render_template(
            "verify_edu.html", user=user,
            error="Wait five minutes before requesting another verification link.", message=None
        ), 429
    verification_secret = secrets.token_urlsafe(32)
    user.verification_token_hash = hash_secret(verification_secret)
    user.verification_expires_at = now + timedelta(hours=1)
    user.verification_sent_at = now
    verify_link = absolute_url("verify_email", token=verification_secret)
    db.session.commit()
    try:
        send_email(
            user, "Verify your Relay account",
            f"Hi {user.full_name.split()[0]},\n\nOpen this link to verify your invited NYU email:\n{verify_link}\n\n- Relay Team",
            message_type="verification", source_id=user.verification_token_hash,
        )
    except EmailDeliveryError:
        return render_template(
            "verify_edu.html", user=user, error="Relay could not deliver the verification email. Try again later or contact support.", message=None
        ), 503
    return render_template("verify_edu.html", user=user, error=None, message="A new verification link was sent.")


@app.route("/send-verification-code", methods=["POST"])
def send_verification_code():
    abort(404)

@app.route("/verify-edu")
def verify_edu():
    user = require_user()
    if not user:
        return redirect(url_for("login"))
    if user.email_verified:
        return redirect(url_for("dashboard"))
    return render_template("verify_edu.html", user=user, error=None, message=None)

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


@app.route("/conduct")
def conduct():
    return render_template("conduct.html", user=current_user())


@app.route("/health")
@app.route("/health/live")
def health_live():
    return jsonify({"status": "ok"}), 200


@app.route("/health/ready")
def health_ready():
    try:
        db.session.execute(sql_text("SELECT 1"))
        revision = db.session.execute(
            sql_text("SELECT version_num FROM alembic_version")
        ).scalar_one_or_none()
        limiter_storage_ready = limiter.storage.check()
    except Exception:
        db.session.rollback()
        return jsonify({"status": "not_ready"}), 503
    if revision != DATABASE_SCHEMA_REVISION:
        return jsonify({"status": "not_ready"}), 503
    if not limiter_storage_ready:
        return jsonify({"status": "not_ready"}), 503
    return jsonify({"status": "ready"}), 200


@app.cli.command("reconcile-credits")
@click.option("--user-id", help="Limit the read-only report to one account.")
def reconcile_credits(user_id=None):
    """Report balance/ledger discrepancies without changing data."""
    query = CreditAccount.query
    if user_id:
        query = query.filter_by(user_id=user_id)
    results = [LedgerService.reconcile(account.user_id) for account in query.order_by(CreditAccount.user_id).all()]
    report = {
        "mode": "read-only",
        "accounts": [
            {
                "user_id": result.user_id,
                "balance": result.balance,
                "ledger_total": result.ledger_total,
                "reconciles": result.reconciles,
            }
            for result in results
        ],
        "discrepancy_count": sum(not result.reconciles for result in results),
    }
    click.echo(json.dumps(report, sort_keys=True))
    if report["discrepancy_count"]:
        raise click.ClickException(
            "Discrepancies found. No repair was attempted; use a reviewed versioned migration."
        )


@app.cli.command("settle-expired-requests")
@click.option("--apply", "apply_changes", is_flag=True, help="Commit source-unique refunds and cancellations.")
@click.option("--grace-minutes", type=click.IntRange(min=15, max=1440), default=60, show_default=True)
def settle_expired_requests(apply_changes=False, grace_minutes=60):
    """Preview or settle unaccepted requests after the configured grace period."""
    cutoff = utc_now() - timedelta(minutes=grace_minutes)
    candidates = Session.query.filter(
        Session.status == SessionStatus.REQUESTED,
        Session.scheduled_at.is_not(None),
        Session.scheduled_at <= cutoff,
    ).order_by(Session.id).all()
    report = {
        "mode": "apply" if apply_changes else "dry-run",
        "cutoff_utc": cutoff.isoformat() + "Z",
        "candidate_count": len(candidates),
        "settled_count": 0,
        "delivery_failure_count": 0,
    }
    if not apply_changes:
        click.echo(json.dumps(report, sort_keys=True))
        return
    if os.environ.get("RELAY_SCHEDULER_AUTHENTICATED", "").lower() != "true":
        raise click.ClickException(
            "Apply mode requires an authenticated scheduler context. No changes were made."
        )
    settled = []
    try:
        for candidate in candidates:
            booked = Session.query.filter_by(id=candidate.id).with_for_update().one()
            if booked.status != SessionStatus.REQUESTED or booked.scheduled_at > cutoff:
                continue
            LedgerService.refund_session(
                booked,
                actor_user_id=booked.learner_id,
                reason="Unaccepted request expired after the trial grace period",
            )
            SessionStateMachine.transition(booked, SessionStatus.CANCELLED)
            booked.cancellation_reason = "Unaccepted request expired"
            report["settled_count"] += 1
            settled.append(booked)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    for booked in settled:
        report["delivery_failure_count"] += send_session_notifications(
            [get_user(booked.teacher_id), get_user(booked.learner_id)],
            booked=booked,
            message_type="session_expired",
            subject="Relay session request expired",
        )
    click.echo(json.dumps(report, sort_keys=True))
    if report["delivery_failure_count"]:
        raise click.ClickException(
            "Settlement succeeded, but one or more expiry notifications failed. Inspect secret-free delivery records."
        )


@app.cli.command("send-session-reminders")
@click.option(
    "--apply",
    "apply_changes",
    is_flag=True,
    help="Send each due participant reminder once.",
)
@click.option(
    "--within-minutes",
    type=click.IntRange(min=15, max=2880),
    default=1440,
    show_default=True,
    help="Include confirmed sessions starting within this future window.",
)
def send_session_reminders(apply_changes=False, within_minutes=1440):
    """Preview or send idempotent reminders for upcoming confirmed sessions."""
    now = utc_now()
    horizon = now + timedelta(minutes=within_minutes)
    candidates = Session.query.filter(
        Session.status == SessionStatus.CONFIRMED,
        Session.scheduled_at.is_not(None),
        Session.scheduled_at > now,
        Session.scheduled_at <= horizon,
    ).order_by(Session.scheduled_at, Session.id).all()
    report = {
        "mode": "apply" if apply_changes else "dry-run",
        "window_end_utc": horizon.isoformat() + "Z",
        "candidate_count": len(candidates),
        "recipient_count": 0,
        "delivery_failure_count": 0,
    }
    if not apply_changes:
        click.echo(json.dumps(report, sort_keys=True))
        return
    if os.environ.get("RELAY_SCHEDULER_AUTHENTICATED", "").lower() != "true":
        raise click.ClickException(
            "Apply mode requires an authenticated scheduler context. No reminders were sent."
        )

    for booked in candidates:
        if users_are_blocked(booked.teacher_id, booked.learner_id):
            continue
        recipients = [get_user(booked.teacher_id), get_user(booked.learner_id)]
        active_recipients = [
            recipient
            for recipient in recipients
            if recipient and recipient.account_status == "active"
        ]
        report["recipient_count"] += len(active_recipients)
        report["delivery_failure_count"] += send_session_notifications(
            active_recipients,
            booked=booked,
            message_type="session_reminder",
            subject="Upcoming Relay session reminder",
        )
    click.echo(json.dumps(report, sort_keys=True))
    if report["delivery_failure_count"]:
        raise click.ClickException(
            "One or more reminders failed. Session state was unchanged; inspect secret-free delivery records."
        )


@app.cli.command("prepare-rehearsal-data")
@click.option(
    "--apply",
    "apply_changes",
    is_flag=True,
    help="Create the deterministic synthetic rehearsal fixture.",
)
def prepare_rehearsal_data(apply_changes=False):
    """Preview or create a privacy-safe, idempotent non-production fixture."""
    synthetic_users = (
        ("relay-rehearsal-teacher@example.invalid", "Relay Rehearsal Teacher"),
        ("relay-rehearsal-learner@example.invalid", "Relay Rehearsal Learner"),
    )
    existing_count = User.query.filter(User.email.in_([row[0] for row in synthetic_users])).count()
    report = {
        "mode": "apply" if apply_changes else "dry-run",
        "fixture": "relay-rehearsal-v1",
        "synthetic_user_count": len(synthetic_users),
        "existing_user_count": existing_count,
        "created_user_count": 0,
        "created_listing_count": 0,
    }
    if not apply_changes:
        click.echo(json.dumps(report, sort_keys=True))
        return
    if TRIAL.environment not in {"test", "staging"}:
        raise click.ClickException(
            "Rehearsal data is allowed only in test or staging. No changes were made."
        )
    if os.environ.get("RELAY_REHEARSAL_DATA_AUTHORIZED", "").lower() != "true":
        raise click.ClickException(
            "Apply mode requires explicit rehearsal-data authorization. No changes were made."
        )
    rehearsal_password = os.environ.get("RELAY_REHEARSAL_PASSWORD", "")
    password_errors = validate_password(rehearsal_password)
    if password_errors:
        raise click.ClickException(
            "RELAY_REHEARSAL_PASSWORD must satisfy the application password policy."
        )

    try:
        created = {}
        for email, full_name in synthetic_users:
            user = User.query.filter_by(email=email).first()
            if user and (
                user.full_name != full_name
                or user.school != "Synthetic rehearsal fixture"
            ):
                raise click.ClickException(
                    "A reserved synthetic identity is already used by unexpected data. No changes were committed."
                )
            if not user:
                user = User(
                    email=email,
                    full_name=full_name,
                    password_hash=generate_password_hash(rehearsal_password),
                    email_verified=True,
                    edu_verified=True,
                    onboarded=True,
                    school="Synthetic rehearsal fixture",
                    account_status="active",
                    role="user",
                )
                db.session.add(user)
                db.session.flush()
                db.session.add(CreditAccount(user_id=user.id, balance=0))
                report["created_user_count"] += 1
            elif not user.credit_balance:
                db.session.add(CreditAccount(user_id=user.id, balance=0))
                db.session.flush()
            record_current_consents(user)
            LedgerService.grant_starter(user, TRIAL.starter_credits)
            created[email] = user

        teacher = created[synthetic_users[0][0]]
        listing = UserSkill.query.filter_by(
            user_id=teacher.id,
            name="Watercolor fundamentals",
        ).first()
        if not listing:
            db.session.add(UserSkill(
                user_id=teacher.id,
                name="Watercolor fundamentals",
                category=PILOT_VERTICAL,
                description="Synthetic creative-skill listing for controlled rehearsal only.",
                proficiency=3,
                credit_cost=TRIAL.credit_cost,
            ))
            report["created_listing_count"] = 1
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    click.echo(json.dumps(report, sort_keys=True))


@app.cli.command("trial-health-report")
def trial_health_report():
    """Emit aggregate, read-only trial operations metrics without participant PII."""
    session_counts = {
        status.value: Session.query.filter_by(status=status).count()
        for status in SessionStatus
    }
    reconciliation = [
        LedgerService.reconcile(account.user_id)
        for account in CreditAccount.query.order_by(CreditAccount.user_id).all()
    ]
    report = {
        "mode": "read-only",
        "generated_at": utc_now().isoformat() + "Z",
        "participants": {
            "active": User.query.filter_by(account_status="active").count(),
            "verified": User.query.filter_by(account_status="active", email_verified=True).count(),
            "onboarded": User.query.filter_by(account_status="active", onboarded=True).count(),
            "synthetic_rehearsal": User.query.filter(
                User.email.like("%@example.invalid")
            ).count(),
        },
        "active_listings": UserSkill.query.filter_by(is_active=True).count(),
        "sessions": session_counts,
        "open_safety_reports": SafetyReport.query.filter_by(status="open").count(),
        "open_disputes": SessionDispute.query.filter_by(status="open").count(),
        "failed_email_deliveries": EmailDelivery.query.filter_by(status="failed").count(),
        "ledger_discrepancies": sum(not item.reconciles for item in reconciliation),
    }
    click.echo(json.dumps(report, sort_keys=True))


# ══════════════════════════════════════════════════════════
#  ROUTES: PROFILE
# ══════════════════════════════════════════════════════════

@app.route("/profile/<user_id>")
def view_profile(user_id):
    current = current_user()
    if not current or not current.email_verified or missing_current_consents(current):
        abort(404)
    profile = get_user(user_id)
    if not profile or not profile.email_verified or profile.account_status != "active":
        abort(404)
    if current.id != profile.id and users_are_blocked(current.id, profile.id):
        abort(404)
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
#  ROUTES: AFTER LOGIN INIT / REDIRECT
# ══════════════════════════════════════════════════════════
@app.route("/add-skill", methods=["POST"])
@limiter.limit("30 per hour", key_func=authenticated_limit_key)
def add_skill():
    user = require_onboarded()
    if not user:
        return redirect(url_for("login"))
    if user == "redirect_verification":
        return redirect(url_for("verify_edu"))
    if user == "redirect_consent":
        return redirect(url_for("consent"))
    if user == "redirect_onboarding":
        return redirect(url_for("onboarding"))
    name = sanitize(request.form.get("name", ""))
    category = sanitize(request.form.get("category", ""))
    description = sanitize(request.form.get("description", ""), 300)
    topic_error = validate_trial_topic(name, description)
    if not name:
        return render_template(
            "error.html", user=user, code=400, message="Enter a skill name."
        ), 400
    if category not in get_pilot_categories():
        return render_template(
            "error.html",
            user=user,
            code=400,
            message="That category is outside the controlled trial.",
        ), 400
    if topic_error:
        return render_template(
            "error.html", user=user, code=400, message=topic_error
        ), 400
    db.session.add(UserSkill(
        user_id=user.id,
        name=name,
        category=category,
        description=description,
        credit_cost=TRIAL.credit_cost,
    ))
    db.session.commit()
    return redirect(url_for("dashboard"))

@app.route("/remove-skill/<skill_id>", methods=["POST"])
@limiter.limit("30 per hour", key_func=authenticated_limit_key)
def remove_skill(skill_id):
    user = require_onboarded()
    if not user:
        return redirect(url_for("login"))
    if user == "redirect_verification":
        return redirect(url_for("verify_edu"))
    if user == "redirect_consent":
        return redirect(url_for("consent"))
    if user == "redirect_onboarding":
        return redirect(url_for("onboarding"))
    skill = db.session.get(UserSkill, skill_id)
    if not skill or skill.user_id != user.id: abort(404)
    skill.is_active = False
    db.session.commit()
    return redirect(url_for("dashboard"))

# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    debug = not TRIAL.is_deployed
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)
