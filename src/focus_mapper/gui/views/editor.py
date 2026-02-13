import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from pathlib import Path
import yaml

from focus_mapper.spec import load_focus_spec
from focus_mapper.mapping.config import load_mapping_config, MappingConfig, MappingRule
from focus_mapper.gui.components.step_forms import get_form_class

class MappingEditorView(ttk.Frame):
    def __init__(
        self,
        parent,
        app_context,
        file_path=None,
        template_spec="v1.3",
        dataset_type=None,
        dataset_instance_name=None,
    ):
        super().__init__(parent)
        self.app = app_context
        self.file_path = file_path
        self.original_path = file_path
        self.spec_version = template_spec
        self.dataset_type = dataset_type
        self.dataset_instance_name = dataset_instance_name
        self.mappings_dir = Path.home() / ".focus_mapper" / "mappings"
        # Mutable state
        self.rules_dict = {} # target -> MappingRule object (or dict wrapper)
        self.validation_defaults = {}
        
        self.spec = None
        self.current_column = None
        
        self._load_data()
        self._create_ui()
        self._populate_tree()

    def _load_data(self):
        if self.file_path and self.file_path.exists():
            try:
                config = load_mapping_config(self.file_path)
                self.spec_version = config.spec_version
                self.dataset_type = config.dataset_type
                self.dataset_instance_name = config.dataset_instance_name
                self.validation_defaults = config.validation_defaults
                # Convert list to dict for editing
                self.rules_dict = {r.target: r for r in config.rules}
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load mapping: {e}")
                self.app.show_mappings_view()
                return
        else:
            # New mapping - start empty
            self.rules_dict = {}
            self.validation_defaults = {}
            if not self.dataset_type:
                self.dataset_type = "CostAndUsage"
            if not self.file_path:
                self.file_path = self.mappings_dir / "mapping.yaml"
        
        try:
            self.spec = load_focus_spec(self.spec_version)
        except Exception:
            # Fallback if spec load fails
            pass

    def _create_ui(self):
        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=5)
        ttk.Button(toolbar, text="Back", command=self.on_back).pack(side="left")
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=5)
        ttk.Button(toolbar, text="Save", command=self.on_save).pack(side="right")

        meta = ttk.Frame(self)
        meta.pack(fill="x", pady=(0, 5))

        self.name_var = tk.StringVar(value=self.file_path.name if self.file_path else "mapping.yaml")
        ttk.Label(meta, text="Mapping Name:").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=2)
        name_entry = ttk.Entry(meta, textvariable=self.name_var, width=40)
        name_entry.grid(row=0, column=1, sticky="w", pady=2)
        self.name_required = ttk.Label(meta, text="*", foreground="red")
        self.name_required.grid(row=0, column=2, sticky="w", pady=2)

        ttk.Label(meta, text="Spec Version:").grid(row=0, column=3, sticky="w", padx=(12, 6), pady=2)
        self.spec_var = tk.StringVar(value=self.spec_version)
        spec_entry = ttk.Entry(meta, textvariable=self.spec_var, width=10, state="disabled")
        spec_entry.grid(row=0, column=4, sticky="w", pady=2)

        ttk.Label(meta, text="Dataset Type:").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=2)
        self.dataset_type_var = tk.StringVar(value="CostAndUsage")
        self.dataset_type_cb = ttk.Combobox(
            meta,
            textvariable=self.dataset_type_var,
            values=["CostAndUsage"],
            state="disabled",
            width=18,
        )
        self.dataset_type_cb.grid(row=1, column=1, sticky="w", pady=2)

        ttk.Label(meta, text="Dataset Instance Name:").grid(row=1, column=3, sticky="w", padx=(12, 6), pady=2)
        self.dataset_instance_var = tk.StringVar(value=self.dataset_instance_name or "")
        self.dataset_instance_entry = ttk.Entry(meta, textvariable=self.dataset_instance_var, width=30)
        self.dataset_instance_entry.grid(row=1, column=4, sticky="w", pady=2)
        self.dataset_instance_required = ttk.Label(meta, text="*", foreground="red")
        self.dataset_instance_required.grid(row=1, column=5, sticky="w", pady=2)

        def toggle_v13_fields():
            is_v13 = self.spec_version in {"v1.3", "1.3"}
            state = "normal" if is_v13 else "disabled"
            self.dataset_instance_entry.configure(state=state)
            if is_v13:
                self.dataset_instance_required.grid()
            else:
                self.dataset_instance_required.grid_remove()

        def update_required_indicators(event=None):
            name_ok = bool(self.name_var.get().strip())
            if name_ok:
                self.name_required.grid_remove()
            else:
                self.name_required.grid()

            is_v13 = self.spec_version in {"v1.3", "1.3"}
            instance_ok = bool(self.dataset_instance_var.get().strip())
            if is_v13 and not instance_ok:
                self.dataset_instance_required.grid()
            else:
                self.dataset_instance_required.grid_remove()

        name_entry.bind("<KeyRelease>", update_required_indicators)
        self.dataset_instance_entry.bind("<KeyRelease>", update_required_indicators)

        toggle_v13_fields()
        update_required_indicators()

        # Main Split
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        # Left: Columns Tree
        left_frame = ttk.Frame(paned, width=300) 
        paned.add(left_frame, weight=1)
        
        tree_toolbar = ttk.Frame(left_frame)
        tree_toolbar.pack(fill="x")
        ttk.Button(tree_toolbar, text="+", width=3, command=self.on_add_column).pack(side="right")
        ttk.Label(tree_toolbar, text="Columns").pack(side="left")

        self.tree = ttk.Treeview(left_frame, columns=("status",), show="tree headings", selectmode="browse")
        self.tree.heading("status", text="Status")
        self.tree.column("status", width=50)
        self.tree.column("#0", width=200)
        self.tree.heading("#0", text="Column Name")
        
        scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.tree.bind("<<TreeviewSelect>>", self.on_column_select)

        # Right: Column Details
        self.right_frame = ttk.Frame(paned)
        paned.add(self.right_frame, weight=3)
        
        # We'll dynamically populate right_frame based on selection

    def _populate_tree(self):
        # Merge spec columns and existing config
        mapped_cols = set(self.rules_dict.keys())
        spec_cols = set()
        if self.spec:
            spec_cols = {c.name for c in self.spec.columns}
        
        all_cols = sorted(list(spec_cols | mapped_cols))
        
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)

        for col in all_cols:
            status = "Mapped" if col in mapped_cols else "-"
            self.tree.insert("", "end", iid=col, text=col, values=(status,))

    def on_column_select(self, event):
        selection = self.tree.selection()
        if not selection:
            return
        
        col_name = selection[0]
        self.current_column = col_name
        self._show_column_details(col_name)

    def _show_column_details(self, col_name):
        # Clear right frame
        for widget in self.right_frame.winfo_children():
            widget.destroy()

        # Header
        header = ttk.Frame(self.right_frame)
        header.pack(fill="x", pady=10)
        ttk.Label(header, text=f"Column: {col_name}", font=("Helvetica", 12, "bold")).pack(side="left")
        
        # If not mapped, button to Initialize
        if col_name not in self.rules_dict:
            btn = ttk.Button(self.right_frame, text="Create Mapping Rule", 
                             command=lambda: self.create_rule(col_name))
            btn.pack(pady=20)
            return

        rule = self.rules_dict[col_name]
        
        # Steps List
        lf = ttk.LabelFrame(self.right_frame, text="Transformation Steps")
        lf.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Step List Container
        step_container = ttk.Frame(lf)
        step_container.pack(fill="both", expand=True)

        for i, step in enumerate(rule.steps):
            self._render_step(step_container, i, step)

        # Add Step Button
        ttk.Button(lf, text="Add Step", command=lambda: self.add_step(col_name)).pack(pady=5)

    def _render_step(self, parent, index, step_config):
        frame = ttk.Frame(parent, borderwidth=1, relief="solid")
        frame.pack(fill="x", pady=2, padx=2)
        
        header = ttk.Frame(frame, style="StepHeader.TFrame")
        header.pack(fill="x")
        
        op = step_config.get("op", "unknown")
        ttk.Label(header, text=f"Step {index+1}: {op}", font=("Helvetica", 10, "bold")).pack(side="left", padx=5)
        
        # Delete button
        ttk.Button(header, text="X", width=2, 
                   command=lambda: self.delete_step(index)).pack(side="right")
        
        # Config Form
        FormClass = get_form_class(op)
        form = FormClass(frame, step_config, on_change=self.mark_dirty)
        form.pack(fill="x", padx=10, pady=5)

    def create_rule(self, col_name):
        # Create a new MappingRule
        # Since MappingRule is frozen, we might need a mutable proxy or just recreate it on save/update?
        # Actually, MappingRule.steps is a list[dict]. The list itself is mutable!
        # The MappingRule object is frozen, so I can't assign to .steps if it was not a list, but list content can catch changes.
        # However, to be safe and clean, let's create a new one.
        self.rules_dict[col_name] = MappingRule(target=col_name, steps=[])
        self.mark_dirty()
        self.tree.set(col_name, "status", "Mapped")
        self._show_column_details(col_name)

    def add_step(self, col_name):
        # Prompt for Op
        ops = ["from_column", "const", "sql", "cast", "null", "concat"] # etc
        op = simpledialog.askstring("Add Step", f"Enter operation: {', '.join(ops)}", parent=self)
        if op and op in ops:
            step = {"op": op}
            # List is mutable, even in frozen dataclass if initialized
            self.rules_dict[col_name].steps.append(step)
            self.mark_dirty()
            self._show_column_details(col_name)

    def delete_step(self, index):
        if self.current_column:
            self.rules_dict[self.current_column].steps.pop(index)
            self.mark_dirty()
            self._show_column_details(self.current_column)

    def mark_dirty(self):
        # TODO: Enable save button state or * indicator
        pass

    def on_add_column(self):
        name = simpledialog.askstring("New Extension Column", "Enter column name (e.g., x_CostCenter):", parent=self)
        if name:
            if not name.startswith("x_"):
                name = "x_" + name
            if name not in self.rules_dict:
                self.create_rule(name)
                # Add to tree
                self.tree.insert("", "end", iid=name, text=name, values=("Mapped",))
                self.tree.selection_set(name)

    def on_save(self):
        name = (self.name_var.get() or "").strip()
        if not name:
            messagebox.showwarning("Missing Name", "Please enter a mapping name.", parent=self)
            return
        if self.spec_version in {"v1.3", "1.3"}:
            instance_name = (self.dataset_instance_var.get() or "").strip()
            if not instance_name:
                messagebox.showwarning(
                    "Missing Dataset Instance Name",
                    "Please enter a dataset instance name.",
                    parent=self,
                )
                return
        if not name.endswith(".yaml"):
            name = f"{name}.yaml"
        self.mappings_dir.mkdir(parents=True, exist_ok=True)
        new_path = self.mappings_dir / name

        if new_path.exists() and (self.original_path is None or new_path != self.original_path):
            if not messagebox.askyesno(
                "Confirm Overwrite",
                f"{new_path.name} already exists. Overwrite?",
                parent=self,
            ):
                return
        self.file_path = new_path

        # Serialize config to YAML
        # Convert rules dict to dict of dicts
        self.dataset_type = "CostAndUsage" if self.spec_version in {"v1.3", "1.3"} else None
        self.dataset_instance_name = (
            self.dataset_instance_var.get().strip() or None
            if self.spec_version in {"v1.3", "1.3"}
            else None
        )
        data = {
            "spec_version": self.spec_version,
            "validation": { "default": self.validation_defaults } if self.validation_defaults else {},
            "mappings": {
                k: {"steps": v.steps} for k, v in self.rules_dict.items()
            }
        }

        if self.dataset_type:
            data["dataset_type"] = self.dataset_type
        if self.dataset_instance_name:
            data["dataset_instance_name"] = self.dataset_instance_name
        
        with open(self.file_path, "w") as f:
            yaml.dump(data, f, sort_keys=False)

        if self.original_path and self.original_path != self.file_path and self.original_path.exists():
            try:
                self.original_path.unlink()
            except Exception:
                pass
        self.original_path = self.file_path
        
        messagebox.showinfo("Saved", f"Mapping saved to {self.file_path.name}", parent=self)

    def on_back(self):
        self.app.show_mappings_view()
