"""Tasks tab for IAMonitor popup window."""
import logging
from typing import Callable, Optional

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # type: ignore[import]

from iamonitor.models.task_budget import TaskBudget
from iamonitor import config as cfg

logger = logging.getLogger(__name__)

_OVER_BUDGET_CSS = b"""
.over-budget {
    color: #F44336;
    font-weight: bold;
}
"""


class TaskRow(Gtk.Box):
    """A single task row in the task list."""

    def __init__(
        self,
        task: TaskBudget,
        on_toggle: Callable[[TaskBudget], None],
        on_delete: Callable[[TaskBudget], None],
        on_time_added: Callable[[TaskBudget, int], None],
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._task = task
        self._on_toggle = on_toggle
        self._on_delete = on_delete
        self._on_time_added = on_time_added

        # Apply CSS for over-budget styling
        provider = Gtk.CssProvider()
        provider.load_from_data(_OVER_BUDGET_CSS)
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen() if self.get_screen() else Gtk.Window().get_screen(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self.set_margin_top(4)
        self.set_margin_bottom(4)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self._name_label = Gtk.Label(label=task.name)
        self._name_label.set_xalign(0.0)
        self._name_label.set_hexpand(True)
        if task.used_minutes > task.allocated_minutes:
            self._name_label.get_style_context().add_class("over-budget")
        header.pack_start(self._name_label, True, True, 0)

        self._toggle_btn = Gtk.Button()
        self._toggle_btn.set_label("■ Stop" if task.is_active else "▶ Start")
        self._toggle_btn.connect("clicked", self._on_toggle_clicked)
        if task.is_active:
            self._toggle_btn.get_style_context().add_class("suggested-action")
        header.pack_start(self._toggle_btn, False, False, 0)

        del_btn = Gtk.Button(label="✕")
        del_btn.set_relief(Gtk.ReliefStyle.NONE)
        del_btn.connect("clicked", self._on_delete_clicked)
        header.pack_start(del_btn, False, False, 0)

        self.pack_start(header, False, False, 0)

        # Progress bar row
        prog_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._progress = Gtk.ProgressBar()
        self._progress.set_hexpand(True)
        frac = (task.used_minutes / task.allocated_minutes) if task.allocated_minutes > 0 else 0.0
        self._progress.set_fraction(min(1.0, max(0.0, frac)))

        self._time_label = Gtk.Label(
            label=f"{task.used_minutes}/{task.allocated_minutes} min"
        )
        self._time_label.set_xalign(1.0)
        prog_box.pack_start(self._progress, True, True, 0)
        prog_box.pack_start(self._time_label, False, False, 0)
        self.pack_start(prog_box, False, False, 0)

        # Add time row (only shown when active)
        add_time_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        add_time_lbl = Gtk.Label(label="Add min:")
        self._add_spin = Gtk.SpinButton.new_with_range(1, 480, 1)
        self._add_spin.set_value(30)
        add_btn = Gtk.Button(label="Add")
        add_btn.connect("clicked", self._on_add_time)
        add_time_box.pack_start(add_time_lbl, False, False, 0)
        add_time_box.pack_start(self._add_spin, False, False, 0)
        add_time_box.pack_start(add_btn, False, False, 0)
        self._add_time_box = add_time_box
        if not task.is_active:
            add_time_box.hide()
        self.pack_start(add_time_box, False, False, 0)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.pack_start(sep, False, False, 4)

    def update_task(self, task: TaskBudget) -> None:
        """Refresh the row from an updated task object."""
        self._task = task
        self._name_label.set_text(task.name)
        if task.used_minutes > task.allocated_minutes:
            self._name_label.get_style_context().add_class("over-budget")
        else:
            self._name_label.get_style_context().remove_class("over-budget")

        self._toggle_btn.set_label("■ Stop" if task.is_active else "▶ Start")
        if task.is_active:
            self._toggle_btn.get_style_context().add_class("suggested-action")
            self._add_time_box.show()
        else:
            self._toggle_btn.get_style_context().remove_class("suggested-action")
            self._add_time_box.hide()

        frac = (task.used_minutes / task.allocated_minutes) if task.allocated_minutes > 0 else 0.0
        self._progress.set_fraction(min(1.0, max(0.0, frac)))
        self._time_label.set_text(f"{task.used_minutes}/{task.allocated_minutes} min")

    def _on_toggle_clicked(self, _btn: Gtk.Button) -> None:
        self._on_toggle(self._task)

    def _on_delete_clicked(self, _btn: Gtk.Button) -> None:
        self._on_delete(self._task)

    def _on_add_time(self, _btn: Gtk.Button) -> None:
        minutes = int(self._add_spin.get_value())
        self._on_time_added(self._task, minutes)


class TasksTab(Gtk.Box):
    """Tab for managing task budgets."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(12)
        self.set_margin_end(12)

        self._tasks: list[TaskBudget] = []
        self._rows: dict[str, TaskRow] = {}  # task.id -> TaskRow

        # ---- Add task bar ----
        add_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._name_entry = Gtk.Entry()
        self._name_entry.set_placeholder_text("Task name…")
        self._name_entry.set_hexpand(True)
        self._name_entry.connect("activate", self._on_add_clicked)

        self._minutes_spin = Gtk.SpinButton.new_with_range(1, 1440, 15)
        self._minutes_spin.set_value(60)
        self._minutes_spin.set_width_chars(4)

        add_btn = Gtk.Button(label="+ Add")
        add_btn.get_style_context().add_class("suggested-action")
        add_btn.connect("clicked", self._on_add_clicked)

        add_box.pack_start(self._name_entry, True, True, 0)
        add_box.pack_start(self._minutes_spin, False, False, 0)
        add_box.pack_start(add_btn, False, False, 0)
        self.pack_start(add_box, False, False, 0)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.pack_start(sep, False, False, 8)

        # ---- Scrollable task list ----
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(150)
        scroll.set_max_content_height(300)

        self._list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        scroll.add(self._list_box)
        self.pack_start(scroll, True, True, 0)

        self._empty_label = Gtk.Label(label="No tasks yet. Add one above.")
        self._empty_label.get_style_context().add_class("dim-label")
        self._list_box.pack_start(self._empty_label, False, False, 8)

        # Load persisted tasks
        self._load_tasks()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_tasks(self) -> None:
        """Load tasks from config and build the list."""
        raw = cfg.load_tasks()
        self._tasks = [TaskBudget.from_dict(d) for d in raw]
        self._rebuild_list()

    def _save_tasks(self) -> None:
        cfg.save_tasks([t.to_dict() for t in self._tasks])

    def _rebuild_list(self) -> None:
        """Remove all rows and rebuild from self._tasks."""
        for child in self._list_box.get_children():
            self._list_box.remove(child)
        self._rows.clear()

        if not self._tasks:
            self._list_box.pack_start(self._empty_label, False, False, 8)
            self._list_box.show_all()
            return

        for task in self._tasks:
            row = TaskRow(task, self._on_toggle, self._on_delete, self._on_time_added)
            self._rows[task.id] = row
            self._list_box.pack_start(row, False, False, 0)

        self._list_box.show_all()

    def _on_add_clicked(self, _widget) -> None:  # type: ignore[type-arg]
        name = self._name_entry.get_text().strip()
        if not name:
            return
        minutes = int(self._minutes_spin.get_value())
        task = TaskBudget(name=name, allocated_minutes=minutes)
        self._tasks.append(task)
        self._save_tasks()
        self._name_entry.set_text("")
        self._rebuild_list()

    def _on_toggle(self, task: TaskBudget) -> None:
        """Toggle a task's active state (only one can be active at a time)."""
        new_active = not task.is_active
        for t in self._tasks:
            t.is_active = False
        task.is_active = new_active
        self._save_tasks()
        self._rebuild_list()

    def _on_delete(self, task: TaskBudget) -> None:
        """Prompt and delete a task."""
        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),  # type: ignore[arg-type]
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Delete task '{task.name}'?",
        )
        dialog.format_secondary_text("This cannot be undone.")
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.YES:
            self._tasks = [t for t in self._tasks if t.id != task.id]
            self._save_tasks()
            self._rebuild_list()

    def _on_time_added(self, task: TaskBudget, minutes: int) -> None:
        """Add used minutes to a task."""
        for t in self._tasks:
            if t.id == task.id:
                t.used_minutes += minutes
                break
        self._save_tasks()
        self._rebuild_list()
