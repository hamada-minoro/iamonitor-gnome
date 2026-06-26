"""Settings tab for IAMonitor popup window."""
import logging
from typing import Callable, Optional

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib  # type: ignore[import]

from iamonitor import config as cfg
from iamonitor.services.credential_helper import get_oauth_token, save_manual_token

logger = logging.getLogger(__name__)


def _make_section_label(text: str) -> Gtk.Label:
    lbl = Gtk.Label()
    lbl.set_markup(f"<span size='x-small' weight='bold' letter_spacing='1500'>{text.upper()}</span>")
    lbl.get_style_context().add_class("section-header")
    lbl.set_xalign(0.0)
    lbl.set_margin_top(14)
    lbl.set_margin_bottom(5)
    return lbl


def _make_row(label_text: str, widget: Gtk.Widget) -> Gtk.Box:
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    row.set_margin_bottom(4)
    lbl = Gtk.Label(label=label_text)
    lbl.set_xalign(0.0)
    lbl.set_width_chars(18)
    row.pack_start(lbl, False, False, 0)
    row.pack_start(widget, True, True, 0)
    return row


class SettingsTab(Gtk.Box):
    """Tab for configuring IAMonitor."""

    def __init__(
        self,
        on_token_changed: Callable[[str], None],
        on_interval_changed: Callable[[int], None],
        on_config_changed: Callable[[dict], None],
        on_start_countdown: Callable[[int, int], None],
        on_stop_countdown: Callable[[], None],
        on_reset_data: Callable[[], None],
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        self.set_margin_start(14)
        self.set_margin_end(14)

        self._on_token_changed = on_token_changed
        self._on_interval_changed = on_interval_changed
        self._on_config_changed = on_config_changed
        self._on_start_countdown = on_start_countdown
        self._on_stop_countdown = on_stop_countdown
        self._on_reset_data = on_reset_data

        self._config = cfg.load_config()
        self._countdown_running = False

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(350)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # ---- OAuth Section ----
        inner.pack_start(_make_section_label("OAuth Token"), False, False, 0)

        self._source_label = Gtk.Label(label="Source: detecting…")
        self._source_label.set_xalign(0.0)
        self._source_label.get_style_context().add_class("dim-label")
        inner.pack_start(self._source_label, False, False, 0)

        token_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._token_entry = Gtk.Entry()
        self._token_entry.set_placeholder_text("Bearer token (auto-detected or manual)")
        self._token_entry.set_hexpand(True)
        self._token_entry.set_visibility(False)  # password mode

        self._show_token_btn = Gtk.ToggleButton(label="Show")
        self._show_token_btn.connect("toggled", self._on_show_token_toggled)

        self._save_token_btn = Gtk.Button(label="Save")
        self._save_token_btn.get_style_context().add_class("suggested-action")
        self._save_token_btn.connect("clicked", self._on_save_token)

        token_row.pack_start(self._token_entry, True, True, 0)
        token_row.pack_start(self._show_token_btn, False, False, 0)
        token_row.pack_start(self._save_token_btn, False, False, 0)
        inner.pack_start(token_row, False, False, 0)

        # ---- Polling interval ----
        inner.pack_start(_make_section_label("Polling Interval"), False, False, 0)

        interval_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._interval_buttons: list[tuple[int, Gtk.RadioButton]] = []
        intervals = [(30, "30s"), (60, "1min"), (120, "2min"), (300, "5min"), (600, "10min")]
        group: Optional[Gtk.RadioButton] = None
        current_interval = self._config.get("polling_interval", 120)
        for value, label in intervals:
            btn: Gtk.RadioButton
            if group is None:
                btn = Gtk.RadioButton.new_with_label(None, label)
                group = btn
            else:
                btn = Gtk.RadioButton.new_with_label_from_widget(group, label)
            if value == current_interval:
                btn.set_active(True)
            btn.connect("toggled", self._on_interval_toggled, value)
            interval_box.pack_start(btn, False, False, 0)
            self._interval_buttons.append((value, btn))
        inner.pack_start(interval_box, False, False, 0)

        # ---- Plan ----
        inner.pack_start(_make_section_label("Plan"), False, False, 0)

        self._plan_combo = Gtk.ComboBoxText()
        for plan_id, plan_label in [("pro", "Pro"), ("max_5x", "Max 5x"), ("max_20x", "Max 20x")]:
            self._plan_combo.append(plan_id, plan_label)
        self._plan_combo.set_active_id(self._config.get("plan_type", "pro"))
        self._plan_combo.connect("changed", self._on_plan_changed)
        inner.pack_start(_make_row("Plan type:", self._plan_combo), False, False, 0)

        # ---- Daily budget ----
        inner.pack_start(_make_section_label("Daily Budget"), False, False, 0)

        self._budget_spin = Gtk.SpinButton.new_with_range(30, 1440, 30)
        self._budget_spin.set_value(self._config.get("daily_budget_minutes", 480))
        self._budget_spin.connect("value-changed", self._on_budget_changed)
        inner.pack_start(_make_row("Budget (minutes):", self._budget_spin), False, False, 0)

        self._alert_spin = Gtk.SpinButton.new_with_range(10, 100, 5)
        self._alert_spin.set_value(self._config.get("alert_at_percentage", 80))
        self._alert_spin.connect("value-changed", self._on_alert_changed)
        inner.pack_start(_make_row("Alert at (%):", self._alert_spin), False, False, 0)

        # ---- Auto reset ----
        inner.pack_start(_make_section_label("Auto Reset"), False, False, 0)

        self._reset_hour_spin = Gtk.SpinButton.new_with_range(0, 23, 1)
        self._reset_hour_spin.set_value(self._config.get("reset_hour", 0))
        self._reset_hour_spin.connect("value-changed", self._on_reset_hour_changed)
        inner.pack_start(_make_row("Reset at hour:", self._reset_hour_spin), False, False, 0)

        # ---- Manual countdown timer ----
        inner.pack_start(_make_section_label("Manual Timer"), False, False, 0)

        timer_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._timer_hours_spin = Gtk.SpinButton.new_with_range(0, 23, 1)
        self._timer_hours_spin.set_width_chars(3)
        h_lbl = Gtk.Label(label="h")
        self._timer_min_spin = Gtk.SpinButton.new_with_range(0, 59, 5)
        self._timer_min_spin.set_width_chars(3)
        m_lbl = Gtk.Label(label="min")

        self._timer_start_btn = Gtk.Button(label="Start")
        self._timer_start_btn.get_style_context().add_class("suggested-action")
        self._timer_start_btn.connect("clicked", self._on_timer_start_stop)

        self._countdown_display = Gtk.Label(label="--:--")
        self._countdown_display.set_width_chars(6)

        for w in (self._timer_hours_spin, h_lbl, self._timer_min_spin, m_lbl,
                  self._timer_start_btn, self._countdown_display):
            timer_box.pack_start(w, False, False, 0)
        inner.pack_start(timer_box, False, False, 0)

        # ---- Danger zone ----
        inner.pack_start(_make_section_label("Danger Zone"), False, False, 0)

        reset_btn = Gtk.Button(label="Reset Today's Data")
        reset_btn.get_style_context().add_class("destructive-action")
        reset_btn.connect("clicked", self._on_reset_data_clicked)
        inner.pack_start(reset_btn, False, False, 0)

        scroll.add(inner)
        self.pack_start(scroll, True, True, 0)

        # Detect token on init
        GLib.idle_add(self._detect_token)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def update_countdown_display(self, remaining_seconds: Optional[int]) -> None:
        """Update the countdown display label (called from app)."""
        if remaining_seconds is None:
            self._countdown_display.set_text("--:--")
            self._countdown_running = False
            self._timer_start_btn.set_label("Start")
        elif remaining_seconds <= 0:
            self._countdown_display.set_text("00:00")
            self._countdown_running = False
            self._timer_start_btn.set_label("Start")
        else:
            h = remaining_seconds // 3600
            m = (remaining_seconds % 3600) // 60
            s = remaining_seconds % 60
            if h > 0:
                self._countdown_display.set_text(f"{h}:{m:02d}:{s:02d}")
            else:
                self._countdown_display.set_text(f"{m:02d}:{s:02d}")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _detect_token(self) -> bool:
        """Detect the OAuth token and update UI (runs once on idle)."""
        try:
            token, source = get_oauth_token()
            if token:
                self._token_entry.set_text(token)
                self._source_label.set_text(f"Source: {source} ✓")
                self._on_token_changed(token)
            else:
                self._source_label.set_text("Source: not found — enter manually")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Token detection error: %s", exc)
            self._source_label.set_text("Source: detection failed")
        return False  # don't repeat

    def _on_show_token_toggled(self, btn: Gtk.ToggleButton) -> None:
        self._token_entry.set_visibility(btn.get_active())
        btn.set_label("Hide" if btn.get_active() else "Show")

    def _on_save_token(self, _btn: Gtk.Button) -> None:
        token = self._token_entry.get_text().strip()
        save_manual_token(token)
        self._source_label.set_text("Source: config (manually saved)")
        self._on_token_changed(token)

    def _on_interval_toggled(self, btn: Gtk.RadioButton, value: int) -> None:
        if btn.get_active():
            self._config["polling_interval"] = value
            cfg.save_config(self._config)
            self._on_interval_changed(value)

    def _on_plan_changed(self, combo: Gtk.ComboBoxText) -> None:
        plan_id = combo.get_active_id()
        if plan_id:
            self._config["plan_type"] = plan_id
            cfg.save_config(self._config)
            self._on_config_changed(self._config)

    def _on_budget_changed(self, spin: Gtk.SpinButton) -> None:
        self._config["daily_budget_minutes"] = int(spin.get_value())
        cfg.save_config(self._config)
        self._on_config_changed(self._config)

    def _on_alert_changed(self, spin: Gtk.SpinButton) -> None:
        self._config["alert_at_percentage"] = int(spin.get_value())
        cfg.save_config(self._config)
        self._on_config_changed(self._config)

    def _on_reset_hour_changed(self, spin: Gtk.SpinButton) -> None:
        self._config["reset_hour"] = int(spin.get_value())
        cfg.save_config(self._config)
        self._on_config_changed(self._config)

    def _on_timer_start_stop(self, _btn: Gtk.Button) -> None:
        if self._countdown_running:
            self._countdown_running = False
            self._timer_start_btn.set_label("Start")
            self._countdown_display.set_text("--:--")
            self._on_stop_countdown()
        else:
            hours = int(self._timer_hours_spin.get_value())
            minutes = int(self._timer_min_spin.get_value())
            if hours == 0 and minutes == 0:
                return
            self._countdown_running = True
            self._timer_start_btn.set_label("Stop")
            self._on_start_countdown(hours, minutes)

    def _on_reset_data_clicked(self, _btn: Gtk.Button) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),  # type: ignore[arg-type]
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Reset today's data?",
        )
        dialog.format_secondary_text(
            "This will clear the in-memory daily summary. "
            "History file data will not be modified."
        )
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.YES:
            self._on_reset_data()
