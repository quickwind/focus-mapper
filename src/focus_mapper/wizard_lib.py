"""Reusable wizard building blocks for interactive CLI wizards.

This module provides common prompting, validation, and completion patterns
that can be used by any interactive CLI wizard.
"""
from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from typing import Callable, Generator

# Re-export completers for convenience
from .completer import (
    path_completion,
    column_completion,
    value_completion,
    PathCompleter,
    ColumnCompleter,
    ValueCompleter,
)

__all__ = [
    # Type alias
    "PromptFunc",
    # Completers
    "path_completion",
    "column_completion",
    "value_completion",
    "PathCompleter",
    "ColumnCompleter",
    "ValueCompleter",
    # Menu prompting
    "prompt_menu",
    # Input validation
    "prompt_int",
    "prompt_decimal",
    "prompt_bool",
    "prompt_choice",
    "prompt_datetime_format",
    # Specialized prompts
    "prompt_with_path_completion",
    "prompt_with_value_completion",
    "prompt_with_column_completion",
]

PromptFunc = Callable[[str], str]


# ========================
# MENU PROMPTING
# ========================


def prompt_menu(
    prompt: PromptFunc,
    header: str,
    options: list[tuple[str, str]],
    *,
    default: str | None = None,
) -> str:
    """Display a numbered menu and return the selected option name.

    Args:
        prompt: Input function (e.g., input or custom prompt)
        header: Menu title (e.g., "Choose mapping (init):")
        options: List of (name, label) tuples. Name is returned, label is displayed.
        default: Default selection (returned on empty input)

    Returns:
        The name of the selected option

    Example:
        >>> options = [("from_column", "from_column"), ("const", "const"), ("skip", "skip")]
        >>> choice = prompt_menu(input, "Choose:", options, default="skip")
        # User sees:
        # Choose:
        #     [1] from_column
        #     [2] const
        #     [3] skip
        # > (default: skip):
        # User types: 2
        # Returns: "const"
    """
    # Build menu string with each option on its own line
    menu_lines = [header]
    for i, (_, label) in enumerate(options):
        menu_lines.append(f"\t[{i + 1}] {label}")
    
    # Build input prompt with default hint
    if default:
        input_prompt = f"> (default: {default}): "
    else:
        input_prompt = "> "
    
    menu = "\n".join(menu_lines) + "\n" + input_prompt

    # Create lookup: {"1": "name1", "name1": "name1", "label1": "name1", ...}
    lookup: dict[str, str] = {}
    for i, (name, label) in enumerate(options):
        lookup[str(i + 1)] = name
        lookup[name.lower()] = name
        if label.lower() != name.lower():
            lookup[label.lower()] = name

    while True:
        choice = prompt(menu).strip().lower()
        if choice == "" and default:
            return default
        if choice in lookup:
            return lookup[choice]
        valid_options = ", ".join(name for name, _ in options)
        print(f"Invalid choice. Options: {valid_options}\n")


# ========================
# INPUT VALIDATION
# ========================


def prompt_int(prompt: PromptFunc, text: str, *, default: int | None = None) -> int | None:
    """Prompt for an integer, return None or default on empty input.

    Args:
        prompt: Input function
        text: Prompt text
        default: Value returned on empty input

    Returns:
        Parsed integer, default, or None
    """
    while True:
        value = prompt(text).strip()
        if value == "":
            return default
        try:
            return int(value)
        except ValueError:
            print("Invalid integer. Try again.\n")


def prompt_decimal(prompt: PromptFunc, text: str) -> Decimal | None:
    """Prompt for a decimal number, return None on empty input.

    Args:
        prompt: Input function
        text: Prompt text

    Returns:
        Parsed Decimal or None
    """
    while True:
        value = prompt(text).strip()
        if value == "":
            return None
        try:
            return Decimal(value)
        except (InvalidOperation, ValueError):
            print("Invalid number. Try again.\n")


def prompt_bool(
    prompt: PromptFunc, text: str, *, default: bool | None = None
) -> bool | None:
    """Prompt for a yes/no response.

    Args:
        prompt: Input function
        text: Prompt text (should include hint like "[y/n]")
        default: Value returned on empty input

    Returns:
        True for yes, False for no, default/None for empty
    """
    while True:
        value = prompt(text).strip().lower()
        if value == "":
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Invalid choice. Enter y or n.\n")


def prompt_choice(
    prompt: PromptFunc,
    text: str,
    choices: set[str],
    *,
    default: str | None = None,
    allow_empty: bool = False,
) -> str | None:
    """Prompt for a choice from a set of valid options.

    Args:
        prompt: Input function
        text: Prompt text
        choices: Set of valid choices (matched case-insensitively)
        default: Value returned on empty input
        allow_empty: If True, empty input returns default even if None

    Returns:
        The selected choice or default
    """
    choices_lower = {c.lower(): c for c in choices}

    while True:
        value = prompt(text).strip().lower()
        if value == "":
            if allow_empty or default is not None:
                return default
            print("Empty input not allowed. Please enter a value.\n")
            continue
        if value in choices_lower:
            return choices_lower[value]
        print(f"Invalid choice. Options: {', '.join(sorted(choices))}\n")


def prompt_datetime_format(prompt: PromptFunc, text: str) -> str | None:
    """Prompt for a datetime format string (e.g., %Y-%m-%d).

    Args:
        prompt: Input function
        text: Prompt text

    Returns:
        Valid datetime format string or None on empty
    """
    while True:
        value = prompt(text).strip()
        if value == "":
            return None
        if "%" not in value or not any(
            token in value for token in ("%Y", "%y", "%m", "%d", "%H", "%M", "%S")
        ):
            print("Invalid format. Include datetime directives like %Y-%m-%d.\n")
            continue
        try:
            now = datetime.now(timezone.utc)
            _ = now.strftime(value)
        except Exception:
            print("Invalid datetime format string. Try again.\n")
            continue
        return value


# ========================
# SPECIALIZED PROMPTS
# ========================


def prompt_with_path_completion(text: str) -> str:
    """Prompt with file path tab-completion enabled.

    Uses readline for tab-completion of file paths.

    Args:
        text: Prompt text

    Returns:
        User input string
    """
    with path_completion():
        return input(text)


def prompt_with_value_completion(text: str, values: list[str]) -> str:
    """Prompt with value tab-completion enabled.

    Args:
        text: Prompt text
        values: List of valid values for completion

    Returns:
        User input string
    """
    with value_completion(values):
        return input(text)


def prompt_with_column_completion(text: str, columns: list[str]) -> str:
    """Prompt with column name tab-completion enabled.

    Args:
        text: Prompt text
        columns: List of column names for completion

    Returns:
        User input string
    """
    with column_completion(columns):
        return input(text)
