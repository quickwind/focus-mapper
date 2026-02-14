"""Tkinter desktop application shell for focus-mapper GUI views."""

import tkinter as tk
from tkinter import ttk
import json
import os
from pathlib import Path

class App(tk.Tk):
    """Main GUI application window and view router."""
    def __init__(self):
        """Initialize root window, shared settings, and initial view."""
        super().__init__()

        self.title("Focus Mapper")
        self.geometry("1350x800")
        self._set_app_icon()
        
        # Configure grid layout
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # Setup Styles (placeholder for now)
        self.style = ttk.Style(self)
        self.style.theme_use('clam') 

        # Navigation Sidebar
        self.nav_frame = ttk.Frame(self, width=200, padding=10)
        self.nav_frame.grid(row=0, column=0, sticky="ns")
        
        # Content Area
        self.content_frame = ttk.Frame(self, padding=20)
        self.content_frame.grid(row=0, column=1, sticky="nsew")

        self.current_view = None
        self.views = {}
        self.config_dir = Path.home() / ".focus_mapper"
        self.settings_path = self.config_dir / "settings.json"
        self.settings = self._load_settings()

        self._create_navigation()
        self._show_welcome_view()

    def _create_navigation(self):
        """Create left-side navigation and action buttons."""
        ttk.Label(self.nav_frame, text="Focus Mapper", font=("Helvetica", 16, "bold")).pack(pady=(0, 20))
        
        # Navigation Buttons
        ttk.Button(self.nav_frame, text="Mappings", command=self.show_mappings_view).pack(fill="x", pady=5)
        ttk.Button(self.nav_frame, text="Generator", command=self.show_generator_view).pack(fill="x", pady=5)
        
        ttk.Separator(self.nav_frame, orient="horizontal").pack(fill="x", pady=20)
        ttk.Button(self.nav_frame, text="Settings", command=self.show_settings_view).pack(fill="x", pady=5)

    def _show_welcome_view(self):
        """Initialize local app directories and show default view."""
        # Determine the user home directory and settings path
        home_dir = self.config_dir
        if not home_dir.exists():
            try:
                home_dir.mkdir(parents=True, exist_ok=True)
                (home_dir / "mappings").mkdir(exist_ok=True)
            except Exception as e:
                print(f"Warning: Could not create config directory: {e}")

        self.show_mappings_view()
    
    def show_mappings_view(self):
        """Open mappings manager view."""
        self._clear_content()
        from focus_mapper.gui.views.mappings import MappingsListView
        self.current_view = MappingsListView(self.content_frame, self)
        self.current_view.pack(fill="both", expand=True)

    def show_generator_view(self):
        """Open generator view, reusing existing instance when available."""
        if self.current_view and self.current_view.__class__.__name__ == "GeneratorView":
            return
        for widget in self.content_frame.winfo_children():
            if widget.__class__.__name__ == "GeneratorView":
                self._show_existing_view(widget)
                return
        self._clear_content()
        from focus_mapper.gui.views.generator import GeneratorView
        self.current_view = GeneratorView(self.content_frame, self)
        self.current_view.pack(fill="both", expand=True)

    def show_settings_view(self):
        """Open settings view."""
        self._clear_content()
        from focus_mapper.gui.views.settings import SettingsView
        self.current_view = SettingsView(self.content_frame, self)
        self.current_view.pack(fill="both", expand=True)

    def show_report_view(self, report_data, back_view=None):
        """Open report view and optionally retain a back-reference view."""
        if self.current_view and back_view is not self.current_view:
            self.current_view.destroy()
        elif self.current_view:
            self.current_view.pack_forget()
        from focus_mapper.gui.views.report import ReportView
        self.current_view = ReportView(self.content_frame, self, report_data=report_data, back_view=back_view)
        self.current_view.pack(fill="both", expand=True)

    def _show_existing_view(self, view):
        """Show an existing view instance in the content area."""
        if self.current_view and self.current_view is not view:
            self.current_view.destroy()
        self.current_view = view
        view.pack(fill="both", expand=True)

    def _load_settings(self):
        """Load persisted GUI settings and sync related environment variables."""
        try:
            if self.settings_path.exists():
                settings = json.loads(self.settings_path.read_text(encoding="utf-8"))
                spec_dir = settings.get("spec_dir")
                if spec_dir:
                    os.environ["FOCUS_SPEC_DIR"] = str(spec_dir)
                else:
                    os.environ.pop("FOCUS_SPEC_DIR", None)
                return settings
        except Exception as e:
            print(f"Warning: Could not load settings: {e}")
        return {}

    def save_settings(self):
        """Persist current GUI settings to disk."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            self.settings_path.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"Warning: Could not save settings: {e}")

    def get_setting(self, key, default=None):
        """Read one setting value with optional default."""
        return self.settings.get(key, default)

    def set_setting(self, key, value):
        """Set/remove one setting and persist it."""
        if value in ("", None):
            self.settings.pop(key, None)
        else:
            self.settings[key] = value
        if key == "spec_dir":
            if value in ("", None):
                os.environ.pop("FOCUS_SPEC_DIR", None)
            else:
                os.environ["FOCUS_SPEC_DIR"] = str(value)
        self.save_settings()

    def _clear_content(self):
        """Destroy all widgets in the content container."""
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    def _set_app_icon(self):
        """Set application icon from bundled PNG using cross-platform Tk APIs."""
        icon_path = Path(__file__).resolve().parent / "assets" / "icon.png"
        if not icon_path.exists():
            return
        try:
            # On Windows, prefer .ico for the window icon if available
            if os.name == 'nt':
                ico_path = icon_path.with_suffix(".ico")
                if ico_path.exists():
                    self.iconbitmap(str(ico_path))
                    return

            # Keep a strong reference to avoid Tk image GC issues.
            self._icon_image = tk.PhotoImage(file=str(icon_path))
            self.iconphoto(True, self._icon_image)
        except Exception as e:
            print(f"Warning: Could not set app icon: {e}")
