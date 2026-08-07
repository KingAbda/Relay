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
        self.links = []
        self.assets = []
        self.forms = 0
        self.inputs = 0
        self.iframes = []
        self.inline_scripts = 0
        self._inside_script = False
        self._script_has_source = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "a":
            self.links.append(values)
        elif tag == "form":
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
    def test_page_is_static_and_links_only_to_the_reviewed_form(self):
        html = (LANDING / "index.html").read_text(encoding="utf-8")
        parser = LandingParser()
        parser.feed(html)

        self.assertEqual(parser.forms, 0)
        self.assertEqual(parser.inputs, 0)
        self.assertEqual(parser.inline_scripts, 0)
        self.assertTrue(all(not asset.startswith(("http://", "https://")) for asset in parser.assets))
        self.assertEqual(parser.iframes, [])
        form_links = [link for link in parser.links if link.get("href", "").startswith("https://docs.google.com/forms/")]
        self.assertEqual(len(form_links), 1)
        self.assertEqual(form_links[0].get("target"), "_blank")
        self.assertIn("noopener", form_links[0].get("rel", ""))
        self.assertEqual(html.count("Join the Interest List"), 2)
        self.assertIn('<a class="btn" href="#join">Interest List</a>', html)
        self.assertIn('<main id="main" tabindex="-1">', html)
        self.assertIn('<meta name="referrer" content="no-referrer"', html)
        self.assertIn("doesn't guarantee", html)
        self.assertIn("Built from 300+ student interviews at NYU", html)
        self.assertNotIn('class="cue"', html)
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
            self.assertTrue((RUNTIME / "fonts" / f"{name}.ttf").is_file())

    def test_security_headers_are_fail_closed(self):
        headers = (LANDING / "_headers").read_text(encoding="utf-8")
        for marker in (
            "Content-Security-Policy:",
            "base-uri 'none'",
            "frame-ancestors 'none'",
            "object-src 'none'",
            "script-src 'self'",
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
        self.assertIn('reduced.addEventListener("change", onMotionPreferenceChange)', script)
        self.assertNotIn("LERP", script)
        self.assertIn("var p = rawProgress();", script)
        self.assertIn("new ResizeObserver", script)
        self.assertIn("var INPUT_SCALE = 0.85", script)
        self.assertIn("var MAX_INPUT_DELTA = 120", script)
        self.assertIn("var MAX_FORWARD_SPEED = 0.96", script)
        self.assertIn("var MAX_REVERSE_SPEED = 0.84", script)
        self.assertIn("difference > 0 ? MAX_FORWARD_SPEED : MAX_REVERSE_SPEED", script)
        self.assertIn("function controlledScrollFrame(now)", script)
        self.assertIn("function wheelDeltaPixels(event)", script)
        self.assertIn("function queueControlledDelta(rawDelta, stageEnd)", script)
        self.assertIn("function shouldCatchReverseEntry(rawDelta, y, stageEnd)", script)
        self.assertIn("if (rawDelta < -MAX_INPUT_DELTA)", script)
        self.assertIn("controlledTarget = stageStart;", script)
        self.assertIn("Math.max(window.innerHeight * 1.5, 900)", script)
        self.assertIn("controlledActive || fastEntry || y + rawDelta <= stageEnd + 2", script)
        self.assertIn("window.scrollTo(0, stageEnd);", script)
        self.assertIn('window.addEventListener("wheel", onWheel, { passive: false })', script)
        self.assertIn("event.preventDefault();", script)
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("eval(", script)

    def test_reduced_motion_and_print_have_linear_fallbacks(self):
        styles = (RUNTIME / "paper-scroll.css").read_text(encoding="utf-8")
        self.assertIn("@media (prefers-reduced-motion: reduce)", styles)
        self.assertIn("@media print", styles)
        self.assertIn(".stage-wrap { height: auto; overflow: hidden; }", styles)
        self.assertIn(".act { width: auto; opacity: 1 !important;", styles)

    def test_narrow_viewports_keep_the_canopy_artwork_visible(self):
        styles = (RUNTIME / "paper-scroll.css").read_text(encoding="utf-8")
        responsive = styles.split("@media (max-width: 1040px)", 1)[1]
        responsive = responsive.split("@media (max-width: 760px)", 1)[0]
        self.assertIn(".layer-canopy { background-size: 100% auto; }", responsive)

    def test_tablet_cards_stay_in_a_row_until_the_narrow_breakpoint(self):
        styles = (RUNTIME / "paper-scroll.css").read_text(encoding="utf-8")
        tablet = styles.split("@media (max-width: 1040px)", 1)[1]
        tablet = tablet.split("@media (max-width: 840px)", 1)[0]
        narrow = styles.split("@media (max-width: 840px)", 1)[1]
        narrow = narrow.split("@media (max-width: 760px)", 1)[0]
        self.assertNotIn(".steps { grid-template-columns: 1fr", tablet)
        self.assertIn(".steps { grid-template-columns: 1fr", narrow)

    def test_compact_phones_use_the_linear_stage_fallback(self):
        styles = (RUNTIME / "paper-scroll.css").read_text(encoding="utf-8")
        script = (RUNTIME / "paper-scroll.js").read_text(encoding="utf-8")
        compact_query = "(max-width: 760px) and (max-height: 700px)"
        self.assertIn(compact_query, styles)
        self.assertIn(compact_query, script)

    def test_labels_and_notes_override_broad_paragraph_styles(self):
        styles = (RUNTIME / "paper-scroll.css").read_text(encoding="utf-8")
        for selector in (
            ".act-1 .eyebrow",
            ".act-1 .trust-line",
            ".closing .eyebrow",
            ".closing .form-note",
        ):
            self.assertIn(selector, styles)

    def test_static_section_copy_uses_the_available_desktop_width(self):
        styles = (RUNTIME / "paper-scroll.css").read_text(encoding="utf-8")
        self.assertIn(".section h2 { max-width: none;", styles)
        self.assertIn(".section-copy { max-width: 100%;", styles)
        self.assertIn(".faq-head { max-width: none;", styles)
        self.assertIn(".closing-inner { width: min(900px, 100%); text-align: center; }", styles)

    def test_final_cta_is_centered_and_prominent(self):
        styles = (RUNTIME / "paper-scroll.css").read_text(encoding="utf-8")
        self.assertIn(".closing { min-height: 540px;", styles)
        self.assertIn("align-items: center; justify-content: center;", styles)
        self.assertIn(".closing .eyebrow { width: 100%; max-width: none;", styles)
        self.assertIn("text-align: center; font-size: 11px;", styles)
        self.assertIn(".form-cta { display: flex; justify-content: center;", styles)
        self.assertIn(".closing .form-cta .btn { min-height: 48px;", styles)
        self.assertIn(".closing .form-cta .btn { width: 100%; justify-content: center;", styles)

    def test_nav_interest_button_keeps_its_intrinsic_width(self):
        styles = (RUNTIME / "paper-scroll.css").read_text(encoding="utf-8")
        self.assertIn(".nav > .btn { grid-column: 3; justify-self: end; width: max-content; }", styles)


if __name__ == "__main__":
    unittest.main()
