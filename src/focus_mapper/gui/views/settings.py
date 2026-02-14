"""Settings view for persisted GUI configuration options."""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from focus_mapper.gui.ui_utils import set_tooltip


class SettingsView(ttk.Frame):
    """Render and persist advanced GUI settings."""
    def __init__(self, parent, app_context):
        """Initialize settings view with app context."""
        super().__init__(parent)
        self.app = app_context
        self._create_ui()

    def _create_ui(self):
        """Build settings form controls."""
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
        set_tooltip(label, tooltip_text)
        self.spec_dir_var = tk.StringVar(value=self.app.get_setting("spec_dir", "") or "")
        self.spec_dir_entry = ttk.Entry(advanced, textvariable=self.spec_dir_var)
        self.spec_dir_entry.grid(row=0, column=1, sticky="ew", padx=8, pady=8)
        set_tooltip(self.spec_dir_entry, tooltip_text)
        ttk.Button(advanced, text="Browse...", command=self.on_browse_spec_dir).grid(row=0, column=2, padx=8, pady=8)

        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=8, pady=8)
        ttk.Button(actions, text="Clear", command=self.on_clear).pack(side="left")
        ttk.Button(actions, text="Save", command=self.on_save).pack(side="right")

    def on_browse_spec_dir(self):
        """Select spec override directory from filesystem."""
        selected = filedialog.askdirectory(parent=self, title="Select Custom Spec Directory")
        if selected:
            self.spec_dir_var.set(selected)

    def on_clear(self):
        """Clear spec directory setting input."""
        self.spec_dir_var.set("")

    def on_save(self):
        """Persist settings to app configuration storage."""
        spec_dir = (self.spec_dir_var.get() or "").strip()
        self.app.set_setting("spec_dir", spec_dir or None)
        messagebox.showinfo("Saved", "Settings saved.", parent=self)
