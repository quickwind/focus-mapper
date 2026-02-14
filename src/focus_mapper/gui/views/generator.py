"""Dataset generation view with preview, logs, and report navigation."""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter import font as tkfont
from pathlib import Path
import threading
import traceback

from focus_mapper.api import generate
from focus_mapper.gui.ui_utils import set_tooltip, refresh_sort_headers, sort_tree_items


class GeneratorView(ttk.Frame):
    """Generator screen to run mapping and inspect output preview."""
    def __init__(self, parent, app_context):
        """Initialize generator view state and widgets."""
        super().__init__(parent)
        self.app = app_context
        self.mappings_dir = Path.home() / ".focus_mapper" / "mappings"
        self._preview_sort_state = {}
        self._preview_base_headings = {}
        self._create_ui()

    def _create_ui(self):
        """Create generation form, preview table, logs, and progress bar."""
        # Header
        ttk.Label(self, text="Generate FOCUS Dataset", font=("Helvetica", 16, "bold")).pack(anchor="w", pady=(0, 20))

        # Form Container
        form = ttk.Frame(self)
        form.pack(fill="x", padx=10)

        # 1. Input Source
        ttk.Label(form, text="Input Data (CSV/Parquet):").grid(row=0, column=0, sticky="w", pady=5)
        self.input_entry = ttk.Entry(form, width=50)
        self.input_entry.grid(row=0, column=1, sticky="ew", padx=5)
        set_tooltip(self.input_entry, "Source dataset path (.csv or .parquet).")
        input_btn = ttk.Button(form, text="Browse...", command=self.browse_input)
        input_btn.grid(row=0, column=2)
        set_tooltip(input_btn, "Choose input data file.")

        # 2. Mapping Configuration
        ttk.Label(form, text="Mapping Config:").grid(row=1, column=0, sticky="w", pady=5)
        self.mapping_var = tk.StringVar()
        self.mapping_cb = ttk.Combobox(form, textvariable=self.mapping_var, width=47, state="readonly")
        self.mapping_cb.grid(row=1, column=1, sticky="ew", padx=5)
        set_tooltip(self.mapping_cb, "Select mapping YAML to apply.")
        self._populate_mappings()
        
        # 3. Output Path
        ttk.Label(form, text="Output File:").grid(row=2, column=0, sticky="w", pady=5)
        self.output_entry = ttk.Entry(form, width=50)
        self.output_entry.grid(row=2, column=1, sticky="ew", padx=5)
        set_tooltip(self.output_entry, "Destination output file path.")
        output_btn = ttk.Button(form, text="Browse...", command=self.browse_output)
        output_btn.grid(row=2, column=2)
        set_tooltip(output_btn, "Choose output path (.csv or .parquet).")

        form.columnconfigure(1, weight=1)

        # Action Button
        self.generate_btn = ttk.Button(self, text="Generate Dataset", command=self.on_generate)
        self.generate_btn.pack(pady=12)
        set_tooltip(self.generate_btn, "Run generation using selected input/mapping.")

        # Preview Area
        ttk.Label(self, text="Result Preview (first 100 rows):").pack(anchor="w", padx=10, pady=(0, 4))
        preview_frame = ttk.Frame(self)
        preview_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.preview_tree = ttk.Treeview(preview_frame, show="headings", height=12)
        self.preview_tree.pack(side="left", fill="both", expand=True)
        set_tooltip(self.preview_tree, "Preview of generated output. Click a header to sort.")
        preview_y = ttk.Scrollbar(preview_frame, orient="vertical", command=self.preview_tree.yview)
        preview_y.pack(side="right", fill="y")
        preview_x = ttk.Scrollbar(self, orient="horizontal", command=self.preview_tree.xview)
        preview_x.pack(fill="x", padx=10, pady=(0, 8))
        self.preview_tree.configure(yscrollcommand=preview_y.set, xscrollcommand=preview_x.set)

        # Logs
        ttk.Label(self, text="Logs:").pack(anchor="w", padx=10)
        self.log_text = tk.Text(self, height=8, state="disabled")
        self.log_text.pack(fill="both", expand=False, padx=10, pady=(0, 8))
        set_tooltip(self.log_text, "Generation logs and status messages.")

        # Progress
        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.pack(fill="x", padx=10, pady=(0, 10))
        set_tooltip(self.progress, "Generation progress indicator.")

    def _populate_mappings(self):
        """Load available mapping YAML files into the mapping selector."""
        if not self.mappings_dir.exists():
            return
        files = [f.name for f in self.mappings_dir.glob("*.yaml")]
        self.mapping_cb['values'] = files
        if files:
            self.mapping_cb.current(0)

    def browse_input(self):
        """Select input data file path."""
        f = filedialog.askopenfilename(filetypes=[("Data files", "*.csv *.parquet"), ("All files", "*.*")], parent=self)
        if f:
            self.input_entry.delete(0, "end")
            self.input_entry.insert(0, f)

    def browse_output(self):
        """Select output file path."""
        f = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv"), ("Parquet", "*.parquet")], parent=self)
        if f:
            self.output_entry.delete(0, "end")
            self.output_entry.insert(0, f)

    def log(self, message):
        """Append one line to logs panel."""
        self.log_text.config(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def on_generate(self):
        """Validate inputs and launch background generation task."""
        input_path = self.input_entry.get()
        mapping_name = self.mapping_var.get()
        output_path = self.output_entry.get()

        if not all([input_path, mapping_name, output_path]):
            messagebox.showwarning("Missing Info", "Please provide Input, Mapping, and Output.", parent=self)
            return

        mapping_path = self.mappings_dir / mapping_name
        if not mapping_path.exists():
             messagebox.showerror("Error", f"Mapping file not found: {mapping_path}", parent=self)
             return

        self.generate_btn.config(state="disabled")
        self.progress.start(10)
        self.log("Starting generation (spec version comes from mapping config)...")
        self._clear_preview()

        # Run in thread
        thread = threading.Thread(target=self._run_generation, args=(input_path, mapping_path, output_path), daemon=True)
        thread.start()

    def _run_generation(self, input_path, mapping_path, output_path):
        """Worker thread body for dataset generation."""
        try:
            spec_dir = self.app.get_setting("spec_dir", None)
            result = generate(
                input_data=input_path,
                mapping=str(mapping_path),
                output_path=output_path,
                spec_dir=spec_dir or None,
            )
            
            self.after(0, self._on_success, result)
        except Exception as e:
            trace = traceback.format_exc()
            self.after(0, self._on_error, str(e), trace)

    def _on_success(self, result):
        """Handle successful generation on UI thread."""
        self.progress.stop()
        self.generate_btn.config(state="normal")
        self._show_preview(result.output_df)
        
        if result.is_valid:
            self.log(f"Success! Generated {len(result.output_df)} rows.")
            messagebox.showinfo("Success", "Dataset generated successfully.", parent=self)
        else:
            self.log(f"Generated with validation errors.")
            self.log(f"Errors: {result.validation.summary.errors}")
            messagebox.showwarning("Validation Issues", "Dataset generated but has validation errors. Check logs/report.", parent=self)
            
        # Show Report Button
        if hasattr(self, 'view_report_btn'):
            self.view_report_btn.destroy()
            
        self.view_report_btn = ttk.Button(self, text="View Validation Report", 
                                          command=lambda: self.open_report(result.validation, len(result.output_df)))
        self.view_report_btn.pack(pady=10)
        set_tooltip(self.view_report_btn, "Open validation findings for this generation result.")

    def open_report(self, validation_report, total_rows=None):
        """Serialize report data and open report view."""
        data = None
        if hasattr(validation_report, "to_dict") and callable(validation_report.to_dict):
            data = validation_report.to_dict()
        else:
            try:
                data = validation_report.model_dump()
            except AttributeError:
                try:
                    data = validation_report.dict()
                except AttributeError:
                    if isinstance(validation_report, dict):
                        data = validation_report
        if not isinstance(data, dict):
            messagebox.showerror("Error", "Unable to open validation report due to serialization failure.", parent=self)
            return
        if total_rows is not None:
            data["total_rows"] = int(total_rows)
            if isinstance(data.get("summary"), dict) and "total_rows" not in data["summary"]:
                data["summary"]["total_rows"] = int(total_rows)

        self.app.show_report_view(data, back_view=self)

    def _clear_preview(self):
        """Reset preview table content and sort state."""
        for item in self.preview_tree.get_children():
            self.preview_tree.delete(item)
        self.preview_tree["columns"] = ()
        self._preview_sort_state = {}
        self._preview_base_headings = {}

    def _show_preview(self, df):
        """Render first 100 rows into preview table."""
        self._clear_preview()
        if df is None or df.empty:
            return

        preview_df = df.head(100).copy()
        index_col = "__row_index__"
        columns = [index_col] + [str(c) for c in preview_df.columns]
        self.preview_tree["columns"] = columns
        self._preview_base_headings = {col: ("#" if col == index_col else col) for col in columns}
        for col in columns:
            self.preview_tree.heading(col, text="#" if col == index_col else col, command=lambda c=col: self._sort_preview(c))
            self.preview_tree.column(col, anchor="e" if col == index_col else "w", stretch=False)

        for idx, row in enumerate(preview_df.itertuples(index=False, name=None), start=1):
            values = [idx]
            values.extend("" if v is None else str(v) for v in row)
            self.preview_tree.insert("", "end", values=values)
        self._autosize_preview_columns(preview_df, columns, index_col)
        self._refresh_preview_sort_headers()

    def _sort_preview(self, column: str):
        """Sort preview table by clicked header column."""
        self._preview_sort_state = sort_tree_items(self.preview_tree, column, self._preview_sort_state)
        self._refresh_preview_sort_headers()

    def _refresh_preview_sort_headers(self):
        """Update preview header arrows for active sort."""
        refresh_sort_headers(self.preview_tree, self._preview_base_headings, self._preview_sort_state)

    def _autosize_preview_columns(self, preview_df, columns, index_col):
        """Auto-fit preview columns to content using min/max limits."""
        min_width = 80
        max_width = 420
        padding = 20
        font = tkfont.nametofont("TkDefaultFont")

        for col in columns:
            header = "#" if col == index_col else col
            width = font.measure(header) + padding
            if col == index_col:
                width = max(width, 60)
                self.preview_tree.column(col, width=min(width, 90))
                continue

            series = preview_df[col] if col in preview_df.columns else []
            for val in series:
                text = "" if val is None else str(val)
                candidate = font.measure(text) + padding
                if candidate > width:
                    width = candidate
                if width >= max_width:
                    width = max_width
                    break

            width = max(min_width, min(width, max_width))
            self.preview_tree.column(col, width=width)

    def _on_error(self, error_msg, trace):
        """Handle generation failure on UI thread."""
        self.progress.stop()
        self.generate_btn.config(state="normal")
        self.log(f"Error: {error_msg}")
        print(trace)
        messagebox.showerror("Generation Failed", error_msg)
