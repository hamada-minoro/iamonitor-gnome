"""Activity monitor service for IAMonitor.

Watches ~/.claude/history.jsonl via inotify and provides daily usage summaries.
"""
import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from iamonitor.models.usage_data import DailySummary, UsageEntry, UsageTrend

logger = logging.getLogger(__name__)

_HISTORY_FILE = Path.home() / ".claude" / "history.jsonl"
_HISTORY_DIR = _HISTORY_FILE.parent

# Gaps >= 600s are counted as 2 minutes of "active time" (session boundary)
_SESSION_GAP_THRESHOLD = 600
_SESSION_BOUNDARY_CREDIT = 120  # seconds credited at session start


def _start_of_today_ms() -> int:
    """Return Unix timestamp in milliseconds for midnight of today (local time)."""
    now = datetime.now()
    midnight = datetime(now.year, now.month, now.day, tzinfo=None)
    return int(midnight.timestamp() * 1000)


def _parse_entry(raw: str) -> Optional[UsageEntry]:
    """Parse a single JSONL line into a UsageEntry. Returns None on error."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        return UsageEntry(
            display=obj.get("display", ""),
            timestamp_ms=int(obj.get("timestamp", 0)),
            project=obj.get("project"),
            session_id=obj.get("sessionId"),
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.debug("Skipping malformed history line: %s (%s)", raw[:80], exc)
        return None


def _compute_summary(entries: list[UsageEntry]) -> DailySummary:
    """Build a DailySummary from a list of today's entries."""
    if not entries:
        return DailySummary()

    # Sort ascending by timestamp
    sorted_entries = sorted(entries, key=lambda e: e.timestamp_ms)

    # Count unique sessions
    session_ids = {e.session_id for e in sorted_entries if e.session_id}
    session_count = len(session_ids) if session_ids else 1

    # Active time estimation
    timestamps_s = [e.timestamp_ms / 1000.0 for e in sorted_entries]
    active_seconds = 0
    if len(timestamps_s) == 1:
        active_seconds = _SESSION_BOUNDARY_CREDIT
    else:
        for i in range(1, len(timestamps_s)):
            gap = timestamps_s[i] - timestamps_s[i - 1]
            if gap < _SESSION_GAP_THRESHOLD:
                active_seconds += gap
            else:
                active_seconds += _SESSION_BOUNDARY_CREDIT

    return DailySummary(
        prompt_count=len(sorted_entries),
        session_count=session_count,
        active_minutes=int(active_seconds / 60),
        entries=sorted_entries,
    )


def _calculate_trend(all_entries: list[UsageEntry]) -> UsageTrend:
    """Compare last hour vs previous hour entry counts."""
    now = time.time()
    last_hour_start = now - 3600
    prev_hour_start = now - 7200

    last_count = sum(
        1 for e in all_entries if last_hour_start <= e.timestamp_ms / 1000 < now
    )
    prev_count = sum(
        1 for e in all_entries
        if prev_hour_start <= e.timestamp_ms / 1000 < last_hour_start
    )

    if last_count > prev_count:
        return UsageTrend.UP
    if last_count < prev_count:
        return UsageTrend.DOWN
    return UsageTrend.STABLE


class ActivityMonitor:
    """Monitors ~/.claude/history.jsonl and reports daily activity summaries."""

    def __init__(self, on_update: Callable[[DailySummary], None]) -> None:
        self._on_update = on_update
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._current_summary = DailySummary()
        self.trend = UsageTrend.STABLE

    def start(self) -> None:
        """Start the background inotify watcher thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="ActivityMonitor",
            daemon=True,
        )
        self._thread.start()
        logger.info("ActivityMonitor started")

    def stop(self) -> None:
        """Stop the watcher thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("ActivityMonitor stopped")

    def get_summary(self) -> DailySummary:
        """Return the most recent daily summary (thread-safe read)."""
        return self._current_summary

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_history(self) -> list[UsageEntry]:
        """Read all entries from history.jsonl; return list of today's entries only."""
        if not _HISTORY_FILE.exists():
            logger.debug("history.jsonl not found at %s", _HISTORY_FILE)
            return []

        all_entries: list[UsageEntry] = []
        today_cutoff = _start_of_today_ms()

        try:
            with _HISTORY_FILE.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    entry = _parse_entry(line)
                    if entry and entry.timestamp_ms >= today_cutoff:
                        all_entries.append(entry)
        except OSError as exc:
            logger.warning("Could not read history.jsonl: %s", exc)

        return all_entries

    def _refresh(self) -> None:
        """Reload history and dispatch update to UI thread."""
        entries = self._load_history()
        self.trend = _calculate_trend(entries)
        summary = _compute_summary(entries)
        self._current_summary = summary
        self._dispatch(summary)

    def _dispatch(self, summary: DailySummary) -> None:
        """Send summary to the GTK main thread via GLib.idle_add."""
        try:
            from gi.repository import GLib  # type: ignore[import]
            GLib.idle_add(self._on_update, summary)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to dispatch activity update: %s", exc)

    def _run(self) -> None:
        """Daemon thread: initial load then inotify watch loop."""
        # Initial load
        self._refresh()

        # Try inotify_simple first, fall back to polling
        try:
            self._run_inotify()
        except ImportError:
            logger.warning("inotify_simple not available, falling back to polling")
            self._run_polling()

    def _run_inotify(self) -> None:
        """Watch the history directory via inotify_simple."""
        import inotify_simple  # type: ignore[import]

        inotify = inotify_simple.INotify()
        flags = inotify_simple.flags.MODIFY | inotify_simple.flags.CREATE

        # Ensure the ~/.claude directory exists before watching
        _HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        wd = inotify.add_watch(str(_HISTORY_DIR), flags)

        logger.info("inotify watching %s", _HISTORY_DIR)
        try:
            while not self._stop_event.is_set():
                events = inotify.read(timeout=1000)  # ms
                for event in events:
                    if "history.jsonl" in event.name or not event.name:
                        logger.debug("inotify event on history.jsonl, refreshing")
                        self._refresh()
                        break
        finally:
            try:
                inotify.rm_watch(wd)
            except Exception:  # noqa: BLE001
                pass
            inotify.close()

    def _run_polling(self) -> None:
        """Fallback: poll the file modification time every 5 seconds."""
        last_mtime = 0.0
        while not self._stop_event.is_set():
            try:
                if _HISTORY_FILE.exists():
                    mtime = _HISTORY_FILE.stat().st_mtime
                    if mtime != last_mtime:
                        last_mtime = mtime
                        self._refresh()
            except OSError as exc:
                logger.debug("Polling stat error: %s", exc)
            self._stop_event.wait(timeout=5)
