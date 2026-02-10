import tkinter as tk
from tkinter import ttk

class StepForm(ttk.Frame):
    def __init__(self, parent, step_config, on_change=None):
        super().__init__(parent)
        self.step_config = step_config
        self.on_change = on_change
        self._create_widgets()

    def _create_widgets(self):
        pass

    def _notify_change(self):
        if self.on_change:
            self.on_change()

class FromColumnForm(StepForm):
    def _create_widgets(self):
        ttk.Label(self, text="Source Column:").pack(anchor="w")
        self.entry = ttk.Entry(self)
        self.entry.pack(fill="x", pady=2)
        if "column" in self.step_config:
            self.entry.insert(0, self.step_config["column"])
        
        self.entry.bind("<KeyRelease>", self._on_update)

    def _on_update(self, event=None):
        self.step_config["column"] = self.entry.get()
        self._notify_change()

class ConstForm(StepForm):
    def _create_widgets(self):
        ttk.Label(self, text="Constant Value:").pack(anchor="w")
        self.entry = ttk.Entry(self)
        self.entry.pack(fill="x", pady=2)
        if "value" in self.step_config:
            self.entry.insert(0, str(self.step_config["value"]))
        
        self.entry.bind("<KeyRelease>", self._on_update)

    def _on_update(self, event=None):
        self.step_config["value"] = self.entry.get()
        self._notify_change()

class SQLForm(StepForm):
    def _create_widgets(self):
        ttk.Label(self, text="SQL Expression (DuckDB):").pack(anchor="w")
        
        self.text = tk.Text(self, height=5, font=("Courier", 12))
        self.text.pack(fill="x", pady=2)
        
        val = self.step_config.get("expr") or self.step_config.get("query") or ""
        self.text.insert("1.0", str(val))
        
        self.text.bind("<KeyRelease>", self._on_update)
        
        self.mode_var = tk.StringVar(value="expr" if "expr" in self.step_config else "query")
        # Default to expr if neither
        if "expr" not in self.step_config and "query" not in self.step_config:
            self.mode_var.set("expr")

        frame = ttk.Frame(self)
        frame.pack(fill="x", pady=5)
        ttk.Radiobutton(frame, text="Expression", variable=self.mode_var, value="expr", command=self._on_update).pack(side="left")
        ttk.Radiobutton(frame, text="Full Query", variable=self.mode_var, value="query", command=self._on_update).pack(side="left")

    def _on_update(self, event=None):
        content = self.text.get("1.0", "end-1c")
        mode = self.mode_var.get()
        
        # Clear old keys
        self.step_config.pop("expr", None)
        self.step_config.pop("query", None)
        
        self.step_config[mode] = content
        self._notify_change()

class CastForm(StepForm):
    def _create_widgets(self):
        ttk.Label(self, text="Target Type:").pack(anchor="w")
        self.type_var = tk.StringVar(value=self.step_config.get("to", "string"))
        cb = ttk.Combobox(self, textvariable=self.type_var, values=["string", "int", "float", "decimal", "datetime"])
        cb.pack(fill="x", pady=2)
        cb.bind("<<ComboboxSelected>>", self._on_update)

    def _on_update(self, event=None):
        self.step_config["to"] = self.type_var.get()
        self._notify_change()

def get_form_class(op_name):
    # Mapping of op to form class
    mapping = {
        "from_column": FromColumnForm,
        "const": ConstForm,
        "sql": SQLForm,
        "cast": CastForm,
        # TODO: Add others: math, concat, coalesce, pandas_expr, when, map_values, etc.
    }
    return mapping.get(op_name, StepForm) # Default to empty if not found
