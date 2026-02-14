"""Dataset generation view with preview, logs, and report navigation."""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter import font as tkfont
from pathlib import Path
import threading
import traceback
import pandas as pd

from focus_mapper.api import generate
from focus_mapper.io import read_table
from focus_mapper.mapping.config import load_mapping_config
from focus_mapper.mapping.executor import generate_focus_dataframe
from focus_mapper.spec import load_focus_spec
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
        thread = threading.Thread(
            target=self._prepare_and_run_generation,
            args=(input_path, mapping_path, output_path),
            daemon=True,
        )
        thread.start()

    def _prepare_and_run_generation(self, input_path, mapping_path, output_path):
        """Prepare optional v1.3 recency config, then run final generation."""
        try:
            spec_dir = self.app.get_setting("spec_dir", None)
            mapping = load_mapping_config(mapping_path)
            spec = load_focus_spec(mapping.spec_version, spec_dir=spec_dir or None)

            dataset_instance_complete = None
            sector_complete_map = None

            version = spec.version.lstrip("v")
            if version >= "1.3" and mapping.dataset_type == "CostAndUsage":
                self.after(0, self.log, "Preparing v1.3 recency configuration...")
                input_df = read_table(Path(input_path))
                out_df_for_sectors = generate_focus_dataframe(input_df, mapping=mapping, spec=spec)
                sector_pairs = self._extract_time_sector_pairs(out_df_for_sectors)

                response_box: dict[str, tuple[bool, dict[tuple[str, str], bool]] | None] = {"value": None}
                wait_event = threading.Event()

                def ask_user():
                    try:
                        response_box["value"] = self._ask_recency_config(sector_pairs)
                    finally:
                        wait_event.set()

                self.after(0, ask_user)
                wait_event.wait()
                response = response_box["value"]
                if response is None:
                    self.after(0, self._on_cancelled)
                    return
                dataset_instance_complete, sector_complete_map = response

            self._run_generation(
                input_path,
                mapping_path,
                output_path,
                dataset_instance_complete=dataset_instance_complete,
                sector_complete_map=sector_complete_map,
            )
        except Exception as e:
            trace = traceback.format_exc()
            self.after(0, self._on_error, str(e), trace)

    def _run_generation(
        self,
        input_path,
        mapping_path,
        output_path,
        dataset_instance_complete=None,
        sector_complete_map=None,
    ):
        """Worker thread body for dataset generation."""
        try:
            spec_dir = self.app.get_setting("spec_dir", None)
            result = generate(
                input_data=input_path,
                mapping=str(mapping_path),
                output_path=output_path,
                spec_dir=spec_dir or None,
                dataset_instance_complete=dataset_instance_complete,
                sector_complete_map=sector_complete_map,
            )
            
            self.after(0, self._on_success, result)
        except Exception as e:
            trace = traceback.format_exc()
            self.after(0, self._on_error, str(e), trace)

    def _extract_time_sector_pairs(self, output_df):
        """Extract distinct (ChargePeriodStart, ChargePeriodEnd) pairs as strings."""
        if "ChargePeriodStart" not in output_df.columns or "ChargePeriodEnd" not in output_df.columns:
            return []
        pairs = (
            output_df[["ChargePeriodStart", "ChargePeriodEnd"]]
            .drop_duplicates()
            .itertuples(index=False, name=None)
        )
        return [(str(start), str(end)) for start, end in pairs]

    def _ask_recency_config(self, sector_pairs):
        """Prompt user for dataset/time-sector completeness values for v1.3."""
        dialog = tk.Toplevel(self)
        dialog.title("v1.3 Recency Configuration")
        dialog.geometry("860x620")
        dialog.minsize(760, 520)
        dialog.transient(self)
        dialog.grab_set()

        self.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() // 2) - (860 // 2)
        y = self.winfo_rooty() + (self.winfo_height() // 2) - (620 // 2)
        dialog.geometry(f"+{x}+{y}")

        container = ttk.Frame(dialog, padding=14)
        container.pack(fill="both", expand=True)

        ttk.Label(container, text="Dataset Recency (v1.3 CostAndUsage)", font=("Helvetica", 13, "bold")).pack(anchor="w")
        ttk.Label(
            container,
            text=(
                "Set whether the dataset instance is complete. "
                "If incomplete, configure completeness for each time sector."
            ),
            wraplength=800,
        ).pack(anchor="w", pady=(4, 10))

        dataset_complete_var = tk.BooleanVar(value=True)
        sector_vars: dict[tuple[str, str], tk.BooleanVar] = {
            pair: tk.BooleanVar(value=True) for pair in sector_pairs
        }

        dataset_row = ttk.Frame(container)
        dataset_row.pack(fill="x", pady=(0, 8))
        ttk.Label(dataset_row, text="Dataset Instance Complete:").pack(side="left")
        rb_yes = ttk.Radiobutton(dataset_row, text="Yes", variable=dataset_complete_var, value=True)
        rb_no = ttk.Radiobutton(dataset_row, text="No", variable=dataset_complete_var, value=False)
        rb_yes.pack(side="left", padx=(10, 6))
        rb_no.pack(side="left")
        set_tooltip(rb_yes, "All periods in this dataset instance are complete.")
        set_tooltip(rb_no, "One or more periods are incomplete. Configure sectors below.")

        ttk.Separator(container, orient="horizontal").pack(fill="x", pady=(2, 8))
        header_row = ttk.Frame(container)
        header_row.pack(fill="x")
        ttk.Label(header_row, text="Time Sector Completeness:").pack(side="left", anchor="w")
        bulk_actions = ttk.Frame(header_row)
        bulk_actions.pack(side="right")

        sectors_outer = ttk.Frame(container)
        sectors_outer.pack(fill="both", expand=True, pady=(6, 10))

        if not sector_pairs:
            ttk.Label(
                sectors_outer,
                text="No ChargePeriodStart/ChargePeriodEnd sectors found in generated output.",
                foreground="#666666",
            ).pack(anchor="w")
        else:
            canvas = tk.Canvas(sectors_outer, borderwidth=0, highlightthickness=0)
            yscroll = ttk.Scrollbar(sectors_outer, orient="vertical", command=canvas.yview)
            sectors_frame = ttk.Frame(canvas)
            sectors_window = canvas.create_window((0, 0), window=sectors_frame, anchor="nw")

            def on_sectors_configure(_event):
                canvas.configure(scrollregion=canvas.bbox("all"))

            def on_canvas_configure(event):
                canvas.itemconfigure(sectors_window, width=event.width)

            sectors_frame.bind("<Configure>", on_sectors_configure)
            canvas.bind("<Configure>", on_canvas_configure)
            canvas.configure(yscrollcommand=yscroll.set)
            canvas.pack(side="left", fill="both", expand=True)
            yscroll.pack(side="right", fill="y")

            def refresh_sector_state():
                enabled = not dataset_complete_var.get()
                for checkbox in sector_checkboxes:
                    checkbox.configure(state="normal" if enabled else "disabled")
                check_all_btn.configure(state="normal" if enabled else "disabled")
                uncheck_all_btn.configure(state="normal" if enabled else "disabled")

            def set_all_sectors(value: bool):
                for pair in sector_pairs:
                    sector_vars[pair].set(value)

            check_all_btn = ttk.Button(bulk_actions, text="Check all", command=lambda: set_all_sectors(True))
            check_all_btn.pack(side="left", padx=(0, 6))
            set_tooltip(check_all_btn, "Mark all listed time sectors as complete.")
            uncheck_all_btn = ttk.Button(bulk_actions, text="Uncheck all", command=lambda: set_all_sectors(False))
            uncheck_all_btn.pack(side="left")
            set_tooltip(uncheck_all_btn, "Mark all listed time sectors as incomplete.")

            sector_checkboxes = []
            for start, end in sector_pairs:
                row = ttk.Frame(sectors_frame)
                row.pack(fill="x", pady=2)
                display_start = self._format_focus_datetime_display(start)
                display_end = self._format_focus_datetime_display(end)
                label = ttk.Label(row, text=f"{display_start}  ->  {display_end}")
                label.pack(side="left", fill="x", expand=True)
                set_tooltip(label, "Time sector in output data derived from ChargePeriodStart/ChargePeriodEnd.")
                cb = ttk.Checkbutton(row, text="Complete", variable=sector_vars[(start, end)])
                cb.pack(side="right")
                set_tooltip(cb, "Whether this time sector is complete.")
                sector_checkboxes.append(cb)

            dataset_complete_var.trace_add("write", lambda *_args: refresh_sector_state())
            refresh_sector_state()

        result = {"value": None}

        def on_ok():
            dataset_complete = bool(dataset_complete_var.get())
            sector_map: dict[tuple[str, str], bool] = {}
            if not dataset_complete:
                for pair in sector_pairs:
                    sector_map[pair] = bool(sector_vars[pair].get())
            result["value"] = (dataset_complete, sector_map)
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btns = ttk.Frame(container)
        btns.pack(fill="x")
        ttk.Button(btns, text="Cancel", command=on_cancel).pack(side="right", padx=(8, 0))
        ttk.Button(btns, text="OK", command=on_ok).pack(side="right")

        dialog.wait_window()
        return result["value"]

    def _format_focus_datetime_display(self, raw_value):
        """Format date/time for UI display as FOCUS UTC timestamp (YYYY-MM-DDTHH:MM:SSZ)."""
        text = str(raw_value).strip()
        if not text:
            return text
        try:
            dt = pd.to_datetime(text, utc=True, errors="raise")
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return text

    def _on_cancelled(self):
        """Handle user cancellation of v1.3 recency configuration."""
        self.progress.stop()
        self.generate_btn.config(state="normal")
        self.log("Generation cancelled by user.")

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
