"""Main application class for IAMonitor."""
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Notify", "0.7")

try:
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator3  # type: ignore[import]
except (ValueError, ImportError):
    try:
        gi.require_version("AppIndicator3", "0.1")
        from gi.repository import AppIndicator3  # type: ignore[import]
    except (ValueError, ImportError) as exc:
        print(
            f"ERROR: Neither AyatanaAppIndicator3 nor AppIndicator3 found.\n"
            f"Install libayatana-appindicator3-dev or libappindicator3-dev.\n{exc}",
            file=sys.stderr,
        )
        AppIndicator3 = None  # type: ignore[assignment]

from gi.repository import Gtk, GLib, Notify  # type: ignore[import]

from iamonitor import config as cfg
from iamonitor.models.usage_data import DailySummary, RateLimitData, UsageTrend
from iamonitor.services.anthropic_api import AnthropicAPIService
from iamonitor.services.activity_monitor import ActivityMonitor
from iamonitor.services.budget_manager import BudgetManager
from iamonitor.ui.main_window import MainWindow

logger = logging.getLogger(__name__)

# Path to the SVG icon shipped with the package
_ICON_PATH = str(
    Path(__file__).parent.parent / "data" / "icons" / "iamonitor.svg"
)
# Fallback to a standard system icon name if SVG not found
_ICON_FALLBACK = "utilities-system-monitor"


class IAMonitorApp:
    """Top-level application: wires together services, indicator and window."""

    def __init__(self) -> None:
        self._loop = GLib.MainLoop()
        self._config = cfg.load_config()

        # Initialise libnotify
        if not Notify.is_initted():
            Notify.init("IAMonitor")

        # --- Services ---
        self._api_service = AnthropicAPIService(on_update=self._on_api_update)
        self._activity_monitor = ActivityMonitor(on_update=self._on_activity_update)
        self._budget_manager = BudgetManager(
            on_budget_update=self._on_budget_update,
            config=self._config,
        )

        # --- State ---
        self._latest_summary = DailySummary()
        self._latest_rate_limit = RateLimitData()
        self._budget_used = 0
        self._budget_total = self._config.get("daily_budget_minutes", 480)

        # --- UI ---
        self._window: Optional[MainWindow] = None
        self._indicator: Optional[object] = None
        self._setup_window()
        self._setup_indicator()

        # Apply initial config to services
        token = self._config.get("oauth_token", "")
        if token:
            self._api_service.set_token(token)
        self._api_service.set_interval(self._config.get("polling_interval", 120))

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run(self) -> int:
        """Start all services and enter the GLib main loop."""
        self._activity_monitor.start()
        self._api_service.start()
        self._budget_manager.start_glib_timer()

        # Schedule a one-time countdown refresh every second when active
        GLib.timeout_add_seconds(1, self._tick_countdown)

        logger.info("IAMonitor running")
        try:
            self._loop.run()
        except KeyboardInterrupt:
            self.quit()
        return 0

    def quit(self) -> None:
        """Stop all services and quit the main loop."""
        logger.info("IAMonitor quitting")
        self._api_service.stop()
        self._activity_monitor.stop()
        self._budget_manager.stop_glib_timer()
        Notify.uninit()
        self._loop.quit()

    # ------------------------------------------------------------------
    # Service callbacks (called on GTK main thread via GLib.idle_add)
    # ------------------------------------------------------------------

    def _on_api_update(self, data: RateLimitData) -> None:
        self._latest_rate_limit = data

        # Update tray label
        if data.error is None and data.session_utilization > 0:
            pct = int(data.session_utilization * 100)
            self._set_indicator_label(f"{pct}%")
        elif data.error:
            self._set_indicator_label("⚠")
        else:
            self._set_indicator_label("--")

        if self._window:
            self._window.update_api_data(data)

    def _on_activity_update(self, summary: DailySummary) -> None:
        self._latest_summary = summary
        self._budget_manager.update_used(summary.active_minutes)

        if self._window:
            trend = self._activity_monitor.trend
            self._window.update_local_data(
                summary,
                budget_used=self._budget_used,
                budget_total=self._budget_total,
                trend=trend,
            )
            self._window.get_dashboard().update_budget_reset(
                self._config.get("reset_hour", 0)
            )

    def _on_budget_update(self, used: int, total: int, countdown: Optional[int]) -> None:
        self._budget_used = used
        self._budget_total = total
        if self._window:
            self._window.update_countdown_display(countdown)

    # ------------------------------------------------------------------
    # Settings callbacks (wired into SettingsTab)
    # ------------------------------------------------------------------

    def _on_token_changed(self, token: str) -> None:
        self._api_service.set_token(token)
        self._api_service.poll_now()

    def _on_interval_changed(self, seconds: int) -> None:
        self._api_service.set_interval(seconds)

    def _on_config_changed(self, new_config: dict) -> None:
        self._config = new_config
        self._budget_manager.update_config(new_config)

    def _on_start_countdown(self, hours: int, minutes: int) -> None:
        self._budget_manager.start_countdown(hours, minutes)

    def _on_stop_countdown(self) -> None:
        self._budget_manager.stop_countdown()

    def _on_reset_data(self) -> None:
        """Reset in-memory daily summary."""
        self._latest_summary = DailySummary()
        self._budget_used = 0
        if self._window:
            self._window.update_local_data(
                self._latest_summary,
                budget_used=0,
                budget_total=self._budget_total,
            )

    # ------------------------------------------------------------------
    # Indicator
    # ------------------------------------------------------------------

    def _setup_indicator(self) -> None:
        if AppIndicator3 is None:
            logger.warning("AppIndicator3 unavailable — running without system tray")
            return

        icon_path = _ICON_PATH if Path(_ICON_PATH).exists() else _ICON_FALLBACK

        try:
            indicator = AppIndicator3.Indicator.new(
                "iamonitor",
                icon_path,
                AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
            )
            indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            indicator.set_label("--", "100%")

            menu = self._build_indicator_menu()
            indicator.set_menu(menu)

            self._indicator = indicator
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to create AppIndicator: %s", exc)

    def _build_indicator_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()

        show_item = Gtk.MenuItem(label="Show / Hide")
        show_item.connect("activate", lambda _: self._toggle_window())
        menu.append(show_item)

        sep = Gtk.SeparatorMenuItem()
        menu.append(sep)

        poll_item = Gtk.MenuItem(label="Poll Now")
        poll_item.connect("activate", lambda _: self._api_service.poll_now())
        menu.append(poll_item)

        about_item = Gtk.MenuItem(label="About")
        about_item.connect("activate", self._on_about)
        menu.append(about_item)

        sep2 = Gtk.SeparatorMenuItem()
        menu.append(sep2)

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda _: self.quit())
        menu.append(quit_item)

        menu.show_all()
        return menu

    def _set_indicator_label(self, label: str) -> None:
        if self._indicator is not None:
            try:
                self._indicator.set_label(label, "100%")  # type: ignore[union-attr]
            except Exception as exc:  # noqa: BLE001
                logger.debug("Failed to set indicator label: %s", exc)

    # ------------------------------------------------------------------
    # Window
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        self._window = MainWindow(
            on_token_changed=self._on_token_changed,
            on_interval_changed=self._on_interval_changed,
            on_config_changed=self._on_config_changed,
            on_start_countdown=self._on_start_countdown,
            on_stop_countdown=self._on_stop_countdown,
            on_reset_data=self._on_reset_data,
        )

    def _toggle_window(self) -> None:
        if self._window:
            self._window.toggle()

    def _on_about(self, _item: Gtk.MenuItem) -> None:
        dialog = Gtk.AboutDialog()
        dialog.set_program_name("IAMonitor")
        dialog.set_version("1.0.0")
        dialog.set_comments("Claude Pro/Max usage monitor for GNOME/Linux")
        dialog.set_website("https://github.com/hamada-minoro/IAMonitor-Gnome")
        dialog.set_authors(["hamada-minoro"])
        dialog.set_license_type(Gtk.License.MIT_X11)
        dialog.run()
        dialog.destroy()

    # ------------------------------------------------------------------
    # Periodic tick for countdown display
    # ------------------------------------------------------------------

    def _tick_countdown(self) -> bool:
        remaining = self._budget_manager.get_countdown_remaining()
        if self._window:
            self._window.update_countdown_display(remaining)
        return True  # keep ticking
