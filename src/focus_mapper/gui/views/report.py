"""Validation report view with filtering and sortable findings table."""

import tkinter as tk
from tkinter import ttk
import json
from pathlib import Path
from focus_mapper.gui.ui_utils import (
    set_tooltip,
    refresh_sort_headers,
    autosize_treeview_columns,
)


class ReportView(ttk.Frame):
    """Display validation summary and findings for one generation run."""
    def __init__(self, parent, app_context, report_path=None, report_data=None, back_view=None):
        super().__init__(parent)
        self.app = app_context
        self.report_data = report_data
        self.back_view = back_view
        
        if report_path and not self.report_data:
            try:
                with open(report_path, "r") as f:
                    self.report_data = json.load(f)
            except Exception as e:
                print(f"Error loading report: {e}")
        self._sort_state = {"col": "severity", "descending": False}
        self._base_headings = {
            "severity": "Severity",
            "column": "Column",
            "message": "Message",
            "rows": "Rows",
        }

        self._create_ui()
        self._populate_tree()

    def _create_ui(self):
        """Build report header, filters, and findings table."""
        # Header
        header = ttk.Frame(self)
        header.pack(fill="x", pady=10)
        back_btn = ttk.Button(header, text="Back", command=self.on_back)
        back_btn.pack(side="left")
        set_tooltip(back_btn, "Return to the previous generator results page.")
        ttk.Label(header, text="Validation Report", font=("Helvetica", 16, "bold")).pack(side="left", padx=20)

        # Summary
        if self.report_data and "summary" in self.report_data:
            s = self.report_data["summary"]
            total_rows = s.get("total_rows", self.report_data.get("total_rows", "?"))
            summary_text = f"Total Rows: {total_rows} | Errors: {s.get('errors', 0)} | Warnings: {s.get('warnings', 0)}"
            ttk.Label(self, text=summary_text).pack(anchor="w", padx=10)

        # Filters
        filter_frame = ttk.Frame(self)
        filter_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(filter_frame, text="Filter Severity:").pack(side="left")
        self.severity_var = tk.StringVar(value="All")
        self.severity_cb = ttk.Combobox(
            filter_frame,
            textvariable=self.severity_var,
            values=["All", "ERROR", "WARN", "INFO"],
            state="readonly",
        )
        self.severity_cb.pack(side="left", padx=5)
        self.severity_cb.bind("<<ComboboxSelected>>", lambda _e: self._populate_tree())
        set_tooltip(self.severity_cb, "Filter findings by severity.")

        # Findings Tree
        columns = ("severity", "column", "message", "rows")
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        self.tree.heading("severity", command=lambda: self._on_sort("severity"))
        self.tree.heading("column", command=lambda: self._on_sort("column"))
        self.tree.heading("message", command=lambda: self._on_sort("message"))
        self.tree.heading("rows", command=lambda: self._on_sort("rows"))
        
        self.tree.column("severity", width=80)
        self.tree.column("column", width=150)
        self.tree.column("message", width=400)
        self.tree.column("rows", width=100)
        set_tooltip(self.tree, "Validation findings table. Click a header to sort.")

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Tag configuration for colors
        self.tree.tag_configure("ERROR", background="#ffdddd")
        self.tree.tag_configure("WARN", background="#ffffdd")
        self.tree.tag_configure("INFO", background="#ddeeff")
        self._refresh_sort_headers()

    def _populate_tree(self):
        """Populate findings table from report data and active filters/sort."""
        # Clear
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        if not self.report_data or "findings" not in self.report_data:
            return

        sev_filter = self.severity_var.get()
        
        findings = list(self.report_data["findings"])
        findings.sort(key=self._sort_key_for_finding, reverse=self._sort_state["descending"])

        for f in findings:
            severity = f.get("severity", "INFO")
            
            if sev_filter != "All" and severity != sev_filter:
                continue
                
            col = f.get("column", "-")
            msg = f.get("message", "")
            rows = self._rows_text(f)
            
            self.tree.insert("", "end", values=(severity, col, msg, rows), tags=(severity,))
        self._autosize_columns()

    def _rows_text(self, finding):
        """Render row-count cell text from finding payload."""
        if "failing_rows" in finding and finding.get("failing_rows") is not None:
            return str(finding.get("failing_rows"))
        if "rows" in finding:
            return str(finding.get("rows"))
        return "-"

    def _on_sort(self, col):
        """Toggle sorting on a table column."""
        if self._sort_state["col"] == col:
            self._sort_state["descending"] = not self._sort_state["descending"]
        else:
            # Severity default order is ERROR -> WARN -> INFO
            self._sort_state = {"col": col, "descending": False}
        self._refresh_sort_headers()
        self._populate_tree()

    def _refresh_sort_headers(self):
        """Refresh sort arrow indicator in table headers."""
        state = {
            self._sort_state["col"]: self._sort_state["descending"],
        }
        refresh_sort_headers(self.tree, self._base_headings, state)

    def _sort_key_for_finding(self, finding):
        """Return sortable key for current sort column."""
        col = self._sort_state["col"]
        if col == "severity":
            rank = {"ERROR": 0, "WARN": 1, "INFO": 2}
            return rank.get(finding.get("severity", "INFO"), 99)
        if col == "column":
            return str(finding.get("column", "")).lower()
        if col == "message":
            return str(finding.get("message", "")).lower()
        if col == "rows":
            if finding.get("failing_rows") is not None:
                return int(finding.get("failing_rows"))
            rows_val = finding.get("rows")
            if isinstance(rows_val, list):
                return len(rows_val)
            try:
                return int(rows_val)
            except Exception:
                return 0
        return 0

    def _autosize_columns(self):
        """Auto-size findings table columns with conservative bounds."""
        bounds = {
            "severity": (80, 130),
            "column": (120, 280),
            "message": (220, 680),
            "rows": (80, 180),
        }
        min_widths = {k: v[0] for k, v in bounds.items()}
        max_widths = {k: v[1] for k, v in bounds.items()}
        autosize_treeview_columns(self.tree, self._base_headings, min_widths, max_widths)

    def on_back(self):
        """Return to previous view if retained, otherwise open generator view."""
        if self.back_view is not None and self.back_view.winfo_exists():
            self.destroy()
            self.app.current_view = self.back_view
            self.back_view.pack(fill="both", expand=True)
            return
        self.app.show_generator_view()
