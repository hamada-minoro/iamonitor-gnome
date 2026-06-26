"""Main popup window for IAMonitor."""
import math
import logging
from typing import Optional

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib  # type: ignore[import]

from iamonitor.models.usage_data import DailySummary, RateLimitData, UsageTrend
from iamonitor.ui.dashboard_tab import DashboardTab
from iamonitor.ui.tasks_tab import TasksTab
from iamonitor.ui.settings_tab import SettingsTab

logger = logging.getLogger(__name__)


_WINDOW_CSS = """
/* ── Window shell ─────────────────────────────── */
window#IAMonitorWindow {
    background-color: rgba(16, 17, 30, 0.95);
    border-radius: 14px;
    border: 1px solid rgba(255, 255, 255, 0.10);
}
window#IAMonitorWindow > box,
window#IAMonitorWindow notebook,
window#IAMonitorWindow notebook > header,
window#IAMonitorWindow notebook > header > tabs,
window#IAMonitorWindow notebook > stack,
window#IAMonitorWindow scrolledwindow,
window#IAMonitorWindow viewport {
    background-color: transparent;
}

/* ── Tabs ─────────────────────────────────────── */
window#IAMonitorWindow notebook > header {
    border-bottom: 1px solid rgba(255,255,255,0.08);
    padding: 0 8px;
}
window#IAMonitorWindow notebook > header > tabs > tab {
    color: rgba(232,232,240,0.45);
    background-color: transparent;
    background-image: none;
    border: none;
    border-radius: 8px;
    padding: 5px 16px;
    margin: 4px 2px;
    box-shadow: none;
    text-shadow: none;
    font-size: 0.88em;
    letter-spacing: 0.3px;
    transition: all 120ms ease;
}
window#IAMonitorWindow notebook > header > tabs > tab:checked {
    color: #E8E8F0;
    background-color: rgba(124,106,250,0.28);
    background-image: none;
    box-shadow: none;
}
window#IAMonitorWindow notebook > header > tabs > tab:hover:not(:checked) {
    background-color: rgba(255,255,255,0.07);
    background-image: none;
    color: rgba(232,232,240,0.75);
}
window#IAMonitorWindow notebook > header > tabs > tab label {
    color: inherit;
}

/* ── Typography ───────────────────────────────── */
window#IAMonitorWindow label {
    color: #E8E8F0;
}
.dim-label {
    color: rgba(232,232,240,0.42);
    font-size: 0.81em;
}
.caption {
    color: rgba(232,232,240,0.45);
    font-size: 0.77em;
    letter-spacing: 0.4px;
}
.error {
    color: #FF5370;
}
.section-header {
    color: rgba(232,232,240,0.35);
    font-size: 0.70em;
    letter-spacing: 1.8px;
}

/* ── Buttons ──────────────────────────────────── */
window#IAMonitorWindow button {
    background-color: rgba(255,255,255,0.08);
    background-image: none;
    border: 1px solid rgba(255,255,255,0.11);
    border-radius: 8px;
    color: #E8E8F0;
    padding: 4px 10px;
    box-shadow: none;
    text-shadow: none;
    -gtk-icon-shadow: none;
    transition: background-color 120ms ease;
}
window#IAMonitorWindow button:hover {
    background-color: rgba(255,255,255,0.14);
    background-image: none;
    border-color: rgba(255,255,255,0.18);
}
window#IAMonitorWindow button:active {
    background-color: rgba(255,255,255,0.05);
    background-image: none;
}
window#IAMonitorWindow button.suggested-action {
    background-color: rgba(124,106,250,0.32);
    background-image: none;
    border-color: rgba(124,106,250,0.55);
    color: #E8E8F0;
}
window#IAMonitorWindow button.suggested-action:hover {
    background-color: rgba(124,106,250,0.48);
    background-image: none;
}
window#IAMonitorWindow button.destructive-action {
    background-color: rgba(255,83,112,0.18);
    background-image: none;
    border-color: rgba(255,83,112,0.38);
    color: #FF8FA3;
}
window#IAMonitorWindow button.destructive-action:hover {
    background-color: rgba(255,83,112,0.32);
    background-image: none;
}

/* ── Entry / SpinButton ───────────────────────── */
window#IAMonitorWindow entry {
    background-color: rgba(255,255,255,0.07);
    background-image: none;
    border: 1px solid rgba(255,255,255,0.11);
    border-radius: 8px;
    color: #E8E8F0;
    caret-color: #7C6AFA;
    box-shadow: none;
    padding: 5px 10px;
}
window#IAMonitorWindow entry:focus {
    border-color: rgba(124,106,250,0.65);
    background-color: rgba(124,106,250,0.07);
    box-shadow: none;
}
window#IAMonitorWindow spinbutton {
    background-color: rgba(255,255,255,0.07);
    background-image: none;
    border: 1px solid rgba(255,255,255,0.11);
    border-radius: 8px;
    color: #E8E8F0;
    box-shadow: none;
}
window#IAMonitorWindow spinbutton button {
    background-color: transparent;
    background-image: none;
    border: none;
    box-shadow: none;
    padding: 2px 4px;
    min-width: 0;
}

/* ── ComboBox ─────────────────────────────────── */
window#IAMonitorWindow combobox button {
    background-color: rgba(255,255,255,0.07);
    background-image: none;
    border: 1px solid rgba(255,255,255,0.11);
    border-radius: 8px;
    color: #E8E8F0;
    box-shadow: none;
}

/* ── ProgressBar ──────────────────────────────── */
window#IAMonitorWindow progressbar > trough {
    background-color: rgba(255,255,255,0.08);
    background-image: none;
    border-radius: 4px;
    border: none;
    min-height: 4px;
    box-shadow: none;
}
window#IAMonitorWindow progressbar > trough > progress {
    background-color: #7C6AFA;
    background-image: none;
    border-radius: 4px;
    border: none;
    box-shadow: none;
}

/* ── Radio buttons ────────────────────────────── */
window#IAMonitorWindow radiobutton label {
    color: rgba(232,232,240,0.72);
    font-size: 0.88em;
}
window#IAMonitorWindow radiobutton:checked label {
    color: #E8E8F0;
}

/* ── Scrollbar ────────────────────────────────── */
window#IAMonitorWindow scrollbar {
    background-color: transparent;
    border: none;
}
window#IAMonitorWindow scrollbar slider {
    background-color: rgba(255,255,255,0.14);
    border-radius: 4px;
    min-width: 4px;
    min-height: 4px;
}
window#IAMonitorWindow scrollbar slider:hover {
    background-color: rgba(255,255,255,0.24);
}

/* ── Separator ────────────────────────────────── */
window#IAMonitorWindow separator {
    background-color: rgba(255,255,255,0.08);
    min-height: 1px;
    min-width: 1px;
}

/* ── Frame / StatCard ─────────────────────────── */
window#IAMonitorWindow frame {
    background-color: transparent;
    border: none;
}
.stat-card {
    background-color: rgba(255,255,255,0.055);
    border: 1px solid rgba(255,255,255,0.09);
    border-radius: 12px;
    padding: 4px;
}
"""

_WINDOW_WIDTH = 380


class MainWindow(Gtk.Window):
    """Floating popup window that appears near the system tray."""

    def __init__(
        self,
        on_token_changed,
        on_interval_changed,
        on_config_changed,
        on_start_countdown,
        on_stop_countdown,
        on_reset_data,
    ) -> None:
        super().__init__(title="IAMonitor")
        self.set_name("IAMonitorWindow")
        self.set_decorated(False)
        self.set_default_size(_WINDOW_WIDTH, -1)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)
        self._last_height: int = 0  # cached after first show

        # Request RGBA visual so CSS rgba() background-color is properly transparent.
        # On composited desktops (GNOME/ZorinOS) the compositor handles blending;
        # no custom draw handler needed — GTK3's CSS engine does everything.
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.set_visual(visual)

        # Apply dark-glass CSS
        provider = Gtk.CssProvider()
        provider.load_from_data(_WINDOW_CSS.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        # Header
        header = self._build_header()

        # Notebook
        self._notebook = Gtk.Notebook()
        self._notebook.set_tab_pos(Gtk.PositionType.TOP)
        self._notebook.set_scrollable(True)

        self._dashboard = DashboardTab()
        self._notebook.append_page(self._dashboard, Gtk.Label(label="Dashboard"))

        self._tasks = TasksTab()
        self._notebook.append_page(self._tasks, Gtk.Label(label="Tasks"))

        self._settings = SettingsTab(
            on_token_changed=on_token_changed,
            on_interval_changed=on_interval_changed,
            on_config_changed=on_config_changed,
            on_start_countdown=on_start_countdown,
            on_stop_countdown=on_stop_countdown,
            on_reset_data=on_reset_data,
        )
        self._notebook.append_page(self._settings, Gtk.Label(label="Settings"))

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        vbox.pack_start(header, False, False, 0)
        vbox.pack_start(self._notebook, True, True, 0)

        # Bottom padding so content doesn't hug the rounded corner
        bottom_pad = Gtk.Box()
        bottom_pad.set_size_request(-1, 6)
        vbox.pack_end(bottom_pad, False, False, 0)

        self.add(vbox)

        self.connect("focus-out-event", self._on_focus_out)
        self.connect("key-press-event", self._on_key_press)
        self.connect("delete-event", lambda w, e: w.hide() or True)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def show_near_tray(self) -> None:
        """Position the window on the monitor where the user clicked."""
        display = Gdk.Display.get_default()
        screen = display.get_default_screen()

        # Read the pointer position BEFORE showing the window.
        # This is what identifies the correct monitor: the user's cursor is
        # already on the monitor where they clicked the tray icon.
        try:
            seat = display.get_default_seat()
            pointer = seat.get_pointer()
            _, px, py = pointer.get_position()
            monitor_num = screen.get_monitor_at_point(px, py)
        except Exception:
            monitor_num = screen.get_primary_monitor()

        monitor_geom = screen.get_monitor_geometry(monitor_num)

        # Detect whether the panel is at the top or bottom of this monitor.
        try:
            work = screen.get_monitor_workarea(monitor_num)
            top_gap = work.y - monitor_geom.y
            bottom_gap = (monitor_geom.y + monitor_geom.height) - (work.y + work.height)
            panel_at_bottom = bottom_gap > top_gap
        except Exception:
            top_gap = 40
            panel_at_bottom = False

        x = monitor_geom.x + monitor_geom.width - _WINDOW_WIDTH - 10

        # Use cached height from a previous show, or a safe estimate.
        # This lets us pre-position before show_all() so the window never
        # appears on the wrong monitor even for a single frame.
        est_h = self._last_height if self._last_height > 0 else 460
        if panel_at_bottom:
            try:
                y = work.y + work.height - est_h - 8
            except Exception:
                y = monitor_geom.y + monitor_geom.height - est_h - 50
        else:
            y = monitor_geom.y + top_gap + 4

        # Clamp to monitor bounds with the estimated height
        x = max(monitor_geom.x + 5, min(x, monitor_geom.x + monitor_geom.width - _WINDOW_WIDTH - 5))
        y = max(monitor_geom.y + 5, min(y, monitor_geom.y + monitor_geom.height - est_h - 5))

        # Pre-position THEN show — avoids the window flashing on the wrong monitor
        self.move(x, y)
        self.show_all()

        # Flush pending events so GTK computes the real height
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)

        _, h = self.get_size()
        self._last_height = h

        # Refine y with the real height (only matters for bottom-panel layout)
        if panel_at_bottom:
            try:
                y = work.y + work.height - h - 8
            except Exception:
                y = monitor_geom.y + monitor_geom.height - h - 50
            y = max(monitor_geom.y + 5, min(y, monitor_geom.y + monitor_geom.height - h - 5))
            self.move(x, y)

        self.present()

    def toggle(self) -> None:
        if self.get_visible():
            self.hide()
        else:
            self.show_near_tray()

    def get_dashboard(self) -> DashboardTab:
        return self._dashboard

    def get_settings_tab(self) -> SettingsTab:
        return self._settings

    # ------------------------------------------------------------------
    # Delegated update methods
    # ------------------------------------------------------------------

    def update_api_data(self, data: RateLimitData) -> None:
        self._dashboard.update_api_data(data)

    def update_local_data(
        self,
        summary: DailySummary,
        budget_used: int = 0,
        budget_total: int = 480,
        trend: UsageTrend = UsageTrend.STABLE,
    ) -> None:
        self._dashboard.update_local_data(summary, budget_used, budget_total, trend)

    def update_countdown_display(self, remaining_seconds: Optional[int]) -> None:
        self._settings.update_countdown_display(remaining_seconds)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_header(self) -> Gtk.Box:
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        header.set_margin_top(14)
        header.set_margin_bottom(10)
        header.set_margin_start(16)
        header.set_margin_end(12)

        # Accent dot
        dot = Gtk.DrawingArea()
        dot.set_size_request(8, 8)
        dot.connect("draw", self._draw_accent_dot)
        dot_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        dot_box.set_valign(Gtk.Align.CENTER)
        dot_box.pack_start(dot, False, False, 0)
        header.pack_start(dot_box, False, False, 0)

        # Title block
        title_block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        title_block.set_margin_start(10)
        title_block.set_valign(Gtk.Align.CENTER)

        title_lbl = Gtk.Label()
        title_lbl.set_markup("<span size='medium' weight='bold' letter_spacing='500'>IAMonitor</span>")
        title_lbl.set_xalign(0.0)
        title_block.pack_start(title_lbl, False, False, 0)

        sub_lbl = Gtk.Label()
        sub_lbl.set_markup("<span size='small'>Claude Pro / Max</span>")
        sub_lbl.set_xalign(0.0)
        sub_lbl.get_style_context().add_class("dim-label")
        title_block.pack_start(sub_lbl, False, False, 0)

        header.pack_start(title_block, True, True, 0)

        # Close button
        close_btn = Gtk.Button()
        close_lbl = Gtk.Label()
        close_lbl.set_markup("<span size='small'>✕</span>")
        close_btn.add(close_lbl)
        close_btn.set_relief(Gtk.ReliefStyle.NONE)
        close_btn.set_valign(Gtk.Align.CENTER)
        close_btn.set_size_request(28, 28)
        close_btn.connect("clicked", lambda _: self.hide())
        header.pack_end(close_btn, False, False, 0)

        return header

    def _draw_accent_dot(self, widget, cr) -> None:
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        cx, cy = w / 2, h / 2
        r = min(w, h) / 2

        # Glow
        cr.set_source_rgba(0.486, 0.416, 0.980, 0.30)
        cr.arc(cx, cy, r + 3, 0, 2 * math.pi)
        cr.fill()

        # Core
        cr.set_source_rgba(0.486, 0.416, 0.980, 1.0)
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.fill()

    def _on_focus_out(self, _widget: Gtk.Window, _event: Gdk.EventFocus) -> bool:
        for w in Gtk.Window.list_toplevels():
            if w is not self and w.get_visible() and isinstance(w, Gtk.Dialog):
                return False
        self.hide()
        return False

    def _on_key_press(self, _widget: Gtk.Window, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        return False
