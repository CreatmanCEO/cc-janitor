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
                from .screens.sessions_screen import SessionsScreen
                yield SessionsScreen()
            with TabPane(t("perms.title"), id="perms"):
                from .screens.perms_screen import PermsScreen
                yield PermsScreen()
            with TabPane(t("context.title"), id="context"):
                from .screens.context_screen import ContextScreen
                yield ContextScreen()
            with TabPane("Memory", id="memory"):
                from .screens.memory_screen import MemoryScreen
                yield MemoryScreen()
            with TabPane("Hooks", id="hooks"):
                from .screens.hooks_screen import HooksScreen
                yield HooksScreen()
            with TabPane("Schedule", id="schedule"):
                from .screens.schedule_screen import ScheduleScreen
                yield ScheduleScreen()
            with TabPane("Audit", id="audit"):
                from .screens.audit_screen import AuditScreen
                yield AuditScreen()
        yield Footer()

    def action_toggle_lang(self) -> None:
        from ..i18n import _current_lang

        new = "ru" if _current_lang == "en" else "en"
        set_lang(new)


def run() -> None:
    CcJanitorApp().run()
