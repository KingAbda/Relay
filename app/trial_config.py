"""Single source of truth for Relay's controlled-trial contract."""

from __future__ import annotations

from dataclasses import dataclass
import os
from urllib.parse import urlparse

from email_validator import EmailNotValidError, validate_email


VALID_TRIAL_CATEGORIES = frozenset(
    {
        "creative",
        "academic",
        "technical",
        "social",
        "lifestyle",
        "finance",
        "languages",
        "trades",
        "other",
    }
)

CATEGORY_NAMES = {
    "creative": "Creative",
    "academic": "Academic",
    "technical": "Technical",
    "social": "Social",
    "lifestyle": "Lifestyle",
    "finance": "Finance & Career",
    "languages": "Languages",
    "trades": "Trades",
    "other": "Other",
}


def _csv(value: str | None) -> tuple[str, ...]:
    return tuple(item.strip().lower() for item in (value or "").split(",") if item.strip())


def _positive_int(name: str, value: str | None, default: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if parsed < 1 or parsed > 10:
        raise RuntimeError(f"{name} must be between 1 and 10")
    return parsed


def _proxy_hops(name: str, value: str | None, *, required: bool) -> int:
    if required and value is None:
        raise RuntimeError(f"{name} is required in production")
    try:
        parsed = int(value) if value is not None else 0
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if parsed < 0 or parsed > 5:
        raise RuntimeError(f"{name} must be between 0 and 5")
    return parsed


@dataclass(frozen=True)
class TrialConfig:
    environment: str
    category: str
    credit_cost: int
    starter_credits: int
    public_url: str
    trusted_hosts: tuple[str, ...]
    allowed_email_domains: tuple[str, ...]
    invited_emails: tuple[str, ...]
    require_invite: bool
    email_backend: str
    proxy_x_for: int
    proxy_x_proto: int
    proxy_x_host: int

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_deployed(self) -> bool:
        """Treat staging and production as equally fail-closed environments."""
        return self.environment in {"staging", "production"}

    @property
    def category_name(self) -> str:
        return CATEGORY_NAMES[self.category]

    @property
    def participant_mode(self) -> str:
        return "invite-only"

    def email_domain_allowed(self, domain: str) -> bool:
        normalized = domain.strip().lower().rstrip(".")
        return any(
            normalized == allowed or normalized.endswith(f".{allowed}")
            for allowed in self.allowed_email_domains
        )

    def email_is_invited(self, email: str) -> bool:
        if not self.require_invite:
            return True
        return email.strip().lower() in self.invited_emails


def load_trial_config(environ: dict[str, str] | os._Environ[str] = os.environ) -> TrialConfig:
    environment = environ.get("RELAY_ENV", "development").strip().lower()
    if environment not in {"development", "test", "staging", "production"}:
        raise RuntimeError(
            "RELAY_ENV must be development, test, staging, or production"
        )
    deployed = environment in {"staging", "production"}
    configured_category = environ.get("RELAY_TRIAL_CATEGORY")
    category = (configured_category or ("" if deployed else "creative")).strip().lower()

    if category not in VALID_TRIAL_CATEGORIES:
        if deployed and not configured_category:
            raise RuntimeError(
                "RELAY_TRIAL_CATEGORY is required in deployed environments; Relay fails closed"
            )
        raise RuntimeError(
            "RELAY_TRIAL_CATEGORY must name exactly one supported category; 'all' is not allowed"
        )

    if deployed:
        secret_key = environ.get("RELAY_SECRET_KEY", "")
        weak_secret_values = {
            "change-me",
            "changeme",
            "replace-me",
            "replace-with-a-random-secret",
            "secret",
        }
        if len(secret_key) < 32 or secret_key.strip().lower() in weak_secret_values:
            raise RuntimeError(
                "RELAY_SECRET_KEY must be a non-placeholder secret of at least 32 characters in production"
            )

    public_url = environ.get("RELAY_PUBLIC_URL", "http://localhost:8000").strip().rstrip("/")
    parsed_public_url = urlparse(public_url)
    if parsed_public_url.scheme not in {"http", "https"} or not parsed_public_url.hostname:
        raise RuntimeError("RELAY_PUBLIC_URL must be an absolute HTTP(S) URL")
    if deployed and parsed_public_url.scheme != "https":
        raise RuntimeError("RELAY_PUBLIC_URL must use HTTPS in deployed environments")

    trusted_hosts = _csv(environ.get("RELAY_TRUSTED_HOSTS"))
    if not trusted_hosts:
        trusted_hosts = (parsed_public_url.hostname.lower(),)
    if deployed and parsed_public_url.hostname.lower() not in trusted_hosts:
        raise RuntimeError(
            "RELAY_TRUSTED_HOSTS must include the RELAY_PUBLIC_URL hostname"
        )

    allowed_email_domains = _csv(environ.get("RELAY_ALLOWED_EMAIL_DOMAINS")) or ("nyu.edu",)
    invited_emails = _csv(environ.get("RELAY_INVITED_EMAILS"))
    require_invite = environ.get(
        "RELAY_REQUIRE_INVITE", "true" if deployed else "false"
    ).strip().lower() == "true"

    email_backend = environ.get(
        "RELAY_EMAIL_BACKEND", "smtp" if deployed else "memory"
    ).strip().lower()
    if email_backend not in {"memory", "smtp", "disabled"}:
        raise RuntimeError("RELAY_EMAIL_BACKEND must be memory, smtp, or disabled")
    if deployed and email_backend != "smtp":
        raise RuntimeError("RELAY_EMAIL_BACKEND must be smtp in deployed environments")
    if deployed and (
        not environ.get("RELAY_SMTP_HOST", "").strip()
        or not environ.get("RELAY_EMAIL_FROM", "").strip()
    ):
        raise RuntimeError(
            "RELAY_SMTP_HOST and RELAY_EMAIL_FROM are required in deployed environments"
        )
    if deployed:
        if allowed_email_domains != ("nyu.edu",):
            raise RuntimeError(
                "RELAY_ALLOWED_EMAIL_DOMAINS must be exactly nyu.edu for this controlled trial"
            )
        if not require_invite:
            raise RuntimeError("RELAY_REQUIRE_INVITE must be true in production")
        if not 10 <= len(invited_emails) <= 20 or len(set(invited_emails)) != len(invited_emails):
            raise RuntimeError(
                "RELAY_INVITED_EMAILS must contain 10–20 unique addresses in production"
            )
        normalized_invites = []
        for invited_email in invited_emails:
            try:
                validated_invite = validate_email(invited_email, check_deliverability=False)
            except EmailNotValidError as exc:
                raise RuntimeError(
                    "RELAY_INVITED_EMAILS contains an invalid address"
                ) from exc
            normalized_invite = validated_invite.normalized.lower()
            normalized_domain = validated_invite.domain.lower().rstrip(".")
            if not any(
                normalized_domain == allowed
                or normalized_domain.endswith(f".{allowed}")
                for allowed in allowed_email_domains
            ):
                raise RuntimeError(
                    "Every invited address must match RELAY_ALLOWED_EMAIL_DOMAINS"
                )
            normalized_invites.append(normalized_invite)
        invited_emails = tuple(normalized_invites)
        database_url = environ.get("DATABASE_URL", "").strip()
        if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise RuntimeError("DATABASE_URL must use PostgreSQL in production")
        rate_storage = environ.get("RATE_LIMIT_STORAGE", "").strip()
        if not rate_storage.startswith(("redis://", "rediss://")):
            raise RuntimeError("RATE_LIMIT_STORAGE must use Redis in production")

    proxy_x_for = _proxy_hops(
        "RELAY_PROXY_X_FOR", environ.get("RELAY_PROXY_X_FOR"),
        required=deployed,
    )
    proxy_x_proto = _proxy_hops(
        "RELAY_PROXY_X_PROTO", environ.get("RELAY_PROXY_X_PROTO"),
        required=deployed,
    )
    proxy_x_host = _proxy_hops(
        "RELAY_PROXY_X_HOST", environ.get("RELAY_PROXY_X_HOST"),
        required=deployed,
    )
    if deployed and proxy_x_for == 0:
        raise RuntimeError("RELAY_PROXY_X_FOR must trust at least one production proxy")
    if deployed and proxy_x_proto == 0:
        raise RuntimeError("RELAY_PROXY_X_PROTO must trust at least one production proxy")

    return TrialConfig(
        environment=environment,
        category=category,
        credit_cost=1,
        starter_credits=_positive_int(
            "RELAY_STARTER_CREDITS", environ.get("RELAY_STARTER_CREDITS"), 2
        ),
        public_url=public_url,
        trusted_hosts=trusted_hosts,
        allowed_email_domains=allowed_email_domains,
        invited_emails=invited_emails,
        require_invite=require_invite,
        email_backend=email_backend,
        proxy_x_for=proxy_x_for,
        proxy_x_proto=proxy_x_proto,
        proxy_x_host=proxy_x_host,
    )
