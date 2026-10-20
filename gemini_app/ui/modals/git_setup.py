"""Interactive modal dialog for configuring Real Name and Git credentials."""

from __future__ import annotations

from typing import Any, Dict, Optional
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Static

from gemini_app.fleet.keys import (
    generate_cluster_keypair,
    get_or_create_cluster_ssh_key,
    get_stored_cluster_key_path,
    save_cluster_key_path,
)
from gemini_app.onboarding import (
    get_git_config,
    get_stored_git_email,
    get_stored_user_real_name,
    setup_git_credentials,
)
from gemini_app.projects import get_user_real_name
from gemini_app.ui.modals.base import ResponsiveModalScreen


class GitSetupModal(ResponsiveModalScreen[Optional[Dict[str, Any]]]):
    """Modal dialog prompting the user for their Real Name and Git credentials."""

    DEFAULT_CSS = """
    GitSetupModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }
    #git_setup_dialog {
        width: 74;
        max-width: 95%;
        height: auto;
        border: thick red;
        background: #0d0d0d;
        padding: 1 2;
    }
    #git_setup_title {
        text-style: bold;
        color: #ffffff;
        margin-bottom: 1;
        text-align: center;
    }
    #git_setup_desc {
        color: #aaaaaa;
        margin-bottom: 1;
    }
    .git_field_label {
        color: #ffffff;
        text-style: bold;
        margin-top: 1;
    }
    #git_name_input, #git_email_input, #cluster_ssh_input {
        width: 100%;
        margin-bottom: 1;
        border: solid red;
    }
    #git_setup_buttons {
        width: 100%;
        height: auto;
        align: right middle;
        margin-top: 1;
    }
    #git_setup_buttons Button {
        margin-left: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="git_setup_dialog"):
            yield Static("👤 Real Name & Git Setup", id="git_setup_title")
            yield Static(
                "Configure your Real Name for project copyright attribution (MIT License & README)\n"
                "and set your Git credentials for autonomous project scaffolding.",
                id="git_setup_desc",
            )
            yield Static("Real Name / Copyright Author:", classes="git_field_label")
            current_name = get_stored_user_real_name() or get_user_real_name() or ""
            yield Input(
                value=current_name,
                placeholder="e.g. Jane Doe",
                id="git_name_input",
            )
            yield Static("Git Email:", classes="git_field_label")
            default_email = get_stored_git_email() or get_git_config("user.email") or ""
            yield Input(
                value=default_email,
                placeholder="e.g. user@example.com",
                id="git_email_input",
            )
            yield Static("Cluster SSH Private Key (for node rescue):", classes="git_field_label")
            existing_key = get_stored_cluster_key_path()
            key_str = str(existing_key) if existing_key else ""
            yield Input(
                value=key_str,
                placeholder="Leave blank to auto-generate ~/.gemini/fleet/id_cluster",
                id="cluster_ssh_input",
            )
            with Horizontal(id="git_setup_buttons"):
                yield Button("Cancel", variant="error", id="git_setup_cancel_btn")
                yield Button("Save & Configure", variant="primary", id="git_setup_save_btn")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#git_name_input", Input).focus()

    @on(Input.Submitted, "#git_name_input")
    def on_name_submitted(self, event: Input.Submitted) -> None:
        self.query_one("#git_email_input", Input).focus()

    @on(Input.Submitted, "#git_email_input")
    def on_email_submitted(self, event: Input.Submitted) -> None:
        self.query_one("#cluster_ssh_input", Input).focus()

    @on(Input.Submitted, "#cluster_ssh_input")
    def on_ssh_submitted(self, event: Input.Submitted) -> None:
        self._handle_save()

    @on(Button.Pressed, "#git_setup_save_btn")
    def on_save_button(self) -> None:
        self._handle_save()

    @on(Button.Pressed, "#git_setup_cancel_btn")
    def on_cancel_button(self) -> None:
        self.dismiss(None)

    def _handle_save(self) -> None:
        name_val = self.query_one("#git_name_input", Input).value.strip()
        email_val = self.query_one("#git_email_input", Input).value.strip()
        ssh_val = self.query_one("#cluster_ssh_input", Input).value.strip()

        if not name_val and not email_val and not ssh_val:
            self.notify("Please enter at least a name, email, or SSH key.", severity="warning")
            return

        res = setup_git_credentials(real_name=name_val, email=email_val)

        if ssh_val:
            p = Path(os.path.expanduser(ssh_val)).resolve()
            if p.is_file():
                save_cluster_key_path(p)
                res["ssh_key_path"] = str(p)
            else:
                self.notify(f"SSH key path '{ssh_val}' not found. Generating default cluster key...", severity="warning")
                priv, _ = generate_cluster_keypair()
                save_cluster_key_path(priv)
                res["ssh_key_path"] = str(priv)
        else:
            # If no key was configured, generate/ensure the default cluster key
            cluster_k = get_or_create_cluster_ssh_key()
            if cluster_k:
                save_cluster_key_path(cluster_k)
                res["ssh_key_path"] = str(cluster_k)

        self.dismiss(res)
