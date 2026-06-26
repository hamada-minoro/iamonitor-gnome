"""Anthropic API polling service for IAMonitor.

Runs in a daemon thread. Uses only urllib.request (no requests library).
Updates are dispatched back to the GTK main loop via GLib.idle_add.
"""
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from typing import Callable, Optional

from iamonitor.models.usage_data import RateLimitData

logger = logging.getLogger(__name__)

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"
_MODEL = "claude-haiku-4-5-20251001"

_REQUEST_BODY = json.dumps({
    "model": _MODEL,
    "max_tokens": 1,
    "messages": [{"role": "user", "content": "ping"}],
}).encode("utf-8")


def _safe_float(value: Optional[str]) -> float:
    """Parse a header value as float, returning 0.0 on failure."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _safe_int(value: Optional[str]) -> int:
    """Parse a header value as int epoch, returning 0 on failure."""
    if value is None:
        return 0
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0


class AnthropicAPIService:
    """Polls the Anthropic API at a configurable interval and reports rate-limit data."""

    def __init__(self, on_update: Callable[[RateLimitData], None]) -> None:
        self._on_update = on_update
        self._token: str = ""
        self._interval: int = 120
        self._stop_event = threading.Event()
        self._poll_now_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def set_token(self, token: str) -> None:
        """Update the Bearer token used for API requests."""
        with self._lock:
            self._token = token.strip()

    def set_interval(self, seconds: int) -> None:
        """Update the polling interval and wake the thread immediately."""
        with self._lock:
            self._interval = max(10, seconds)
        self._poll_now_event.set()  # interrupt current sleep

    def start(self) -> None:
        """Start the background polling thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="AnthropicAPIPoller",
            daemon=True,
        )
        self._thread.start()
        logger.info("AnthropicAPIService started")

    def stop(self) -> None:
        """Signal the background thread to stop and wait for it."""
        self._stop_event.set()
        self._poll_now_event.set()  # unblock any wait
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("AnthropicAPIService stopped")

    def poll_now(self) -> None:
        """Trigger an immediate poll cycle (non-blocking)."""
        self._poll_now_event.set()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Main polling loop — runs in daemon thread."""
        # Initial poll after a short delay so the UI can set up first
        self._poll_now_event.wait(timeout=2)
        self._poll_now_event.clear()

        while not self._stop_event.is_set():
            self._do_poll()

            with self._lock:
                interval = self._interval

            # Wait for interval or until woken early
            self._poll_now_event.wait(timeout=float(interval))
            self._poll_now_event.clear()

    def _do_poll(self) -> None:
        """Perform a single API poll and dispatch result to the UI thread."""
        with self._lock:
            token = self._token

        if not token:
            data = RateLimitData(error="No OAuth token configured", last_updated=time.time())
            self._dispatch(data)
            return

        try:
            req = urllib.request.Request(
                _API_URL,
                data=_REQUEST_BODY,
                method="POST",
                headers={
                    "Authorization": f"Bearer {token}",
                    "anthropic-version": _API_VERSION,
                    "content-type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                headers = resp.headers
                data = RateLimitData(
                    session_utilization=_safe_float(
                        headers.get("anthropic-ratelimit-unified-5h-utilization")
                    ),
                    session_reset_epoch=_safe_int(
                        headers.get("anthropic-ratelimit-unified-5h-reset")
                    ),
                    weekly_utilization=_safe_float(
                        headers.get("anthropic-ratelimit-unified-7d-utilization")
                    ),
                    weekly_reset_epoch=_safe_int(
                        headers.get("anthropic-ratelimit-unified-7d-reset")
                    ),
                    last_updated=time.time(),
                    error=None,
                )
                logger.debug(
                    "API poll OK: session=%.1f%% weekly=%.1f%%",
                    data.session_utilization * 100,
                    data.weekly_utilization * 100,
                )
        except urllib.error.HTTPError as exc:
            # Even error responses may carry rate-limit headers
            headers = exc.headers
            if headers and headers.get("anthropic-ratelimit-unified-5h-utilization"):
                data = RateLimitData(
                    session_utilization=_safe_float(
                        headers.get("anthropic-ratelimit-unified-5h-utilization")
                    ),
                    session_reset_epoch=_safe_int(
                        headers.get("anthropic-ratelimit-unified-5h-reset")
                    ),
                    weekly_utilization=_safe_float(
                        headers.get("anthropic-ratelimit-unified-7d-utilization")
                    ),
                    weekly_reset_epoch=_safe_int(
                        headers.get("anthropic-ratelimit-unified-7d-reset")
                    ),
                    last_updated=time.time(),
                    error=f"HTTP {exc.code}",
                )
            else:
                data = RateLimitData(
                    error=f"HTTP error {exc.code}: {exc.reason}",
                    last_updated=time.time(),
                )
            logger.warning("API HTTP error: %s %s", exc.code, exc.reason)
        except Exception as exc:  # noqa: BLE001
            data = RateLimitData(error=str(exc), last_updated=time.time())
            logger.warning("API poll failed: %s", exc)

        self._dispatch(data)

    def _dispatch(self, data: RateLimitData) -> None:
        """Send update to the GTK main thread via GLib.idle_add."""
        try:
            from gi.repository import GLib  # type: ignore[import]
            GLib.idle_add(self._on_update, data)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to dispatch API update: %s", exc)
