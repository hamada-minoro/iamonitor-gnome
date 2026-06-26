"""Reusable GTK widgets for IAMonitor."""
import math
import logging
from typing import Optional

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk  # type: ignore[import]

logger = logging.getLogger(__name__)

# Neon palette — reads well on dark glass backgrounds
_COLOR_GREEN  = (0.18, 0.90, 0.58)   # #2DE594
_COLOR_YELLOW = (1.00, 0.78, 0.00)   # #FFC800
_COLOR_RED    = (1.00, 0.33, 0.44)   # #FF5470

_ANIM_FRAMES = 12
_ANIM_MS = 25


def _gauge_color(value: float) -> tuple[float, float, float]:
    if value >= 0.80:
        return _COLOR_RED
    if value >= 0.50:
        return _COLOR_YELLOW
    return _COLOR_GREEN


class CircularGauge(Gtk.Box):
    """Circular arc progress gauge with animated glow effect."""

    def __init__(self, label: str = "", size: int = 100) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._label_text = label
        self._size = size
        self._value: float = 0.0
        self._displayed: float = 0.0
        self._anim_step = 0
        self._anim_target: float = 0.0
        self._anim_start: float = 0.0
        self._timer_id: Optional[int] = None

        self._drawing_area = Gtk.DrawingArea()
        self._drawing_area.set_size_request(size, size)
        self._drawing_area.connect("draw", self._on_draw)
        self.pack_start(self._drawing_area, False, False, 0)

        if label:
            lbl = Gtk.Label(label=label)
            lbl.get_style_context().add_class("caption")
            self.pack_start(lbl, False, False, 0)

    def set_value(self, value: float) -> None:
        value = max(0.0, min(1.0, value))
        if value == self._value:
            return
        self._anim_start = self._displayed
        self._anim_target = value
        self._value = value
        self._anim_step = 0
        if self._timer_id is None:
            self._timer_id = GLib.timeout_add(_ANIM_MS, self._on_anim_tick)

    def _on_anim_tick(self) -> bool:
        self._anim_step += 1
        t = min(1.0, self._anim_step / _ANIM_FRAMES)
        t2 = 1.0 - (1.0 - t) ** 3  # ease-out cubic
        self._displayed = self._anim_start + (self._anim_target - self._anim_start) * t2
        self._drawing_area.queue_draw()
        if self._anim_step >= _ANIM_FRAMES:
            self._timer_id = None
            return False
        return True

    def _on_draw(self, widget: Gtk.DrawingArea, cr) -> None:  # type: ignore[type-arg]
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        cx, cy = w / 2, h / 2
        radius = min(w, h) / 2 - 12
        line_w = 7.0

        cr.set_line_cap(1)  # cairo.LINE_CAP_ROUND

        # Background track — faint white ring
        cr.set_line_width(line_w)
        cr.set_source_rgba(1, 1, 1, 0.09)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.stroke()

        if self._displayed > 0.001:
            r, g, b = _gauge_color(self._displayed)
            start_angle = -math.pi / 2
            end_angle = start_angle + 2 * math.pi * self._displayed

            # Outer glow — widest, most transparent
            cr.set_source_rgba(r, g, b, 0.12)
            cr.set_line_width(line_w * 3.2)
            cr.arc(cx, cy, radius, start_angle, end_angle)
            cr.stroke()

            # Mid glow
            cr.set_source_rgba(r, g, b, 0.28)
            cr.set_line_width(line_w * 1.8)
            cr.arc(cx, cy, radius, start_angle, end_angle)
            cr.stroke()

            # Core arc — fully opaque, crisp
            cr.set_source_rgba(r, g, b, 1.0)
            cr.set_line_width(line_w)
            cr.arc(cx, cy, radius, start_angle, end_angle)
            cr.stroke()

        # Centre percentage text — white, bold
        pct_text = f"{int(self._displayed * 100)}%"
        cr.set_source_rgba(0.91, 0.91, 0.94, 1.0)
        cr.select_font_face("Sans", 0, 1)  # bold
        cr.set_font_size(radius * 0.36)
        extents = cr.text_extents(pct_text)
        cr.move_to(cx - extents.width / 2, cy + extents.height / 2)
        cr.show_text(pct_text)


class StatCard(Gtk.Frame):
    """Glass card with a label and a large value."""

    def __init__(self, label: str, value: str = "--") -> None:
        super().__init__()
        self.set_shadow_type(Gtk.ShadowType.NONE)
        self.get_style_context().add_class("stat-card")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(12)
        box.set_margin_end(12)

        self._label_widget = Gtk.Label(label=label)
        self._label_widget.set_halign(Gtk.Align.CENTER)
        self._label_widget.get_style_context().add_class("caption")
        box.pack_start(self._label_widget, False, False, 0)

        self._value_widget = Gtk.Label()
        self._value_widget.set_halign(Gtk.Align.CENTER)
        self._value_widget.set_markup(
            f"<span size='large' weight='bold' foreground='#E8E8F0'>{value}</span>"
        )
        box.pack_start(self._value_widget, False, False, 0)

        self.add(box)

    def set_value(self, value: str) -> None:
        escaped = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self._value_widget.set_markup(
            f"<span size='large' weight='bold' foreground='#E8E8F0'>{escaped}</span>"
        )

    def set_label(self, label: str) -> None:
        self._label_widget.set_text(label)


class ProgressRow(Gtk.Box):
    """A row with a label, progress bar and a right-hand value label."""

    def __init__(self, label: str) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.set_margin_top(4)
        self.set_margin_bottom(4)

        lbl = Gtk.Label(label=label)
        lbl.set_width_chars(12)
        lbl.set_xalign(0.0)
        self.pack_start(lbl, False, False, 0)

        self._progress = Gtk.ProgressBar()
        self._progress.set_hexpand(True)
        self.pack_start(self._progress, True, True, 0)

        self._value_label = Gtk.Label(label="--")
        self._value_label.set_width_chars(8)
        self._value_label.set_xalign(1.0)
        self.pack_end(self._value_label, False, False, 0)

    def set_progress(self, fraction: float, text: str = "") -> None:
        self._progress.set_fraction(max(0.0, min(1.0, fraction)))
        if text:
            self._value_label.set_text(text)

    def set_value_text(self, text: str) -> None:
        self._value_label.set_text(text)


def apply_css(widget: Gtk.Widget, css: str) -> None:
    provider = Gtk.CssProvider()
    provider.load_from_data(css.encode("utf-8"))
    widget.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
