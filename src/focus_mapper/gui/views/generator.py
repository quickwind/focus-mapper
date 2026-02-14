import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter import font as tkfont
from pathlib import Path
import threading
import traceback

from focus_mapper.api import generate

class GeneratorView(ttk.Frame):
    def __init__(self, parent, app_context):
        super().__init__(parent)
        self.app = app_context
        self.mappings_dir = Path.home() / ".focus_mapper" / "mappings"
        self._create_ui()

    def _create_ui(self):
        # Header
        ttk.Label(self, text="Generate FOCUS Dataset", font=("Helvetica", 16, "bold")).pack(anchor="w", pady=(0, 20))

        # Form Container
        form = ttk.Frame(self)
        form.pack(fill="x", padx=10)

        # 1. Input Source
        ttk.Label(form, text="Input Data (CSV/Parquet):").grid(row=0, column=0, sticky="w", pady=5)
        self.input_entry = ttk.Entry(form, width=50)
        self.input_entry.grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(form, text="Browse...", command=self.browse_input).grid(row=0, column=2)

        # 2. Mapping Configuration
        ttk.Label(form, text="Mapping Config:").grid(row=1, column=0, sticky="w", pady=5)
        self.mapping_var = tk.StringVar()
        self.mapping_cb = ttk.Combobox(form, textvariable=self.mapping_var, width=47, state="readonly")
        self.mapping_cb.grid(row=1, column=1, sticky="ew", padx=5)
        self._populate_mappings()
        
        # 3. Output Path
        ttk.Label(form, text="Output File:").grid(row=2, column=0, sticky="w", pady=5)
        self.output_entry = ttk.Entry(form, width=50)
        self.output_entry.grid(row=2, column=1, sticky="ew", padx=5)
        ttk.Button(form, text="Browse...", command=self.browse_output).grid(row=2, column=2)

        form.columnconfigure(1, weight=1)

        # Action Button
        self.generate_btn = ttk.Button(self, text="Generate Dataset", command=self.on_generate)
        self.generate_btn.pack(pady=12)

        # Preview Area
        ttk.Label(self, text="Result Preview (first 100 rows):").pack(anchor="w", padx=10, pady=(0, 4))
        preview_frame = ttk.Frame(self)
        preview_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.preview_tree = ttk.Treeview(preview_frame, show="headings", height=12)
        self.preview_tree.pack(side="left", fill="both", expand=True)
        preview_y = ttk.Scrollbar(preview_frame, orient="vertical", command=self.preview_tree.yview)
        preview_y.pack(side="right", fill="y")
        preview_x = ttk.Scrollbar(self, orient="horizontal", command=self.preview_tree.xview)
        preview_x.pack(fill="x", padx=10, pady=(0, 8))
        self.preview_tree.configure(yscrollcommand=preview_y.set, xscrollcommand=preview_x.set)

        # Logs
        ttk.Label(self, text="Logs:").pack(anchor="w", padx=10)
        self.log_text = tk.Text(self, height=8, state="disabled")
        self.log_text.pack(fill="both", expand=False, padx=10, pady=(0, 8))

        # Progress
        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.pack(fill="x", padx=10, pady=(0, 10))

    def _populate_mappings(self):
        if not self.mappings_dir.exists():
            return
        files = [f.name for f in self.mappings_dir.glob("*.yaml")]
        self.mapping_cb['values'] = files
        if files:
            self.mapping_cb.current(0)

    def browse_input(self):
        f = filedialog.askopenfilename(filetypes=[("Data files", "*.csv *.parquet"), ("All files", "*.*")], parent=self)
        if f:
            self.input_entry.delete(0, "end")
            self.input_entry.insert(0, f)

    def browse_output(self):
        f = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv"), ("Parquet", "*.parquet")], parent=self)
        if f:
            self.output_entry.delete(0, "end")
            self.output_entry.insert(0, f)

    def log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def on_generate(self):
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

    def open_report(self, validation_report, total_rows=None):
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
        for item in self.preview_tree.get_children():
            self.preview_tree.delete(item)
        self.preview_tree["columns"] = ()

    def _show_preview(self, df):
        self._clear_preview()
        if df is None or df.empty:
            return

        preview_df = df.head(100).copy()
        index_col = "__row_index__"
        columns = [index_col] + [str(c) for c in preview_df.columns]
        self.preview_tree["columns"] = columns
        for col in columns:
            self.preview_tree.heading(col, text="#" if col == index_col else col)
            self.preview_tree.column(col, anchor="e" if col == index_col else "w", stretch=False)

        for idx, row in enumerate(preview_df.itertuples(index=False, name=None), start=1):
            values = [idx]
            values.extend("" if v is None else str(v) for v in row)
            self.preview_tree.insert("", "end", values=values)
        self._autosize_preview_columns(preview_df, columns, index_col)

    def _autosize_preview_columns(self, preview_df, columns, index_col):
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
        self.progress.stop()
        self.generate_btn.config(state="normal")
        self.log(f"Error: {error_msg}")
        print(trace)
        messagebox.showerror("Generation Failed", error_msg)
