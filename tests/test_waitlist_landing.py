"""Focused checks for the free static Relay waitlist build."""

import importlib.util
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LANDING = ROOT / "landing"



def load_builder():
    spec = importlib.util.spec_from_file_location("relay_landing_build", LANDING / "build.py")
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.assets = []
        self.inline_scripts = 0
        self.forms = 0
        self.inputs = 0
        self.iframes = []
        self._inside_script = False
        self._script_has_src = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "a":
            self.links.append(values)
        elif tag == "link" and values.get("href"):
            self.assets.append(values["href"])
        elif tag == "img" and values.get("src"):
            self.assets.append(values["src"])
        elif tag == "script":
            self._inside_script = True
            self._script_has_src = bool(values.get("src"))
            if values.get("src"):
                self.assets.append(values["src"])
        elif tag == "form":
            self.forms += 1
        elif tag == "input":
            self.inputs += 1
        elif tag == "iframe":
            self.iframes.append(values)

    def handle_data(self, data):
        if self._inside_script and not self._script_has_src and data.strip():
            self.inline_scripts += 1

    def handle_endtag(self, tag):
        if tag == "script":
            self._inside_script = False
            self._script_has_src = False


class WaitlistLandingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = load_builder()

    def build_site(self, form_url=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name) / "site"
        self.builder.build(output, form_url)
        return output

    def test_default_build_links_to_the_reviewed_google_form(self):
        output = self.build_site()
        html = (output / "index.html").read_text(encoding="utf-8")
        parser = PageParser()
        parser.feed(html)

        self.assertEqual(parser.forms, 0)
        self.assertEqual(parser.inputs, 0)
        self.assertEqual(parser.inline_scripts, 0)
        self.assertTrue(all(not asset.startswith(("http://", "https://")) for asset in parser.assets))
        self.assertEqual(parser.iframes, [])
        form_links = [link for link in parser.links if link.get("href") == self.builder.DEFAULT_FORM_URL]
        self.assertEqual(len(form_links), 1)
        self.assertEqual(form_links[0].get("target"), "_blank")
        self.assertIn("noopener", form_links[0].get("rel", ""))
        self.assertNotIn('aria-disabled="true"', html)
        self.assertNotIn("__WAITLIST_", html)
        self.assertIn("doesn't guarantee", html)
        self.assertIn("about twenty", html)
        self.assertIn("Built from 300+ student interviews at NYU", html)
        self.assertNotIn("August 15", html)

    def test_build_packages_canonical_paper_scroll_assets_exactly(self):
        output = self.build_site()
        self.assertEqual(
            [path.relative_to(output) for path in output.rglob("*.html")],
            [Path("index.html")],
        )
        runtime = output / "paper-scroll"
        for asset in self.builder.PAPER_ASSETS:
            self.assertEqual(
                (runtime / "assets" / asset).read_bytes(),
                (LANDING / "paper-scroll" / "assets" / asset).read_bytes(),
                f"{asset} drifted from the paper-scroll source",
            )
        self.assertEqual(
            (runtime / "paper-scroll.css").read_bytes(),
            (LANDING / "paper-scroll" / "paper-scroll.css").read_bytes(),
        )
        self.assertEqual(
            (runtime / "paper-scroll.js").read_bytes(),
            (LANDING / "paper-scroll" / "paper-scroll.js").read_bytes(),
        )
        self.assertTrue((runtime / "fonts" / "Oswald-VariableFont.ttf").is_file())

    def test_google_form_build_can_override_the_link(self):
        form_url = "https://docs.google.com/forms/d/e/example/viewform"
        output = self.build_site(form_url)
        html = (output / "index.html").read_text(encoding="utf-8")

        self.assertIn(f'href="{form_url}"', html)
        self.assertNotIn(self.builder.DEFAULT_FORM_URL, html)
        self.assertIn("Join the Interest List", html)
        self.assertNotIn('aria-disabled="true"', html)

    def test_canonical_page_preserves_relay_content_and_waitlist_safety(self):
        output = self.build_site()
        html = (output / "index.html").read_text(encoding="utf-8")
        parser = PageParser()
        parser.feed(html)

        self.assertEqual(parser.forms, 0)
        self.assertEqual(parser.inputs, 0)
        self.assertEqual(parser.inline_scripts, 0)
        self.assertTrue(all(not asset.startswith(("http://", "https://")) for asset in parser.assets))
        self.assertEqual(parser.iframes, [])
        self.assertNotIn('aria-disabled="true"', html)
        self.assertNotIn("__WAITLIST_", html)
        for marker in (
            "Teach what you know.",
            "Time is the only thing that moves.",
            "Built from 300+ student interviews at NYU.",
            "Creative skills only, each one reviewed first",
            "Does it cost anything?",
            "How do credits work?",
            "What can I actually teach?",
            "Who gets in?",
            "Does the interest list mean I'm in?",
            "Please don't send anything sensitive.",
        ):
            self.assertIn(marker, html)

    def test_canonical_page_packages_runtime_assets_and_motion_fallbacks(self):
        output = self.build_site()
        paper = output / "paper-scroll"
        for asset in self.builder.PAPER_ASSETS:
            source = LANDING / "paper-scroll" / "assets" / asset
            self.assertEqual((paper / "assets" / asset).read_bytes(), source.read_bytes())

        self.assertEqual(
            (paper / "paper-scroll.css").read_bytes(),
            (LANDING / "paper-scroll" / "paper-scroll.css").read_bytes(),
        )
        self.assertEqual(
            (paper / "paper-scroll.js").read_bytes(),
            (LANDING / "paper-scroll" / "paper-scroll.js").read_bytes(),
        )
        self.assertTrue((paper / "fonts" / "Oswald-VariableFont.ttf").is_file())
        html = (output / "index.html").read_text(encoding="utf-8")
        self.assertIn('<main id="main" tabindex="-1">', html)
        self.assertIn('<meta name="referrer" content="no-referrer"', html)
        script = (paper / "paper-scroll.js").read_text(encoding="utf-8")
        self.assertIn('toggleAttribute("inert", hidden)', script)
        stylesheet = (paper / "paper-scroll.css").read_text(encoding="utf-8")
        self.assertIn(
            '.act[aria-hidden="true"] { visibility: hidden; pointer-events: none; }',
            stylesheet,
        )

    def test_waitlist_url_accepts_only_https_google_forms(self):
        self.assertEqual(
            self.builder.validated_form_url("https://forms.gle/example"),
            "https://forms.gle/example",
        )
        for invalid in (
            "http://forms.gle/example",
            "https://example.com/form",
            "https://docs.google.com/spreadsheets/d/example",
            "javascript:alert(1)",
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.builder.validated_form_url(invalid)

    def test_cloudflare_headers_limit_browser_capabilities(self):
        output = self.build_site()
        headers = (output / "_headers").read_text(encoding="utf-8")
        self.assertIn("Content-Security-Policy:", headers)
        self.assertIn("frame-ancestors 'none'", headers)
        self.assertIn("form-action https://docs.google.com https://forms.gle", headers)
        self.assertIn("frame-src https://docs.google.com", headers)
        self.assertIn("Permissions-Policy:", headers)
        self.assertIn("Cross-Origin-Opener-Policy: same-origin", headers)
        self.assertIn("Cross-Origin-Resource-Policy: same-origin", headers)
        self.assertIn("Referrer-Policy: no-referrer", headers)


if __name__ == "__main__":
    unittest.main()
