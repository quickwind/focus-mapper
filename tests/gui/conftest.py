import pytest
import tkinter as tk
from unittest.mock import MagicMock, patch
import os
import shutil
from pathlib import Path

# Important: This avoids the "Tcl_AsyncDelete: async handler deleted by the wrong thread" error
# and other threading issues when running multiple tests.
@pytest.fixture(scope="session")
def _root():
    root = tk.Tk()
    root.withdraw() # Hide the main window
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass

@pytest.fixture
def mock_config_dir(tmp_path):
    """Fixture to mock the configuration directory to avoid messing with user's real config."""
    config_dir = tmp_path / ".focus_mapper"
    config_dir.mkdir()
    
    # Mock pathlib.Path.home() to return tmp_path
    with patch("pathlib.Path.home", return_value=tmp_path):
        yield config_dir

@pytest.fixture
def app(mock_config_dir, _root):
    """Fixture to create and destroy the App instance for each test."""
    from focus_mapper.gui.app import App
    
    # We patch tk.Tk to avoid creating a new root window, 
    # but App inherits from tk.Tk. 
    # Strategy: Mock App.__init__ or handle it carefully.
    
    # Actually, best practice for testing Tkinter apps that inherit from Tk is:
    # 1. Separate logic from GUI (MVC/MVVM) - hard to retrofit.
    # 2. Use a singleton root (like _root fixture) and patch App to use it as master 
    #    OR instantiate App as a Toplevel if possible 
    #    OR just instantiate App() and destroy() it.
    
    # Since App inherits from tk.Tk, calling App() creates a new root.
    # Tkinter supports multiple roots but it's flaky.
    # Let's try instantiating App, but ensuring we pump events.
    
    # To run specifically without display (CI), we'd need xvfb.
    # For now, let's assume local run with display.
    
    app = App()
    app.withdraw() # Hide it during tests
    
    # Force update to process pending events
    app.update()
    
    yield app
    
    try:
        app.destroy()
    except tk.TclError:
        pass
