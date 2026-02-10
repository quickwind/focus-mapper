import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import threading
import queue
import traceback

from focus_mapper.api import generate
from focus_mapper.spec import list_available_spec_versions

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
        self.mapping_cb = ttk.Combobox(form, textvariable=self.mapping_var, width=47)
        self.mapping_cb.grid(row=1, column=1, sticky="ew", padx=5)
        self._populate_mappings()
        
        # 3. Output Path
        ttk.Label(form, text="Output File:").grid(row=2, column=0, sticky="w", pady=5)
        self.output_entry = ttk.Entry(form, width=50)
        self.output_entry.grid(row=2, column=1, sticky="ew", padx=5)
        ttk.Button(form, text="Browse...", command=self.browse_output).grid(row=2, column=2)

        # 4. Spec Version (Optional)
        ttk.Label(form, text="Spec Version:").grid(row=3, column=0, sticky="w", pady=5)
        self.spec_var = tk.StringVar(value="v1.3")
        specs = ["v1.3", "v1.2", "v1.1"] # Could dynamic list
        self.spec_cb = ttk.Combobox(form, textvariable=self.spec_var, values=specs, width=10)
        self.spec_cb.grid(row=3, column=1, sticky="w", padx=5)

        form.columnconfigure(1, weight=1)

        # Action Button
        self.generate_btn = ttk.Button(self, text="Generate Dataset", command=self.on_generate)
        self.generate_btn.pack(pady=20)

        # Progress
        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.pack(fill="x", padx=10, pady=5)

        # Log Area
        ttk.Label(self, text="Logs:").pack(anchor="w", padx=10)
        self.log_text = tk.Text(self, height=10, state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))

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
        spec_version = self.spec_var.get()

        if not all([input_path, mapping_name, output_path]):
            messagebox.showwarning("Missing Info", "Please provide Input, Mapping, and Output.", parent=self)
            return

        mapping_path = self.mappings_dir / mapping_name
        if not mapping_path.exists():
             messagebox.showerror("Error", f"Mapping file not found: {mapping_path}", parent=self)
             return

        self.generate_btn.config(state="disabled")
        self.progress.start(10)
        self.log("Starting generation...")

        # Run in thread
        thread = threading.Thread(target=self._run_generation, args=(input_path, mapping_path, output_path, spec_version))
        thread.start()

    def _run_generation(self, input_path, mapping_path, output_path, spec_version):
        try:
            result = generate(
                input_data=input_path,
                mapping=str(mapping_path),
                output_path=output_path,
                spec_version=spec_version
            )
            
            self.after(0, self._on_success, result)
        except Exception as e:
            trace = traceback.format_exc()
            self.after(0, self._on_error, str(e), trace)

    def _on_success(self, result):
        self.progress.stop()
        self.generate_btn.config(state="normal")
        
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
                                          command=lambda: self.open_report(result.validation))
        self.view_report_btn.pack(pady=10)

    def open_report(self, validation_report):
        from focus_mapper.gui.views.report import ReportView
        # Convert report object to dict if needed, or pass directly if supported
        # ReportView expects dict structure currently
        import json
        # Fast way: assume it's dict-like or standard object
        # The library returns a pydantic model usually? 
        # result.validation is a ValidationReport object
        # Let's serialize it to be safe and consistent with file loading
        try:
            # Pydantic v2
            data = validation_report.model_dump()
        except AttributeError:
            # Pydantic v1 or just object
            try:
                data = validation_report.dict()
            except AttributeError:
                data = validation_report # Hope for the best or it's already dict
        
        self.app._clear_content()
        self.app.current_view = ReportView(self.app.content_frame, self.app, report_data=data)
        self.app.current_view.pack(fill="both", expand=True)

    def _on_error(self, error_msg, trace):
        self.progress.stop()
        self.generate_btn.config(state="normal")
        self.log(f"Error: {error_msg}")
        print(trace) # Print trace to stdout for debug
        messagebox.showerror("Generation Failed", error_msg)
