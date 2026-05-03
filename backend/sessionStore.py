"""In-memory pairing-session store for the Android-phone input mode.

A laptop creates a session and gets a short code; a phone POSTs captured
images/audio/text to that code; the laptop long-polls and receives the
payload as base64 data URLs ready to feed into `/analyze`.

Single-process only — fine for the dev Flask server, not for a multi-worker
deployment.
"""

import base64
import secrets
import threading
import time
from queue import Empty, Queue
from typing import Any

_SESSION_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_SESSION_CODE_LENGTH = 6
_SESSION_TTL_SECONDS = 60 * 60


class _Session:
    def __init__(self) -> None:
        self.queue: Queue[dict[str, Any]] = Queue()
        self.created_at: float = time.time()
        self.last_seen: float = self.created_at


_sessions: dict[str, _Session] = {}
_lock = threading.Lock()


def _purge_expired(now: float) -> None:
    expired_codes = [
        code for code, session in _sessions.items() if now - session.last_seen > _SESSION_TTL_SECONDS
    ]
    for code in expired_codes:
        _sessions.pop(code, None)


def create_session() -> str:
    now = time.time()
    with _lock:
        _purge_expired(now)
        for _ in range(20):
            code = "".join(secrets.choice(_SESSION_CODE_ALPHABET) for _ in range(_SESSION_CODE_LENGTH))
            if code not in _sessions:
                _sessions[code] = _Session()
                return code
        raise RuntimeError("Could not allocate unique session code")


def session_exists(code: str) -> bool:
    with _lock:
        return code in _sessions


def push_payload(code: str, payload: dict[str, Any]) -> bool:
    with _lock:
        session = _sessions.get(code)
        if session is None:
            return False
        session.last_seen = time.time()

    session.queue.put(payload)
    return True


def pop_payload(code: str, timeout_seconds: float) -> dict[str, Any] | None:
    with _lock:
        session = _sessions.get(code)
        if session is None:
            return None
        session.last_seen = time.time()

    try:
        return session.queue.get(timeout=timeout_seconds)
    except Empty:
        with _lock:
            current = _sessions.get(code)
            if current is not None:
                current.last_seen = time.time()
        return None


def encode_data_url(raw_bytes: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(raw_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
