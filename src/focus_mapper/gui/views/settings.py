import tkinter as tk
from tkinter import ttk, filedialog, messagebox


class _WidgetTooltip:
    def __init__(self, widget):
        self.widget = widget
        self.tip = None
        self.label = None

    def show(self, text: str):
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
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip.geometry(f"+{x}+{y}")

    def hide(self):
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None
            self.label = None


def _set_tooltip(widget, text: str):
    if not text:
        return
    if not hasattr(widget, "_tooltip"):
        widget._tooltip = _WidgetTooltip(widget)
        widget.bind("<Enter>", lambda _e, w=widget: w._tooltip.show(getattr(w, "_tooltip_text", "")))
        widget.bind("<Leave>", lambda _e, w=widget: w._tooltip.hide())
    widget._tooltip_text = text


class SettingsView(ttk.Frame):
    def __init__(self, parent, app_context):
        super().__init__(parent)
        self.app = app_context
        self._create_ui()

    def _create_ui(self):
        ttk.Label(self, text="Settings", font=("Helvetica", 16, "bold")).pack(anchor="w", pady=(0, 12))

        advanced = ttk.LabelFrame(self, text="Advanced")
        advanced.pack(fill="x", padx=8, pady=8)
        advanced.columnconfigure(1, weight=1)

        label = ttk.Label(advanced, text="Custom Spec Dir (dev/test only):")
        label.grid(row=0, column=0, sticky="w", padx=8, pady=8)
        tooltip_text = (
            "Use this only for development/testing custom FOCUS spec JSON files. "
            "When set, GUI flows load specs from this directory first (same as CLI --spec-dir / FOCUS_SPEC_DIR). "
            "Do not use in production."
        )
        _set_tooltip(label, tooltip_text)
        self.spec_dir_var = tk.StringVar(value=self.app.get_setting("spec_dir", "") or "")
        self.spec_dir_entry = ttk.Entry(advanced, textvariable=self.spec_dir_var)
        self.spec_dir_entry.grid(row=0, column=1, sticky="ew", padx=8, pady=8)
        _set_tooltip(self.spec_dir_entry, tooltip_text)
        ttk.Button(advanced, text="Browse...", command=self.on_browse_spec_dir).grid(row=0, column=2, padx=8, pady=8)

        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=8, pady=8)
        ttk.Button(actions, text="Clear", command=self.on_clear).pack(side="left")
        ttk.Button(actions, text="Save", command=self.on_save).pack(side="right")

    def on_browse_spec_dir(self):
        selected = filedialog.askdirectory(parent=self, title="Select Custom Spec Directory")
        if selected:
            self.spec_dir_var.set(selected)

    def on_clear(self):
        self.spec_dir_var.set("")

    def on_save(self):
        spec_dir = (self.spec_dir_var.get() or "").strip()
        self.app.set_setting("spec_dir", spec_dir or None)
        messagebox.showinfo("Saved", "Settings saved.", parent=self)
