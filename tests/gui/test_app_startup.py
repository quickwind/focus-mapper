import pytest
import tkinter as tk
from unittest.mock import MagicMock

def test_app_startup(app):
    """Test that the application starts up and sets the title correctly."""
    assert app.title() == "Focus Mapper"
    
def test_navigation_sidebar_exists(app):
    """Test that the navigation sidebar is created."""
    # Check if nav_frame exists and is a frame
    assert hasattr(app, "nav_frame")
    assert isinstance(app.nav_frame, tk.Widget)

def test_initial_view_is_mappings(app):
    """Test that the initial view is the Mappings view."""
    # Wait for events to process
    app.update()
    
    assert app.current_view is not None
    # We can check the class name of the current view
    assert app.current_view.__class__.__name__ == "MappingsListView"
