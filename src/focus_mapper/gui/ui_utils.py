"""Shared Tkinter UI helpers for tooltips and table interactions."""

from __future__ import annotations

from datetime import date, datetime, timezone
import math
import re
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont
from typing import Callable


class WidgetTooltip:
    """Small hover tooltip bound to a Tk widget."""
    def __init__(self, widget):
        """Create tooltip controller for one widget."""
        self.widget = widget
        self.tip = None
        self.label = None

    def show(self, text: str):
        """Show tooltip content near the widget."""
        if not text:
            self.hide()
            return
        if self.tip is None:
            self.tip = tk.Toplevel(self.widget)
            self.tip.wm_overrideredirect(True)
            self.tip.attributes("-topmost", True)
            self.label = ttk.Label(self.tip, text=text, padding=6, background="#ffffe0")
            self.label.pack()
        else:
            self.label.config(text=text)
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip.geometry(f"+{x}+{y}")

    def hide(self):
        """Hide tooltip window if it exists."""
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None
            self.label = None


def set_tooltip(widget, text: str):
    """Attach/update a tooltip for a widget."""
    if not text:
        return
    if not hasattr(widget, "_tooltip"):
        widget._tooltip = WidgetTooltip(widget)
        widget.bind("<Enter>", lambda _e, w=widget: w._tooltip.show(getattr(w, "_tooltip_text", "")))
        widget.bind("<Leave>", lambda _e, w=widget: w._tooltip.hide())
    widget._tooltip_text = text


def refresh_sort_headers(tree: ttk.Treeview, base_headings: dict[str, str], sort_state: dict[str, bool]):
    """Render sort arrow indicators in tree headers from sort state."""
    arrow_up = " ▲"
    arrow_down = " ▼"
    for col, label in base_headings.items():
        if sort_state.get(col) is None:
            tree.heading(col, text=label)
        else:
            tree.heading(col, text=label + (arrow_down if sort_state[col] else arrow_up))


def sort_tree_items(
    tree: ttk.Treeview,
    column: str,
    sort_state: dict[str, bool],
    key_func: Callable[[str], object] | None = None,
) -> dict[str, bool]:
    """Sort Treeview rows by one column and return updated sort state."""
    items = [(tree.set(iid, column), iid) for iid in tree.get_children("")]
    # First click should sort ascending; subsequent clicks toggle.
    current = sort_state.get(column)
    reverse = False if current is None else (not current)
    key = key_func or (lambda v: str(v).lower())
    items.sort(key=lambda v: key(v[0]), reverse=reverse)
    for idx, (_, iid) in enumerate(items):
        tree.move(iid, "", idx)
    return {column: reverse}


def autosize_treeview_columns(
    tree: ttk.Treeview,
    base_headings: dict[str, str],
    min_widths: dict[str, int],
    max_widths: dict[str, int],
    *,
    value_getter: Callable[[str, str], str] | None = None,
):
    """Auto-size Treeview columns to content within provided min/max widths."""
    font = tkfont.nametofont("TkDefaultFont")
    get_value = value_getter or (lambda iid, col: str(tree.set(iid, col)))
    for col, label in base_headings.items():
        width = font.measure(label) + 20
        for iid in tree.get_children(""):
            width = max(width, font.measure(str(get_value(iid, col))) + 20)
            if width >= max_widths[col]:
                width = max_widths[col]
                break
        tree.column(col, width=max(min_widths[col], min(width, max_widths[col])))


def make_combobox_filterable(combobox: ttk.Combobox, values: list[str]):
    """Enable type-to-filter behavior for a combobox value list."""
    all_values = [str(v) for v in values]
    combobox["values"] = all_values
    # Readonly comboboxes block typing, so switch to normal for filtering.
    if str(combobox.cget("state")) == "readonly":
        combobox.configure(state="normal")

    def _on_keyrelease(event=None):
        if event is not None and event.keysym in {"Up", "Down", "Left", "Right", "Escape"}:
            return
        typed = combobox.get()
        needle = typed.strip().lower()
        if not needle:
            filtered = all_values
        else:
            # Prefix match to narrow to likely source column names quickly.
            filtered = [item for item in all_values if item.lower().startswith(needle)]

        combobox["values"] = filtered
        # Keep user-typed text stable after replacing values.
        combobox.delete(0, "end")
        combobox.insert(0, typed)
        combobox.icursor("end")

        # Auto-open dropdown while typing so users can pick immediately.
        if needle and filtered:
            def _open_dropdown():
                try:
                    combobox.tk.call("ttk::combobox::Post", str(combobox))
                    return
                except Exception:
                    pass
                try:
                    combobox.event_generate("<Down>")
                except Exception:
                    pass
            combobox.after_idle(_open_dropdown)

    combobox.bind("<KeyRelease>", _on_keyrelease, add="+")
    return combobox


_DATETIME_LIKE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ].+)?$")


def format_datetime_utc_z(value) -> str | None:
    """Return datetime formatted as `YYYY-MM-DDTHH:MM:SSZ` when possible."""
    dt_obj: datetime | None = None

    if isinstance(value, datetime):
        dt_obj = value
    elif isinstance(value, date):
        dt_obj = datetime(value.year, value.month, value.day)
    else:
        try:
            import pandas as pd  # type: ignore
            if isinstance(value, pd.Timestamp):
                dt_obj = value.to_pydatetime()
        except Exception:
            pass

    if dt_obj is None and isinstance(value, str):
        raw = value.strip()
        if not raw or not _DATETIME_LIKE_RE.match(raw):
            return None
        try:
            import pandas as pd  # type: ignore
            parsed = pd.to_datetime(raw, utc=True, errors="raise")
            return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            try:
                iso = raw.replace("Z", "+00:00")
                dt_obj = datetime.fromisoformat(iso)
            except Exception:
                return None

    if dt_obj is None:
        return None
    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=timezone.utc)
    else:
        dt_obj = dt_obj.astimezone(timezone.utc)
    return dt_obj.strftime("%Y-%m-%dT%H:%M:%SZ")


def format_value_for_display(value) -> str:
    """Format UI cell value with normalized datetime rendering where applicable."""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    dt_text = format_datetime_utc_z(value)
    if dt_text is not None:
        return dt_text
    return str(value)
