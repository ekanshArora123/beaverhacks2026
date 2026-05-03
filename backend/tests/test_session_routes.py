"""Integration tests for /session/* Flask routes used by Android phone input mode."""

from __future__ import annotations

import base64
import io
import sys
import threading
import time
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent.parent
TESTS_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import programAPI
import sessionStore
from test_prompt_api import PNG_BYTES


class SessionRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        sessionStore._sessions.clear()
        programAPI.app.testing = True
        self.client = programAPI.app.test_client()

    def tearDown(self) -> None:
        sessionStore._sessions.clear()

    def _create_session(self) -> str:
        response = self.client.post("/session/new")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        assert payload is not None
        code = payload.get("code")
        assert isinstance(code, str)
        return code

    def test_session_new_returns_unique_codes(self) -> None:
        first = self._create_session()
        second = self._create_session()
        self.assertNotEqual(first, second)
        self.assertTrue(sessionStore.session_exists(first))
        self.assertTrue(sessionStore.session_exists(second))

    def test_input_with_image_then_pending_returns_data_url(self) -> None:
        code = self._create_session()

        post_response = self.client.post(
            f"/session/{code}/input",
            data={
                "files": (io.BytesIO(PNG_BYTES), "phone.png"),
                "diagram_source": "user",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(post_response.status_code, 200)
        post_payload = post_response.get_json()
        assert post_payload is not None
        self.assertEqual(post_payload.get("image_count"), 1)
        self.assertFalse(post_payload.get("has_audio"))
        self.assertFalse(post_payload.get("has_text"))

        pending_response = self.client.get(f"/session/{code}/pending?timeout=2")
        self.assertEqual(pending_response.status_code, 200)
        pending_payload = pending_response.get_json()
        assert pending_payload is not None

        image_data_urls = pending_payload.get("image_data_urls")
        self.assertIsInstance(image_data_urls, list)
        assert isinstance(image_data_urls, list)
        self.assertEqual(len(image_data_urls), 1)
        self.assertTrue(image_data_urls[0].startswith("data:image/"))

        _, encoded = image_data_urls[0].split(",", 1)
        self.assertEqual(base64.b64decode(encoded), PNG_BYTES)

        self.assertIsNone(pending_payload.get("audio_data_url"))
        self.assertIsNone(pending_payload.get("text_source_2"))
        self.assertEqual(pending_payload.get("diagram_source"), "user")

    def test_input_with_audio_round_trips_data_url_and_extension(self) -> None:
        code = self._create_session()
        audio_bytes = b"FAKE_AUDIO_BYTES_FOR_TEST"

        post_response = self.client.post(
            f"/session/{code}/input",
            data={
                "audio": (io.BytesIO(audio_bytes), "phone.ogg", "audio/ogg"),
                "text_source_2": "the bolt is loose",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(post_response.status_code, 200)
        post_payload = post_response.get_json()
        assert post_payload is not None
        self.assertTrue(post_payload.get("has_audio"))
        self.assertTrue(post_payload.get("has_text"))
        self.assertEqual(post_payload.get("image_count"), 0)

        pending_response = self.client.get(f"/session/{code}/pending?timeout=2")
        self.assertEqual(pending_response.status_code, 200)
        pending_payload = pending_response.get_json()
        assert pending_payload is not None

        self.assertEqual(pending_payload.get("audio_mime"), "audio/ogg")
        self.assertEqual(pending_payload.get("audio_extension"), "ogg")
        self.assertEqual(pending_payload.get("text_source_2"), "the bolt is loose")
        self.assertEqual(pending_payload.get("image_data_urls"), [])

        audio_data_url = pending_payload.get("audio_data_url")
        self.assertIsInstance(audio_data_url, str)
        assert isinstance(audio_data_url, str)
        self.assertTrue(audio_data_url.startswith("data:audio/ogg;base64,"))
        _, encoded = audio_data_url.split(",", 1)
        self.assertEqual(base64.b64decode(encoded), audio_bytes)

    def test_input_to_unknown_session_returns_404(self) -> None:
        response = self.client.post(
            "/session/NOPE99/input",
            data={"text_source_2": "nope"},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 404)

    def test_session_code_in_url_is_case_insensitive(self) -> None:
        """Mobile clients may lowercase the code in the path; server normalizes to uppercase."""
        code = self._create_session()
        lower = code.lower()
        self.assertNotEqual(lower, code)

        post_response = self.client.post(
            f"/session/{lower}/input",
            data={"text_source_2": "from mixed-case URL"},
            content_type="multipart/form-data",
        )
        self.assertEqual(post_response.status_code, 200)

        pending_response = self.client.get(f"/session/{lower}/pending?timeout=2")
        self.assertEqual(pending_response.status_code, 200)
        pending_payload = pending_response.get_json()
        assert pending_payload is not None
        self.assertEqual(pending_payload.get("text_source_2"), "from mixed-case URL")

    def test_input_with_empty_payload_returns_400(self) -> None:
        code = self._create_session()
        response = self.client.post(
            f"/session/{code}/input",
            data={},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        assert payload is not None
        self.assertIn("at least one image", str(payload.get("error", "")).lower())

    def test_input_rejects_unsupported_image_extension(self) -> None:
        code = self._create_session()
        response = self.client.post(
            f"/session/{code}/input",
            data={"files": (io.BytesIO(b"not-really-tiff"), "phone.tiff")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)

    def test_pending_returns_204_when_no_payload_within_timeout(self) -> None:
        code = self._create_session()

        start = time.monotonic()
        response = self.client.get(f"/session/{code}/pending?timeout=1")
        elapsed = time.monotonic() - start

        self.assertEqual(response.status_code, 204)
        self.assertGreaterEqual(elapsed, 0.5)
        self.assertLess(elapsed, 3.0)

    def test_pending_unknown_session_returns_404(self) -> None:
        response = self.client.get("/session/NOPE99/pending?timeout=1")
        self.assertEqual(response.status_code, 404)

    def test_pending_blocks_until_input_arrives(self) -> None:
        code = self._create_session()

        delivered_event = threading.Event()

        def _push_after_delay() -> None:
            time.sleep(0.2)
            self.client.post(
                f"/session/{code}/input",
                data={"text_source_2": "delayed message"},
                content_type="multipart/form-data",
            )
            delivered_event.set()

        pusher = threading.Thread(target=_push_after_delay)
        pusher.start()

        try:
            start = time.monotonic()
            response = self.client.get(f"/session/{code}/pending?timeout=3")
            elapsed = time.monotonic() - start
        finally:
            pusher.join()

        self.assertTrue(delivered_event.is_set())
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(elapsed, 0.1)
        self.assertLess(elapsed, 3.0, "Pending should return as soon as the push happens")

        payload = response.get_json()
        assert payload is not None
        self.assertEqual(payload.get("text_source_2"), "delayed message")

    def test_pending_timeout_arg_is_clamped(self) -> None:
        # Negative / huge timeouts should be clamped to a sane window. We don't
        # want a test to actually wait 10 minutes if the route forwards the value.
        code = self._create_session()

        start = time.monotonic()
        response = self.client.get(f"/session/{code}/pending?timeout=-5")
        elapsed = time.monotonic() - start

        self.assertEqual(response.status_code, 204)
        # Lower clamp is 1.0 second; we should wait at least roughly that long.
        self.assertGreaterEqual(elapsed, 0.5)
        self.assertLess(elapsed, 3.0)


if __name__ == "__main__":
    unittest.main()
