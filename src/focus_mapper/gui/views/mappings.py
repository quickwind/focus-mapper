"""Mappings management view for listing and maintaining mapping YAML files."""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import shutil
from datetime import datetime, timezone
from pathlib import Path
import os

import yaml # Added import
from focus_mapper.gui.ui_utils import (
    set_tooltip,
            refresh_sort_headers,
            sort_tree_items,
            autosize_treeview_columns,
            make_combobox_filterable,
)

class MappingsListView(ttk.Frame):
    """Mappings list screen with CRUD/import/export actions."""
    def __init__(self, parent, app_context):
        """Initialize mappings list view and load table data."""
        super().__init__(parent)
        self.app = app_context
        self.mappings_dir = Path.home() / ".focus_mapper" / "mappings"
        self._sort_state = {}
        self._base_headings = {
            "filename": "File Name",
            "dataset_type": "Dataset Type",
            "dataset_instance": "Dataset Instance Name",
            "column_count": "Column Count",
            "status": "Status",
            "modified": "Last Modified Time",
        }
        
        # Ensure directory exists
        self.mappings_dir.mkdir(parents=True, exist_ok=True)
        
        self._create_ui()
        self.refresh_list()

    def _create_ui(self):
        """Build toolbar and mappings table widgets."""
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
        btn_new = ttk.Button(manage_frame, text="New", command=self.on_new)
        btn_new.pack(side="left", padx=0)
        set_tooltip(btn_new, "Create a new mapping file.")
        btn_edit = ttk.Button(manage_frame, text="Edit", command=self.on_edit)
        btn_edit.pack(side="left", padx=0)
        set_tooltip(btn_edit, "Edit the selected mapping.")
        btn_clone = ttk.Button(manage_frame, text="Clone", command=self.on_clone)
        btn_clone.pack(side="left", padx=0)
        set_tooltip(btn_clone, "Create a copy of the selected mapping.")
        btn_delete = ttk.Button(manage_frame, text="Delete", command=self.on_delete)
        btn_delete.pack(side="left", padx=0)
        set_tooltip(btn_delete, "Delete the selected mapping.")

        # Group 2: Import/Export
        io_frame = ttk.LabelFrame(toolbar, text="Import/Export", padding=(2, 0))
        io_frame.pack(side="left", padx=2)
        btn_import = ttk.Button(io_frame, text="Import", command=self.on_import)
        btn_import.pack(side="left", padx=0)
        set_tooltip(btn_import, "Import a mapping YAML from disk.")
        btn_export = ttk.Button(io_frame, text="Export", command=self.on_export)
        btn_export.pack(side="left", padx=0)
        set_tooltip(btn_export, "Export the selected mapping YAML.")

        # Group 3: Tools
        btn_refresh = ttk.Button(toolbar, text="Refresh", command=self.refresh_list)
        btn_refresh.pack(side="right", padx=5, pady=5)
        set_tooltip(btn_refresh, "Reload mapping files from disk.")


        # Mappings List (Treeview)
        columns = ("filename", "dataset_type", "dataset_instance", "column_count", "status", "modified")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("filename", text="File Name", command=lambda: self._sort_tree("filename"))
        self.tree.heading("dataset_type", text="Dataset Type", command=lambda: self._sort_tree("dataset_type"))
        self.tree.heading("dataset_instance", text="Dataset Instance Name", command=lambda: self._sort_tree("dataset_instance"))
        self.tree.heading("column_count", text="Column Count", command=lambda: self._sort_tree("column_count"))
        self.tree.heading("status", text="Status", command=lambda: self._sort_tree("status"))
        self.tree.heading("modified", text="Last Modified Time", command=lambda: self._sort_tree("modified"))
        self.tree.column("filename", width=220)
        self.tree.column("dataset_type", width=130)
        self.tree.column("dataset_instance", width=200)
        self.tree.column("column_count", width=110)
        self.tree.column("status", width=90)
        self.tree.column("modified", width=170)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        set_tooltip(self.tree, "Mappings table. Click a column header to sort.")
        
        # Double click to edit
        self.tree.bind("<Double-1>", lambda e: self.on_edit())
        self._refresh_sort_headers()

    def refresh_list(self):
        """Reload mapping files and refresh table rows."""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        # Scan directory
        if not self.mappings_dir.exists():
            return

        for file_path in self.mappings_dir.glob("*.yaml"):
            mod_time = os.path.getmtime(file_path)
            dt = datetime.fromtimestamp(mod_time, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            
            # Read mapping details
            spec_ver = "-"
            dataset_type = "-"
            dataset_instance_name = "-"
            column_count = 0
            status = "Ready"
            try:
                with open(file_path, "r") as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        spec_ver = data.get("spec_version", "-")
                        dataset_type = data.get("dataset_type", "-")
                        dataset_instance_name = data.get("dataset_instance_name", "-")
                        mappings = data.get("mappings", {})
                        if isinstance(mappings, dict):
                            column_count = len(mappings)
                        # Ready/Not Ready check: any mandatory column missing or empty steps
                        try:
                            from focus_mapper.spec import load_focus_spec
                            spec = load_focus_spec(spec_ver, spec_dir=self.app.get_setting("spec_dir"))
                            mapped_cols = {
                                k
                                for k, v in (mappings or {}).items()
                                if isinstance(v, dict) and v.get("steps")
                            }
                            for col in spec.mandatory_columns:
                                if col.name not in mapped_cols:
                                    status = "Not Ready"
                                    break
                        except Exception:
                            pass
            except Exception:
                pass

            if spec_ver not in {"v1.3", "1.3"}:
                dataset_instance_name = "-"

            self.tree.insert(
                "",
                "end",
                iid=str(file_path),
                values=(file_path.name, dataset_type, dataset_instance_name, column_count, status, dt),
                tags=("not_ready",) if status == "Not Ready" else (),
            )
        self.tree.tag_configure("not_ready", foreground="red")
        self._autosize_columns()

    def _sort_tree(self, column: str):
        """Sort mappings table by selected column."""
        if column == "column_count":
            def key_fn(v):
                try:
                    return int(v)
                except Exception:
                    return 0
        else:
            key_fn = None
        self._sort_state = sort_tree_items(self.tree, column, self._sort_state, key_func=key_fn)
        self._refresh_sort_headers()

    def _refresh_sort_headers(self):
        """Update header sort arrows for current table sort state."""
        refresh_sort_headers(self.tree, self._base_headings, self._sort_state)

    def _autosize_columns(self):
        """Adjust table column widths to content within sensible bounds."""
        min_w = {
            "filename": 180,
            "dataset_type": 120,
            "dataset_instance": 180,
            "column_count": 110,
            "status": 100,
            "modified": 170,
        }
        max_w = {
            "filename": 360,
            "dataset_type": 220,
            "dataset_instance": 320,
            "column_count": 150,
            "status": 170,
            "modified": 220,
        }
        autosize_treeview_columns(self.tree, self._base_headings, min_w, max_w)

    def get_selected_path(self):
        """Return currently selected mapping file path or warn user."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Selection Required", "Please select a mapping file.", parent=self)
            return None
        return Path(selection[0])

    def on_new(self):
        """Start mapping creation flow."""
        from focus_mapper.gui.views.editor import MappingEditorView
        from tkinter import simpledialog
        
        # New: Use a custom dialog with Combobox
        spec_version = self._ask_spec_version()
        if not spec_version:
            return
            
        self.app._clear_content()
        self.app.current_view = MappingEditorView(self.app.content_frame, self.app, file_path=None, template_spec=spec_version)
        self.app.current_view.pack(fill="both", expand=True)

    def _ask_spec_version(self):
        """Prompt user to choose spec version for a new mapping."""
        # Custom modal dialog for selection
        dialog = tk.Toplevel(self)
        dialog.title("New Mapping")
        dialog.geometry("300x150") # Increased height
        dialog.resizable(False, False)
        
        # Center relative to parent
        self.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() // 2) - (300 // 2)
        y = self.winfo_rooty() + (self.winfo_height() // 2) - (150 // 2)
        dialog.geometry(f"+{x}+{y}")
        
        result = [None] 
        
        def on_ok():
            result[0] = cb.get()
            dialog.destroy()
            
        def on_cancel():
            dialog.destroy()

        content = ttk.Frame(dialog, padding=20)
        content.pack(fill="both", expand=True)
        
        ttk.Label(content, text="Select Spec Version:").pack(anchor="w", pady=(0, 5))
        
        # Get versions dynamically if possible, else hardcode
        versions = ["v1.3", "v1.2", "v1.1"]
        try:
            from focus_mapper.spec import list_available_spec_versions
            versions = sorted(
                list_available_spec_versions(spec_dir=self.app.get_setting("spec_dir")),
                reverse=True,
            )
        except ImportError:
            pass
            
        cb = ttk.Combobox(content, values=versions, state="readonly")
        make_combobox_filterable(cb, versions)
        if versions:
            cb.current(0)
        cb.pack(fill="x", pady=(0, 15))
        
        btn_frame = ttk.Frame(content)
        btn_frame.pack(fill="x")
        ttk.Button(btn_frame, text="Cancel", command=on_cancel).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="OK", command=on_ok).pack(side="right")
        
        dialog.transient(self)
        dialog.grab_set()
        self.wait_window(dialog)
        
        return result[0]

    def on_import(self):
        """Import mapping YAML into local mappings directory."""
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
        """Open selected mapping in editor."""
        path = self.get_selected_path()
        if path:
            from focus_mapper.gui.views.editor import MappingEditorView
            self.app._clear_content()
            self.app.current_view = MappingEditorView(self.app.content_frame, self.app, file_path=path)
            self.app.current_view.pack(fill="both", expand=True)

    def on_clone(self):
        """Clone selected mapping to a new file."""
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
        """Export selected mapping to chosen destination."""
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
        """Delete selected mapping after confirmation."""
        path = self.get_selected_path()
        if path:
            if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete {path.name}?", parent=self):
                try:
                    os.remove(path)
                    self.refresh_list()
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to delete: {e}", parent=self)
