"""Interactive mapping editor view for creating and maintaining mapping YAML."""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from tkinter import font as tkfont
from pathlib import Path
import json
import yaml
import pandas as pd

from focus_mapper.spec import load_focus_spec
from focus_mapper.io import read_table
from focus_mapper.mapping.ops import apply_steps
from focus_mapper.validate import default_validation_settings
from focus_mapper.mapping.config import load_mapping_config, MappingConfig, MappingRule
from focus_mapper.format_validators import (
    validate_key_value_format,
    validate_json_object_format,
)
from focus_mapper.gui.ui_utils import (
    WidgetTooltip as _WidgetTooltip,
    set_tooltip as _set_tooltip,
    make_combobox_filterable,
    format_value_for_display,
)


def _create_star(parent, tooltip: str, **pack_opts):
    """Create a red required-star label with optional tooltip."""
    star = ttk.Label(parent, text="*", foreground="red")
    star._pack_opts = pack_opts
    star.pack(**pack_opts)
    _set_tooltip(star, tooltip)
    return star


def _set_star_visible(star, show: bool, tooltip: str | None = None):
    """Show or hide required-star indicator and update tooltip text."""
    if star is None:
        return
    if tooltip:
        _set_tooltip(star, tooltip)
    if show:
        if not star.winfo_ismapped():
            star.pack(**getattr(star, "_pack_opts", {}))
    else:
        star.pack_forget()


class _OpPicker:
    """Modal operation picker with per-option tooltip descriptions."""
    def __init__(self, parent, options: list[str], descriptions: dict[str, str]):
        """Initialize picker state and option catalog."""
        self.parent = parent
        self.options = options
        self.descriptions = descriptions
        self.result: str | None = None

    def show(self, title: str, current: str | None = None) -> str | None:
        """Open picker modal and return selected operation name."""
        dialog = tk.Toplevel(self.parent)
        dialog.title(title)
        dialog.resizable(False, False)

        self.parent.update_idletasks()
        w, h = 320, 240
        x = self.parent.winfo_rootx() + (self.parent.winfo_width() // 2) - (w // 2)
        y = self.parent.winfo_rooty() + (self.parent.winfo_height() // 2) - (h // 2)
        dialog.geometry(f"{w}x{h}+{x}+{y}")

        content = ttk.Frame(dialog, padding=10)
        content.pack(fill="both", expand=True)
        ttk.Label(content, text="Select operation type:").pack(anchor="w", pady=(0, 6))

        listbox = tk.Listbox(content, height=8)
        listbox.pack(fill="both", expand=True)
        for opt in self.options:
            listbox.insert("end", opt)

        tooltip = _WidgetTooltip(listbox)

        def on_motion(event):
            idx = listbox.nearest(event.y)
            if idx < 0 or idx >= len(self.options):
                tooltip.hide()
                return
            opt = self.options[idx]
            tooltip.show(self.descriptions.get(opt, ""))

        listbox.bind("<Motion>", on_motion)
        listbox.bind("<Leave>", lambda _e: tooltip.hide())

        if current in self.options:
            listbox.selection_set(self.options.index(current))

        def on_ok():
            sel = listbox.curselection()
            if not sel:
                self.result = None
            else:
                self.result = self.options[sel[0]]
            dialog.destroy()

        def on_cancel():
            self.result = None
            dialog.destroy()

        btns = ttk.Frame(content)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="Cancel", command=on_cancel).pack(side="right")
        ttk.Button(btns, text="OK", command=on_ok).pack(side="right", padx=6)

        dialog.transient(self.parent)
        dialog.grab_set()
        self.parent.wait_window(dialog)
        return self.result


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge two dictionaries (override values win)."""
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out.get(k, {}), v)
        else:
            out[k] = v
    return out


def _deep_diff(base: dict, modified: dict) -> dict:
    """Return recursive diff map from `base` to `modified`."""
    diff: dict = {}
    for k, v in modified.items():
        if k not in base:
            diff[k] = v
            continue
        b = base[k]
        if isinstance(v, dict) and isinstance(b, dict):
            child = _deep_diff(b, v)
            if child:
                diff[k] = child
        else:
            if v != b:
                diff[k] = v
    return diff


class _TreeTooltip:
    """Floating tooltip tied to tree rows while hovering."""
    def __init__(self, widget: ttk.Treeview):
        """Create tree-row tooltip controller."""
        self.widget = widget
        self.tip = None
        self.label = None
        self.current_iid = None

    def show(self, text: str, x: int, y: int, iid: str):
        """Show tooltip text at screen coordinates for one row id."""
        if not text:
            self.hide()
            return
        if self.tip is None:
            self.tip = tk.Toplevel(self.widget)
            self.tip.wm_overrideredirect(True)
            self.tip.attributes("-topmost", True)
            self.label = ttk.Label(self.tip, text=text, padding=6, background="#ffffe0")
            self.label.pack()
        else:
            self.label.config(text=text)
        self.tip.geometry(f"+{x}+{y}")
        self.current_iid = iid

    def hide(self):
        """Hide tooltip window and reset current row tracking."""
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None
            self.label = None
        self.current_iid = None

class MappingEditorView(ttk.Frame):
    """Main mapping editor screen with column table and operation editor."""
    def __init__(
        self,
        parent,
        app_context,
        file_path=None,
        template_spec="v1.3",
        dataset_type=None,
        dataset_instance_name=None,
    ):
        """Initialize editor state from existing mapping or template defaults."""
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
        self.validation_defaults = default_validation_settings()
        
        self.spec = None
        self.current_column = None
        self.sample_df = None
        self.dirty = False
        self._suppress_dirty = False
        self._preview_sort_state = {}
        self._preview_base_headings = {}
        
        self._load_data()
        self._suppress_dirty = True
        self._create_ui()
        self._populate_tree()
        self._suppress_dirty = False
        self._update_save_state()
        self.app.protocol("WM_DELETE_WINDOW", self._on_close_window)

    def _load_data(self):
        """Load mapping file/spec and initialize mutable editor state."""
        if self.file_path and self.file_path.exists():
            try:
                config = load_mapping_config(self.file_path)
                self.spec_version = config.spec_version
                self.dataset_type = config.dataset_type
                self.dataset_instance_name = config.dataset_instance_name
                self.validation_defaults = config.validation_defaults or default_validation_settings()
                # Convert list to dict for editing
                self.rules_dict = {r.target: r for r in config.rules}
                for rule in self.rules_dict.values():
                    if getattr(rule, "steps", None) and len(rule.steps) > 1:
                        rule.steps[:] = rule.steps[:1]
            except Exception:
                # Fallback: allow opening mappings with empty/partial configs
                try:
                    raw = yaml.safe_load(self.file_path.read_text(encoding="utf-8")) or {}
                    if isinstance(raw, dict):
                        self.spec_version = raw.get("spec_version", self.spec_version)
                        self.dataset_type = raw.get("dataset_type", self.dataset_type)
                        self.dataset_instance_name = raw.get("dataset_instance_name", self.dataset_instance_name)
                        validation = raw.get("validation", {})
                        if isinstance(validation, dict):
                            self.validation_defaults = validation.get("default", {}) or default_validation_settings()
                        self.rules_dict = {}
                    else:
                        raise ValueError("Invalid mapping format")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to load mapping: {e}")
                    self.app.show_mappings_view()
                    return
        else:
            # New mapping - start empty
            self.rules_dict = {}
            self.validation_defaults = default_validation_settings()
            if not self.dataset_type:
                self.dataset_type = "CostAndUsage"
            if not self.file_path:
                self.file_path = self.mappings_dir / "mapping.yaml"
            self.dirty = True
        
        try:
            self.spec = load_focus_spec(self.spec_version, spec_dir=self.app.get_setting("spec_dir"))
        except Exception:
            # Fallback if spec load fails
            pass

    def _create_ui(self):
        """Build editor toolbar, metadata header, and split-pane layout."""
        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=5)
        ttk.Button(toolbar, text="Back", command=self.on_back).pack(side="left")
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=5)
        ttk.Button(toolbar, text="Load Sample Data", command=self.on_load_sample_data).pack(side="left")
        ttk.Button(toolbar, text="Validation Defaults", command=self.on_edit_validation_defaults).pack(side="left")
        self.save_btn = ttk.Button(toolbar, text="Save", command=self.on_save)
        self.save_btn.pack(side="right")

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

        def on_meta_change(event=None):
            update_required_indicators()
            self.mark_dirty()

        name_entry.bind("<KeyRelease>", on_meta_change)
        self.dataset_instance_entry.bind("<KeyRelease>", on_meta_change)

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

        self.tree = ttk.Treeview(
            left_frame,
            columns=("status", "feature_level", "data_type", "nullable"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("status", text="Status")
        self.tree.heading("feature_level", text="Feature Level")
        self.tree.heading("data_type", text="Data Type")
        self.tree.heading("nullable", text="Nullable")
        self.tree.column("status", width=60)
        self.tree.column("feature_level", width=110)
        self.tree.column("data_type", width=180)
        self.tree.column("nullable", width=80)
        self.tree.column("#0", width=200)
        self.tree.heading("#0", text="Column Name")
        
        scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.tree.bind("<<TreeviewSelect>>", self.on_column_select)
        self.tree.bind("<Motion>", self._on_tree_hover)
        self.tree.bind("<Leave>", self._on_tree_leave)
        self._tree_tooltip = _TreeTooltip(self.tree)
        self._col_descriptions: dict[str, str] = {}
        self._sort_state: dict[str, bool] = {}
        self._setup_tree_sorting()

        # Right: Column Details
        self.right_frame = ttk.Frame(paned)
        paned.add(self.right_frame, weight=3)
        
        # We'll dynamically populate right_frame based on selection

    def _populate_tree(self):
        """Populate left columns table from spec plus configured rules."""
        # Merge spec columns and existing config
        mapped_cols = {k for k, v in self.rules_dict.items() if getattr(v, "steps", [])}
        spec_cols = set()
        if self.spec:
            spec_cols = {c.name for c in self.spec.columns}
        
        all_cols = sorted(list(spec_cols | mapped_cols))
        
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)

        self._col_descriptions = {}
        for col in all_cols:
            spec_col = self.spec.get_column(col) if self.spec else None
            step = None
            if col in self.rules_dict and getattr(self.rules_dict[col], "steps", []):
                step = self.rules_dict[col].steps[0]
            is_valid = self._is_step_valid(col, step, spec_col)
            status = "-"
            if is_valid:
                op = step.get("op") if step else None
                status = f"Mapped ({op})" if op else "Mapped"
            feature_level = "Extension" if col.startswith("x_") else "-"
            data_type = "-"
            nullable = "-"
            description = ""
            if self.spec:
                if spec_col:
                    feature_level = spec_col.feature_level
                    data_type = spec_col.data_type
                    if spec_col.value_format:
                        data_type = f"{data_type} ({spec_col.value_format})"
                    nullable = "Yes" if spec_col.allows_nulls else "No"
                    description = spec_col.description or ""
                    if feature_level.lower() == "mandatory" and not is_valid:
                        status = "TBD"
            if feature_level == "Extension":
                rule = self.rules_dict.get(col)
                if rule and rule.data_type:
                    data_type = rule.data_type
                if rule and rule.description:
                    description = rule.description
                allow_nulls = None
                if rule and rule.validation:
                    allow_nulls = (rule.validation.get("nullable") or {}).get("allow_nulls")
                if allow_nulls is True:
                    nullable = "Yes"
                elif allow_nulls is False:
                    nullable = "No"
                else:
                    nullable = "Yes"
            self._col_descriptions[col] = description
            self.tree.insert(
                "",
                "end",
                iid=col,
                text=col,
                values=(status, feature_level, data_type, nullable),
                tags=("tbd",) if status == "TBD" else (),
            )
        self.tree.tag_configure("tbd", foreground="red")
        self._autosize_columns_tree()

    def _setup_tree_sorting(self):
        """Wire sortable headers for the columns tree."""
        for col in self.tree["columns"]:
            self.tree.heading(col, command=lambda c=col: self._sort_tree(c))
        self.tree.heading("#0", command=lambda: self._sort_tree("#0"))
        self._refresh_sort_headers()

    def _sort_tree(self, col: str):
        """Sort columns tree rows by the selected table column."""
        items = []
        for iid in self.tree.get_children(""):
            if col == "#0":
                value = self.tree.item(iid, "text")
            else:
                value = self.tree.set(iid, col)
            items.append((value, iid))

        reverse = not self._sort_state.get(col, False)
        items.sort(key=lambda v: (str(v[0]).lower()), reverse=reverse)

        for index, (_, iid) in enumerate(items):
            self.tree.move(iid, "", index)

        self._sort_state = {col: reverse}
        self._refresh_sort_headers()

    def _refresh_sort_headers(self):
        """Refresh sort arrow indicators in columns tree headers."""
        arrow_up = " ▲"
        arrow_down = " ▼"
        columns = list(self.tree["columns"]) + ["#0"]
        for col in columns:
            text = self.tree.heading(col, option="text")
            if text.endswith(arrow_up) or text.endswith(arrow_down):
                text = text[:-2]
            is_desc = self._sort_state.get(col)
            if is_desc is None:
                self.tree.heading(col, text=text)
            else:
                self.tree.heading(col, text=text + (arrow_down if is_desc else arrow_up))

    def _autosize_columns_tree(self):
        """Auto-fit columns tree widths to visible content within bounds."""
        # Resize columns to content with max bounds so long text does not dominate layout.
        font = tkfont.nametofont("TkDefaultFont")
        bounds = {
            "#0": (170, 360),
            "status": (90, 220),
            "feature_level": (110, 220),
            "data_type": (150, 360),
            "nullable": (80, 120),
        }
        headers = {
            "#0": "Column Name",
            "status": "Status",
            "feature_level": "Feature Level",
            "data_type": "Data Type",
            "nullable": "Nullable",
        }
        for col, (min_w, max_w) in bounds.items():
            width = font.measure(headers[col]) + 20
            for iid in self.tree.get_children(""):
                value = self.tree.item(iid, "text") if col == "#0" else self.tree.set(iid, col)
                width = max(width, font.measure(str(value)) + 20)
                if width >= max_w:
                    width = max_w
                    break
            self.tree.column(col, width=max(min_w, min(width, max_w)))

    def _on_tree_hover(self, event):
        """Show hovered column description tooltip in columns tree."""
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            self._tree_tooltip.hide()
            return
        if self._tree_tooltip.current_iid == row_id:
            return
        desc = self._col_descriptions.get(row_id, "")
        if not desc:
            self._tree_tooltip.hide()
            return
        x = self.tree.winfo_rootx() + 10
        y = self.tree.winfo_rooty() + event.y + 10
        self._tree_tooltip.show(desc, x, y, row_id)

    def _on_tree_leave(self, _event):
        """Hide tree tooltip when pointer leaves tree widget."""
        self._tree_tooltip.hide()

    def on_column_select(self, event):
        """Handle selection change and render selected column details."""
        selection = self.tree.selection()
        if not selection:
            return
        
        col_name = selection[0]
        self.current_column = col_name
        self._show_column_details(col_name)

    def _show_column_details(self, col_name):
        """Render right-side editor panel for selected target column."""
        self._suppress_dirty = True
        # Clear right frame
        for widget in self.right_frame.winfo_children():
            widget.destroy()

        # Header
        header = ttk.Frame(self.right_frame)
        header.pack(fill="x", pady=10)
        ttk.Label(header, text=f"Column: {col_name}", font=("Helvetica", 12, "bold")).pack(side="left")
        ttk.Button(header, text="Override Validation", command=lambda: self.on_edit_column_validation(col_name)).pack(side="right")

        spec_col = self.spec.get_column(col_name) if self.spec else None
        if spec_col and spec_col.description:
            desc = ttk.Label(self.right_frame, text=spec_col.description, wraplength=500, foreground="#444")
            desc.pack(anchor="w", padx=5, pady=(0, 8))

        # If not mapped, button to Initialize
        if col_name not in self.rules_dict:
            btn = ttk.Button(self.right_frame, text="Create Mapping Rule", 
                             command=lambda: self.create_rule(col_name))
            btn.pack(pady=20)
            self._suppress_dirty = False
            return

        rule = self.rules_dict[col_name]
        is_extension = spec_col is None

        if is_extension:
            meta_frame = ttk.LabelFrame(self.right_frame, text="Extension Metadata")
            meta_frame.pack(fill="x", padx=5, pady=(0, 6))
            ttk.Label(meta_frame, text="Data Type:").grid(row=0, column=0, sticky="w", padx=(6, 6), pady=4)
            data_type_var = tk.StringVar(value=rule.data_type or "String")
            type_options = ["String", "Decimal", "Date/Time", "Integer", "Boolean", "JSON"]
            data_type_cb = ttk.Combobox(
                meta_frame,
                textvariable=data_type_var,
                values=type_options,
                state="readonly",
                width=18,
            )
            data_type_cb.grid(row=0, column=1, sticky="w", pady=4)
            _set_tooltip(data_type_cb, "Data type for this extension column.")

            ttk.Label(meta_frame, text="Description:").grid(row=1, column=0, sticky="w", padx=(6, 6), pady=4)
            desc_var = tk.StringVar(value=rule.description or "")
            desc_entry = ttk.Entry(meta_frame, textvariable=desc_var, width=60)
            desc_entry.grid(row=1, column=1, sticky="w", pady=4)
            _set_tooltip(desc_entry, "Short description for this extension column.")

            ttk.Label(meta_frame, text="Nullable:").grid(row=2, column=0, sticky="w", padx=(6, 6), pady=4)
            nullable_val = None
            if rule.validation and isinstance(rule.validation, dict):
                nullable_val = (rule.validation.get("nullable") or {}).get("allow_nulls")
            if nullable_val is None:
                nullable_val = True
            nullable_var = tk.BooleanVar(value=bool(nullable_val))
            nullable_cb = ttk.Checkbutton(meta_frame, variable=nullable_var, text="Allow nulls")
            nullable_cb.grid(row=2, column=1, sticky="w", pady=4)
            _set_tooltip(nullable_cb, "Whether this extension column allows null values.")

            def on_ext_meta_change(*_):
                self._update_rule_meta(col_name, data_type_var.get().strip() or None, desc_var.get().strip() or None)

            data_type_cb.bind("<<ComboboxSelected>>", lambda _e: on_ext_meta_change())
            desc_entry.bind("<KeyRelease>", lambda _e: on_ext_meta_change())
            nullable_cb.configure(command=lambda: self._update_rule_nullable(col_name, nullable_var.get()))

        lf = ttk.LabelFrame(self.right_frame, text="Transformation Configuration")
        lf.pack(fill="both", expand=True, padx=5, pady=5)

        config_header = ttk.Frame(lf)
        config_header.pack(fill="x", padx=8, pady=(8, 4))
        config_header.columnconfigure(1, weight=1)
        ttk.Label(config_header, text="Operation Type:").grid(row=0, column=0, sticky="w")
        op_descriptions = self._operation_descriptions()
        op_options = self._available_operation_types(col_name)
        self.op_var = tk.StringVar(value=(rule.steps[0].get("op") if rule.steps else ""))
        op_cb = ttk.Combobox(config_header, textvariable=self.op_var, values=op_options, state="normal", width=24)
        make_combobox_filterable(op_cb, op_options)
        op_cb.grid(row=0, column=1, sticky="ew", padx=6)

        help_text_var = tk.StringVar(value=op_descriptions.get(self.op_var.get(), ""))
        op_help = ttk.Label(lf, textvariable=help_text_var, foreground="#555")
        op_help.pack(anchor="w", padx=10, pady=(0, 4))
        op_tip = _WidgetTooltip(op_cb)

        def current_op_tip_text() -> str:
            typed = (self.op_var.get() or "").strip()
            match = next((item for item in op_options if item.lower() == typed.lower()), None)
            if match:
                return op_descriptions.get(match, "Choose operation type.")
            return "Choose operation type (type to filter by prefix)."

        def show_op_tip(_event=None):
            op_tip.show(current_op_tip_text())

        def hide_op_tip(_event=None):
            op_tip.hide()

        def ensure_op_item_tooltips():
            """Bind hover tooltips to combobox dropdown list items."""
            try:
                popdown = op_cb.tk.call("ttk::combobox::PopdownWindow", str(op_cb))
                listbox = op_cb.nametowidget(f"{popdown}.f.l")
            except Exception:
                return
            if getattr(op_cb, "_op_item_tooltip_bound", False):
                return
            item_tip = _WidgetTooltip(listbox)

            def on_item_motion(event):
                try:
                    idx = listbox.nearest(event.y)
                    item = str(listbox.get(idx))
                except Exception:
                    item_tip.hide()
                    return
                text = op_descriptions.get(item, "")
                if text:
                    item_tip.show(text)
                else:
                    item_tip.hide()

            listbox.bind("<Motion>", on_item_motion, add="+")
            listbox.bind("<Leave>", lambda _e: item_tip.hide(), add="+")
            listbox.bind("<ButtonRelease-1>", lambda _e: item_tip.hide(), add="+")
            op_cb._op_item_tooltip_bound = True

        def apply_selected_op(op: str):
            step = {"op": op}
            self._set_single_step(col_name, step)
            self._render_op_config(config_container, col_name, step, spec_col)
            if hasattr(self, "preview_frame"):
                if op in {"const", "null"}:
                    self.preview_frame.pack_forget()
                else:
                    self.preview_frame.pack(fill="both", expand=False, padx=5, pady=5)
                    self._update_preview(col_name, step)

        def on_op_change(_event=None):
            typed = (self.op_var.get() or "").strip()
            if not typed:
                help_text_var.set("")
                return
            match = next((item for item in op_options if item.lower() == typed.lower()), None)
            if not match:
                help_text_var.set("Select one of the available operation types.")
                if op_cb.focus_get() == op_cb:
                    show_op_tip()
                return
            if self.op_var.get() != match:
                self.op_var.set(match)
            desc = op_descriptions.get(match, "")
            help_text_var.set(desc)
            existing = rule.steps[0] if rule.steps and rule.steps[0].get("op") == match else None
            if existing is None:
                apply_selected_op(match)
            if op_cb.focus_get() == op_cb:
                show_op_tip()

        def clear_op():
            self.op_var.set("")
            help_text_var.set("")
            self._set_single_step(col_name, None)
            for w in config_container.winfo_children():
                w.destroy()
            if hasattr(self, "preview_frame"):
                self.preview_frame.pack_forget()
            hide_op_tip()

        op_cb.bind("<Enter>", show_op_tip)
        op_cb.bind("<Leave>", hide_op_tip)
        op_cb.bind("<FocusIn>", show_op_tip)
        op_cb.bind("<FocusOut>", hide_op_tip)
        op_cb.bind("<Button-1>", lambda _e: op_cb.after_idle(ensure_op_item_tooltips), add="+")
        op_cb.bind("<Down>", lambda _e: op_cb.after_idle(ensure_op_item_tooltips), add="+")
        op_cb.bind("<KeyRelease>", lambda _e: op_cb.after_idle(ensure_op_item_tooltips), add="+")
        op_cb.bind("<<ComboboxSelected>>", on_op_change)
        op_cb.bind("<KeyRelease>", on_op_change, add="+")
        ttk.Button(config_header, text="Clear", command=clear_op).grid(row=0, column=2, padx=(0, 6))

        # Config container
        config_container = ttk.Frame(lf)
        config_container.pack(fill="both", expand=True, padx=8, pady=8)

        if rule.steps:
            self._render_op_config(config_container, col_name, rule.steps[0], spec_col)

        if self.sample_df is not None:
            # Preview panel
            self.preview_frame = ttk.LabelFrame(self.right_frame, text="Preview (first 100 rows)")
            self.preview_frame.pack(fill="both", expand=False, padx=5, pady=5)
            self.preview_tree = ttk.Treeview(
                self.preview_frame,
                columns=("index", "value"),
                show="headings",
                height=12,
            )
            self.preview_tree.heading("index", text="#", command=lambda: self._sort_preview_tree("index"))
            self.preview_tree.heading("value", text="Value", command=lambda: self._sort_preview_tree("value"))
            self.preview_tree.column("index", width=48, anchor="e", stretch=False)
            self.preview_tree.column("value", width=300, anchor="center")
            self._preview_base_headings = {"index": "#", "value": "Value"}
            self._preview_sort_state = {}
            self._refresh_preview_sort_headers()
            preview_scroll = ttk.Scrollbar(self.preview_frame, orient="vertical", command=self.preview_tree.yview)
            self.preview_tree.configure(yscrollcommand=preview_scroll.set)
            self.preview_tree.pack(side="left", fill="both", expand=True)
            preview_scroll.pack(side="right", fill="y")
            self.preview_error = ttk.Label(self.preview_frame, text="", foreground="red")
            self.preview_error.pack(anchor="w", padx=6, pady=(4, 0))

            if rule.steps:
                if rule.steps[0].get("op") in {"const", "null"}:
                    self.preview_frame.pack_forget()
                else:
                    self._update_preview(col_name, rule.steps[0])
        self._suppress_dirty = False

    def _sort_preview_tree(self, column: str):
        """Sort per-column preview table by selected column."""
        if not hasattr(self, "preview_tree"):
            return
        items = [(self.preview_tree.set(iid, column), iid) for iid in self.preview_tree.get_children("")]
        reverse = not self._preview_sort_state.get(column, False)
        if column == "index":
            def key_fn(v):
                try:
                    return int(v[0])
                except Exception:
                    return 0
        else:
            key_fn = lambda v: str(v[0]).lower()
        items.sort(key=key_fn, reverse=reverse)
        for idx, (_, iid) in enumerate(items):
            self.preview_tree.move(iid, "", idx)
        self._preview_sort_state = {column: reverse}
        self._refresh_preview_sort_headers()

    def _refresh_preview_sort_headers(self):
        """Refresh sort arrow indicators in preview table headers."""
        if not hasattr(self, "preview_tree"):
            return
        arrow_up = " ▲"
        arrow_down = " ▼"
        for col, label in self._preview_base_headings.items():
            if self._preview_sort_state.get(col) is None:
                self.preview_tree.heading(col, text=label)
            else:
                self.preview_tree.heading(col, text=label + (arrow_down if self._preview_sort_state[col] else arrow_up))

    def _autosize_preview_tree_columns(self):
        """Auto-fit preview table column widths within configured bounds."""
        if not hasattr(self, "preview_tree"):
            return
        font = tkfont.nametofont("TkDefaultFont")
        bounds = {"index": (44, 72), "value": (160, 540)}
        headers = {"index": "#", "value": "Value"}
        for col, (min_w, max_w) in bounds.items():
            width = font.measure(headers[col]) + 20
            for iid in self.preview_tree.get_children(""):
                width = max(width, font.measure(str(self.preview_tree.set(iid, col))) + 20)
                if width >= max_w:
                    width = max_w
                    break
            self.preview_tree.column(col, width=max(min_w, min(width, max_w)))

    def _pick_operation_type(self, current: str | None = None) -> str | None:
        """Open operation picker and return selected operation name."""
        options = self._available_operation_types(self.current_column or "")
        descriptions = self._operation_descriptions()
        picker = _OpPicker(self, options, descriptions)
        return picker.show("Add Operation", current=current)

    def _operation_descriptions(self) -> dict[str, str]:
        """Return operation descriptions used by tooltips/help text."""
        return {
            "from_column": "Use a single input column as the value.",
            "const": "Use a constant value for all rows.",
            "null": "Set all values to null.",
            "coalesce": "Use the first non-null value from a list of columns.",
            "map_values": "Map source values using a lookup table.",
            "concat": "Concatenate multiple columns into one string.",
            "math": "Compute arithmetic across columns/const values.",
            "when": "Conditional assignment based on a column value.",
            "sql": "DuckDB SQL expression or query.",
            "pandas_expr": "Pandas expression evaluated against the DataFrame.",
        }

    def _available_operation_types(self, col_name: str) -> list[str]:
        """Return operations allowed for the selected column."""
        options = [
            "from_column",
            "const",
            "null",
            "coalesce",
            "map_values",
            "concat",
            "math",
            "when",
            "sql",
            "pandas_expr",
        ]
        if self.spec and col_name:
            spec_col = self.spec.get_column(col_name)
            if spec_col and not spec_col.allows_nulls and "null" in options:
                options.remove("null")
        return options

    def _set_single_step(self, col_name: str, step: dict | None) -> None:
        """Set (or clear) the single supported transformation step for target."""
        if col_name not in self.rules_dict:
            self.rules_dict[col_name] = MappingRule(target=col_name, steps=[])
        rule = self.rules_dict[col_name]
        if step is None:
            rule.steps.clear()
        else:
            rule.steps[:] = [step]
        self.mark_dirty()
        self._set_status_for_column(col_name)

    def _update_rule_validation(self, col_name: str, validation: dict | None) -> None:
        """Update per-column validation override in editor state."""
        rule = self.rules_dict.get(col_name)
        if not rule:
            rule = MappingRule(target=col_name, steps=[])
        self.rules_dict[col_name] = MappingRule(
            target=rule.target,
            steps=rule.steps,
            description=rule.description,
            data_type=rule.data_type,
            validation=validation,
        )
        if self.tree.exists(col_name) and (self.spec is None or self.spec.get_column(col_name) is None):
            allow_nulls = None
            if validation:
                allow_nulls = (validation.get("nullable") or {}).get("allow_nulls")
            if allow_nulls is True:
                self.tree.set(col_name, "nullable", "Yes")
            elif allow_nulls is False:
                self.tree.set(col_name, "nullable", "No")
            else:
                self.tree.set(col_name, "nullable", "Yes")
        self.mark_dirty()

    def _update_rule_meta(self, col_name: str, data_type: str | None, description: str | None) -> None:
        """Update extension rule metadata fields."""
        rule = self.rules_dict.get(col_name)
        if not rule:
            rule = MappingRule(target=col_name, steps=[])
        self.rules_dict[col_name] = MappingRule(
            target=rule.target,
            steps=rule.steps,
            description=description,
            data_type=data_type,
            validation=rule.validation,
        )
        if self.tree.exists(col_name):
            self.tree.set(col_name, "data_type", data_type or "-")
        if description is not None:
            self._col_descriptions[col_name] = description
        self.mark_dirty()

    def _update_rule_nullable(self, col_name: str, allow_nulls: bool) -> None:
        """Update nullable override for extension rule and table display."""
        rule = self.rules_dict.get(col_name)
        if not rule:
            rule = MappingRule(target=col_name, steps=[])
        validation = dict(rule.validation or {})
        nullable = dict(validation.get("nullable") or {})
        nullable["allow_nulls"] = bool(allow_nulls)
        validation["nullable"] = nullable
        self.rules_dict[col_name] = MappingRule(
            target=rule.target,
            steps=rule.steps,
            description=rule.description,
            data_type=rule.data_type,
            validation=validation,
        )
        if self.tree.exists(col_name):
            self.tree.set(col_name, "nullable", "Yes" if allow_nulls else "No")
        self.mark_dirty()
    def _edit_validation_dialog(self, title: str, initial: dict | None, data_type: str | None = None, allow_remove: bool = False) -> dict | None:
        """Open validation editor dialog and return updated settings payload."""
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.geometry("620x700")
        dialog.resizable(True, True)

        content = ttk.Frame(dialog, padding=10)
        content.pack(fill="both", expand=True)
        initial = initial or {}
        is_defaults = "Defaults" in title

        defaults = {
            "mode": "permissive",
            "datetime": {"format": ""},
            "decimal": {
                "precision": None,
                "scale": None,
                "integer_only": False,
                "min": None,
                "max": None,
            },
            "string": {
                "min_length": None,
                "max_length": None,
                "allow_empty": True,
                "trim": True,
            },
            "json": {"object_only": False},
            "allowed_values": {"case_insensitive": False},
            "nullable": {"allow_nulls": None},
            "presence": {"enforce": True},
        }

        def get_nested(src, *keys, default=None):
            cur = src
            for k in keys:
                if not isinstance(cur, dict) or k not in cur:
                    return default
                cur = cur[k]
            return cur

        validators: list[callable] = []

        def add_row(parent, row, label):
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)

        def add_star(parent, row):
            star = ttk.Label(parent, text="*", foreground="red")
            star.grid(row=row, column=2, sticky="w", padx=(6, 0))
            star.grid_remove()
            return star

        def set_star(star, show, reason):
            if show:
                star.grid()
                _set_tooltip(star, reason)
            else:
                star.grid_remove()

        def combo_row(parent, row, label, values, initial_value, required=False):
            add_row(parent, row, label)
            cb = ttk.Combobox(parent, values=values, state="readonly", width=14)
            cb.grid(row=row, column=1, sticky="w", pady=2)
            cb.set(initial_value)
            star = add_star(parent, row)
            if required:
                validators.append(lambda cb=cb, star=star: validate_required(cb.get(), star))
            return cb, star

        def entry_row(parent, row, label, initial_value, required=False, int_only=False):
            add_row(parent, row, label)
            entry = ttk.Entry(parent, width=20)
            entry.grid(row=row, column=1, sticky="w", pady=2)
            if initial_value is not None:
                entry.insert(0, str(initial_value))
            star = add_star(parent, row)
            if required or int_only:
                validators.append(lambda e=entry, s=star, req=required, io=int_only: validate_entry(e, s, req, io))
            return entry, star

        def check_row(parent, row, label, initial_value):
            add_row(parent, row, label)
            var = tk.BooleanVar(value=bool(initial_value))
            cb = ttk.Checkbutton(parent, variable=var)
            cb.grid(row=row, column=1, sticky="w", pady=2)
            return var

        def validate_required(value, star):
            show = not bool(str(value).strip())
            set_star(star, show, "Please select a value.")
            return not show

        def validate_entry(entry, star, required, int_only):
            raw = entry.get().strip()
            if required and not raw:
                set_star(star, True, "Required.")
                return False
            if raw and int_only:
                try:
                    int(raw)
                except ValueError:
                    set_star(star, True, "Must be an integer.")
                    return False
            set_star(star, False, "")
            return True

        # Common fields
        common = ttk.LabelFrame(content, text="Common")
        common.pack(fill="x", pady=6)
        common.columnconfigure(1, weight=1)
        mode_init = initial.get("mode") or (defaults["mode"] if is_defaults else "")
        mode_cb, mode_star = combo_row(common, 0, "Mode", ["permissive", "strict"], mode_init, required=True)

        nullable_init = get_nested(initial, "nullable", "allow_nulls", default=(defaults["nullable"]["allow_nulls"] if is_defaults else None))
        allowed_init = get_nested(initial, "allowed_values", "case_insensitive", default=(defaults["allowed_values"]["case_insensitive"] if is_defaults else None))
        presence_init = get_nested(initial, "presence", "enforce", default=(defaults["presence"]["enforce"] if is_defaults else None))
        nullable_cb, _ = combo_row(
            common,
            1,
            "Nullable override",
            ["<follow spec>", "true", "false"],
            "<follow spec>" if nullable_init is None else ("true" if nullable_init else "false"),
            required=True,
        )
        allowed_ci_var = check_row(common, 2, "Allowed values case-insensitive", allowed_init if allowed_init is not None else defaults["allowed_values"]["case_insensitive"])
        presence_var = check_row(common, 3, "Presence enforce", presence_init if presence_init is not None else defaults["presence"]["enforce"])

        dtype = (data_type or "").strip().lower()
        show_all = not dtype

        # Datetime
        dt_frame = None
        dt_format_entry = None
        if show_all or dtype in {"datetime", "date/time"}:
            dt_frame = ttk.LabelFrame(content, text="Datetime")
            dt_frame.pack(fill="x", pady=6)
            dt_frame.columnconfigure(1, weight=1)
            dt_format_entry, dt_star = entry_row(
                dt_frame,
                0,
                "Format",
                get_nested(initial, "datetime", "format", default=(defaults["datetime"]["format"] if is_defaults else "")),
                required=False,
            )

        # Decimal
        dec_frame = None
        dec_prec_entry = dec_scale_entry = dec_min_entry = dec_max_entry = None
        dec_int_var = None
        if show_all or dtype == "decimal":
            dec_frame = ttk.LabelFrame(content, text="Decimal")
            dec_frame.pack(fill="x", pady=6)
            dec_frame.columnconfigure(1, weight=1)
            dec_prec_entry, dec_prec_star = entry_row(dec_frame, 0, "Precision", get_nested(initial, "decimal", "precision", default=(defaults["decimal"]["precision"] if is_defaults else None)), int_only=True)
            dec_scale_entry, dec_scale_star = entry_row(dec_frame, 1, "Scale", get_nested(initial, "decimal", "scale", default=(defaults["decimal"]["scale"] if is_defaults else None)), int_only=True)
            dec_min_entry, dec_min_star = entry_row(dec_frame, 2, "Min", get_nested(initial, "decimal", "min", default=(defaults["decimal"]["min"] if is_defaults else None)), int_only=True)
            dec_max_entry, dec_max_star = entry_row(dec_frame, 3, "Max", get_nested(initial, "decimal", "max", default=(defaults["decimal"]["max"] if is_defaults else None)), int_only=True)
            dec_int_val = get_nested(initial, "decimal", "integer_only", default=(defaults["decimal"]["integer_only"] if is_defaults else None))
            dec_int_var = check_row(dec_frame, 4, "Integer only", dec_int_val if dec_int_val is not None else defaults["decimal"]["integer_only"])

        # String
        str_frame = None
        str_min_entry = str_max_entry = None
        str_allow_empty_cb = str_trim_cb = None
        if show_all or dtype == "string":
            str_frame = ttk.LabelFrame(content, text="String")
            str_frame.pack(fill="x", pady=6)
            str_frame.columnconfigure(1, weight=1)
            str_min_entry, str_min_star = entry_row(str_frame, 0, "Min length", get_nested(initial, "string", "min_length", default=(defaults["string"]["min_length"] if is_defaults else None)), int_only=True)
            str_max_entry, str_max_star = entry_row(str_frame, 1, "Max length", get_nested(initial, "string", "max_length", default=(defaults["string"]["max_length"] if is_defaults else None)), int_only=True)
            allow_empty_val = get_nested(initial, "string", "allow_empty", default=(defaults["string"]["allow_empty"] if is_defaults else None))
            trim_val = get_nested(initial, "string", "trim", default=(defaults["string"]["trim"] if is_defaults else None))
            str_allow_empty_var = check_row(str_frame, 2, "Allow empty", allow_empty_val if allow_empty_val is not None else defaults["string"]["allow_empty"])
            str_trim_var = check_row(str_frame, 3, "Trim", trim_val if trim_val is not None else defaults["string"]["trim"])

        # JSON
        json_frame = None
        json_obj_var = None
        if show_all or dtype == "json":
            json_frame = ttk.LabelFrame(content, text="JSON")
            json_frame.pack(fill="x", pady=6)
            json_frame.columnconfigure(1, weight=1)
            obj_val = get_nested(initial, "json", "object_only", default=(defaults["json"]["object_only"] if is_defaults else None))
            json_obj_var = check_row(json_frame, 0, "Object only", obj_val if obj_val is not None else defaults["json"]["object_only"])

        result = [None]

        def parse_int(entry):
            raw = entry.get().strip()
            if not raw:
                return None
            try:
                return int(raw)
            except ValueError:
                return None

        def validate_datetime_format(value: str) -> bool:
            if not value:
                return True
            if "%" not in value:
                return False
            required = ("%Y", "%m", "%d")
            if not all(tok in value for tok in required):
                return False
            try:
                datetime.now(timezone.utc).strftime(value)
            except Exception:
                return False
            return True

        def validate_all():
            ok = True
            for fn in validators:
                if not fn():
                    ok = False
            # datetime format
            if dt_format_entry is not None:
                valid = validate_datetime_format(dt_format_entry.get().strip())
                if not valid:
                    set_star(dt_star, True, "Invalid datetime format. Use strftime directives (ISO-like).")
                    ok = False
                else:
                    set_star(dt_star, False, "")
            # min/max check
            if dec_min_entry is not None and dec_max_entry is not None:
                min_val = parse_int(dec_min_entry)
                max_val = parse_int(dec_max_entry)
                if min_val is not None and min_val < 0:
                    set_star(dec_min_star, True, "Min must be >= 0.")
                    ok = False
                if max_val is not None and max_val < 0:
                    set_star(dec_max_star, True, "Max must be >= 0.")
                    ok = False
                if min_val is not None and max_val is not None and max_val < min_val:
                    set_star(dec_min_star, True, "Min must be <= Max.")
                    set_star(dec_max_star, True, "Max must be >= Min.")
                    ok = False
            # precision/scale check
            if dec_prec_entry is not None and dec_scale_entry is not None:
                prec = parse_int(dec_prec_entry)
                scale = parse_int(dec_scale_entry)
                if prec is not None and prec < 0:
                    set_star(dec_prec_star, True, "Precision must be >= 0.")
                    ok = False
                if scale is not None and scale < 0:
                    set_star(dec_scale_star, True, "Scale must be >= 0.")
                    ok = False
                if prec is not None and scale is not None and scale > prec:
                    set_star(dec_scale_star, True, "Scale must be <= Precision.")
                    ok = False
            return ok

        # duplicate validate_all removed

        def on_ok():
            if not validate_all():
                messagebox.showwarning("Invalid", "Please fix validation errors before continuing.", parent=dialog)
                return
            out: dict = {}
            mode = mode_cb.get().strip()
            if mode:
                out["mode"] = mode

            nullable_val = nullable_cb.get().strip().lower()
            if nullable_val == "true":
                out.setdefault("nullable", {})["allow_nulls"] = True
            elif nullable_val == "false":
                out.setdefault("nullable", {})["allow_nulls"] = False

            out.setdefault("allowed_values", {})["case_insensitive"] = bool(allowed_ci_var.get())

            out.setdefault("presence", {})["enforce"] = bool(presence_var.get())

            if dt_format_entry is not None:
                dt_fmt = dt_format_entry.get().strip()
                if dt_fmt:
                    out.setdefault("datetime", {})["format"] = dt_fmt

            if dec_prec_entry is not None:
                prec = parse_int(dec_prec_entry)
                if prec is not None:
                    out.setdefault("decimal", {})["precision"] = prec
            if dec_scale_entry is not None:
                scale = parse_int(dec_scale_entry)
                if scale is not None:
                    out.setdefault("decimal", {})["scale"] = scale
            if dec_min_entry is not None:
                min_val = parse_int(dec_min_entry)
                if min_val is not None:
                    out.setdefault("decimal", {})["min"] = min_val
            if dec_max_entry is not None:
                max_val = parse_int(dec_max_entry)
                if max_val is not None:
                    out.setdefault("decimal", {})["max"] = max_val
            if dec_int_var is not None:
                out.setdefault("decimal", {})["integer_only"] = bool(dec_int_var.get())

            if str_min_entry is not None:
                smin = parse_int(str_min_entry)
                if smin is not None:
                    out.setdefault("string", {})["min_length"] = smin
            if str_max_entry is not None:
                smax = parse_int(str_max_entry)
                if smax is not None:
                    out.setdefault("string", {})["max_length"] = smax
            if str_allow_empty_var is not None:
                out.setdefault("string", {})["allow_empty"] = bool(str_allow_empty_var.get())
            if str_trim_var is not None:
                out.setdefault("string", {})["trim"] = bool(str_trim_var.get())

            if json_obj_var is not None:
                out.setdefault("json", {})["object_only"] = bool(json_obj_var.get())

            result[0] = out
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btns = ttk.Frame(content)
        btns.pack(fill="x", pady=(12, 0))
        if allow_remove:
            ttk.Button(btns, text="Remove Override", command=lambda: set_remove()).pack(side="left")
        ttk.Button(btns, text="Cancel", command=on_cancel).pack(side="right")
        ttk.Button(btns, text="OK", command=on_ok).pack(side="right", padx=6)

        def set_remove():
            result[0] = "__REMOVE__"
            dialog.destroy()

        dialog.transient(self)
        dialog.grab_set()
        dialog.update_idletasks()
        w = dialog.winfo_width()
        h = dialog.winfo_height()
        x = self.winfo_rootx() + (self.winfo_width() - w) // 2
        y = self.winfo_rooty() + (self.winfo_height() - h) // 2
        dialog.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")
        self.wait_window(dialog)
        return result[0]

    def on_edit_validation_defaults(self):
        """Open dialog to edit global validation defaults."""
        updated = self._edit_validation_dialog("Validation Defaults", self.validation_defaults)
        if updated is None:
            return
        self.validation_defaults = updated
        self.mark_dirty()

    def on_edit_column_validation(self, col_name: str):
        """Open dialog to edit validation override for one target column."""
        rule = self.rules_dict.get(col_name)
        current = rule.validation if rule else None
        data_type = None
        if self.spec:
            spec_col = self.spec.get_column(col_name)
            if spec_col and spec_col.data_type:
                data_type = spec_col.data_type
        if data_type is None and rule and rule.data_type:
            data_type = rule.data_type
        base = self.validation_defaults or default_validation_settings()
        merged = _deep_merge(base, current or {})
        updated = self._edit_validation_dialog(
            f"Validation Override: {col_name}",
            merged,
            data_type=data_type,
            allow_remove=True,
        )
        if updated is None:
            return
        if updated == "__REMOVE__":
            self._update_rule_validation(col_name, None)
            return
        diff = _deep_diff(base, updated or {})
        self._update_rule_validation(col_name, diff or None)

    def _validate_const_json_value(self, raw: str, spec_col):
        """Validate JSON const value against generic/spec-specific format rules."""
        text = (raw or "").strip()
        if not text:
            return False, "Required", False
        try:
            json.loads(text)
        except Exception as e:
            return False, f"Invalid JSON: {e}", False

        value_format = ""
        if spec_col and getattr(spec_col, "value_format", None):
            value_format = str(spec_col.value_format).strip().lower()

        if "key-value" in value_format or "keyvalue" in value_format:
            ok, msg = validate_key_value_format(text)
            return ok, (msg or ""), False
        if "json object" in value_format or "jsonobject" in value_format:
            ok, msg = validate_json_object_format(text)
            # CLI treats warnings as valid input for wizard.
            if ok and msg and "warning" in msg.lower():
                return True, msg, True
            return ok, (msg or ""), False
        return True, "", False

    def _is_step_valid(self, col_name: str, step: dict | None, spec_col) -> bool:
        """Validate one configured step for UI status and save eligibility."""
        if not step or not isinstance(step, dict):
            return False
        op = step.get("op")
        if not op:
            return False

        if op == "from_column":
            return bool(str(step.get("column", "")).strip())

        if op == "const":
            allowed = list(spec_col.allowed_values) if spec_col and spec_col.allowed_values else []
            allow_nullable_string = bool(
                spec_col
                and spec_col.data_type
                and spec_col.data_type.strip().lower() == "string"
                and spec_col.allows_nulls
            )
            value = step.get("value")
            if allowed:
                if value is None:
                    return allow_nullable_string
                return str(value) in allowed
            if allow_nullable_string:
                return True
            if (
                spec_col
                and spec_col.data_type
                and spec_col.data_type.strip().lower() == "json"
            ):
                if isinstance(value, (dict, list)):
                    value_str = json.dumps(value)
                    ok, _, _ = self._validate_const_json_value(value_str, spec_col)
                    return ok
                try:
                    value_str = str(value or "").strip()
                    ok, _, _ = self._validate_const_json_value(value_str, spec_col)
                    return ok
                except Exception:
                    return False
            return bool(str(value or "").strip())

        if op == "null":
            return True

        if op == "coalesce":
            return bool(step.get("columns"))

        if op == "map_values":
            mapping = step.get("mapping") or {}
            if not bool(str(step.get("column", "")).strip()) or not mapping:
                return False
            for k, v in mapping.items():
                if k == v:
                    return False
            return True

        if op == "concat":
            return bool(step.get("columns"))

        if op == "math":
            operator = step.get("operator")
            operands = step.get("operands")
            if operator not in {"add", "sub", "mul", "div"}:
                return False
            if not isinstance(operands, list) or len(operands) != 2:
                return False
            for operand in operands:
                if "column" in operand:
                    if not str(operand.get("column", "")).strip():
                        return False
                    continue
                if "const" in operand:
                    val = operand.get("const")
                    if val is None:
                        return False
                    if isinstance(val, (int, float)):
                        continue
                    if not str(val).strip():
                        return False
                    continue
                return False
            return True

        if op == "when":
            return (
                bool(str(step.get("column", "")).strip())
                and bool(str(step.get("value", "")).strip())
                and bool(str(step.get("then", "")).strip())
            )

        if op == "pandas_expr":
            return bool(str(step.get("expr", "")).strip())

        if op == "sql":
            return bool(str(step.get("expr") or step.get("query") or "").strip())

        return False

    def _render_op_config(self, parent, col_name: str, step: dict, spec_col) -> None:
        """Render operation-specific configuration controls for selected column."""
        for w in parent.winfo_children():
            w.destroy()

        op = step.get("op")
        if not op:
            return

        def add_label(text: str, tooltip: str | None = None, required: bool = False):
            row = ttk.Frame(parent)
            row.pack(anchor="w", pady=(4, 0), fill="x")
            lbl = ttk.Label(row, text=text)
            lbl.pack(side="left")
            star = None
            if required:
                star = _create_star(row, "Required", side="left", padx=(4, 0))
            if tooltip:
                _set_tooltip(lbl, tooltip)
            return lbl, star, row

        def add_entry(key: str, tooltip: str, multiline: bool = False, width: int = 40, required: bool = False, label_text: str | None = None, use_column_picker: bool = False):
            _, label_star, _ = add_label(label_text or f"{key}:", tooltip, required=required)
            if use_column_picker and self.sample_df is not None:
                row = ttk.Frame(parent)
                row.pack(fill="x", pady=(0, 6))
                cb_values = [str(c) for c in self.sample_df.columns]
                cb = ttk.Combobox(row, values=cb_values, state="normal", width=width)
                make_combobox_filterable(cb, cb_values)
                cb.pack(side="left", fill="x", expand=True)
                input_star = _create_star(row, "Required", side="left", padx=(6, 0)) if required else None
                if key in step and step[key] is not None:
                    cb.set(str(step[key]))

                def on_select(_event=None):
                    val = cb.get()
                    step[key] = val
                    if required:
                        show = not bool(val.strip())
                        _set_star_visible(label_star, show, "Required")
                        _set_star_visible(input_star, show, "Required")
                    self.mark_dirty()
                    self._set_status_for_column(col_name)
                    self._update_preview(col_name, step)
                cb.bind("<<ComboboxSelected>>", on_select)
                cb.bind("<KeyRelease>", on_select, add="+")
                _set_tooltip(cb, tooltip)
                on_select()
                return cb
            if multiline:
                frame = ttk.Frame(parent)
                frame.pack(fill="both", expand=True, pady=(0, 6))
                text = tk.Text(frame, height=4, width=width)
                yscroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
                text.configure(yscrollcommand=yscroll.set)
                text.pack(side="left", fill="both", expand=True)
                yscroll.pack(side="right", fill="y")
                input_star = _create_star(frame, "Required", side="left", padx=(6, 0)) if required else None
                if key in step and step[key] is not None:
                    text.insert("1.0", str(step[key]))

                def on_change(_event=None):
                    val = text.get("1.0", "end-1c")
                    step[key] = val
                    if required:
                        show = not bool(val.strip())
                        _set_star_visible(label_star, show, "Required")
                        _set_star_visible(input_star, show, "Required")
                    self.mark_dirty()
                    self._set_status_for_column(col_name)
                    self._update_preview(col_name, step)
                text.bind("<KeyRelease>", on_change)
                _set_tooltip(text, tooltip)
                on_change()
                return text
            row = ttk.Frame(parent)
            row.pack(fill="x", pady=(0, 6))
            entry = ttk.Entry(row, width=width)
            entry.pack(side="left", fill="x", expand=True)
            input_star = _create_star(row, "Required", side="left", padx=(6, 0)) if required else None
            if key in step and step[key] is not None:
                entry.insert(0, str(step[key]))

            def on_change(_event=None):
                val = entry.get()
                step[key] = val
                if required:
                    show = not bool(val.strip())
                    _set_star_visible(label_star, show, "Required")
                    _set_star_visible(input_star, show, "Required")
                self.mark_dirty()
                self._set_status_for_column(col_name)
                self._update_preview(col_name, step)
            entry.bind("<KeyRelease>", on_change)
            _set_tooltip(entry, tooltip)
            on_change()
            return entry

        def add_columns_field(key: str, tooltip: str, required: bool = False):
            _, label_star, _ = add_label(f"{key}:", tooltip, required=required)
            frame = ttk.Frame(parent)
            frame.pack(fill="x", pady=(0, 6))
            listbox = tk.Listbox(frame, height=4)
            listbox.pack(side="left", fill="both", expand=True)
            _set_tooltip(listbox, tooltip)
            btns = ttk.Frame(frame)
            btns.pack(side="left", padx=6, fill="y")

            if self.sample_df is not None:
                entry_values = [str(c) for c in self.sample_df.columns]
                entry = ttk.Combobox(btns, values=entry_values, state="normal", width=16)
                make_combobox_filterable(entry, entry_values)
            else:
                entry = ttk.Entry(btns, width=16)
            entry.pack(pady=(0, 4))
            _set_tooltip(entry, "Column name to add.")
            ttk.Button(btns, text="+", width=3, command=lambda: add_item()).pack(pady=(0, 4))
            ttk.Button(btns, text="-", width=3, command=lambda: remove_item()).pack()
            ttk.Button(btns, text="↑", width=3, command=lambda: move_item(-1)).pack(pady=(6, 0))
            ttk.Button(btns, text="↓", width=3, command=lambda: move_item(1)).pack()

            input_star = _create_star(frame, "Required", side="left", padx=(6, 0)) if required else None

            def sync_list():
                cols = list(listbox.get(0, "end"))
                step[key] = cols
                if required:
                    show = not bool(cols)
                    _set_star_visible(label_star, show, "Required")
                    _set_star_visible(input_star, show, "Required")
                self.mark_dirty()
                self._set_status_for_column(col_name)
                self._update_preview(col_name, step)

            def add_item():
                val = entry.get().strip()
                if not val:
                    return
                existing = set(listbox.get(0, "end"))
                if val in existing:
                    return
                listbox.insert("end", val)
                if isinstance(entry, ttk.Entry):
                    entry.delete(0, "end")
                sync_list()

            def remove_item():
                sel = listbox.curselection()
                if not sel:
                    return
                listbox.delete(sel[0])
                sync_list()

            def move_item(delta: int):
                sel = listbox.curselection()
                if not sel:
                    return
                idx = sel[0]
                new_idx = idx + delta
                if new_idx < 0 or new_idx >= listbox.size():
                    return
                val = listbox.get(idx)
                listbox.delete(idx)
                listbox.insert(new_idx, val)
                listbox.selection_set(new_idx)
                sync_list()

            if key in step and isinstance(step[key], list):
                for col in step[key]:
                    listbox.insert("end", col)
            sync_list()
            return listbox

        if op == "from_column":
            add_entry("column", "Input column name to use as the value.", required=True, use_column_picker=True)
            return

        if op == "const":
            allowed = list(spec_col.allowed_values) if spec_col and spec_col.allowed_values else []
            data_type = spec_col.data_type if spec_col and spec_col.data_type else "-"
            value_format = spec_col.value_format if spec_col and spec_col.value_format else None
            label_hint = f"value (Type: {data_type}"
            if value_format:
                label_hint += f", Format: {value_format}"
            label_hint += "):"
            allow_nullable_string = bool(
                spec_col
                and spec_col.data_type
                and spec_col.data_type.strip().lower() == "string"
                and spec_col.allows_nulls
            )
            if allowed:
                if spec_col and spec_col.allows_nulls:
                    allowed = allowed + ["null"]
                _, label_star, _ = add_label(label_hint, "Constant value (choose from allowed values).", required=not allow_nullable_string)
                row = ttk.Frame(parent)
                row.pack(fill="x", pady=(0, 6))
                cb = ttk.Combobox(row, values=allowed, state="readonly")
                cb.pack(side="left", fill="x", expand=True)
                input_star = None
                if not allow_nullable_string:
                    input_star = _create_star(row, "Required", side="left", padx=(6, 0))
                cur = step.get("value")
                if cur is None:
                    cb.set("null" if "null" in allowed else allowed[0])
                else:
                    cb.set(str(cur))

                def on_select(_event=None):
                    val = cb.get()
                    step["value"] = None if val == "null" else val
                    if not allow_nullable_string:
                        show = not bool(val)
                        _set_star_visible(label_star, show, "Required")
                        _set_star_visible(input_star, show, "Required")
                    self.mark_dirty()
                    self._set_status_for_column(col_name)
                cb.bind("<<ComboboxSelected>>", on_select)
                tip = _WidgetTooltip(cb)
                cb.bind("<Enter>", lambda _e: tip.show("Constant value (choose from allowed values)."))
                cb.bind("<Leave>", lambda _e: tip.hide())
                on_select()
            elif data_type.strip().lower() == "json":
                _, label_star, _ = add_label(
                    label_hint,
                    "Constant JSON value to use for all rows.",
                    required=True,
                )
                row = ttk.Frame(parent)
                row.pack(fill="both", pady=(0, 6))
                btns = ttk.Frame(row)
                btns.pack(side="right", padx=(6, 0), anchor="n")
                text = tk.Text(row, height=6, wrap="word")
                text.pack(side="left", fill="x", expand=True)
                input_star = _create_star(row, "Required", side="left", padx=(6, 0))
                error_lbl = ttk.Label(parent, text="", foreground="red")
                error_lbl.pack(anchor="w", pady=(0, 6))

                cur = step.get("value")
                if cur is not None:
                    if isinstance(cur, (dict, list)):
                        text.insert("1.0", json.dumps(cur, indent=2))
                    else:
                        text.insert("1.0", str(cur))

                def on_json_change(_event=None):
                    raw = text.get("1.0", "end").strip()
                    try:
                        ok, msg, is_warning = self._validate_const_json_value(raw, spec_col)
                    except Exception as e:  # safety
                        ok, msg, is_warning = False, f"Invalid JSON: {e}", False
                    if ok:
                        parsed = json.loads(raw)
                        step["value"] = parsed
                        _set_star_visible(label_star, False, "")
                        _set_star_visible(input_star, False, "")
                        if msg:
                            error_lbl.config(text=msg, foreground="#b36b00" if is_warning else "#333333")
                        else:
                            error_lbl.config(text="", foreground="red")
                    else:
                        step["value"] = raw
                        _set_star_visible(label_star, True, msg or "Invalid JSON")
                        _set_star_visible(input_star, True, msg or "Invalid JSON")
                        error_lbl.config(text=msg or "Invalid JSON", foreground="red")
                    self.mark_dirty()
                    self._set_status_for_column(col_name)
                    self._update_preview(col_name, step)

                def on_prettify():
                    raw = text.get("1.0", "end").strip()
                    if not raw:
                        return
                    try:
                        obj = json.loads(raw)
                        formatted = json.dumps(obj, indent=2)
                        text.delete("1.0", "end")
                        text.insert("1.0", formatted)
                        on_json_change()
                    except Exception as e:
                        messagebox.showwarning("Invalid JSON", f"Cannot prettify invalid JSON:\n{e}", parent=self)

                ttk.Button(btns, text="Prettify", width=10, command=on_prettify).pack(anchor="n")
                _set_tooltip(text, "Enter a valid JSON object/array.")
                text.bind("<KeyRelease>", on_json_change)
                on_json_change()
            else:
                add_entry(
                    "value",
                    "Constant value to use for all rows.",
                    required=not allow_nullable_string,
                    label_text=label_hint,
                )
            return

        if op == "null":
            add_label("No configuration needed.", "All rows will be null.")
            return

        if op == "coalesce":
            add_columns_field("columns", "List of columns to coalesce (first non-null wins).", required=True)
            return

        if op == "map_values":
            add_entry("column", "Source column name (required for single-step).", required=True, use_column_picker=True)
            _, label_star, _ = add_label("mapping:", "Each row maps a source value to a target value.", required=True)
            map_frame = ttk.Frame(parent)
            map_frame.pack(fill="x", pady=(0, 6))
            rows_frame = ttk.Frame(map_frame)
            rows_frame.pack(side="left", fill="both", expand=True)
            input_star = _create_star(map_frame, "Required", side="left", padx=(6, 0))

            def collect_mapping():
                mapping: dict = {}
                valid = True
                seen = set()
                reason = "Required"
                for child in rows_frame.winfo_children():
                    if not isinstance(child, ttk.Frame):
                        continue
                    entries = child.winfo_children()
                    if len(entries) < 2:
                        continue
                    src = entries[0].get().strip()
                    dst = entries[2].get().strip()
                    if src:
                        if src in seen:
                            valid = False
                            reason = "Duplicate source values are not allowed."
                        seen.add(src)
                        if src == dst and src != "":
                            valid = False
                            reason = "Source and target must not be the same."
                        mapping[src] = dst
                step["mapping"] = mapping
                show = not mapping or not valid
                _set_star_visible(label_star, show, reason)
                _set_star_visible(input_star, show, reason)
                self.mark_dirty()
                self._set_status_for_column(col_name)
                self._update_preview(col_name, step)

            def add_row(src_val: str = "", dst_val: str = ""):
                row = ttk.Frame(rows_frame)
                row.pack(fill="x", pady=2)
                src = ttk.Entry(row, width=18)
                src.pack(side="left")
                ttk.Label(row, text="→").pack(side="left", padx=4)
                dst = ttk.Entry(row, width=18)
                dst.pack(side="left")
                btn = ttk.Button(row, text="-", width=2, command=lambda: remove_row(row))
                btn.pack(side="left", padx=(6, 0))
                src.insert(0, src_val)
                dst.insert(0, dst_val)

                src.bind("<KeyRelease>", lambda _e: collect_mapping())
                dst.bind("<KeyRelease>", lambda _e: collect_mapping())
                tip_src = _WidgetTooltip(src)
                tip_dst = _WidgetTooltip(dst)
                src.bind("<Enter>", lambda _e: tip_src.show("Source value to match."))
                src.bind("<Leave>", lambda _e: tip_src.hide())
                dst.bind("<Enter>", lambda _e: tip_dst.show("Target value to output."))
                dst.bind("<Leave>", lambda _e: tip_dst.hide())

            def remove_row(row):
                row.destroy()
                collect_mapping()
            ttk.Button(map_frame, text="+", width=3, command=lambda: add_row()).pack(side="left", padx=6)

            if isinstance(step.get("mapping"), dict) and step["mapping"]:
                for k, v in step["mapping"].items():
                    add_row(str(k), str(v))
            else:
                add_row()
            collect_mapping()

            add_entry("default", "Default value if no mapping match.")
            return

        if op == "concat":
            add_columns_field("columns", "List of columns to join (in order).", required=True)
            add_entry("sep", "Separator string to insert between values.")
            return

        if op == "math":
            _, label_star, _ = add_label("expression:", "Left operand, operator, right operand", required=True)
            row = ttk.Frame(parent)
            row.pack(fill="x", pady=(0, 6))

            left_type = tk.StringVar(value="column")
            left_val = tk.StringVar(value="")
            op_var = tk.StringVar(value=step.get("operator") or "")
            right_type = tk.StringVar(value="const")
            right_val = tk.StringVar(value="")

            if isinstance(step.get("operands"), list) and len(step["operands"]) >= 2:
                def _load_operand(var_type, var_val, operand):
                    if "column" in operand:
                        var_type.set("column")
                        var_val.set(str(operand.get("column") or ""))
                    elif "const" in operand:
                        var_type.set("const")
                        var_val.set(str(operand.get("const") or ""))

                _load_operand(left_type, left_val, step["operands"][0])
                _load_operand(right_type, right_val, step["operands"][1])
            else:
                step["operands"] = [{"column": left_val.get()}, {"const": right_val.get()}]

            left_type_cb = ttk.Combobox(row, values=["column", "const"], textvariable=left_type, state="readonly", width=8)
            left_type_cb.pack(side="left")
            left_container = ttk.Frame(row)
            left_container.pack(side="left", padx=(4, 8))

            op_cb = ttk.Combobox(row, values=["+", "-", "x", "/"], textvariable=op_var, state="readonly", width=5)
            op_cb.pack(side="left", padx=(0, 8))

            right_type_cb = ttk.Combobox(row, values=["column", "const"], textvariable=right_type, state="readonly", width=8)
            right_type_cb.pack(side="left")
            right_container = ttk.Frame(row)
            right_container.pack(side="left", padx=(4, 0))

            tip_left_type = _WidgetTooltip(left_type_cb)
            tip_op = _WidgetTooltip(op_cb)
            tip_right_type = _WidgetTooltip(right_type_cb)
            left_type_cb.bind("<Enter>", lambda _e: tip_left_type.show("Left operand type (column or const)."))
            left_type_cb.bind("<Leave>", lambda _e: tip_left_type.hide())
            op_cb.bind("<Enter>", lambda _e: tip_op.show("Operator."))
            op_cb.bind("<Leave>", lambda _e: tip_op.hide())
            right_type_cb.bind("<Enter>", lambda _e: tip_right_type.show("Right operand type (column or const)."))
            right_type_cb.bind("<Leave>", lambda _e: tip_right_type.hide())

            hint = ttk.Label(parent, text="add = +, sub = -, mul = x, div = /", foreground="#666")
            hint.pack(anchor="w", pady=(0, 6))

            def _get_operand_value(widget, fallback_var):
                try:
                    return widget.get()
                except Exception:
                    return fallback_var.get()

            def _parse_const(val: str):
                try:
                    if val.strip() == "":
                        return None
                    if "." in val or "e" in val.lower():
                        return float(val)
                    return int(val)
                except Exception:
                    return None

            def update_math():
                def build_operand(t, widget, fallback_var):
                    v = _get_operand_value(widget, fallback_var).strip()
                    if t == "column":
                        return {"column": v}
                    const_val = _parse_const(v)
                    return {"const": const_val if const_val is not None else v}

                operands = [
                    build_operand(left_type.get(), left_entry, left_val),
                    build_operand(right_type.get(), right_entry, right_val),
                ]
                op_map = {"+": "add", "-": "sub", "x": "mul", "/": "div"}
                step["operator"] = op_map.get(op_var.get(), "")
                step["operands"] = operands

                valid = self._is_step_valid(col_name, step, spec_col)
                if label_star:
                    label_star.pack_forget() if valid else label_star.pack(side="left", padx=(4, 0))
                self.mark_dirty()
                self._set_status_for_column(col_name)
                self._update_preview(col_name, step)

            def rebuild_operand(container, operand_type, value_var):
                for w in container.winfo_children():
                    w.destroy()
                if self.sample_df is not None and operand_type.get() == "column":
                    new_values = [str(c) for c in self.sample_df.columns]
                    new = ttk.Combobox(container, values=new_values, state="normal", width=18)
                    make_combobox_filterable(new, new_values)
                    if value_var.get():
                        new.set(value_var.get())
                    new.bind("<<ComboboxSelected>>", lambda _e: update_math())
                    new.bind("<KeyRelease>", lambda _e: update_math(), add="+")
                else:
                    new = ttk.Entry(container, textvariable=value_var, width=18)
                    new.bind("<KeyRelease>", lambda _e: update_math())
                new.pack(side="left")
                tip = _WidgetTooltip(new)
                tip_text = "Operand column name." if operand_type.get() == "column" else "Operand constant value."
                new.bind("<Enter>", lambda _e: tip.show(tip_text))
                new.bind("<Leave>", lambda _e: tip.hide())
                return new

            def on_left_type_change(_event=None):
                nonlocal left_entry
                left_entry = rebuild_operand(left_container, left_type, left_val)
                update_math()

            def on_right_type_change(_event=None):
                nonlocal right_entry
                right_entry = rebuild_operand(right_container, right_type, right_val)
                update_math()

            left_type_cb.bind("<<ComboboxSelected>>", on_left_type_change)
            right_type_cb.bind("<<ComboboxSelected>>", on_right_type_change)
            op_cb.bind("<<ComboboxSelected>>", lambda _e: update_math())
            left_entry = rebuild_operand(left_container, left_type, left_val)
            right_entry = rebuild_operand(right_container, right_type, right_val)
            update_math()
            return

        if op == "when":
            cond = ttk.Frame(parent)
            cond.pack(fill="x", pady=(0, 6))
            ttk.Label(cond, text="if column").pack(side="left")
            if self.sample_df is not None:
                col_values = [str(c) for c in self.sample_df.columns]
                col_entry = ttk.Combobox(cond, values=col_values, state="normal", width=20)
                make_combobox_filterable(col_entry, col_values)
            else:
                col_entry = ttk.Entry(cond, width=20)
            col_entry.pack(side="left", padx=4)
            ttk.Label(cond, text="==").pack(side="left")
            val_entry = ttk.Entry(cond, width=20)
            val_entry.pack(side="left", padx=4)

            then_row = ttk.Frame(parent)
            then_row.pack(fill="x", pady=(0, 6))
            ttk.Label(then_row, text="Then:").pack(side="left")
            then_entry = ttk.Entry(then_row, width=30)
            then_entry.pack(side="left", padx=4)

            else_row = ttk.Frame(parent)
            else_row.pack(fill="x", pady=(0, 6))
            ttk.Label(else_row, text="Else:").pack(side="left")
            else_entry = ttk.Entry(else_row, width=30)
            else_entry.pack(side="left", padx=4)

            tip_col = _WidgetTooltip(col_entry)
            tip_val = _WidgetTooltip(val_entry)
            tip_then = _WidgetTooltip(then_entry)
            tip_else = _WidgetTooltip(else_entry)
            col_entry.bind("<Enter>", lambda _e: tip_col.show("Column name to test."))
            col_entry.bind("<Leave>", lambda _e: tip_col.hide())
            val_entry.bind("<Enter>", lambda _e: tip_val.show("Value to compare against."))
            val_entry.bind("<Leave>", lambda _e: tip_val.hide())
            then_entry.bind("<Enter>", lambda _e: tip_then.show("Value when condition matches."))
            then_entry.bind("<Leave>", lambda _e: tip_then.hide())
            else_entry.bind("<Enter>", lambda _e: tip_else.show("Value when condition does not match."))
            else_entry.bind("<Leave>", lambda _e: tip_else.hide())

            if step.get("column"):
                if isinstance(col_entry, ttk.Combobox):
                    col_entry.set(str(step.get("column")))
                else:
                    col_entry.insert(0, str(step.get("column")))
            if step.get("value") is not None:
                val_entry.insert(0, str(step.get("value")))
            if step.get("then") is not None:
                then_entry.insert(0, str(step.get("then")))
            if step.get("else") is not None:
                else_entry.insert(0, str(step.get("else")))

            def on_change(_event=None):
                step["column"] = col_entry.get()
                step["value"] = val_entry.get()
                step["then"] = then_entry.get()
                step["else"] = else_entry.get()
                self.mark_dirty()
                self._set_status_for_column(col_name)
                self._update_preview(col_name, step)

            col_entry.bind("<KeyRelease>", on_change, add="+")
            if isinstance(col_entry, ttk.Combobox):
                col_entry.bind("<<ComboboxSelected>>", on_change)
            val_entry.bind("<KeyRelease>", on_change)
            then_entry.bind("<KeyRelease>", on_change)
            else_entry.bind("<KeyRelease>", on_change)
            on_change()
            return

        if op == "pandas_expr":
            _, label_star, _ = add_label("expr:", "Pandas expression (uses df and current).", required=True)
            frame = ttk.Frame(parent)
            frame.pack(fill="both", expand=True, pady=(0, 6))
            text = tk.Text(frame, height=6, wrap="none")
            yscroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
            text.configure(yscrollcommand=yscroll.set)
            text.pack(side="left", fill="both", expand=True)
            yscroll.pack(side="right", fill="y")
            input_star = _create_star(frame, "Required", side="left", padx=(6, 0))
            if step.get("expr"):
                text.insert("1.0", step.get("expr"))

            def on_change(_event=None):
                val = text.get("1.0", "end-1c")
                step["expr"] = val
                show = not bool(val.strip())
                _set_star_visible(label_star, show, "Required")
                _set_star_visible(input_star, show, "Required")
                self.mark_dirty()
                self._set_status_for_column(col_name)
            text.bind("<KeyRelease>", on_change)
            _set_tooltip(text, "Pandas expression (uses df and current).")
            on_change()
            ttk.Button(parent, text="Dry Run Test", command=lambda: self._run_preview_test(col_name, step)).pack(anchor="w", pady=(4, 0))
            return

        if op == "sql":
            add_label("mode:", "Expression uses SELECT <expr> AS result FROM src. Query must start with SELECT/WITH.")
            mode_var = tk.StringVar(value="expr" if "expr" in step else "query" if "query" in step else "expr")
            mode_frame = ttk.Frame(parent)
            mode_frame.pack(anchor="w", pady=(0, 4))
            ttk.Radiobutton(mode_frame, text="Expression", variable=mode_var, value="expr").pack(side="left")
            ttk.Radiobutton(mode_frame, text="Full Query", variable=mode_var, value="query").pack(side="left", padx=8)

            _, label_star, _ = add_label("sql:", "SQL expression or query based on selected mode.", required=True)
            frame = ttk.Frame(parent)
            frame.pack(fill="both", expand=True, pady=(0, 6))
            text = tk.Text(frame, height=6, wrap="none")
            yscroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
            text.configure(yscrollcommand=yscroll.set)
            text.pack(side="left", fill="both", expand=True)
            yscroll.pack(side="right", fill="y")
            input_star = _create_star(frame, "Required", side="left", padx=(6, 0))
            if mode_var.get() == "expr":
                text.insert("1.0", step.get("expr", ""))
            else:
                text.insert("1.0", step.get("query", ""))

            def on_sql_change(_event=None):
                content = text.get("1.0", "end-1c")
                step.pop("expr", None)
                step.pop("query", None)
                step[mode_var.get()] = content
                show = not bool(content.strip())
                _set_star_visible(label_star, show, "Required")
                _set_star_visible(input_star, show, "Required")
                self.mark_dirty()
                self._set_status_for_column(col_name)

            def on_mode_change():
                content = text.get("1.0", "end-1c")
                text.delete("1.0", "end")
                text.insert("1.0", content)
                on_sql_change()

            text.bind("<KeyRelease>", on_sql_change)
            mode_var.trace_add("write", lambda *_: on_mode_change())
            _set_tooltip(text, "SQL expression or query based on selected mode.")
            on_sql_change()
            ttk.Button(parent, text="Dry Run Test", command=lambda: self._run_preview_test(col_name, step)).pack(anchor="w", pady=(4, 0))
            return

    def _status_for_column(self, col_name: str) -> tuple[str, tuple[str, ...]]:
        """Compute display status/tags for one target row in columns table."""
        spec_col = self.spec.get_column(col_name) if self.spec else None
        step = None
        if col_name in self.rules_dict and getattr(self.rules_dict[col_name], "steps", []):
            step = self.rules_dict[col_name].steps[0]
        is_valid = self._is_step_valid(col_name, step, spec_col)
        status = "-"
        if is_valid:
            op = step.get("op") if step else None
            status = f"Mapped ({op})" if op else "Mapped"
        if spec_col and spec_col.feature_level.lower() == "mandatory" and not is_valid:
            return "TBD", ("tbd",)
        return status, ()

    def _set_status_for_column(self, col_name: str) -> None:
        """Update one row status/tags in columns table."""
        status, tags = self._status_for_column(col_name)
        if self.tree.exists(col_name):
            self.tree.set(col_name, "status", status)
            self.tree.item(col_name, tags=tags)

    def create_rule(
        self,
        col_name,
        data_type: str | None = None,
        description: str | None = None,
        initial_step: dict | None = None,
        nullable: bool | None = None,
    ):
        """Create a new rule object for a target and open its editor panel."""
        # Create a new MappingRule
        # Since MappingRule is frozen, we might need a mutable proxy or just recreate it on save/update?
        # Actually, MappingRule.steps is a list[dict]. The list itself is mutable!
        # The MappingRule object is frozen, so I can't assign to .steps if it was not a list, but list content can catch changes.
        # However, to be safe and clean, let's create a new one.
        steps = []
        if initial_step:
            steps = [initial_step]
        validation = None
        if nullable is not None:
            validation = {"nullable": {"allow_nulls": bool(nullable)}}
        self.rules_dict[col_name] = MappingRule(
            target=col_name,
            steps=steps,
            description=description,
            data_type=data_type,
            validation=validation,
        )
        self.mark_dirty()
        self._set_status_for_column(col_name)
        self._show_column_details(col_name)

    def on_load_sample_data(self):
        """Load sample source data to enable pickers and transformation preview."""
        path = filedialog.askopenfilename(
            title="Load Sample Data (CSV/Parquet)",
            filetypes=[("Data files", "*.csv *.parquet"), ("All files", "*.*")],
            parent=self,
        )
        if not path:
            return
        try:
            df = read_table(Path(path))
            self.sample_df = df.head(100)
            messagebox.showinfo("Sample Loaded", f"Loaded {len(self.sample_df)} rows.", parent=self)
            if self.current_column:
                self._show_column_details(self.current_column)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load data: {e}", parent=self)

    def _update_preview(self, col_name: str, step: dict | None):
        """Refresh transformation preview table for current column/step."""
        if not hasattr(self, "preview_tree"):
            return
        # Clear
        for item in self.preview_tree.get_children():
            self.preview_tree.delete(item)
        self.preview_error.config(text="")
        if self.sample_df is None or step is None:
            return
        if step.get("op") in {"const", "null"}:
            return
        try:
            op = step.get("op")
            if op in {"from_column", "map_values", "when"}:
                src = step.get("column")
                if not src or src not in self.sample_df.columns:
                    self.preview_error.config(text="Preview requires a valid source column.")
                    return
            if op in {"coalesce", "concat"}:
                cols = step.get("columns") or []
                if not cols or not all(c in self.sample_df.columns for c in cols):
                    self.preview_error.config(text="Preview requires valid source columns.")
                    return
            step_preview = dict(step)
            if op == "when":
                src = step_preview.get("column")
                series = self.sample_df[src]
                value = step_preview.get("value")
                then_value = step_preview.get("then")
                else_value = step_preview.get("else")
                if pd.api.types.is_numeric_dtype(series):
                    def _parse_num(v):
                        try:
                            if v is None or str(v).strip() == "":
                                return v
                            return float(v)
                        except Exception:
                            return v
                    value = _parse_num(value)
                    then_value = _parse_num(then_value)
                    else_value = _parse_num(else_value)
                mask = series == value
                result = pd.Series([else_value] * len(series))
                series = result.where(~mask, other=then_value)
            elif step.get("op") == "map_values" and (not step.get("mapping")):
                src = step.get("column")
                if src and src in self.sample_df.columns:
                    series = self.sample_df[src]
                else:
                    series = apply_steps(self.sample_df, steps=[step_preview], target=col_name)
            else:
                series = apply_steps(self.sample_df, steps=[step_preview], target=col_name)
            for idx, val in enumerate(series.head(100).tolist(), start=1):
                self.preview_tree.insert("", "end", values=(idx, format_value_for_display(val)))
            self._autosize_preview_tree_columns()
        except Exception as e:
            self.preview_error.config(text=str(e))

    def _run_preview_test(self, col_name: str, step: dict | None):
        """Execute explicit dry-run preview for SQL/pandas_expr steps."""
        if self.sample_df is None:
            messagebox.showwarning("No Sample Data", "Load sample data first.", parent=self)
            return
        if step is None:
            return
        # Clear
        if hasattr(self, "preview_tree"):
            for item in self.preview_tree.get_children():
                self.preview_tree.delete(item)
        if hasattr(self, "preview_error"):
            self.preview_error.config(text="")
        try:
            series = apply_steps(self.sample_df, steps=[step], target=col_name)
            if hasattr(self, "preview_tree"):
                for idx, val in enumerate(series.head(100).tolist(), start=1):
                    self.preview_tree.insert("", "end", values=(idx, format_value_for_display(val)))
                self._autosize_preview_tree_columns()
        except Exception as e:
            err = str(e)
            dialog = tk.Toplevel(self)
            dialog.title("Dry Run Failed")
            dialog.geometry("600x300")
            dialog.resizable(True, True)
            content = ttk.Frame(dialog, padding=10)
            content.pack(fill="both", expand=True)
            ttk.Label(content, text="Error:", font=("Helvetica", 12, "bold")).pack(anchor="w")
            text = tk.Text(content, height=10, wrap="word")
            text.pack(fill="both", expand=True, pady=(6, 10))
            text.insert("1.0", err)
            text.configure(state="disabled")
            ttk.Button(content, text="OK", command=dialog.destroy).pack(side="right")
            dialog.transient(self)
            dialog.grab_set()
            self.wait_window(dialog)

    def _update_save_state(self):
        """Enable/disable save button based on editor dirty state."""
        if hasattr(self, "save_btn"):
            self.save_btn.configure(state="normal" if self.dirty else "disabled")

    def _confirm_discard(self) -> bool:
        """Prompt before discarding unsaved changes."""
        if not self.dirty:
            return True
        return messagebox.askyesno(
            "Unsaved Changes",
            "You have unsaved changes. Quit without saving?",
            parent=self,
        )

    def _on_close_window(self):
        """Handle top-level close event with unsaved-changes guard."""
        if self._confirm_discard():
            self.app.destroy()

    def mark_dirty(self):
        """Mark editor as dirty and refresh save button state."""
        if self._suppress_dirty:
            return
        if not self.dirty:
            self.dirty = True
            self._update_save_state()

    def _infer_extension_type(self, col_name: str) -> str:
        """Infer extension data type from loaded sample column dtype/values."""
        if self.sample_df is None or col_name not in self.sample_df.columns:
            return "String"
        series = self.sample_df[col_name]
        try:
            from pandas.api.types import (
                is_bool_dtype,
                is_datetime64_any_dtype,
                is_float_dtype,
                is_integer_dtype,
            )
        except Exception:
            return "String"
        if is_datetime64_any_dtype(series):
            return "Date/Time"
        if is_integer_dtype(series):
            return "Integer"
        if is_float_dtype(series):
            return "Decimal"
        if is_bool_dtype(series):
            return "Boolean"
        if series.dtype == "object":
            sample = next((v for v in series if v is not None and v is not pd.NA), None)
            if isinstance(sample, dict):
                return "JSON"
        return "String"

    def _prompt_extension_column(self):
        """Prompt for extension column metadata and optional source mapping."""
        dialog = tk.Toplevel(self)
        dialog.title("New Extension Column")
        dialog.resizable(False, False)

        content = ttk.Frame(dialog, padding=10)
        content.pack(fill="both", expand=True)

        ttk.Label(content, text="Column Name:").grid(row=0, column=0, sticky="w", pady=4)
        name_var = tk.StringVar()
        name_values = [str(c) for c in self.sample_df.columns] if self.sample_df is not None else []
        name_cb = ttk.Combobox(content, textvariable=name_var, values=name_values, width=40)
        make_combobox_filterable(name_cb, name_values)
        name_cb.grid(row=0, column=1, sticky="w", pady=4)
        _set_tooltip(name_cb, "Choose from sample data or type a new extension column name.")

        ttk.Label(content, text="Data Type:").grid(row=1, column=0, sticky="w", pady=4)
        data_type_var = tk.StringVar(value="String")
        type_options = ["String", "Decimal", "Date/Time", "Integer", "Boolean", "JSON"]
        data_type_cb = ttk.Combobox(
            content,
            textvariable=data_type_var,
            values=type_options,
            state="readonly",
            width=18,
        )
        data_type_cb.grid(row=1, column=1, sticky="w", pady=4)
        _set_tooltip(data_type_cb, "Data type for the extension column.")

        ttk.Label(content, text="Description:").grid(row=2, column=0, sticky="w", pady=4)
        desc_var = tk.StringVar()
        desc_entry = ttk.Entry(content, textvariable=desc_var, width=60)
        desc_entry.grid(row=2, column=1, sticky="w", pady=4)
        _set_tooltip(desc_entry, "Short description for this extension column.")

        ttk.Label(content, text="Nullable:").grid(row=3, column=0, sticky="w", pady=4)
        nullable_var = tk.BooleanVar(value=True)
        nullable_cb = ttk.Checkbutton(content, variable=nullable_var, text="Allow nulls")
        nullable_cb.grid(row=3, column=1, sticky="w", pady=4)
        _set_tooltip(nullable_cb, "Whether this extension column allows null values.")

        def on_name_change(*_):
            name = name_var.get().strip()
            if name in name_values:
                data_type_var.set(self._infer_extension_type(name))

        name_cb.bind("<<ComboboxSelected>>", on_name_change)
        name_cb.bind("<KeyRelease>", on_name_change, add="+")

        result = {"value": None}

        def on_ok():
            name = (name_var.get() or "").strip()
            if not name:
                messagebox.showwarning("Missing Name", "Please enter a column name.", parent=dialog)
                return
            source_column = None
            if name in name_values:
                source_column = name
            if not name.startswith("x_"):
                name = "x_" + name
            if self.tree.exists(name) or name in self.rules_dict:
                messagebox.showwarning("Duplicate Column", f"{name} already exists.", parent=dialog)
                return
            result["value"] = {
                "name": name,
                "data_type": data_type_var.get().strip() or "String",
                "description": (desc_var.get() or "").strip() or None,
                "source_column": source_column,
                "nullable": bool(nullable_var.get()),
            }
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btns = ttk.Frame(content)
        btns.grid(row=4, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(btns, text="Cancel", command=on_cancel).pack(side="right")
        ttk.Button(btns, text="OK", command=on_ok).pack(side="right", padx=6)

        dialog.transient(self)
        dialog.grab_set()
        dialog.update_idletasks()
        w = dialog.winfo_width()
        h = dialog.winfo_height()
        x = self.winfo_rootx() + (self.winfo_width() - w) // 2
        y = self.winfo_rooty() + (self.winfo_height() - h) // 2
        dialog.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")
        self.wait_window(dialog)
        return result["value"]

    def on_add_column(self):
        """Add extension column rule via metadata prompt workflow."""
        result = self._prompt_extension_column()
        if not result:
            return
        name = result["name"]
        data_type = result.get("data_type")
        description = result.get("description")
        source_column = result.get("source_column")
        nullable = result.get("nullable")
        initial_step = None
        if source_column:
            initial_step = {"op": "from_column", "column": source_column}
        if name not in self.rules_dict:
            # Insert tree row first so _set_status_for_column can find it
            nullable_display = "Yes" if nullable else "No"
            self.tree.insert(
                "",
                "end",
                iid=name,
                text=name,
                values=("-", "Extension", data_type or "-", nullable_display),
            )
            self._col_descriptions[name] = description or ""
            self.create_rule(
                name,
                data_type=data_type,
                description=description,
                initial_step=initial_step,
                nullable=nullable,
            )
            # Select and scroll into view
            self.tree.selection_set(name)
            self.tree.see(name)

    def on_save(self):
        """Validate editor state and persist mapping YAML to disk."""
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
        mappings = {}
        for k, v in self.rules_dict.items():
            steps = v.steps[:1] if getattr(v, "steps", None) else []
            if not steps:
                continue
            spec_col = self.spec.get_column(k) if self.spec else None
            if not self._is_step_valid(k, steps[0], spec_col):
                continue
            body = {"steps": steps}
            if v.description:
                body["description"] = v.description
            if v.data_type:
                body["data_type"] = v.data_type
            if v.validation:
                body["validation"] = v.validation
            mappings[k] = body

        data = {
            "spec_version": self.spec_version,
            "validation": { "default": self.validation_defaults } if self.validation_defaults is not None else {},
            "mappings": mappings,
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
        self.dirty = False
        self._update_save_state()
        
        messagebox.showinfo("Saved", f"Mapping saved to {self.file_path.name}", parent=self)

    def on_back(self):
        """Return to mappings view, confirming discard if editor is dirty."""
        if not self._confirm_discard():
            return
        self.app.show_mappings_view()
