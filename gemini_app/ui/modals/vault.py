"""Interactive Vault modals: authentication, categorized password/secret/file entries, and master dashboard."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Optional

from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Checkbox, Input, Label, Static, TextArea

from gemini_app.ui.modals.base import ResponsiveModalScreen
from gemini_app.ui.modals.inputs import FilePathInput
from gemini_app.vault import (
    clear_session_passkey,
    delete_password,
    delete_secret,
    delete_vault_file,
    export_file,
    get_password,
    get_secret,
    get_session_passkey,
    is_session_unlocked,
    is_vault_configured,
    list_categorized_files,
    list_passwords,
    list_secrets,
    retrieve_from_vault,
    rotate_vault_passkey,
    set_session_passkey,
    set_vault_passkey,
    store_file,
    store_password,
    store_secret,
    verify_vault_passkey,
)


class VaultAuthModal(ResponsiveModalScreen[Optional[str]]):
    """Modal dialog prompting the user for vault passkey authentication with an explicit reason."""

    DEFAULT_CSS = """
    VaultAuthModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }
    #vault_auth_dialog {
        width: 68;
        max-width: 95%;
        height: auto;
        border: thick #3399ff;
        background: #0d0d0d;
        padding: 1 2;
    }
    #vault_auth_title {
        text-style: bold;
        color: #ffffff;
        margin-bottom: 1;
        text-align: center;
    }
    #vault_auth_reason_box {
        background: #141f2d;
        border-left: thick #3399ff;
        padding: 1;
        margin-bottom: 1;
    }
    #vault_auth_reason_title {
        color: #3399ff;
        text-style: bold;
    }
    #vault_auth_reason_text {
        color: #e0e0e0;
    }
    #vault_auth_input {
        width: 100%;
        margin-bottom: 1;
        border: solid #3399ff;
    }
    #vault_auth_buttons {
        width: 100%;
        height: auto;
        align: right middle;
    }
    #vault_auth_buttons Button {
        margin-left: 1;
    }
    VaultAuthModal.-mobile #vault_auth_dialog {
        width: 100vw;
        height: 100vh;
        max-width: 100vw;
        max-height: 100vh;
        border: none;
        padding: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+g", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        reason: str = "Unlocking Vault Management Console",
        title: str = "🔐 Vault Passkey Required",
        is_setup: bool = False,
    ) -> None:
        super().__init__()
        self.reason = reason
        self.dialog_title = title
        self.is_setup = is_setup or not is_vault_configured()

    def compose(self) -> ComposeResult:
        with Vertical(id="vault_auth_dialog"):
            yield Static(self.dialog_title, id="vault_auth_title")
            with Vertical(id="vault_auth_reason_box"):
                yield Static("Purpose / Reason:", id="vault_auth_reason_title")
                yield Static(self.reason, id="vault_auth_reason_text")

            if self.is_setup:
                yield Label("Set a new Vault Passkey to encrypt and protect your credentials:", classes="field_lbl")
                yield Input(
                    placeholder="Enter new passkey",
                    password=True,
                    id="vault_setup_pass",
                )
                yield Label("Confirm new Vault Passkey (2x confirmation):", classes="field_lbl")
                yield Input(
                    placeholder="Confirm new passkey",
                    password=True,
                    id="vault_setup_confirm",
                )
            else:
                yield Label("Enter Vault Passkey:", classes="field_lbl")
                yield Input(
                    placeholder="••••••••",
                    password=True,
                    id="vault_auth_input",
                )

            with Horizontal(id="vault_auth_buttons"):
                yield Button("Cancel", variant="error", id="vault_auth_cancel")
                yield Button("Unlock" if not self.is_setup else "Configure Vault", variant="primary", id="vault_auth_submit")

    def on_mount(self) -> None:
        super().on_mount()
        target = "#vault_setup_pass" if self.is_setup else "#vault_auth_input"
        try:
            self.query_one(target, Input).focus()
        except Exception:
            pass

    @on(Input.Submitted)
    def on_input_submitted(self) -> None:
        self._handle_submit()

    @on(Button.Pressed, "#vault_auth_submit")
    def on_submit_pressed(self) -> None:
        self._handle_submit()

    @on(Button.Pressed, "#vault_auth_cancel")
    def on_cancel_pressed(self) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _handle_submit(self) -> None:
        if self.is_setup:
            p1 = self.query_one("#vault_setup_pass", Input).value.strip()
            p2 = self.query_one("#vault_setup_confirm", Input).value.strip()
            if not p1:
                self.notify("Passkey cannot be empty.", severity="error")
                return
            if p1 != p2:
                self.notify("Passkeys did not match. Please re-enter.", severity="error")
                return
            set_vault_passkey(p1)
            set_session_passkey(p1)
            self.notify("✓ Vault passkey set and unlocked.", timeout=3.0)
            self.dismiss(p1)
        else:
            val = self.query_one("#vault_auth_input", Input).value.strip()
            if not val:
                self.notify("Passkey cannot be empty.", severity="error")
                return
            if verify_vault_passkey(val):
                set_session_passkey(val)
                self.dismiss(val)
            else:
                self.notify("Incorrect vault passkey.", severity="error")


class VaultChangePasskeyModal(ResponsiveModalScreen[Optional[bool]]):
    """Modal dialog prompting the user to rotate their vault passkey with mandatory 2x confirmation."""

    DEFAULT_CSS = """
    VaultChangePasskeyModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }
    #vault_rotate_dialog {
        width: 70;
        max-width: 95%;
        height: auto;
        border: thick #ffaa00;
        background: #0d0d0d;
        padding: 1 2;
    }
    #vault_rotate_title {
        text-style: bold;
        color: #ffaa00;
        margin-bottom: 1;
        text-align: center;
    }
    #vault_rotate_desc {
        color: #aaaaaa;
        margin-bottom: 1;
    }
    .rotate_lbl {
        color: #ffffff;
        text-style: bold;
        margin-top: 1;
    }
    #curr_pass, #new_pass, #confirm_pass {
        width: 100%;
        margin-bottom: 1;
    }
    #vault_rotate_buttons {
        width: 100%;
        height: auto;
        align: right middle;
    }
    #vault_rotate_buttons Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+g", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="vault_rotate_dialog"):
            yield Static("🔐 Rotate Vault Passkey", id="vault_rotate_title")
            yield Static(
                "Atomic re-encryption: unlocks all stored passwords, secrets, and files in memory "
                "with your current passkey, and re-encrypts all items with your new passkey.",
                id="vault_rotate_desc",
            )
            yield Label("Current Passkey:", classes="rotate_lbl")
            yield Input(placeholder="Current Passkey", password=True, id="curr_pass")
            yield Label("New Passkey:", classes="rotate_lbl")
            yield Input(placeholder="New Passkey", password=True, id="new_pass")
            yield Label("Confirm New Passkey (2x confirmation):", classes="rotate_lbl")
            yield Input(placeholder="Confirm New Passkey", password=True, id="confirm_pass")

            with Horizontal(id="vault_rotate_buttons"):
                yield Button("Cancel", variant="error", id="rotate_cancel")
                yield Button("Rotate & Re-encrypt", variant="primary", id="rotate_submit")

    def on_mount(self) -> None:
        super().on_mount()
        # Pre-fill current passkey if cached in session
        cached = get_session_passkey()
        if cached:
            self.query_one("#curr_pass", Input).value = cached
            self.query_one("#new_pass", Input).focus()
        else:
            self.query_one("#curr_pass", Input).focus()

    @on(Button.Pressed, "#rotate_submit")
    def on_submit(self) -> None:
        self._handle_rotation()

    @on(Button.Pressed, "#rotate_cancel")
    def on_cancel(self) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _handle_rotation(self) -> None:
        curr = self.query_one("#curr_pass", Input).value.strip()
        new1 = self.query_one("#new_pass", Input).value.strip()
        new2 = self.query_one("#confirm_pass", Input).value.strip()

        if not curr:
            self.notify("Current passkey is required.", severity="error")
            return
        if not new1:
            self.notify("New passkey cannot be empty.", severity="error")
            return
        if new1 != new2:
            self.notify("New passkeys do not match (2x confirmation check failed).", severity="error")
            return

        res = rotate_vault_passkey(curr, new1)
        if res.get("status") == "success":
            count = res.get("rotated_count", 0)
            self.notify(f"✓ Passkey rotated successfully. {count} items re-encrypted.", timeout=4.0)
            self.dismiss(True)
        else:
            self.notify(f"Rotation error: {res.get('message')}", severity="error")


class VaultPasswordEntryModal(ResponsiveModalScreen[Optional[dict]]):
    """Modal dialog prompting to save a password entry."""

    DEFAULT_CSS = """
    VaultPasswordEntryModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }
    #vault_pass_dialog {
        width: 72;
        max-width: 95%;
        height: auto;
        border: thick #3399ff;
        background: #0d0d0d;
        padding: 1 2;
    }
    #vault_pass_title {
        text-style: bold;
        color: #ffffff;
        margin-bottom: 1;
        text-align: center;
    }
    .vault_field_lbl {
        color: #ffffff;
        text-style: bold;
        margin-top: 1;
    }
    #pass_title, #pass_user, #pass_val, #pass_notes {
        width: 100%;
        margin-bottom: 1;
    }
    #vault_pass_buttons {
        width: 100%;
        height: auto;
        align: right middle;
    }
    #vault_pass_buttons Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+g", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="vault_pass_dialog"):
            yield Static("🔑 Store Password in Vault", id="vault_pass_title")
            yield Label("Title / Account Name:", classes="vault_field_lbl")
            yield Input(placeholder="e.g. Google Mail, GitHub, Server Admin", id="pass_title")
            yield Label("Username / Email (optional):", classes="vault_field_lbl")
            yield Input(placeholder="user@example.com", id="pass_user")
            yield Label("Password:", classes="vault_field_lbl")
            yield Input(placeholder="••••••••", password=True, id="pass_val")
            yield Label("Notes / Recovery Hints (optional):", classes="vault_field_lbl")
            yield Input(placeholder="Security notes, secondary email, etc.", id="pass_notes")

            with Horizontal(id="vault_pass_buttons"):
                yield Button("Cancel", variant="error", id="pass_cancel")
                yield Button("Save Password", variant="primary", id="pass_save")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#pass_title", Input).focus()

    @on(Button.Pressed, "#pass_save")
    def on_save(self) -> None:
        title = self.query_one("#pass_title", Input).value.strip()
        user = self.query_one("#pass_user", Input).value.strip()
        pwd = self.query_one("#pass_val", Input).value
        notes = self.query_one("#pass_notes", Input).value.strip()

        if not title:
            self.notify("Title is required.", severity="error")
            return
        if not pwd:
            self.notify("Password cannot be empty.", severity="error")
            return

        try:
            target = store_password(title=title, password=pwd, username=user, notes=notes)
            self.notify(f"✓ Password '{title}' encrypted and stored in vault.", timeout=3.5)
            self.dismiss({"title": title, "path": str(target)})
        except Exception as e:
            self.notify(f"Failed to store password: {e}", severity="error")

    @on(Button.Pressed, "#pass_cancel")
    def on_cancel(self) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class VaultSecretEntryModal(ResponsiveModalScreen[Optional[dict]]):
    """Modal dialog prompting to save a secret string with a 5-row infinite-length text area."""

    DEFAULT_CSS = """
    VaultSecretEntryModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }
    #vault_sec_dialog {
        width: 78;
        max-width: 95%;
        height: auto;
        border: thick #3399ff;
        background: #0d0d0d;
        padding: 1 2;
    }
    #vault_sec_title {
        text-style: bold;
        color: #ffffff;
        margin-bottom: 1;
        text-align: center;
    }
    .vault_field_lbl {
        color: #ffffff;
        text-style: bold;
        margin-top: 1;
    }
    #sec_title {
        width: 100%;
        margin-bottom: 1;
    }
    #sec_val {
        width: 100%;
        height: 8;
        margin-bottom: 1;
        background: #000000;
        border: solid #3399ff;
    }
    #vault_sec_buttons {
        width: 100%;
        height: auto;
        align: right middle;
    }
    #vault_sec_buttons Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+g", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="vault_sec_dialog"):
            yield Static("🔒 Store Secret String in Vault", id="vault_sec_title")
            yield Label("Title / Key Label:", classes="vault_field_lbl")
            yield Input(placeholder="e.g. Stripe Webhook Secret, Production RSA Key", id="sec_title")
            yield Label("Secret String (Infinite length, multiline supported):", classes="vault_field_lbl")
            yield TextArea(id="sec_val")

            with Horizontal(id="vault_sec_buttons"):
                yield Button("Cancel", variant="error", id="sec_cancel")
                yield Button("Save Secret", variant="primary", id="sec_save")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#sec_title", Input).focus()

    @on(Button.Pressed, "#sec_save")
    def on_save(self) -> None:
        title = self.query_one("#sec_title", Input).value.strip()
        secret_text = self.query_one("#sec_val", TextArea).text.strip()

        if not title:
            self.notify("Title is required.", severity="error")
            return
        if not secret_text:
            self.notify("Secret content cannot be empty.", severity="error")
            return

        try:
            target = store_secret(title=title, secret_text=secret_text)
            self.notify(f"✓ Secret '{title}' encrypted and stored in vault.", timeout=3.5)
            self.dismiss({"title": title, "path": str(target)})
        except Exception as e:
            self.notify(f"Failed to store secret: {e}", severity="error")

    @on(Button.Pressed, "#sec_cancel")
    def on_cancel(self) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class VaultFileEntryModal(ResponsiveModalScreen[Optional[dict]]):
    """Modal dialog prompting to encrypt and store a file with PathAutocompleteInput and shred option."""

    DEFAULT_CSS = """
    VaultFileEntryModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }
    #vault_file_dialog {
        width: 76;
        max-width: 95%;
        height: auto;
        border: thick #3399ff;
        background: #0d0d0d;
        padding: 1 2;
    }
    #vault_file_title {
        text-style: bold;
        color: #ffffff;
        margin-bottom: 1;
        text-align: center;
    }
    .vault_field_lbl {
        color: #ffffff;
        text-style: bold;
        margin-top: 1;
    }
    #file_title, #file_path_input {
        width: 100%;
        margin-bottom: 1;
    }
    #file_shred_row {
        width: 100%;
        height: auto;
        margin-bottom: 1;
        align-vertical: middle;
    }
    #vault_file_buttons {
        width: 100%;
        height: auto;
        align: right middle;
    }
    #vault_file_buttons Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+g", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="vault_file_dialog"):
            yield Static("📁 Encrypt & Store File in Vault", id="vault_file_title")
            yield Label("Title / File Label:", classes="vault_field_lbl")
            yield Input(placeholder="e.g. Production Keypair, Database Backup", id="file_title")
            yield Label("File Path (Tab to autocomplete, double-tab to escape to buttons):", classes="vault_field_lbl")
            yield FilePathInput(placeholder="Path to local file...", id="file_path_input")
            with Horizontal(id="file_shred_row"):
                yield Checkbox("Securely shred original plaintext file after encrypting", id="file_shred_check")

            with Horizontal(id="vault_file_buttons"):
                yield Button("Cancel", variant="error", id="file_cancel")
                yield Button("Encrypt & Store", variant="primary", id="file_save")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#file_title", Input).focus()

    @on(Button.Pressed, "#file_save")
    def on_save(self) -> None:
        title = self.query_one("#file_title", Input).value.strip()
        path_str = self.query_one("#file_path_input", FilePathInput).value.strip()
        shred = self.query_one("#file_shred_check", Checkbox).value

        if not title:
            self.notify("Title is required.", severity="error")
            return
        if not path_str:
            self.notify("File path is required.", severity="error")
            return

        src_path = Path(path_str).expanduser()
        if not src_path.is_file():
            self.notify(f"File not found: {path_str}", severity="error")
            return

        try:
            target = store_file(title=title, file_path=src_path, shred_original=shred)
            shred_msg = " (original shredded)" if shred else ""
            self.notify(f"✓ File '{title}' encrypted and stored in vault{shred_msg}.", timeout=3.5)
            self.dismiss({"title": title, "path": str(target)})
        except Exception as e:
            self.notify(f"Failed to encrypt file: {e}", severity="error")

    @on(Button.Pressed, "#file_cancel")
    def on_cancel(self) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class VaultDashboardModal(ResponsiveModalScreen[None]):
    """Master Vault Management Console: browse, search, and manage passwords, secrets, and files."""

    DEFAULT_CSS = """
    VaultDashboardModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }
    #vault_dash_dialog {
        width: 86;
        max-width: 95%;
        height: 30;
        max-height: 90vh;
        border: thick #3399ff;
        background: #0d0d0d;
        padding: 1 2;
    }
    #vault_dash_header {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }
    #vault_dash_title {
        text-style: bold;
        color: #ffffff;
        text-align: center;
        width: 100%;
    }
    #vault_category_bar {
        width: 100%;
        height: auto;
        margin-bottom: 1;
        align-horizontal: center;
    }
    #vault_category_bar Button {
        margin: 0 1;
    }
    #vault_search_filter {
        width: 100%;
        margin-bottom: 1;
        border: solid #3399ff;
    }
    #vault_entries_scroll {
        width: 100%;
        height: 1fr;
        border: solid #222222;
        background: #050505;
        padding: 1;
    }
    .vault_card {
        width: 100%;
        height: auto;
        border: solid #2a2a2a;
        background: #111111;
        padding: 0 1;
        margin-bottom: 1;
    }
    .vault_card_title {
        color: #3399ff;
        text-style: bold;
    }
    .vault_card_meta {
        color: #888888;
    }
    .vault_card_val {
        color: #e0e0e0;
        text-style: bold;
    }
    .vault_card_actions {
        width: 100%;
        height: auto;
        align-horizontal: right;
        margin-top: 0;
    }
    .vault_card_actions Button {
        margin-left: 1;
    }
    #vault_dash_toolbar {
        width: 100%;
        height: auto;
        margin-top: 1;
        align-horizontal: right;
    }
    #vault_dash_toolbar Button {
        margin: 0 0;
    }
    VaultDashboardModal.-mobile #vault_dash_dialog {
        width: 100vw;
        height: 100vh;
        max-width: 100vw;
        max-height: 100vh;
        border: none;
        padding: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("ctrl+g", "close", "Close"),
        Binding("p", "new_password", "New Password"),
        Binding("s", "new_secret", "New Secret"),
        Binding("f", "new_file", "New File"),
        Binding("r", "rotate_passkey", "Rotate Passkey"),
        Binding("l", "lock_vault", "Lock Vault"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.active_category: str = "passwords"  # "passwords" | "secrets" | "files"
        self.filter_query: str = ""
        self.revealed_items: set[str] = set()
        self.displayed_passwords: list[dict[str, Any]] = []
        self.displayed_secrets: list[dict[str, Any]] = []
        self.displayed_files: list[dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="vault_dash_dialog"):
            with Vertical(id="vault_dash_header"):
                yield Static("🔐 Gemini Vault Management Console", id="vault_dash_title")
                with Horizontal(id="vault_category_bar"):
                    yield Button("🔑 Passwords", variant="primary", id="cat_passwords_btn")
                    yield Button("🔒 Secrets", variant="default", id="cat_secrets_btn")
                    yield Button("📁 Files", variant="default", id="cat_files_btn")
                yield Input(placeholder="🔍 Search entries by title...", id="vault_search_filter")

            yield VerticalScroll(id="vault_entries_scroll")

            with Horizontal(id="vault_dash_toolbar"):
                yield Button("+ Password", variant="success", id="dash_add_pass")
                yield Button("+ Secret", variant="success", id="dash_add_sec")
                yield Button("+ File", variant="success", id="dash_add_file")
                yield Button("Rotate Key", variant="warning", id="dash_rotate")
                yield Button("Lock", variant="error", id="dash_lock")
                yield Button("Close", id="dash_close")

    def on_mount(self) -> None:
        super().on_mount()
        self.refresh_entries()

    def refresh_entries(self) -> None:
        scroll = self.query_one("#vault_entries_scroll", VerticalScroll)
        scroll.remove_children()

        q = self.filter_query.strip().lower()

        if self.active_category == "passwords":
            passwords = list_passwords()
            self.displayed_passwords = [p for p in passwords if not q or q in p["title"].lower() or q in p["username"].lower()]
            if not self.displayed_passwords:
                scroll.mount(Static("[dim]No passwords found. Press '+ Password' to store one.[/dim]"))
                return
            for i, p in enumerate(self.displayed_passwords):
                title = p["title"]
                is_revealed = title in self.revealed_items
                disp_val = p["password"] if is_revealed else "••••••••"
                rev_label = "Hide" if is_revealed else "Reveal"

                card_children = [
                    Static(f"🔑 {title}", classes="vault_card_title"),
                ]
                if p.get("username"):
                    card_children.append(Static(f"User: {p['username']}", classes="vault_card_meta"))
                card_children.append(Static(f"Pass: {disp_val}", classes="vault_card_val"))
                if p.get("notes"):
                    card_children.append(Static(f"Notes: {p['notes']}", classes="vault_card_meta"))

                act_row = Horizontal(
                    Button(rev_label, id=f"rev_pass_{i}"),
                    Button("Copy", id=f"copy_pass_{i}"),
                    Button("Delete", variant="error", id=f"del_pass_{i}"),
                    classes="vault_card_actions",
                )
                card_children.append(act_row)
                card = Vertical(*card_children, classes="vault_card")
                scroll.mount(card)

        elif self.active_category == "secrets":
            secrets_list = list_secrets()
            self.displayed_secrets = [s for s in secrets_list if not q or q in s["title"].lower()]
            if not self.displayed_secrets:
                scroll.mount(Static("[dim]No secrets found. Press '+ Secret' to store one.[/dim]"))
                return
            for i, s in enumerate(self.displayed_secrets):
                title = s["title"]
                raw_sec = s.get("secret", "")
                preview = (raw_sec[:40] + "...") if len(raw_sec) > 40 else raw_sec

                act_row = Horizontal(
                    Button("Copy", id=f"copy_sec_{i}"),
                    Button("Delete", variant="error", id=f"del_sec_{i}"),
                    classes="vault_card_actions",
                )
                card = Vertical(
                    Static(f"🔒 {title}", classes="vault_card_title"),
                    Static(f"Payload: {preview}", classes="vault_card_val"),
                    act_row,
                    classes="vault_card",
                )
                scroll.mount(card)

        elif self.active_category == "files":
            files_list = list_categorized_files()
            self.displayed_files = [f for f in files_list if not q or q in f["title"].lower() or q in f["original_name"].lower()]
            if not self.displayed_files:
                scroll.mount(Static("[dim]No files encrypted in vault. Press '+ File' to store one.[/dim]"))
                return
            for i, f in enumerate(self.displayed_files):
                title = f["title"]
                orig_name = f.get("original_name", "")
                size_kb = f.get("original_size", 0) / 1024
                legacy_tag = " [dim cyan](Root/Legacy)[/dim cyan]" if f.get("is_legacy") else ""

                act_row = Horizontal(
                    Button("Copy", id=f"copy_file_{i}"),
                    Button("Export", id=f"export_file_{i}"),
                    Button("Delete", variant="error", id=f"del_file_{i}"),
                    classes="vault_card_actions",
                )
                card = Vertical(
                    Static(f"📁 {title}{legacy_tag}", classes="vault_card_title"),
                    Static(f"Original: {orig_name} ({size_kb:.1f} KB)", classes="vault_card_meta"),
                    act_row,
                    classes="vault_card",
                )
                scroll.mount(card)

    @on(Input.Changed, "#vault_search_filter")
    def on_filter_changed(self, event: Input.Changed) -> None:
        self.filter_query = event.value
        self.refresh_entries()

    @on(Button.Pressed, "#cat_passwords_btn")
    def on_cat_pass(self) -> None:
        self.active_category = "passwords"
        self._update_cat_buttons()
        self.refresh_entries()

    @on(Button.Pressed, "#cat_secrets_btn")
    def on_cat_sec(self) -> None:
        self.active_category = "secrets"
        self._update_cat_buttons()
        self.refresh_entries()

    @on(Button.Pressed, "#cat_files_btn")
    def on_cat_files(self) -> None:
        self.active_category = "files"
        self._update_cat_buttons()
        self.refresh_entries()

    def _update_cat_buttons(self) -> None:
        for cat, bid in (("passwords", "#cat_passwords_btn"), ("secrets", "#cat_secrets_btn"), ("files", "#cat_files_btn")):
            btn = self.query_one(bid, Button)
            btn.variant = "primary" if self.active_category == cat else "default"

    @on(Button.Pressed)
    def on_button_click(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""

        # Bottom toolbar buttons
        if btn_id == "dash_close":
            self.dismiss(None)
            return
        elif btn_id == "dash_lock":
            self.action_lock_vault()
            return
        elif btn_id == "dash_rotate":
            self.action_rotate_passkey()
            return
        elif btn_id == "dash_add_pass":
            self.action_new_password()
            return
        elif btn_id == "dash_add_sec":
            self.action_new_secret()
            return
        elif btn_id == "dash_add_file":
            self.action_new_file()
            return

        # Entry actions: Reveal Password
        if btn_id.startswith("rev_pass_"):
            try:
                idx = int(btn_id.replace("rev_pass_", ""))
                p = self.displayed_passwords[idx]
                title = p["title"]
                if title in self.revealed_items:
                    self.revealed_items.remove(title)
                else:
                    self.revealed_items.add(title)
                self.refresh_entries()
            except Exception:
                pass
            return

        # Entry actions: Copy Password
        if btn_id.startswith("copy_pass_"):
            try:
                idx = int(btn_id.replace("copy_pass_", ""))
                p = self.displayed_passwords[idx]
                title = p["title"]
                pwd_data = get_password(title)
                self.app.copy_to_clipboard(pwd_data.get("password", ""))
                self.notify(f"✓ Copied password for '{title}' to clipboard.")
            except Exception as e:
                self.notify(f"Copy error: {e}", severity="error")
            return

        # Entry actions: Delete Password
        if btn_id.startswith("del_pass_"):
            try:
                idx = int(btn_id.replace("del_pass_", ""))
                p = self.displayed_passwords[idx]
                title = p["title"]
                delete_password(title)
                self.revealed_items.discard(title)
                self.notify(f"Deleted password '{title}'.")
                self.refresh_entries()
            except Exception as e:
                self.notify(f"Delete error: {e}", severity="error")
            return

        # Entry actions: Copy Secret
        if btn_id.startswith("copy_sec_"):
            try:
                idx = int(btn_id.replace("copy_sec_", ""))
                s = self.displayed_secrets[idx]
                title = s["title"]
                sec_data = get_secret(title)
                self.app.copy_to_clipboard(sec_data.get("secret", ""))
                self.notify(f"✓ Copied secret '{title}' to clipboard.")
            except Exception as e:
                self.notify(f"Copy error: {e}", severity="error")
            return

        # Entry actions: Delete Secret
        if btn_id.startswith("del_sec_"):
            try:
                idx = int(btn_id.replace("del_sec_", ""))
                s = self.displayed_secrets[idx]
                title = s["title"]
                delete_secret(title)
                self.notify(f"Deleted secret '{title}'.")
                self.refresh_entries()
            except Exception as e:
                self.notify(f"Delete error: {e}", severity="error")
            return

        # Entry actions: Copy File Content
        if btn_id.startswith("copy_file_"):
            try:
                idx = int(btn_id.replace("copy_file_", ""))
                f_item = self.displayed_files[idx]
                title = f_item["title"]
                data = retrieve_from_vault(f_item.get("file_name") or title)
                text = data.decode("utf-8")
                self.app.copy_to_clipboard(text)
                self.notify(f"✓ Copied contents of '{title}' to clipboard.")
            except UnicodeDecodeError:
                self.notify(f"'{title}' is a binary file; use Export instead.", severity="warning")
            except Exception as e:
                self.notify(f"Copy error: {e}", severity="error")
            return

        # Entry actions: Export File
        if btn_id.startswith("export_file_"):
            try:
                idx = int(btn_id.replace("export_file_", ""))
                f_item = self.displayed_files[idx]
                title = f_item["title"]
                dest_dir = Path.cwd()
                exported = export_file(f_item.get("file_name") or title, dest_dir)
                self.notify(f"✓ Exported '{title}' to {exported.name} in current directory.")
            except Exception as e:
                self.notify(f"Export error: {e}", severity="error")
            return

        # Entry actions: Delete File
        if btn_id.startswith("del_file_"):
            try:
                idx = int(btn_id.replace("del_file_", ""))
                f_item = self.displayed_files[idx]
                title = f_item["title"]
                delete_vault_file(f_item.get("file_name") or title)
                self.notify(f"Deleted vault file '{title}'.")
                self.refresh_entries()
            except Exception as e:
                self.notify(f"Delete error: {e}", severity="error")
            return

    def action_close(self) -> None:
        self.dismiss(None)

    def action_lock_vault(self) -> None:
        clear_session_passkey()
        self.notify("Vault locked. Session credentials cleared from RAM.", severity="warning")
        self.dismiss(None)

    def action_rotate_passkey(self) -> None:
        def _on_done(res: bool | None) -> None:
            if res:
                self.refresh_entries()
        self.app.push_screen(VaultChangePasskeyModal(), _on_done)

    def action_new_password(self) -> None:
        def _on_saved(res: dict | None) -> None:
            if res:
                self.active_category = "passwords"
                self._update_cat_buttons()
                self.refresh_entries()
        self.app.push_screen(VaultPasswordEntryModal(), _on_saved)

    def action_new_secret(self) -> None:
        def _on_saved(res: dict | None) -> None:
            if res:
                self.active_category = "secrets"
                self._update_cat_buttons()
                self.refresh_entries()
        self.app.push_screen(VaultSecretEntryModal(), _on_saved)

    def action_new_file(self) -> None:
        def _on_saved(res: dict | None) -> None:
            if res:
                self.active_category = "files"
                self._update_cat_buttons()
                self.refresh_entries()
        self.app.push_screen(VaultFileEntryModal(), _on_saved)
