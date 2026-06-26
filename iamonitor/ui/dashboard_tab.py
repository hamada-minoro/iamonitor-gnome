"""Dashboard tab for IAMonitor popup window."""
import logging
import time
from datetime import datetime
from typing import Optional

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib  # type: ignore[import]

from iamonitor.models.usage_data import DailySummary, RateLimitData, UsageTrend
from iamonitor.ui.widgets import CircularGauge, StatCard

logger = logging.getLogger(__name__)

_TREND_SYMBOLS = {
    UsageTrend.UP: "↑",
    UsageTrend.DOWN: "↓",
    UsageTrend.STABLE: "→",
}


def _format_reset_countdown(epoch: int) -> str:
    """Return a human-readable 'resets in Xh Ym' string."""
    if epoch <= 0:
        return "unknown"
    remaining = epoch - int(time.time())
    if remaining <= 0:
        return "resetting…"
    hours = remaining // 3600
    minutes = (remaining % 3600) // 60
    return f"{hours}h {minutes}m"


def _format_time(ts_ms: int) -> str:
    """Format a millisecond timestamp as HH:MM."""
    try:
        return datetime.fromtimestamp(ts_ms / 1000).strftime("%H:%M")
    except (OSError, ValueError):
        return "??"


class DashboardTab(Gtk.Box):
    """Main dashboard view with API or local-fallback mode."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        self.set_margin_start(14)
        self.set_margin_end(14)

        self._has_api_data = False
        self._trend = UsageTrend.STABLE

        # --- API mode section ---
        self._api_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        gauges_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        gauges_box.set_halign(Gtk.Align.CENTER)

        self._session_gauge = CircularGauge("Session (5h)", size=90)
        self._weekly_gauge = CircularGauge("Weekly (7d)", size=90)
        gauges_box.pack_start(self._session_gauge, False, False, 0)
        gauges_box.pack_start(self._weekly_gauge, False, False, 0)
        self._api_section.pack_start(gauges_box, False, False, 4)

        resets_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        resets_box.set_halign(Gtk.Align.CENTER)

        self._session_reset_label = Gtk.Label(label="Session resets: --")
        self._session_reset_label.get_style_context().add_class("dim-label")
        self._weekly_reset_label = Gtk.Label(label="Weekly resets: --")
        self._weekly_reset_label.get_style_context().add_class("dim-label")
        resets_box.pack_start(self._session_reset_label, False, False, 0)
        resets_box.pack_start(self._weekly_reset_label, False, False, 0)
        self._api_section.pack_start(resets_box, False, False, 0)

        self._updated_label = Gtk.Label(label="Last updated: --")
        self._updated_label.get_style_context().add_class("dim-label")
        self._updated_label.set_halign(Gtk.Align.CENTER)
        self._api_section.pack_start(self._updated_label, False, False, 4)

        self._error_label = Gtk.Label(label="")
        self._error_label.get_style_context().add_class("error")
        self._error_label.set_halign(Gtk.Align.CENTER)
        self._error_label.set_line_wrap(True)
        self._api_section.pack_start(self._error_label, False, False, 0)

        # --- Local mode section ---
        self._local_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        budget_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        budget_box.set_halign(Gtk.Align.CENTER)
        self._budget_gauge = CircularGauge("Daily Budget", size=90)
        budget_box.pack_start(self._budget_gauge, False, False, 0)
        self._local_section.pack_start(budget_box, False, False, 4)

        stats_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        stats_box.set_halign(Gtk.Align.CENTER)
        self._prompts_card = StatCard("Prompts")
        self._sessions_card = StatCard("Sessions")
        self._time_card = StatCard("Active")
        for card in (self._prompts_card, self._sessions_card, self._time_card):
            stats_box.pack_start(card, True, True, 0)
        self._local_section.pack_start(stats_box, False, False, 4)

        self._budget_reset_label = Gtk.Label(label="Budget resets: --")
        self._budget_reset_label.get_style_context().add_class("dim-label")
        self._budget_reset_label.set_halign(Gtk.Align.CENTER)
        self._local_section.pack_start(self._budget_reset_label, False, False, 0)

        # --- Separator ---
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)

        # --- Recent activity ---
        activity_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        activity_lbl = Gtk.Label()
        activity_lbl.set_markup(
            "<span size='small' weight='bold' letter_spacing='1200'>RECENT ACTIVITY</span>"
        )
        activity_lbl.get_style_context().add_class("section-header")
        self._trend_label = Gtk.Label(label="→")
        self._trend_label.get_style_context().add_class("dim-label")
        activity_header.pack_start(activity_lbl, False, False, 0)
        activity_header.pack_start(self._trend_label, False, False, 0)

        self._activity_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

        self.pack_start(self._api_section, False, False, 0)
        self.pack_start(self._local_section, False, False, 0)
        self.pack_start(sep, False, False, 8)
        self.pack_start(activity_header, False, False, 4)
        self.pack_start(self._activity_list, False, False, 0)

        # Start with local mode visible
        self._api_section.hide()
        self._local_section.show_all()

        # GLib timer for countdown refresh (every 30s)
        GLib.timeout_add_seconds(30, self._refresh_countdowns)

        self._last_api_data: Optional[RateLimitData] = None

    # ------------------------------------------------------------------
    # Public update methods (called from GTK main thread)
    # ------------------------------------------------------------------

    def update_api_data(self, data: RateLimitData) -> None:
        """Update the API-mode gauges."""
        self._last_api_data = data
        has_data = (
            data.error is None
            and (data.session_utilization > 0 or data.weekly_utilization > 0 or data.session_reset_epoch > 0)
        )

        if has_data:
            if not self._has_api_data:
                self._has_api_data = True
                self._api_section.show_all()
                self._local_section.hide()

            self._session_gauge.set_value(data.session_utilization)
            self._weekly_gauge.set_value(data.weekly_utilization)
            self._session_reset_label.set_text(
                f"Session resets: {_format_reset_countdown(data.session_reset_epoch)}"
            )
            self._weekly_reset_label.set_text(
                f"Weekly resets: {_format_reset_countdown(data.weekly_reset_epoch)}"
            )
            if data.last_updated:
                ts = datetime.fromtimestamp(data.last_updated).strftime("%H:%M:%S")
                self._updated_label.set_text(f"Last updated: {ts}")
            self._error_label.set_text("")
        else:
            if data.error:
                self._error_label.set_text(f"⚠ {data.error}")

    def update_local_data(self, summary: DailySummary, budget_used: int = 0,
                          budget_total: int = 480, trend: UsageTrend = UsageTrend.STABLE) -> None:
        """Update local-mode stats."""
        self._trend = trend
        self._trend_label.set_text(_TREND_SYMBOLS.get(trend, "→"))

        # Update stat cards
        self._prompts_card.set_value(str(summary.prompt_count))
        self._sessions_card.set_value(str(summary.session_count))
        h, m = divmod(summary.active_minutes, 60)
        self._time_card.set_value(f"{h}h{m:02d}m")

        # Budget gauge
        if budget_total > 0:
            frac = min(1.0, budget_used / budget_total)
            self._budget_gauge.set_value(frac)

        # Recent activity list
        self._rebuild_activity_list(summary)

    def update_budget_reset(self, reset_hour: int) -> None:
        """Update the budget reset countdown display."""
        from datetime import datetime as dt
        now = dt.now()
        # Next reset at reset_hour:00
        next_reset = now.replace(hour=reset_hour, minute=0, second=0, microsecond=0)
        if next_reset <= now:
            # Tomorrow
            from datetime import timedelta
            next_reset += timedelta(days=1)
        diff = int((next_reset - now).total_seconds())
        h = diff // 3600
        m = (diff % 3600) // 60
        self._budget_reset_label.set_text(f"Budget resets in: {h}h {m:02d}m")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _rebuild_activity_list(self, summary: DailySummary) -> None:
        """Rebuild the recent activity list widget."""
        for child in self._activity_list.get_children():
            self._activity_list.remove(child)

        entries = list(reversed(summary.entries))[:5]
        for entry in entries:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            time_lbl = Gtk.Label(label=_format_time(entry.timestamp_ms))
            time_lbl.set_width_chars(5)
            time_lbl.get_style_context().add_class("dim-label")
            time_lbl.set_xalign(0.0)

            display = entry.display[:80] if entry.display else "(no display)"
            disp_lbl = Gtk.Label(label=display)
            disp_lbl.set_xalign(0.0)
            disp_lbl.set_ellipsize(3)  # PANGO_ELLIPSIZE_END = 3

            row.pack_start(time_lbl, False, False, 0)
            row.pack_start(disp_lbl, True, True, 0)
            self._activity_list.pack_start(row, False, False, 0)

        if not entries:
            empty = Gtk.Label(label="No activity today")
            empty.get_style_context().add_class("dim-label")
            self._activity_list.pack_start(empty, False, False, 0)

        self._activity_list.show_all()

    def _refresh_countdowns(self) -> bool:
        """Periodically refresh the countdown labels."""
        if self._last_api_data and self._has_api_data:
            data = self._last_api_data
            self._session_reset_label.set_text(
                f"Session resets: {_format_reset_countdown(data.session_reset_epoch)}"
            )
            self._weekly_reset_label.set_text(
                f"Weekly resets: {_format_reset_countdown(data.weekly_reset_epoch)}"
            )
        return True  # keep timer alive
