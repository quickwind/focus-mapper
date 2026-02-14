from focus_mapper.gui import ui_utils


class _FakeTree:
    def __init__(self):
        self._rows = {}
        self._order = []
        self._headings = {}
        self._columns = {}

    def add_row(self, iid, values):
        self._rows[iid] = dict(values)
        self._order.append(iid)

    def set(self, iid, column):
        return self._rows[iid].get(column, "")

    def get_children(self, _parent=""):
        return list(self._order)

    def move(self, iid, _parent, index):
        self._order.remove(iid)
        self._order.insert(index, iid)

    def heading(self, col, text=None):
        if text is not None:
            self._headings[col] = text
        return self._headings.get(col, "")

    def column(self, col, width=None):
        if width is not None:
            self._columns[col] = int(width)
        return {"width": self._columns.get(col, 0)}


class _FakeFont:
    def measure(self, text):
        return len(str(text)) * 7


def test_sort_tree_items_first_click_ascending_then_descending():
    tree = _FakeTree()
    tree.add_row("1", {"name": "b"})
    tree.add_row("2", {"name": "a"})

    state = ui_utils.sort_tree_items(tree, "name", {})
    assert tree.get_children("") == ["2", "1"]
    assert state == {"name": False}

    state = ui_utils.sort_tree_items(tree, "name", state)
    assert tree.get_children("") == ["1", "2"]
    assert state == {"name": True}


def test_refresh_sort_headers_sets_arrow_text():
    tree = _FakeTree()
    ui_utils.refresh_sort_headers(tree, {"name": "Name"}, {"name": False})
    assert tree.heading("name") == "Name ▲"
    ui_utils.refresh_sort_headers(tree, {"name": "Name"}, {"name": True})
    assert tree.heading("name") == "Name ▼"


def test_autosize_treeview_columns_clamps_bounds(monkeypatch):
    monkeypatch.setattr(ui_utils.tkfont, "nametofont", lambda _name: _FakeFont())
    tree = _FakeTree()
    tree.add_row("1", {"col": "x"})
    tree.add_row("2", {"col": "y" * 200})

    ui_utils.autosize_treeview_columns(
        tree,
        base_headings={"col": "Column"},
        min_widths={"col": 80},
        max_widths={"col": 220},
    )
    width = tree.column("col")["width"]
    assert 80 <= width <= 220
