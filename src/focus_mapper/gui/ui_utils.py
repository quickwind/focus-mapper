"""Shared Tkinter UI helpers for tooltips and table interactions."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont
from typing import Callable


class WidgetTooltip:
    """Small hover tooltip bound to a Tk widget."""
    def __init__(self, widget):
        self.widget = widget
        self.tip = None
        self.label = None

    def show(self, text: str):
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
