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
            line = (
                readline.get_line_buffer()
                if (readline and hasattr(readline, "get_line_buffer"))
                else text
            )

            path_delims = " \t\n\"\\'`@$><=;|&{("
            path_start = 0
            for i in range(len(line) - 1, -1, -1):
                if line[i] in path_delims:
                    path_start = i + 1
                    break
            full_path_prefix = line[path_start:]

            expanded = os.path.expanduser(full_path_prefix)

            if not full_path_prefix:
                pattern = "*"
            else:
                pattern = expanded + "*"

            try:
                matches = glob.glob(pattern)

                processed = []
                for m in matches:
                    if os.path.isdir(m) and not m.endswith(os.sep):
                        m += os.sep

                    processed.append(
                        os.path.basename(m.rstrip(os.sep))
                        + (os.sep if os.path.isdir(m) else "")
                    )

                self.matches = sorted(list(set(processed)))
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
        doc = getattr(readline, "__doc__", "")
        if doc and "libedit" in doc:
            readline.parse_and_bind("bind ^I rl_complete")
        else:
            readline.parse_and_bind("tab: complete")

        # Restore default delimiters (includes /) so readline only asks us
        # to complete the part after the last slash.
        readline.set_completer_delims(" \t\n\"\\'`@$><=;|&{(")
        yield
    finally:
        readline.set_completer(old_completer)
        readline.set_completer_delims(old_delims)
