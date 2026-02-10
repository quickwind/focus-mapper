import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import shutil
from pathlib import Path
import os

import yaml # Added import

class MappingsListView(ttk.Frame):
    def __init__(self, parent, app_context):
        super().__init__(parent)
        self.app = app_context
        self.mappings_dir = Path.home() / ".focus_mapper" / "mappings"
        
        # Ensure directory exists
        self.mappings_dir.mkdir(parents=True, exist_ok=True)
        
        self._create_ui()
        self.refresh_list()

    def _create_ui(self):
        # Header
        header_frame = ttk.Frame(self)
        header_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(header_frame, text="Mappings Manager", font=("Helvetica", 16, "bold")).pack(side="left")
        
        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 10))
        
        # Group 1: Manage
        manage_frame = ttk.LabelFrame(toolbar, text="Manage", padding=(2, 0))
        manage_frame.pack(side="left", padx=2)
        ttk.Button(manage_frame, text="New", command=self.on_new).pack(side="left", padx=0)
        ttk.Button(manage_frame, text="Edit", command=self.on_edit).pack(side="left", padx=0)
        ttk.Button(manage_frame, text="Clone", command=self.on_clone).pack(side="left", padx=0)
        ttk.Button(manage_frame, text="Delete", command=self.on_delete).pack(side="left", padx=0)

        # Group 2: Import/Export
        io_frame = ttk.LabelFrame(toolbar, text="Import/Export", padding=(2, 0))
        io_frame.pack(side="left", padx=2)
        ttk.Button(io_frame, text="Import", command=self.on_import).pack(side="left", padx=0)
        ttk.Button(io_frame, text="Export", command=self.on_export).pack(side="left", padx=0)

        # Group 3: Tools
        ttk.Button(toolbar, text="Refresh", command=self.refresh_list).pack(side="right", padx=5, pady=5)


        # Mappings List (Treeview)
        columns = ("filename", "spec_version", "modified")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("filename", text="Filename")
        self.tree.heading("spec_version", text="Spec Version")
        self.tree.heading("modified", text="Last Modified")
        self.tree.column("filename", width=250)
        self.tree.column("spec_version", width=80)
        self.tree.column("modified", width=150)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Double click to edit
        self.tree.bind("<Double-1>", lambda e: self.on_edit())

    def refresh_list(self):
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        # Scan directory
        if not self.mappings_dir.exists():
            return

        for file_path in self.mappings_dir.glob("*.yaml"):
            mod_time = os.path.getmtime(file_path)
            from datetime import datetime
            dt = datetime.fromtimestamp(mod_time).strftime('%Y-%m-%d %H:%M:%S')
            
            # Read spec version
            spec_ver = "-"
            try:
                with open(file_path, "r") as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        spec_ver = data.get("spec_version", "-")
            except Exception:
                pass
            
            self.tree.insert("", "end", iid=str(file_path), values=(file_path.name, spec_ver, dt))

    def get_selected_path(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Selection Required", "Please select a mapping file.", parent=self)
            return None
        return Path(selection[0])

    def on_new(self):
        from focus_mapper.gui.views.editor import MappingEditorView
        from tkinter import simpledialog
        
        # Prompt for spec version
        spec_version = simpledialog.askstring("New Mapping", "Enter Spec Version (v1.1, v1.2, v1.3):", initialvalue="v1.3", parent=self)
        if not spec_version:
            return
            
        self.app._clear_content()
        self.app.current_view = MappingEditorView(self.app.content_frame, self.app, file_path=None, template_spec=spec_version)
        self.app.current_view.pack(fill="both", expand=True)

    def on_import(self):
        file_path = filedialog.askopenfilename(
            title="Import Mapping",
            filetypes=[("YAML files", "*.yaml"), ("All files", "*.*")],
            parent=self
        )
        if file_path:
            try:
                src = Path(file_path)
                dest = self.mappings_dir / src.name
                if dest.exists():
                    if not messagebox.askyesno("Confirm Overwrite", f"{dest.name} already exists. Overwrite?", parent=self):
                        return
                shutil.copy2(src, dest)
                self.refresh_list()
                messagebox.showinfo("Success", f"Imported {src.name}", parent=self)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to import: {e}", parent=self)

    def on_edit(self):
        path = self.get_selected_path()
        if path:
            from focus_mapper.gui.views.editor import MappingEditorView
            self.app._clear_content()
            self.app.current_view = MappingEditorView(self.app.content_frame, self.app, file_path=path)
            self.app.current_view.pack(fill="both", expand=True)

    def on_clone(self):
        path = self.get_selected_path()
        if path:
            new_name = filedialog.asksaveasfilename(
                initialdir=self.mappings_dir,
                initialfile=f"copy_of_{path.name}",
                title="Clone Mapping As",
                defaultextension=".yaml",
                filetypes=[("YAML files", "*.yaml")],
                parent=self
            )
            if new_name:
                try:
                    shutil.copy2(path, new_name)
                    self.refresh_list()
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to clone: {e}", parent=self)

    def on_export(self):
        path = self.get_selected_path()
        if path:
            dest = filedialog.asksaveasfilename(
                initialfile=path.name,
                title="Export Mapping",
                defaultextension=".yaml",
                filetypes=[("YAML files", "*.yaml")],
                parent=self
            )
            if dest:
                try:
                    shutil.copy2(path, dest)
                    messagebox.showinfo("Success", f"Exported to {dest}", parent=self)
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to export: {e}", parent=self)

    def on_delete(self):
        path = self.get_selected_path()
        if path:
            if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete {path.name}?", parent=self):
                try:
                    os.remove(path)
                    self.refresh_list()
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to delete: {e}", parent=self)
