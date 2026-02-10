import tkinter as tk
from tkinter import ttk
import json
from pathlib import Path

class ReportView(ttk.Frame):
    def __init__(self, parent, app_context, report_path=None, report_data=None):
        super().__init__(parent)
        self.app = app_context
        self.report_data = report_data
        
        if report_path and not self.report_data:
            try:
                with open(report_path, "r") as f:
                    self.report_data = json.load(f)
            except Exception as e:
                print(f"Error loading report: {e}")

        self._create_ui()
        self._populate_tree()

    def _create_ui(self):
        # Header
        header = ttk.Frame(self)
        header.pack(fill="x", pady=10)
        ttk.Button(header, text="Back", command=self.on_back).pack(side="left")
        ttk.Label(header, text="Validation Report", font=("Helvetica", 16, "bold")).pack(side="left", padx=20)

        # Summary
        if self.report_data and "summary" in self.report_data:
            s = self.report_data["summary"]
            summary_text = f"Total Rows: {s.get('total_rows', '?')} | Errors: {s.get('errors', 0)} | Warnings: {s.get('warnings', 0)}"
            ttk.Label(self, text=summary_text).pack(anchor="w", padx=10)

        # Filters
        filter_frame = ttk.Frame(self)
        filter_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(filter_frame, text="Filter Severity:").pack(side="left")
        self.severity_var = tk.StringVar(value="All")
        ttk.Combobox(filter_frame, textvariable=self.severity_var, values=["All", "ERROR", "WARN", "INFO"], state="readonly").pack(side="left", padx=5)
        ttk.Button(filter_frame, text="Apply", command=self._populate_tree).pack(side="left")

        # Findings Tree
        columns = ("severity", "column", "message", "rows")
        self.tree = ttk.Treeview(self, columns=columns, show="headings")
        self.tree.heading("severity", text="Severity")
        self.tree.heading("column", text="Column")
        self.tree.heading("message", text="Message")
        self.tree.heading("rows", text="Rows")
        
        self.tree.column("severity", width=80)
        self.tree.column("column", width=150)
        self.tree.column("message", width=400)
        self.tree.column("rows", width=100)

        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)
        scrollbar.pack(side="right", fill="y")
        
        # Tag configuration for colors
        self.tree.tag_configure("ERROR", background="#ffdddd")
        self.tree.tag_configure("WARN", background="#ffffdd")
        self.tree.tag_configure("INFO", background="#ddeeff")

    def _populate_tree(self):
        # Clear
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        if not self.report_data or "findings" not in self.report_data:
            return

        sev_filter = self.severity_var.get()
        
        for f in self.report_data["findings"]:
            severity = f.get("severity", "INFO")
            
            if sev_filter != "All" and severity != sev_filter:
                continue
                
            col = f.get("column", "-")
            msg = f.get("message", "")
            rows = str(f.get("rows", []))
            
            self.tree.insert("", "end", values=(severity, col, msg, rows), tags=(severity,))

    def on_back(self):
        # Go back to Generator view? or just close if it was a popup?
        # Assuming we replace content, ask app to show generator
        self.app.show_generator_view()
