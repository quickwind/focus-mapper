"""Unit tests for wizard_lib module."""
from __future__ import annotations

from decimal import Decimal
from io import StringIO
import sys

import pytest

from focus_mapper.wizard_lib import (
    prompt_menu,
    prompt_int,
    prompt_decimal,
    prompt_bool,
    prompt_choice,
    prompt_datetime_format,
)


def make_input_iter(inputs: list[str]):
    """Create a prompt function that returns values from a list."""
    it = iter(inputs)
    def fake_prompt(text: str) -> str:
        return next(it)
    return fake_prompt


class TestPromptMenu:
    """Tests for prompt_menu function."""

    def test_select_by_number(self):
        """User can select an option by its number."""
        prompt = make_input_iter(["2"])
        options = [("from_column", "from_column"), ("const", "const"), ("skip", "skip")]
        result = prompt_menu(prompt, "Choose:", options)
        assert result == "const"

    def test_select_by_name(self):
        """User can select an option by its name."""
        prompt = make_input_iter(["const"])
        options = [("from_column", "from_column"), ("const", "const"), ("skip", "skip")]
        result = prompt_menu(prompt, "Choose:", options)
        assert result == "const"

    def test_select_by_name_case_insensitive(self):
        """Name matching is case-insensitive."""
        prompt = make_input_iter(["CONST"])
        options = [("from_column", "from_column"), ("const", "const")]
        result = prompt_menu(prompt, "Choose:", options)
        assert result == "const"

    def test_default_on_empty_input(self):
        """Empty input returns the default."""
        prompt = make_input_iter([""])
        options = [("from_column", "from_column"), ("const", "const"), ("skip", "skip")]
        result = prompt_menu(prompt, "Choose:", options, default="skip")
        assert result == "skip"

    def test_invalid_then_valid(self, capsys):
        """Invalid input prompts again until valid."""
        prompt = make_input_iter(["invalid", "1"])
        options = [("from_column", "from_column"), ("const", "const")]
        result = prompt_menu(prompt, "Choose:", options)
        assert result == "from_column"
        captured = capsys.readouterr()
        assert "Invalid choice" in captured.out

    def test_menu_format_multiline(self):
        """Menu is displayed with each option on its own line."""
        # Capture the menu text by examining what's passed to prompt
        captured_menu = None
        def capture_prompt(text: str) -> str:
            nonlocal captured_menu
            captured_menu = text
            return "1"
        
        options = [("a", "Option A"), ("b", "Option B")]
        prompt_menu(capture_prompt, "Select:", options, default="a")
        
        # Verify multiline format with tabs
        assert "Select:" in captured_menu
        assert "\t[1] Option A" in captured_menu
        assert "\t[2] Option B" in captured_menu
        assert "> (default: a):" in captured_menu


class TestPromptInt:
    """Tests for prompt_int function."""

    def test_valid_integer(self):
        """Valid integer is parsed and returned."""
        prompt = make_input_iter(["42"])
        result = prompt_int(prompt, "Enter number: ")
        assert result == 42

    def test_negative_integer(self):
        """Negative integers are accepted."""
        prompt = make_input_iter(["-10"])
        result = prompt_int(prompt, "Enter number: ")
        assert result == -10

    def test_empty_returns_none(self):
        """Empty input returns None when no default."""
        prompt = make_input_iter([""])
        result = prompt_int(prompt, "Enter number: ")
        assert result is None

    def test_empty_returns_default(self):
        """Empty input returns default when specified."""
        prompt = make_input_iter([""])
        result = prompt_int(prompt, "Enter number: ", default=5)
        assert result == 5

    def test_invalid_then_valid(self, capsys):
        """Invalid input prompts again until valid."""
        prompt = make_input_iter(["abc", "42"])
        result = prompt_int(prompt, "Enter number: ")
        assert result == 42
        captured = capsys.readouterr()
        assert "Invalid integer" in captured.out


class TestPromptDecimal:
    """Tests for prompt_decimal function."""

    def test_valid_decimal(self):
        """Valid decimal is parsed and returned."""
        prompt = make_input_iter(["3.14"])
        result = prompt_decimal(prompt, "Enter decimal: ")
        assert result == Decimal("3.14")

    def test_integer_as_decimal(self):
        """Integers are valid decimals."""
        prompt = make_input_iter(["42"])
        result = prompt_decimal(prompt, "Enter decimal: ")
        assert result == Decimal("42")

    def test_empty_returns_none(self):
        """Empty input returns None."""
        prompt = make_input_iter([""])
        result = prompt_decimal(prompt, "Enter decimal: ")
        assert result is None

    def test_invalid_then_valid(self, capsys):
        """Invalid input prompts again until valid."""
        prompt = make_input_iter(["abc", "1.5"])
        result = prompt_decimal(prompt, "Enter decimal: ")
        assert result == Decimal("1.5")
        captured = capsys.readouterr()
        assert "Invalid number" in captured.out


class TestPromptBool:
    """Tests for prompt_bool function."""

    def test_yes_variants(self):
        """y and yes return True."""
        for value in ["y", "Y", "yes", "YES", "Yes"]:
            prompt = make_input_iter([value])
            result = prompt_bool(prompt, "Continue? ")
            assert result is True

    def test_no_variants(self):
        """n and no return False."""
        for value in ["n", "N", "no", "NO", "No"]:
            prompt = make_input_iter([value])
            result = prompt_bool(prompt, "Continue? ")
            assert result is False

    def test_empty_returns_default_true(self):
        """Empty input returns default when True."""
        prompt = make_input_iter([""])
        result = prompt_bool(prompt, "Continue? ", default=True)
        assert result is True

    def test_empty_returns_default_false(self):
        """Empty input returns default when False."""
        prompt = make_input_iter([""])
        result = prompt_bool(prompt, "Continue? ", default=False)
        assert result is False

    def test_empty_returns_none_when_no_default(self):
        """Empty input returns None when no default specified."""
        prompt = make_input_iter([""])
        result = prompt_bool(prompt, "Continue? ")
        assert result is None

    def test_invalid_then_valid(self, capsys):
        """Invalid input prompts again until valid."""
        prompt = make_input_iter(["maybe", "y"])
        result = prompt_bool(prompt, "Continue? ")
        assert result is True
        captured = capsys.readouterr()
        assert "Invalid choice" in captured.out


class TestPromptChoice:
    """Tests for prompt_choice function."""

    def test_valid_choice(self):
        """Valid choice is returned."""
        prompt = make_input_iter(["red"])
        result = prompt_choice(prompt, "Pick color: ", {"red", "green", "blue"})
        assert result == "red"

    def test_case_insensitive(self):
        """Choices are matched case-insensitively."""
        prompt = make_input_iter(["RED"])
        result = prompt_choice(prompt, "Pick color: ", {"red", "green", "blue"})
        assert result == "red"

    def test_empty_returns_default(self):
        """Empty input returns default."""
        prompt = make_input_iter([""])
        result = prompt_choice(prompt, "Pick color: ", {"red", "green"}, default="red")
        assert result == "red"

    def test_invalid_then_valid(self, capsys):
        """Invalid input prompts again until valid."""
        prompt = make_input_iter(["yellow", "red"])
        result = prompt_choice(prompt, "Pick color: ", {"red", "green", "blue"})
        assert result == "red"
        captured = capsys.readouterr()
        assert "Invalid choice" in captured.out


class TestPromptDatetimeFormat:
    """Tests for prompt_datetime_format function."""

    def test_valid_format(self):
        """Valid datetime format is returned."""
        prompt = make_input_iter(["%Y-%m-%d"])
        result = prompt_datetime_format(prompt, "Format: ")
        assert result == "%Y-%m-%d"

    def test_complex_format(self):
        """Complex datetime formats are accepted."""
        prompt = make_input_iter(["%Y-%m-%dT%H:%M:%S"])
        result = prompt_datetime_format(prompt, "Format: ")
        assert result == "%Y-%m-%dT%H:%M:%S"

    def test_empty_returns_none(self):
        """Empty input returns None."""
        prompt = make_input_iter([""])
        result = prompt_datetime_format(prompt, "Format: ")
        assert result is None

    def test_invalid_then_valid(self, capsys):
        """Invalid format prompts again until valid."""
        prompt = make_input_iter(["not-a-format", "%Y-%m-%d"])
        result = prompt_datetime_format(prompt, "Format: ")
        assert result == "%Y-%m-%d"
        captured = capsys.readouterr()
        assert "Invalid format" in captured.out
