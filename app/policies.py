"""Safety validation for the deliberately narrow controlled trial."""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse


APPROVED_PUBLIC_LOCATIONS = (
    "Bobst Library lobby",
    "Kimmel Center lobby",
    "NYU Dibner Library lobby",
)

_PROHIBITED_PATTERNS = (
    re.compile(r"\b(medical|clinical|diagnos(?:e|is|tic)|therapy|therapist|prescription)\b", re.I),
    re.compile(r"\b(weapon|firearm|gun|knife fighting|explosive|bomb)\b", re.I),
    re.compile(r"\b(hack(?:ing)? accounts?|steal|fraud|counterfeit|illegal)\b", re.I),
    re.compile(r"\b(boxing|sparring|martial arts|weight lifting|weight training|acrobatics)\b", re.I),
)


def validate_trial_topic(name: str, description: str) -> str | None:
    content = f"{name} {description}".strip()
    if not content:
        return "Enter a skill name."
    if any(pattern.search(content) for pattern in _PROHIBITED_PATTERNS):
        return "This topic is outside the controlled trial's safety scope."
    return None


def validate_meeting_details(mode: str, details: str) -> tuple[str | None, str | None]:
    normalized_mode = (mode or "").strip().lower()
    normalized_details = (details or "").strip()
    if normalized_mode == "location":
        if normalized_details not in APPROVED_PUBLIC_LOCATIONS:
            return None, "Choose an approved public campus location."
        return f"location:{normalized_details}", None
    if normalized_mode != "video":
        return None, "Choose a public campus location or approved video link."

    parsed = urlparse(normalized_details)
    allowed_hosts = tuple(
        host.strip().lower()
        for host in os.environ.get(
            "RELAY_ALLOWED_MEETING_HOSTS", "nyu.zoom.us,zoom.us,meet.google.com,teams.microsoft.com"
        ).split(",")
        if host.strip()
    )
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.hostname.lower() not in allowed_hosts
    ):
        return None, "Enter an HTTPS link from an approved meeting host."
    return normalized_details, None
