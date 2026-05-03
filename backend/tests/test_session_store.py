"""Unit tests for sessionStore — the in-memory pairing store backing phone input."""

from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import sessionStore


class SessionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        sessionStore._sessions.clear()

    def tearDown(self) -> None:
        sessionStore._sessions.clear()

    def test_create_session_returns_code_in_alphabet(self) -> None:
        code = sessionStore.create_session()
        self.assertEqual(len(code), sessionStore._SESSION_CODE_LENGTH)
        for character in code:
            self.assertIn(character, sessionStore._SESSION_CODE_ALPHABET)

    def test_create_session_returns_unique_codes(self) -> None:
        codes = {sessionStore.create_session() for _ in range(50)}
        self.assertEqual(len(codes), 50)

    def test_session_exists_reflects_create(self) -> None:
        code = sessionStore.create_session()
        self.assertTrue(sessionStore.session_exists(code))
        self.assertFalse(sessionStore.session_exists("ZZZZZZ"))

    def test_push_to_unknown_session_returns_false(self) -> None:
        delivered = sessionStore.push_payload("NOPE99", {"hello": "world"})
        self.assertFalse(delivered)

    def test_push_then_pop_round_trips_payload(self) -> None:
        code = sessionStore.create_session()
        payload = {"image_data_urls": ["data:image/png;base64,AAA"], "text_source_2": "hi"}

        delivered = sessionStore.push_payload(code, payload)
        self.assertTrue(delivered)

        popped = sessionStore.pop_payload(code, timeout_seconds=1.0)
        self.assertEqual(popped, payload)

    def test_pop_returns_none_on_timeout(self) -> None:
        code = sessionStore.create_session()

        start = time.monotonic()
        popped = sessionStore.pop_payload(code, timeout_seconds=0.1)
        elapsed = time.monotonic() - start

        self.assertIsNone(popped)
        self.assertGreaterEqual(elapsed, 0.05)
        self.assertLess(elapsed, 1.0)

    def test_pop_unknown_session_returns_none_immediately(self) -> None:
        start = time.monotonic()
        popped = sessionStore.pop_payload("NOPE99", timeout_seconds=5.0)
        elapsed = time.monotonic() - start

        self.assertIsNone(popped)
        self.assertLess(elapsed, 0.5, "Unknown session should short-circuit, not wait for timeout")

    def test_payloads_delivered_in_fifo_order(self) -> None:
        code = sessionStore.create_session()
        sessionStore.push_payload(code, {"order": 1})
        sessionStore.push_payload(code, {"order": 2})
        sessionStore.push_payload(code, {"order": 3})

        first = sessionStore.pop_payload(code, timeout_seconds=0.5)
        second = sessionStore.pop_payload(code, timeout_seconds=0.5)
        third = sessionStore.pop_payload(code, timeout_seconds=0.5)

        assert first is not None and second is not None and third is not None
        self.assertEqual(first["order"], 1)
        self.assertEqual(second["order"], 2)
        self.assertEqual(third["order"], 3)

    def test_pop_unblocks_when_push_arrives(self) -> None:
        code = sessionStore.create_session()
        payload = {"image_data_urls": ["data:image/png;base64,AAA"]}

        def _delayed_push() -> None:
            time.sleep(0.1)
            sessionStore.push_payload(code, payload)

        pusher = threading.Thread(target=_delayed_push)
        pusher.start()

        try:
            popped = sessionStore.pop_payload(code, timeout_seconds=2.0)
        finally:
            pusher.join()

        self.assertEqual(popped, payload)

    def test_encode_data_url_format(self) -> None:
        result = sessionStore.encode_data_url(b"\x89PNG\r\n", "image/png")
        self.assertTrue(result.startswith("data:image/png;base64,"))
        # Decoding the base64 portion should round-trip back to the original bytes.
        import base64

        prefix, encoded = result.split(",", 1)
        self.assertEqual(prefix, "data:image/png;base64")
        self.assertEqual(base64.b64decode(encoded), b"\x89PNG\r\n")

    def test_expired_sessions_purged_on_create(self) -> None:
        code = sessionStore.create_session()
        # Force this session's last_seen far into the past so the next create_session
        # purges it.
        sessionStore._sessions[code].last_seen = time.time() - (sessionStore._SESSION_TTL_SECONDS + 10)

        sessionStore.create_session()
        self.assertFalse(sessionStore.session_exists(code))


if __name__ == "__main__":
    unittest.main()
