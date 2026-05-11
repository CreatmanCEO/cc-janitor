from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ConfirmModal(ModalScreen[bool]):
    """Yes/No confirmation modal.

    Returns True if the user clicks Yes, False otherwise (No, Cancel,
    or dismissed). The TUI uses this in place of silently mutating
    ``CC_JANITOR_USER_CONFIRMED`` — every confirmation is an explicit
    click and is reflected in the audit log via :func:`tui_confirmed`.
    """

    BINDINGS = [
        ("enter", "confirm", "Yes"),
        ("y", "confirm", "Yes"),
        ("escape", "cancel", "No"),
        ("n", "cancel", "No"),
    ]

    DEFAULT_CSS = """
    ConfirmModal { align: center middle; }
    #confirm-box {
        width: 60;
        height: auto;
        background: $panel;
        border: round $warning;
        padding: 1 2;
    }
    #confirm-question { padding-bottom: 1; }
    #confirm-buttons { height: 3; align-horizontal: center; }
    """

    def __init__(self, question: str) -> None:
        super().__init__()
        self._question = question

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Static(f"[b]{self._question}[/]", id="confirm-question")
            yield Static("[dim]Y/Enter = yes, N/Esc = no[/]")
            with Vertical(id="confirm-buttons"):
                yield Button("Yes", variant="primary", id="confirm-yes")
                yield Button("No", id="confirm-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-yes":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


@contextmanager
def tui_confirmed() -> Iterator[None]:
    """Set ``CC_JANITOR_USER_CONFIRMED=1`` for the duration of a TUI-confirmed
    mutation, then restore the prior value (deletes the var if it was unset).

    Use ONLY after the user has clicked Yes in a :class:`ConfirmModal`. This
    preserves the central safety contract — the env var is the gate; TUI
    raises that gate explicitly per action, never silently.
    """
    prior = os.environ.get("CC_JANITOR_USER_CONFIRMED")
    os.environ["CC_JANITOR_USER_CONFIRMED"] = "1"
    try:
        yield
    finally:
        if prior is None:
            os.environ.pop("CC_JANITOR_USER_CONFIRMED", None)
        else:
            os.environ["CC_JANITOR_USER_CONFIRMED"] = prior
