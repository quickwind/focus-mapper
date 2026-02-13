import tkinter as tk
from tkinter import ttk
import os
from pathlib import Path

class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Focus Mapper")
        self.geometry("1200x700")
        
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

        self._create_navigation()
        self._show_welcome_view()

    def _create_navigation(self):
        ttk.Label(self.nav_frame, text="Focus Mapper", font=("Helvetica", 16, "bold")).pack(pady=(0, 20))
        
        # Navigation Buttons
        ttk.Button(self.nav_frame, text="Mappings", command=self.show_mappings_view).pack(fill="x", pady=5)
        ttk.Button(self.nav_frame, text="Generator", command=self.show_generator_view).pack(fill="x", pady=5)
        
        ttk.Separator(self.nav_frame, orient="horizontal").pack(fill="x", pady=20)
        
        # Settings removed for now
        # ttk.Button(self.nav_frame, text="Settings", state="disabled").pack(fill="x", pady=5)

    def _show_welcome_view(self):
        # Determine the user home directory and settings path
        home_dir = Path.home() / ".focus_mapper"
        if not home_dir.exists():
            try:
                home_dir.mkdir(parents=True, exist_ok=True)
                (home_dir / "mappings").mkdir(exist_ok=True)
            except Exception as e:
                print(f"Warning: Could not create config directory: {e}")

        self.show_mappings_view()
    
    def show_mappings_view(self):
        self._clear_content()
        from focus_mapper.gui.views.mappings import MappingsListView
        self.current_view = MappingsListView(self.content_frame, self)
        self.current_view.pack(fill="both", expand=True)

    def show_generator_view(self):
        self._clear_content()
        from focus_mapper.gui.views.generator import GeneratorView
        self.current_view = GeneratorView(self.content_frame, self)
        self.current_view.pack(fill="both", expand=True)

    def _clear_content(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()
