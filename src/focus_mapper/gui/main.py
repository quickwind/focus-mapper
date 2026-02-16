"""Entrypoint for launching the Tkinter GUI application."""

import sys

def main():
    """Entry point for the GUI application."""
    # Close PyInstaller splash screen if running from frozen exe
    try:
        import pyi_splash  # type: ignore[import-not-found]
        pyi_splash.close()
    except ImportError:
        pass  # Not running from PyInstaller bundle

    try:
        from focus_mapper.gui.app import App
    except ImportError as e:
        if "tkinter" in str(e):
            print("Error: Tkinter (Python GUI library) is not found or configured correctly.")
            print("\nCommon fixes:")
            print("  - macOS (Homebrew): brew install python-tk")
            print("  - Linux (Debian/Ubuntu): sudo apt-get install python3-tk")
            print("  - Windows: Reinstall Python and ensure 'tcl/tk and IDLE' is checked.")
            sys.exit(1)
        raise e

    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
