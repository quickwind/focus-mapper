import os
import tkinter as tk

import pytest

from focus_mapper.gui.views.report import ReportView

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_GUI_TESTS") != "1",
    reason="GUI tests are opt-in. Set RUN_GUI_TESTS=1 to run.",
)


class _DummyApp:
    def __init__(self, content_frame):
        self.content_frame = content_frame
        self.current_view = None
        self.generator_called = False

    def show_generator_view(self):
        self.generator_called = True


@pytest.fixture()
def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available in this environment: {exc}")
    root.withdraw()
    yield root
    root.destroy()


def _sample_report():
    return {
        "summary": {"errors": 1, "warnings": 1, "total_rows": 10},
        "findings": [
            {"severity": "WARN", "column": "B", "message": "warn", "failing_rows": 2},
            {"severity": "ERROR", "column": "A", "message": "err", "failing_rows": 3},
            {"severity": "INFO", "column": "C", "message": "info", "failing_rows": 1},
        ],
    }


def test_report_default_severity_sort_and_filter(tk_root):
    frame = tk.Frame(tk_root)
    frame.pack()
    app = _DummyApp(frame)
    view = ReportView(frame, app, report_data=_sample_report())
    view.pack()

    rows = [view.tree.set(iid, "severity") for iid in view.tree.get_children("")]
    assert rows[0] == "ERROR"
    assert rows[1] == "WARN"
    assert rows[2] == "INFO"
    assert view.tree.heading("severity", option="text").endswith("▲")

    view.severity_var.set("WARN")
    view._populate_tree()
    rows = [view.tree.set(iid, "severity") for iid in view.tree.get_children("")]
    assert rows == ["WARN"]


def test_report_back_uses_back_view_if_provided(tk_root):
    frame = tk.Frame(tk_root)
    frame.pack()
    app = _DummyApp(frame)
    back_view = tk.Frame(frame)
    view = ReportView(frame, app, report_data=_sample_report(), back_view=back_view)
    view.pack()

    view.on_back()
    assert app.current_view is back_view
    assert not app.generator_called
