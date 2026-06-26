"""Budget manager service for IAMonitor.

Tracks daily usage against a configurable budget and fires notifications.
Also manages an optional manual countdown timer.
"""
import logging
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class BudgetManager:
    """Manages daily usage budget, auto-reset, alerts and manual countdown."""

    def __init__(
        self,
        on_budget_update: Callable[[int, int, Optional[int]], None],
        config: dict,
    ) -> None:
        """
        Args:
            on_budget_update: Callback(used_minutes, total_minutes, countdown_remaining)
                              called on the GTK main thread.
            config: Loaded config dict.
        """
        self._on_budget_update = on_budget_update
        self._config = config

        self._used_minutes: int = 0
        self._total_minutes: int = config.get("daily_budget_minutes", 480)
        self._reset_hour: int = config.get("reset_hour", 0)
        self._alert_pct: int = config.get("alert_at_percentage", 80)

        self._last_reset_day: Optional[int] = None  # day-of-year of last reset
        self._alert_fired: bool = False
        self._notifications_available: bool = False

        # Manual countdown state
        self._countdown_total_seconds: int = 0
        self._countdown_start_time: float = 0.0
        self._countdown_running: bool = False

        self._glib_timer_id: Optional[int] = None

        # Try to init libnotify
        self._init_notifications()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_config(self, config: dict) -> None:
        """Update budget settings from a new config dict."""
        self._config = config
        self._total_minutes = config.get("daily_budget_minutes", 480)
        self._reset_hour = config.get("reset_hour", 0)
        self._alert_pct = config.get("alert_at_percentage", 80)
        self._dispatch()

    def update_used(self, active_minutes: int) -> None:
        """Called by ActivityMonitor callback with today's active minutes."""
        self._used_minutes = active_minutes
        self._check_auto_reset()
        self._check_alert()
        self._dispatch()

    def start_countdown(self, hours: int, minutes: int) -> None:
        """Start a manual countdown timer."""
        total = hours * 3600 + minutes * 60
        if total <= 0:
            return
        self._countdown_total_seconds = total
        self._countdown_start_time = time.time()
        self._countdown_running = True
        self._dispatch()

    def stop_countdown(self) -> None:
        """Stop / clear the manual countdown."""
        self._countdown_running = False
        self._countdown_total_seconds = 0
        self._dispatch()

    def start_glib_timer(self) -> None:
        """Register a GLib 60-second timer for auto-reset checks (call from main thread)."""
        try:
            from gi.repository import GLib  # type: ignore[import]
            self._glib_timer_id = GLib.timeout_add_seconds(60, self._on_timer_tick)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not start GLib budget timer: %s", exc)

    def stop_glib_timer(self) -> None:
        """Remove the GLib timer."""
        if self._glib_timer_id is not None:
            try:
                from gi.repository import GLib  # type: ignore[import]
                GLib.source_remove(self._glib_timer_id)
            except Exception:  # noqa: BLE001
                pass
            self._glib_timer_id = None

    def get_countdown_remaining(self) -> Optional[int]:
        """Return remaining countdown seconds, or None if not running."""
        if not self._countdown_running:
            return None
        elapsed = int(time.time() - self._countdown_start_time)
        remaining = self._countdown_total_seconds - elapsed
        if remaining <= 0:
            self._countdown_running = False
            self._notify("IAMonitor", "Timer countdown has finished!")
            return 0
        return remaining

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_timer_tick(self) -> bool:
        """GLib timer callback. Returns True to keep the timer alive."""
        self._check_auto_reset()
        self._dispatch()
        return True  # keep repeating

    def _check_auto_reset(self) -> None:
        """Reset daily budget if we've crossed the configured reset hour on a new day."""
        from datetime import datetime
        now = datetime.now()
        day_of_year = now.timetuple().tm_yday

        # Trigger if the reset hour has passed and we haven't reset today yet
        if now.hour >= self._reset_hour:
            if self._last_reset_day != day_of_year:
                self._last_reset_day = day_of_year
                if self._used_minutes > 0:
                    # Only log/notify if there was actually usage
                    logger.info("Auto-resetting daily budget (day %d)", day_of_year)
                    self._notify("IAMonitor", "Daily usage budget has been reset.")
                self._alert_fired = False
                # Note: actual used_minutes comes from ActivityMonitor which resets naturally
                # because history.jsonl entries are filtered by today's date

    def _check_alert(self) -> None:
        """Fire a desktop notification when usage crosses the alert threshold."""
        if self._total_minutes <= 0 or self._alert_fired:
            return
        pct_used = (self._used_minutes / self._total_minutes) * 100
        if pct_used >= self._alert_pct:
            self._alert_fired = True
            self._notify(
                "IAMonitor — Budget Alert",
                f"You've used {int(pct_used)}% of your daily budget "
                f"({self._used_minutes}/{self._total_minutes} min).",
            )

    def _dispatch(self) -> None:
        """Send budget update to the GTK main thread via GLib.idle_add."""
        countdown = self.get_countdown_remaining()
        try:
            from gi.repository import GLib  # type: ignore[import]
            GLib.idle_add(self._on_budget_update, self._used_minutes, self._total_minutes, countdown)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to dispatch budget update: %s", exc)

    def _init_notifications(self) -> None:
        """Initialise libnotify if available."""
        try:
            from gi.repository import Notify  # type: ignore[import]
            if not Notify.is_initted():
                Notify.init("IAMonitor")
            self._notifications_available = True
        except Exception as exc:  # noqa: BLE001
            logger.debug("Desktop notifications unavailable: %s", exc)

    def _notify(self, summary: str, body: str) -> None:
        """Show a desktop notification (best-effort)."""
        if not self._notifications_available:
            logger.info("Notification: %s — %s", summary, body)
            return
        try:
            from gi.repository import Notify  # type: ignore[import]
            n = Notify.Notification.new(summary, body, "dialog-information")
            n.show()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to show notification: %s", exc)
