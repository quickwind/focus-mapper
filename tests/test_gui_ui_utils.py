import os
import tkinter as tk
from tkinter import ttk

import pytest

from focus_mapper.gui.ui_utils import (
    autosize_treeview_columns,
    refresh_sort_headers,
    set_tooltip,
    sort_tree_items,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_GUI_TESTS") != "1",
    reason="GUI tests are opt-in. Set RUN_GUI_TESTS=1 to run.",
)


@pytest.fixture()
def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available in this environment: {exc}")
    root.withdraw()
    yield root
    root.destroy()


def test_set_tooltip_attaches_tooltip(tk_root):
    btn = ttk.Button(tk_root, text="x")
    set_tooltip(btn, "Hello")
    assert hasattr(btn, "_tooltip")
    assert getattr(btn, "_tooltip_text") == "Hello"


def test_sort_tree_items_and_refresh_headers(tk_root):
    tree = ttk.Treeview(tk_root, columns=("name",), show="headings")
    tree.heading("name", text="Name")
    tree.insert("", "end", values=("b",))
    tree.insert("", "end", values=("a",))

    state = {}
    state = sort_tree_items(tree, "name", state)
    refresh_sort_headers(tree, {"name": "Name"}, state)
    items = [tree.set(iid, "name") for iid in tree.get_children("")]
    assert items == ["a", "b"]
    assert tree.heading("name", option="text").endswith("▲")

    state = sort_tree_items(tree, "name", state)
    refresh_sort_headers(tree, {"name": "Name"}, state)
    items = [tree.set(iid, "name") for iid in tree.get_children("")]
    assert items == ["b", "a"]
    assert tree.heading("name", option="text").endswith("▼")


def test_autosize_treeview_columns_respects_bounds(tk_root):
    tree = ttk.Treeview(tk_root, columns=("col",), show="headings")
    tree.heading("col", text="Column")
    tree.insert("", "end", values=("short",))
    tree.insert("", "end", values=("x" * 1000,))

    autosize_treeview_columns(
        tree,
        base_headings={"col": "Column"},
        min_widths={"col": 80},
        max_widths={"col": 220},
    )
    width = int(tree.column("col", option="width"))
    assert 80 <= width <= 220
