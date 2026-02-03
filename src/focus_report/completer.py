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
    """
    Implements a custom readline completer for file paths.

    It handles:
    1. Identifying the full path context from the current line buffer.
    2. Expanding user home directories (~).
    3. Globbing the filesystem for matches.
    4. Returning ONLY the portion (basename) that completes the current token.
    """

    def __call__(self, text: str, state: int) -> str | None:
        if state == 0:
            line = (
                readline.get_line_buffer()
                if (readline and hasattr(readline, "get_line_buffer"))
                else text
            )

            # We need to know the full path prefix leading up to the current token 'text'.
            # Since '/' is a delimiter, 'text' is just the last part of the path.
            # We find the start of the path by looking for the last delimiter that is NOT a slash.
            path_delims = " \t\n\"\\'`@$><=;|&{("
            path_start = 0
            # Cursor position in the current word
            for i in range(len(line) - 1, -1, -1):
                if line[i] in path_delims:
                    path_start = i + 1
                    break

            # The full path including what's before the last slash
            # and the current 'text' being completed.
            full_path_prefix = line[path_start:]

            expanded = os.path.expanduser(full_path_prefix)

            # Construct glob pattern.
            # If text is empty (e.g. user just typed '/'), we want to list contents.
            pattern = expanded + "*"

            try:
                matches = glob.glob(pattern)
                results = []
                for m in matches:
                    # Since slashes are delimiters, readline expects us to return
                    # ONLY the part that completes the current token 'text'.
                    # This ensures the completion list (hints) only shows basenames.
                    name = os.path.basename(m.rstrip(os.sep))
                    if os.path.isdir(m):
                        name += os.sep
                    results.append(name)

                self.matches = sorted(list(set(results)))
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

        doc = getattr(readline, "__doc__", "")
        if doc and "libedit" in doc:
            readline.parse_and_bind("bind ^I rl_complete")
        else:
            readline.parse_and_bind("tab: complete")

        # Crucial: include '/' in delimiters so readline treats path segments as tokens.
        # This makes the completion UI show only the last segment (the hint).
        readline.set_completer_delims(" \t\n\"\\'`@$><=;|&{(/")
        yield
    finally:
        readline.set_completer(old_completer)
        readline.set_completer_delims(old_delims)
