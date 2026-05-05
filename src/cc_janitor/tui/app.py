from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Static, TabbedContent, TabPane

from ..i18n import detect_lang, set_lang, t


class CcJanitorApp(App):
    CSS = """
    TabbedContent { height: 100%; }
    """
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("f1", "help", "Help"),
        ("f2", "toggle_lang", "Lang"),
    ]

    def __init__(self) -> None:
        super().__init__()
        set_lang(detect_lang())

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with TabbedContent():
            with TabPane(t("sessions.title"), id="sessions"):
                yield Static("Sessions screen — TODO")
            with TabPane(t("perms.title"), id="perms"):
                yield Static("Permissions screen — TODO")
            with TabPane(t("context.title"), id="context"):
                yield Static("Context screen — TODO")
            with TabPane("Memory", id="memory"):
                yield Static("Memory screen — TODO")
            with TabPane("Hooks", id="hooks"):
                yield Static("Hooks screen — TODO")
            with TabPane("Schedule", id="schedule"):
                yield Static("Schedule screen — TODO")
            with TabPane("Audit", id="audit"):
                yield Static("Audit screen — TODO")
        yield Footer()

    def action_toggle_lang(self) -> None:
        from ..i18n import _current_lang

        new = "ru" if _current_lang == "en" else "en"
        set_lang(new)


def run() -> None:
    CcJanitorApp().run()
