"""Guarded shared-Redis and trusted-proxy integration checks.

This module is intentionally outside default ``test*.py`` discovery. It flushes
only an explicitly acknowledged localhost Redis database.
"""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from urllib.parse import urlparse

from flask import Flask, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from redis import Redis


REDIS_URL = os.environ.get("RELAY_TEST_REDIS_URL", "").strip()
DESTRUCTIVE_OK = os.environ.get("RELAY_REDIS_TEST_DESTRUCTIVE_OK", "").lower() == "true"


def _authorized_test_redis() -> bool:
    if not REDIS_URL or not DESTRUCTIVE_OK:
        return False
    parsed = urlparse(REDIS_URL)
    try:
        database_number = int((parsed.path or "/0").lstrip("/") or "0")
    except ValueError:
        return False
    return (
        parsed.scheme in {"redis", "rediss"}
        and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        and database_number == 15
    )


@unittest.skipUnless(
    _authorized_test_redis(),
    "requires localhost RELAY_TEST_REDIS_URL database 15 and "
    "RELAY_REDIS_TEST_DESTRUCTIVE_OK=true",
)
class SharedRedisProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.update({
            "DATABASE_URL": "sqlite://",
            "RELAY_ENV": "test",
            "RELAY_EMAIL_BACKEND": "memory",
            "RELAY_PUBLIC_URL": "http://localhost",
        })
        cls.cache = Redis.from_url(REDIS_URL)
        cls.cache.ping()

    def setUp(self):
        self.cache.flushdb()

    def tearDown(self):
        self.cache.flushdb()

    @classmethod
    def tearDownClass(cls):
        cls.cache.close()

    @staticmethod
    def _application(name: str):
        from app.main import configure_proxy_boundary

        application = Flask(name)
        application.config.update(
            SECRET_KEY="redis-proxy-test-only",
            TRUSTED_HOSTS=["relay.test"],
        )
        configure_proxy_boundary(
            application,
            SimpleNamespace(proxy_x_for=1, proxy_x_proto=1, proxy_x_host=0),
        )
        limiter = Limiter(
            get_remote_address,
            app=application,
            default_limits=[],
            storage_uri=REDIS_URL,
        )

        @application.get("/probe")
        @limiter.limit("2 per minute")
        def probe():
            return {"address": request.remote_addr, "scheme": request.scheme}

        return application, limiter

    def test_two_application_instances_share_limits_and_ignore_spoofed_leftmost_ip(self):
        first_app, first_limiter = self._application("relay-worker-one")
        second_app, second_limiter = self._application("relay-worker-two")
        self.addCleanup(first_limiter.storage.reset)
        self.addCleanup(second_limiter.storage.reset)

        headers = {
            "X-Forwarded-For": "198.51.100.44, 203.0.113.17",
            "X-Forwarded-Proto": "http, https",
        }
        first = first_app.test_client().get(
            "/probe", base_url="https://relay.test", headers=headers
        )
        second = second_app.test_client().get(
            "/probe", base_url="https://relay.test", headers=headers
        )
        exhausted = first_app.test_client().get(
            "/probe", base_url="https://relay.test", headers=headers
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.get_json(), {
            "address": "203.0.113.17",
            "scheme": "https",
        })
        self.assertEqual(second.status_code, 200)
        self.assertEqual(exhausted.status_code, 429)

        independent_user = second_app.test_client().get(
            "/probe",
            base_url="https://relay.test",
            headers={
                "X-Forwarded-For": "198.51.100.44, 203.0.113.18",
                "X-Forwarded-Proto": "https",
            },
        )
        self.assertEqual(independent_user.status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
