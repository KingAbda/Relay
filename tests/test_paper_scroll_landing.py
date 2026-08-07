"""Static safety checks for the Paper Scroll interest landing page."""

import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LANDING = ROOT / "landing"
RUNTIME = LANDING / "paper-scroll"


class LandingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.assets = []
        self.forms = 0
        self.inputs = 0
        self.iframes = []
        self.inline_scripts = 0
        self._inside_script = False
        self._script_has_source = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "form":
            self.forms += 1
        elif tag == "input":
            self.inputs += 1
        elif tag == "iframe":
            self.iframes.append(values)
        elif tag == "script":
            self._inside_script = True
            self._script_has_source = bool(values.get("src"))
            if values.get("src"):
                self.assets.append(values["src"])
        elif tag == "link" and values.get("href"):
            self.assets.append(values["href"])
        elif tag == "img" and values.get("src"):
            self.assets.append(values["src"])

    def handle_data(self, data):
        if self._inside_script and not self._script_has_source and data.strip():
            self.inline_scripts += 1

    def handle_endtag(self, tag):
        if tag == "script":
            self._inside_script = False
            self._script_has_source = False


class PaperScrollLandingTests(unittest.TestCase):
    def test_page_is_canonical_and_embeds_only_the_reviewed_form(self):
        html = (LANDING / "index.html").read_text(encoding="utf-8")
        parser = LandingParser()
        parser.feed(html)

        self.assertEqual(parser.forms, 0)
        self.assertEqual(parser.inputs, 0)
        self.assertEqual(parser.inline_scripts, 0)
        self.assertTrue(all(not asset.startswith(("http://", "https://")) for asset in parser.assets))
        self.assertEqual(len(parser.iframes), 1)
        self.assertTrue(parser.iframes[0]["src"].startswith("https://docs.google.com/forms/"))
        self.assertEqual(parser.iframes[0].get("title"), "Relay interest list")
        self.assertIn('<main id="main" tabindex="-1">', html)
        self.assertIn('<meta name="referrer" content="no-referrer"', html)
        self.assertIn("doesn't guarantee", html)
        self.assertIn("Built from 300+ student interviews at NYU", html)
        self.assertNotIn("Daniel Porter", html)
        self.assertNotIn("August 15", html)

    def test_runtime_assets_exist(self):
        html = (LANDING / "index.html").read_text(encoding="utf-8")
        parser = LandingParser()
        parser.feed(html)
        for relative in parser.assets:
            path = LANDING / relative
            self.assertTrue(path.is_file(), f"missing landing asset: {relative}")

        for name in ("Fraunces-Variable", "Oswald-VariableFont", "PublicSans-Variable"):
            self.assertTrue((RUNTIME / "fonts" / f"{name}.woff2").is_file())

    def test_security_headers_are_fail_closed(self):
        headers = (LANDING / "_headers").read_text(encoding="utf-8")
        for marker in (
            "Content-Security-Policy:",
            "base-uri 'none'",
            "frame-ancestors 'none'",
            "object-src 'none'",
            "script-src 'self'",
            "frame-src https://docs.google.com",
            "Permissions-Policy:",
            "Referrer-Policy: no-referrer",
            "Cross-Origin-Opener-Policy: same-origin",
            "Cross-Origin-Resource-Policy: same-origin",
            "X-Content-Type-Options: nosniff",
            "X-Frame-Options: DENY",
        ):
            self.assertIn(marker, headers)

    def test_hidden_scroll_acts_leave_the_tab_order(self):
        script = (RUNTIME / "paper-scroll.js").read_text(encoding="utf-8")
        self.assertIn('toggleAttribute("inert", hidden)', script)
        self.assertIn('reduced.addEventListener("change", onScroll)', script)
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("eval(", script)

    def test_reduced_motion_and_print_have_linear_fallbacks(self):
        styles = (RUNTIME / "paper-scroll.css").read_text(encoding="utf-8")
        self.assertIn("@media (prefers-reduced-motion: reduce)", styles)
        self.assertIn("@media print", styles)
        self.assertIn(".stage-wrap { height: auto; overflow: hidden; }", styles)
        self.assertIn(".act { width: auto; opacity: 1 !important;", styles)


if __name__ == "__main__":
    unittest.main()
