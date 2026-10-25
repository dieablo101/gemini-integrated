"""Commands modal dialog listing keyboard shortcuts, power keys, and command-line commands."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Label

from gemini_app.ui.modals.base import ResponsiveModalScreen


class CommandsModal(ResponsiveModalScreen[None]):
    """Reference modal showing all shortcuts, Emacs navigation, and command syntax."""

    DEFAULT_CSS = """
    CommandsModal {
        align: center middle;
        layer: overlay;
        background: rgba(0, 0, 0, 0.85);
    }
    #commands_dialog {
        padding: 1 2;
        width: 78;
        max-width: 92vw;
        height: auto;
        max-height: 90vh;
        overflow-y: auto;
        overflow-x: hidden;
        background: #000000;
    }
    #cmd_modal_title {
        text-style: bold;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
        color: #ffffff;
    }
    .cmd_section_title {
        text-style: bold;
        margin-top: 1;
        margin-bottom: 0;
        width: 100%;
    }
    .cmd_row {
        width: 100%;
        height: auto;
        color: #dddddd;
        text-wrap: wrap;
        margin-left: 1;
    }
    .cmd_key {
        text-style: bold;
    }
    .cmd_desc {
        color: #ffffff;
    }
    #cmd_footer_hint {
        width: 100%;
        text-align: center;
        margin-top: 2;
        margin-bottom: 0;
        text-style: italic;
    }
    CommandsModal.-mobile #commands_dialog {
        width: 100vw;
        height: 100vh;
        max-width: 100vw;
        max-height: 100vh;
        border: none;
        padding: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Close"),
        Binding("ctrl+g", "cancel", "Close"),
        Binding("q", "cancel", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="commands_dialog"):
            yield Label("COMMANDS:", id="cmd_modal_title")

            yield Label("Keyboard:", classes="cmd_section_title")
            yield Label("[bold]Ctrl+F / Ctrl+B[/] : Move cursor right / left", classes="cmd_row")
            yield Label("[bold]Ctrl+N / Ctrl+P[/] : Move cursor down / up", classes="cmd_row")
            yield Label("[bold]Ctrl+A / Ctrl+E[/] : Beginning / end of line", classes="cmd_row")
            yield Label("[bold]Alt+F / Alt+B[/]   : Move forward / backward one word", classes="cmd_row")
            yield Label("[bold]Alt+< / Alt+>[/]   : Move to beginning / end of buffer", classes="cmd_row")
            yield Label("[bold]Ctrl+V / Alt+V[/]  : Page down / page up", classes="cmd_row")
            yield Label("[bold]Ctrl+Space[/]      : Set mark region for selection", classes="cmd_row")
            yield Label("[bold]Ctrl+D[/]          : Delete character forward", classes="cmd_row")
            yield Label("[bold]Ctrl+K[/]          : Kill line forward to clipboard", classes="cmd_row")
            yield Label("[bold]Ctrl+U[/]          : Kill line backward to clipboard", classes="cmd_row")
            yield Label("[bold]Alt+D[/]           : Kill word forward to clipboard", classes="cmd_row")
            yield Label("[bold]Ctrl+W[/]          : Kill selected region / kill word backward", classes="cmd_row")
            yield Label("[bold]Ctrl+Y[/]          : Yank (paste) clipboard text at cursor", classes="cmd_row")
            yield Label("[bold]Alt+W[/]           : Copy selected region to clipboard", classes="cmd_row")
            yield Label("[bold]Ctrl+_ / Ctrl+/[/] : Undo last edit", classes="cmd_row")
            yield Label("[bold]Ctrl+G / Escape[/] : Clear active mark or selection", classes="cmd_row")

            yield Label("PowerKeys:", classes="cmd_section_title")
            yield Label("[bold]C-c c[/]            : Open this Commands reference window", classes="cmd_row")
            yield Label("[bold]C-c m[/]            : Open Cognitive Mind Map Screen", classes="cmd_row")
            yield Label(r"[bold]C-c \[[/]          : Toggle notes editor panel", classes="cmd_row")
            yield Label("[bold]C-c t[/]          : Set active work / task title for feed border", classes="cmd_row")
            yield Label("[bold]C-c e[/]          : Send selected snippet to Emacs buffer", classes="cmd_row")
            yield Label("[bold]C-c w[/]          : Copy selected code snippet to clipboard", classes="cmd_row")
            yield Label("[bold]C-c y[/]          : Yank system clipboard into prompt input", classes="cmd_row")
            yield Label("[bold]C-c r[/]          : Save selected code snippet directly to disk", classes="cmd_row")
            yield Label("[bold]C-c f[/]          : Insert file content from disk as snippet", classes="cmd_row")
            yield Label("[bold]C-c g[/]          : Scan repository & open Git tree selector", classes="cmd_row")
            yield Label("[bold]C-c k[/]          : Emergency Interrupt (halt active generation / retry)", classes="cmd_row")
            # for later exploration by gemini
            # yield Label("[bold]C-c .[/]          : Toggle Fork mode to fork turns", classes="cmd_row")
            yield Label("[bold]Alt+n / Alt+p[/]  : Navigate next / previous snippet", classes="cmd_row")
            yield Label("[bold]C-c `[/]          : Take ephemeral UI snapshot (auto-deleted after review)", classes="cmd_row")

            yield Label("Notes System:", classes="cmd_section_title")
            yield Label("[bold]Alt+1 / Alt+2 / Alt+3[/] : Switch between Gemini / Turn / Global notes", classes="cmd_row")
            yield Label("[bold]Alt+Left / Alt+Right[/]  : Cycle through related turns with notes", classes="cmd_row")
            yield Label("Clicking any [bold]T#<num>[/] chip jumps 10-card slider directly to that note", classes="cmd_row")

            yield Label("Slash Commands:", classes="cmd_section_title")
            yield Label("[bold]/vault [cmd][/]      : Master vault manager (password, file, secret, sync, change, lock)", classes="cmd_row")
            yield Label("[bold]/facescan [reason][/]: Trigger Apple TrueDepth Face ID scan on iPad Wingman", classes="cmd_row")
            yield Label("[bold]/fingerprint [r][/]  : Prompt Android hardware fingerprint sensor (Termux)", classes="cmd_row")
            yield Label("[bold]/bio [reason][/]      : Dispatches platform-aware bilateral biometric challenge", classes="cmd_row")
            yield Label("[bold]/qr [payload][/]      : Generate terminal QR code for phone scanning / node pairing", classes="cmd_row")
            yield Label("[bold]/api-key[/]          : Configure / update Google Gemini API key", classes="cmd_row")
            yield Label("[bold]/git-setup[/]        : Configure Real Name & Git credentials", classes="cmd_row")
            yield Label("[bold]/scaffold <name>[/]  : Scaffold new project in ~/Projects with Git & License", classes="cmd_row")
            yield Label("[bold]/sys-deps[/]         : Check & install missing Linux system dependencies", classes="cmd_row")
            yield Label("[bold]/title <task>[/]   : Set active work title dynamically", classes="cmd_row")
            yield Label("[bold]/snapshot <name>[/] : Take permanent named UI snapshot (saved to disk)", classes="cmd_row")
            yield Label("[bold]/snapshots[/]        : View count and list of held snapshots", classes="cmd_row")
            yield Label("[bold]/theme <color>[/]    : Switch color theme instantly", classes="cmd_row")
            yield Label("[bold]/accent <area> <c>[/]: Pulse/set accent for area (feed|notes|input|all)", classes="cmd_row")
            yield Label("[bold]/pulse [color][/]    : Pulse global theme accent playfully", classes="cmd_row")
            yield Label("[bold]/mind-anim <eff>[/]  : Trigger Mind animation (sparkle|pulse|wave|synapse)", classes="cmd_row")
            yield Label("[bold]/state [tier][/]     : Introspect app state (visual|runtime|workflow|all)", classes="cmd_row")
            yield Label("[bold]/diff[/]             : Inspect git status and diff preview", classes="cmd_row")
            yield Label("[bold]/tokens[/]           : Session stats and token estimation", classes="cmd_row")
            yield Label("[bold]/abort[/]            : Emergency interrupt active generation / retry countdown", classes="cmd_row")
            yield Label("[bold]/reboot[/]           : In-place console application restart", classes="cmd_row")
            yield Label("[bold]/clear[/]            : Clear chat feed", classes="cmd_row")

            yield Label("CommandLine:", classes="cmd_section_title")
            yield Label("Execute commands directly from the prompt input using the format:", classes="cmd_row")
            yield Label("  [bold]!/<command>:<argument>[/]", classes="cmd_row")
            yield Label("  • [bold]![/][bold]/[/] : Command instantiator prefix", classes="cmd_row")
            yield Label("  • [bold]<command>[/] : The command name", classes="cmd_row")
            yield Label("  • [bold]:[/] : Argument delimiter", classes="cmd_row")
            yield Label("  • [bold]<argument>[/] : The parameter value passed to the command", classes="cmd_row")

            yield Label("User Interface:", classes="cmd_section_title")
            yield Label("[bold]!/ui-theme:<color>[/]", classes="cmd_row")
            yield Label("  Change the interface color theme.", classes="cmd_row")
            yield Label("  Available options: [bold]red, blue, green, orange, purple, yellow, pink[/]", classes="cmd_row")
            yield Label("  Example: [italic]!/ui-theme:blue[/]", classes="cmd_row")

            yield Label("State & Vault Backup:", classes="cmd_section_title")
            yield Label("[bold]!/backup-now[/]", classes="cmd_row")
            yield Label("  Trigger immediate 24-hr check backup of ~/.gemini to private GitHub repository.", classes="cmd_row")

            yield Label("ESC / Ctrl + g to exit", id="cmd_footer_hint")

    def action_cancel(self) -> None:
        self.dismiss(None)
