"""Static assertions over real rendered public routes.

These checks catch accessibility and truthfulness regressions without claiming to
replace browser, keyboard, screen-reader, or responsive visual evidence.
"""

from html.parser import HTMLParser
import os
from pathlib import Path
import re
import unittest


os.environ.update({
    "DATABASE_URL": "sqlite://",
    "RELAY_ENV": "test",
    "RELAY_TRIAL_CATEGORY": "creative",
    "RELAY_EMAIL_BACKEND": "memory",
    "RELAY_PUBLIC_URL": "http://localhost",
    "RELAY_REQUIRE_INVITE": "false",
})

from app.main import app, db
from sqlalchemy import text


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROUTES = (
    "/", "/browse", "/about", "/privacy", "/terms", "/safety",
    "/conduct", "/login", "/signup", "/forgot-password",
)


class SurfaceParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.labels_for = set()
        self.label_depth = 0
        self.controls = []
        self.images = []
        self.external_assets = []
        self.inline_scripts = 0
        self.post_forms = []
        self._form_stack = []
        self.visible_text = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if element_id := attributes.get("id"):
            self.ids.append(element_id)
        if tag == "label":
            self.label_depth += 1
            if target := attributes.get("for"):
                self.labels_for.add(target)
        if tag in {"input", "select", "textarea"}:
            control_type = attributes.get("type", "").lower()
            if control_type != "hidden":
                self.controls.append({
                    "tag": tag,
                    "id": attributes.get("id"),
                    "name": attributes.get("name"),
                    "nested": self.label_depth > 0,
                    "aria": attributes.get("aria-label") or attributes.get("aria-labelledby"),
                    "title": attributes.get("title"),
                })
            if self._form_stack and attributes.get("name") == "csrf_token":
                self._form_stack[-1]["csrf"] = True
        if tag == "form":
            form = {
                "method": attributes.get("method", "get").lower(),
                "action": attributes.get("action", ""),
                "csrf": False,
            }
            self._form_stack.append(form)
        if tag == "img":
            self.images.append(attributes)
        if tag in {"img", "script", "link", "source"}:
            asset = attributes.get("src") or attributes.get("href") or attributes.get("srcset")
            if asset and (asset.startswith("http://") or asset.startswith("https://") or asset.startswith("//")):
                self.external_assets.append(asset)
        if tag == "script" and not attributes.get("src"):
            self.inline_scripts += 1

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag == "label":
            self.label_depth -= 1

    def handle_endtag(self, tag):
        if tag == "label":
            self.label_depth -= 1
        if tag == "form" and self._form_stack:
            form = self._form_stack.pop()
            if form["method"] == "post":
                self.post_forms.append(form)

    def handle_data(self, data):
        if data.strip():
            self.visible_text.append(data.strip())


class PublicSurfaceTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=True)
        self.client = app.test_client()
        with app.app_context():
            db.session.execute(text("DROP TABLE IF EXISTS alembic_version"))
            db.drop_all()
            db.create_all()
            db.session.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            db.session.execute(text("INSERT INTO alembic_version VALUES ('20260713_01')"))
            db.session.commit()

    def test_rendered_public_routes_have_accessible_truthful_static_markup(self):
        forbidden_claims = (
            "$4.99", "$9.99", "upgrade only if relay becomes a habit",
            "unlimited monthly credits", "share a proof video", "become an ambassador",
        )
        for route in PUBLIC_ROUTES:
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                parser = SurfaceParser()
                parser.feed(response.get_data(as_text=True))

                self.assertEqual(len(parser.ids), len(set(parser.ids)), "duplicate HTML id")
                self.assertEqual(parser.inline_scripts, 0, "inline script violates the CSP")
                self.assertEqual(parser.external_assets, [], "external served asset bypasses the allowlist")
                for form in parser.post_forms:
                    self.assertTrue(form["csrf"], f"POST form lacks CSRF: {form['action']}")
                for control in parser.controls:
                    self.assertTrue(control["name"], f"unnamed {control['tag']} control")
                    self.assertTrue(
                        control["nested"]
                        or control["aria"]
                        or control["title"]
                        or (control["id"] and control["id"] in parser.labels_for),
                        f"unlabelled {control['tag']} control: {control['name']}",
                    )
                for image in parser.images:
                    self.assertIn("alt", image, "image lacks alt text")
                    self.assertTrue(image.get("width") and image.get("height"), "image lacks dimensions")
                rendered_text = " ".join(parser.visible_text).casefold()
                for claim in forbidden_claims:
                    self.assertNotIn(claim, rendered_text)

        # Jinja branches can hide authenticated or state-specific forms from the
        # public route sample. Parse every template as source as a second, static
        # guard against adding an unnamed or visually-only-labelled form control.
        for template in sorted((ROOT / "app" / "templates").glob("*.html")):
            with self.subTest(template=template.name):
                source = template.read_text(encoding="utf-8")
                parser = SurfaceParser()
                parser.feed(source)
                self.assertNotIn("{% if false %}", source, "dead feature branch in template")
                for claim in forbidden_claims:
                    self.assertNotIn(claim, source.casefold(), "disabled claim remains in source")
                for control in parser.controls:
                    self.assertTrue(control["name"], f"unnamed {control['tag']} control")
                    self.assertTrue(
                        control["nested"]
                        or control["aria"]
                        or control["title"]
                        or (control["id"] and control["id"] in parser.labels_for),
                        f"unlabelled {control['tag']} control: {control['name']}",
                    )

    def test_stylesheets_have_balanced_blocks_and_no_truncated_declarations(self):
        for relative in ("app/static/elevate.css", "app/static/style.css"):
            with self.subTest(stylesheet=relative):
                css = (ROOT / relative).read_text(encoding="utf-8")
                without_comments = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
                self.assertEqual(without_comments.count("{"), without_comments.count("}"))
                self.assertIsNone(
                    re.search(r"[;{]\s*[A-Za-z_-]{1,5}\s*}", without_comments),
                    "possible truncated CSS declaration",
                )
                self.assertIsNone(
                    re.search(r"var\([^)]*\)[0-9A-Za-z#]+", without_comments),
                    "unexpected characters after CSS var()",
                )


if __name__ == "__main__":
    unittest.main()
