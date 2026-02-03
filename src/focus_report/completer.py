from __future__ import annotations

import glob
import os
from contextlib import contextmanager
from typing import Generator

try:
    import readline
except ImportError:
    readline = None


class PathCompleter:
    def __call__(self, text: str, state: int) -> str | None:
        if state == 0:
            # Expand ~ and handle empty text
            expanded = os.path.expanduser(text)

            # Construct glob pattern
            if not text:
                pattern = "*"
            else:
                pattern = expanded + "*"

            try:
                matches = glob.glob(pattern)
                # Filter out anything that doesn't start with the expanded text
                # (glob usually handles this but expanduser can be tricky)

                processed = []
                for m in matches:
                    # Add trailing slash for directories
                    if os.path.isdir(m) and not m.endswith(os.sep):
                        m += os.sep

                    # If the user started with ~, we should return matches starting with ~
                    if text.startswith("~"):
                        # This is a bit complex to reverse expanduser perfectly,
                        # but we can try a simple replacement if it fits.
                        home = os.path.expanduser("~")
                        if m.startswith(home):
                            m = "~" + m[len(home) :]

                    processed.append(m)

                self.matches = sorted(processed)
            except Exception:
                self.matches = []

        try:
            return self.matches[state]
        except (IndexError, AttributeError):
            return None


@contextmanager
def path_completion() -> Generator[None, None, None]:
    """Context manager to enable tab-completion for file paths during input()."""
    if readline is None:
        yield
        return

    old_completer = readline.get_completer()
    old_delims = readline.get_completer_delims()

    try:
        readline.set_completer(PathCompleter())
        # Standard bash-like bindings
        if "libedit" in readline.__doc__:  # type: ignore
            readline.parse_and_bind("bind ^I rl_complete")
        else:
            readline.parse_and_bind("tab: complete")

        # Don't break paths on slashes or dots
        readline.set_completer_delims(" \t\n;")
        yield
    finally:
        readline.set_completer(old_completer)
        readline.set_completer_delims(old_delims)
