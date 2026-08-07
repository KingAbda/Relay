#!/usr/bin/env python3
"""Build the free static Relay paper-scroll waitlist."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
LANDING = ROOT / "landing"
PAPER_VARIANT = LANDING / "paper-scroll"
DEFAULT_FORM_URL = (
    "https://docs.google.com/forms/d/e/"
    "1FAIpQLSf5AY36RTQXhs15-SQ0QvucUQJuX0k-k2BsYl59WKrLmWAxgg/"
    "viewform"
)
PAPER_ASSETS = (
    "favicon.svg",
    "relay-logo-violet.svg",
    "hero-paper-landscape.webp",
    "footer-paper-landscape.webp",
    "layer-sky.webp",
    "layer-far.webp",
    "layer-mid.webp",
    "layer-near.webp",
    "layer-canopy.webp",
)


def validated_form_url(raw_value: str) -> str | None:
    value = raw_value.strip()
    if not value:
        return None
    parsed = urlparse(value)
    allowed_hosts = {"docs.google.com", "forms.gle"}
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
        raise ValueError("RELAY_WAITLIST_FORM_URL must be an HTTPS Google Forms URL")
    if parsed.hostname == "docs.google.com" and not parsed.path.startswith("/forms/"):
        raise ValueError("docs.google.com waitlist URLs must point to /forms/")
    return value


def render_paper_template(source: Path, form_url: str | None) -> str:
    html = source.read_text(encoding="utf-8")
    if not form_url:
        return html
    return html.replace(f'href="{DEFAULT_FORM_URL}"', f'href="{form_url}"')


def build(output: Path, form_url: str | None) -> None:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    html = render_paper_template(LANDING / "index.html", form_url)
    (output / "index.html").write_text(html, encoding="utf-8")

    paper_output = output / "paper-scroll"
    paper_assets = paper_output / "assets"
    paper_assets.mkdir(parents=True)
    shutil.copy2(PAPER_VARIANT / "paper-scroll.css", paper_output / "paper-scroll.css")
    shutil.copy2(PAPER_VARIANT / "paper-scroll.js", paper_output / "paper-scroll.js")
    shutil.copytree(PAPER_VARIANT / "fonts", paper_output / "fonts")
    for asset in PAPER_ASSETS:
        shutil.copy2(PAPER_VARIANT / "assets" / asset, paper_assets / asset)

    shutil.copy2(LANDING / "_headers", output / "_headers")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=LANDING / "dist")
    args = parser.parse_args()
    form_url = validated_form_url(os.environ.get("RELAY_WAITLIST_FORM_URL", ""))
    build(args.output.resolve(), form_url)
    print(f"built Relay landing page at {args.output.resolve()}")


if __name__ == "__main__":
    main()
