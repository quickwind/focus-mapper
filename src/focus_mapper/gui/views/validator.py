"""Dataset validation view with logs and report navigation."""

import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from focus_mapper.api import validate
from focus_mapper.gui.ui_utils import set_tooltip
from focus_mapper.spec import list_available_spec_versions


class ValidatorView(ttk.Frame):
    """Validator screen to run validation on existing FOCUS datasets."""

    def __init__(self, parent, app_context):
        """Initialize validator view state and widgets."""
        super().__init__(parent)
        self.app = app_context
        self.mappings_dir = Path.home() / ".focus_mapper" / "mappings"
        self._last_report = None
        self._create_ui()

    def _create_ui(self):
        """Create validation form, logs, and progress bar."""
        ttk.Label(self, text="Validate FOCUS Dataset", font=("Helvetica", 16, "bold")).pack(anchor="w", pady=(0, 20))

        form = ttk.Frame(self)
        form.pack(fill="x", padx=10)

        ttk.Label(form, text="Input Data (CSV/Parquet):").grid(row=0, column=0, sticky="w", pady=5)
        self.input_entry = ttk.Entry(form, width=56)
        self.input_entry.grid(row=0, column=1, sticky="ew", padx=5)
        set_tooltip(self.input_entry, "FOCUS dataset file to validate.")
        input_btn = ttk.Button(form, text="Browse...", command=self.browse_input)
        input_btn.grid(row=0, column=2)
        set_tooltip(input_btn, "Choose the input data file.")

        ttk.Label(form, text="Spec Version:").grid(row=1, column=0, sticky="w", pady=5)
        self.spec_var = tk.StringVar(value="v1.3")
        self.spec_cb = ttk.Combobox(form, textvariable=self.spec_var, state="readonly", width=53)
        self.spec_cb.grid(row=1, column=1, sticky="ew", padx=5)
        set_tooltip(self.spec_cb, "FOCUS spec version used for validation.")
        self._populate_spec_versions()

        ttk.Label(form, text="Mapping Config (optional):").grid(row=2, column=0, sticky="w", pady=5)
        self.mapping_var = tk.StringVar()
        self.mapping_cb = ttk.Combobox(form, textvariable=self.mapping_var, width=53, state="readonly")
        self.mapping_cb.grid(row=2, column=1, sticky="ew", padx=5)
        set_tooltip(self.mapping_cb, "Optional mapping YAML for validation overrides.")
        self._populate_mappings()

        ttk.Label(form, text="Validation Report Out (optional):").grid(row=3, column=0, sticky="w", pady=5)
        self.report_out_entry = ttk.Entry(form, width=56)
        self.report_out_entry.grid(row=3, column=1, sticky="ew", padx=5)
        set_tooltip(self.report_out_entry, "Optional path to write validation report JSON.")
        report_out_btn = ttk.Button(form, text="Browse...", command=self.browse_report_out)
        report_out_btn.grid(row=3, column=2)
        set_tooltip(report_out_btn, "Choose validation report output file.")

        form.columnconfigure(1, weight=1)

        self.validate_btn = ttk.Button(self, text="Validate Dataset", command=self.on_validate)
        self.validate_btn.pack(pady=12)
        set_tooltip(self.validate_btn, "Run validation using the selected options.")

        self.view_report_btn = ttk.Button(self, text="View Validation Report", command=self.open_last_report)
        self.view_report_btn.pack(pady=(0, 8))
        self.view_report_btn.config(state="disabled")
        set_tooltip(self.view_report_btn, "Open findings from the latest validation run.")

        ttk.Label(self, text="Logs:").pack(anchor="w", padx=10)
        self.log_text = tk.Text(self, height=14, state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        set_tooltip(self.log_text, "Validation logs and status messages.")

        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.pack(fill="x", padx=10, pady=(0, 10))
        set_tooltip(self.progress, "Validation progress indicator.")

    def _populate_spec_versions(self):
        """Load available spec versions into the selector."""
        versions = ["v1.3", "v1.2", "v1.1"]
        try:
            versions = sorted(
                list_available_spec_versions(spec_dir=self.app.get_setting("spec_dir")),
                reverse=True,
            )
        except Exception:
            pass
        self.spec_cb["values"] = versions
        if versions:
            self.spec_var.set("v1.3" if "v1.3" in versions else versions[0])

    def _populate_mappings(self):
        """Load available mappings into the optional selector."""
        if not self.mappings_dir.exists():
            self.mapping_cb["values"] = []
            return
        files = sorted(f.name for f in self.mappings_dir.glob("*.yaml"))
        self.mapping_cb["values"] = [""] + files
        self.mapping_var.set("")

    def browse_input(self):
        """Select input dataset path."""
        path = filedialog.askopenfilename(
            filetypes=[("Data files", "*.csv *.parquet"), ("All files", "*.*")],
            parent=self,
        )
        if path:
            self.input_entry.delete(0, "end")
            self.input_entry.insert(0, path)

    def browse_report_out(self):
        """Select optional report output path."""
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
            parent=self,
        )
        if path:
            self.report_out_entry.delete(0, "end")
            self.report_out_entry.insert(0, path)

    def log(self, message):
        """Append one line to logs panel."""
        self.log_text.config(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def on_validate(self):
        """Validate inputs and launch background validation task."""
        input_path = self.input_entry.get().strip()
        spec_version = self.spec_var.get().strip()
        mapping_name = self.mapping_var.get().strip()
        report_out = self.report_out_entry.get().strip()

        if not input_path:
            messagebox.showwarning("Missing Info", "Please provide an input dataset.", parent=self)
            return
        if not spec_version:
            messagebox.showwarning("Missing Info", "Please select a spec version.", parent=self)
            return

        mapping_path = None
        if mapping_name:
            mapping_path = self.mappings_dir / mapping_name
            if not mapping_path.exists():
                messagebox.showerror("Error", f"Mapping file not found: {mapping_path}", parent=self)
                return

        self.validate_btn.config(state="disabled")
        self.view_report_btn.config(state="disabled")
        self._last_report = None
        self.progress.start(10)
        self.log(f"Starting validation with spec {spec_version}...")

        thread = threading.Thread(
            target=self._run_validation,
            args=(input_path, spec_version, mapping_path, report_out),
            daemon=True,
        )
        thread.start()

    def _run_validation(self, input_path, spec_version, mapping_path, report_out):
        """Worker thread body for validation."""
        try:
            spec_dir = self.app.get_setting("spec_dir", None)
            report = validate(
                data=input_path,
                spec_version=spec_version,
                spec_dir=spec_dir or None,
                mapping=str(mapping_path) if mapping_path else None,
                output_path=report_out or None,
                write_report=bool(report_out),
            )
            self.after(0, self._on_success, report)
        except Exception as exc:
            trace = traceback.format_exc()
            self.after(0, self._on_error, str(exc), trace)

    def _on_success(self, report):
        """Handle successful validation on UI thread."""
        self.progress.stop()
        self.validate_btn.config(state="normal")
        self._last_report = report
        self.view_report_btn.config(state="normal")
        errors = int(getattr(report.summary, "errors", 0))
        warnings = int(getattr(report.summary, "warnings", 0))
        self.log(f"Validation complete. Errors: {errors}, Warnings: {warnings}")
        if errors > 0:
            messagebox.showwarning("Validation Complete", f"Validation finished with {errors} error(s).", parent=self)
        else:
            messagebox.showinfo("Validation Complete", "Validation passed with no errors.", parent=self)

    def _on_error(self, error_msg, trace):
        """Handle validation failure on UI thread."""
        self.progress.stop()
        self.validate_btn.config(state="normal")
        self.view_report_btn.config(state="disabled")
        self.log(f"Error: {error_msg}")
        print(trace)
        messagebox.showerror("Validation Failed", error_msg, parent=self)

    def open_last_report(self):
        """Open report view for the latest validation result."""
        if self._last_report is None:
            messagebox.showwarning("No Report", "Run validation first.", parent=self)
            return

        data = None
        if hasattr(self._last_report, "to_dict") and callable(self._last_report.to_dict):
            data = self._last_report.to_dict()
        else:
            try:
                data = self._last_report.model_dump()
            except AttributeError:
                try:
                    data = self._last_report.dict()
                except AttributeError:
                    if isinstance(self._last_report, dict):
                        data = self._last_report

        if not isinstance(data, dict):
            messagebox.showerror("Error", "Unable to open validation report due to serialization failure.", parent=self)
            return
        self.app.show_report_view(data, back_view=self)
