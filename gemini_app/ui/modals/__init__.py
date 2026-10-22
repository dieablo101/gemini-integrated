"""Modal dialogs: commands, confirm, fork, inputs, snippets, git trees, api key, frame select, and vault."""

from gemini_app.ui.modals.api_key import ApiKeyModal
from gemini_app.ui.modals.base import ResponsiveModalScreen
from gemini_app.ui.modals.commands import CommandsModal
from gemini_app.ui.modals.confirm import ConfirmModal
from gemini_app.ui.modals.fork import ForkModal
from gemini_app.ui.modals.git_setup import GitSetupModal
from gemini_app.ui.modals.inputs import (
    DirectoryPathInput,
    FilePathInput,
    TitlePromptModal,
)
from gemini_app.ui.modals.password import PasswordModal, PasswordPromptModal
from gemini_app.ui.modals.snippets import (
    FrameSelectModal,
    GitTreeModal,
    InsertFileModal,
    WriteSnippetModal,
)
from gemini_app.ui.modals.vault import (
    VaultAuthModal,
    VaultChangePasskeyModal,
    VaultDashboardModal,
    VaultFileEntryModal,
    VaultPasswordEntryModal,
    VaultSecretEntryModal,
)
from gemini_app.ui.modals.wingman_auth import WingmanAuthModal

__all__ = [
    "ApiKeyModal",
    "GitSetupModal",
    "PasswordModal",
    "PasswordPromptModal",
    "ResponsiveModalScreen",
    "CommandsModal",
    "ConfirmModal",
    "ForkModal",
    "DirectoryPathInput",
    "FilePathInput",
    "TitlePromptModal",
    "WriteSnippetModal",
    "InsertFileModal",
    "GitTreeModal",
    "FrameSelectModal",
    "VaultAuthModal",
    "VaultChangePasskeyModal",
    "VaultDashboardModal",
    "VaultFileEntryModal",
    "VaultPasswordEntryModal",
    "VaultSecretEntryModal",
    "WingmanAuthModal",
]
