### Gemini

# Gemini Textual TUI

A full-featured, terminal-based AI chat interface powered by the official **Google GenAI SDK** and built on top of **Textual**. 

Designed specifically for Emacs-style keyboard workflows, this application features full Mark/Kill-ring text manipulation, dynamic code snippet reference insertion, multi-chat local persistence, and direct two-way integration with running Emacs instances via `emacsclient`.

Lamens: Open this program in a terminal window and emacs in another, even multiple frames of emacs with various windows. Simply select a code snippet from gemini with alt + n or alt + p and ctrl + y it directly into your emacs file at cursor location. In emacs, to send a code snippet to gemini through this app, simply press ctrl + c then g then i while in an emacs frame / window  and it will paste into this app from your emacs client frame / window. You can edit the code snippet also from within this app before finalizing it to send to Gemini. Want to move around your recent chats with gemini? press ctrl + c then b and change the chat, this app keeps persistant chat history by default. This app allows you to communicate and program with the google LLM ( large language model ) aka Gemini at high speed by integrating the IDE emacs with Gemini AI integration.

I have full intention of making this more robust as time goes on, ill work on it as I see fit. No requests or ideas taken into consideration. Cannot be sold, redistributed for profit or used for any unlawful acts.

---

## 1. Installation & Environment Setup

This project requires **Python 3.10+** (Python 3.11+ recommended).

### Additionals - important

- Install emacs on your system via command line
Add to ~/.bashrc at the bottom 
- alias emacs="emacsclient -nw -a ''"

AND
- copy or move file additionals/init.el into ~/.emacs.d folder and replace default

### Create and Activate Virtual Environment

Create virtual environment (adjust path if needed, e.g., /opt/gemini/.venv)
python3 -m venv .venv

### Activate virtual environment
source .venv/bin/activate

### Install Required Python Packages

Install the necessary dependencies using pip:

pip install google-genai textual rich pyperclip

| Package | Purpose |
| :--- | :--- |
| google-genai | Official Google GenAI SDK (Gemini API calls) |
| textual | Terminal User Interface (TUI) application framework |
| rich | Terminal markup, Markdown rendering, and code syntax highlighting |
| pyperclip | Cross-platform OS clipboard access (Kill ring / Yank support) |

### API Key Configuration

Ensure your Google Gemini API key is exported into your environment before running the app:

export GEMINI_API_KEY="your-gemini-api-key-here"

(Optional) If you want system-wide clipboard integration on Linux without a native display manager clipboard, install xclip or xsel:
sudo apt install xclip   # Debian/Ubuntu
sudo pacman -S xclip     # Arch Linux

---

## 2. Project & Folder Structure

The project follows a decoupled, modular package architecture separating rendering logic, backend integrations, and UI state:

```text
gemini_tui/
├── gemini.py                   # Main CLI executable / entrypoint script
├── chats/                      # Directory where conversation JSON files are saved
│
└── gemini_app/
    ├── __init__.py             # Exports top-level ChatApp
    ├── app.py                  # Core application orchestration & event lifecycle
    ├── config.py               # Constants, filesystem paths, and model configurations
    ├── events.py               # Custom Textual Message definitions (RemoteInsert, etc.)
    ├── styles.tcss             # Textual CSS stylesheet (supports textual dev live-reload)
    │
    ├── hooks/
    │   ├── __init__.py
    │   └── markdown.py         # Monkeys-patches MarkdownFence for real source line numbers
    │
    ├── services/
    │   ├── __init__.py
    │   ├── chat_store.py       # Persistence layer: saves, loads, and deletes chat JSON
    │   ├── emacs.py            # emacsclient IPC wrapper & frame/window query evaluator
    │   ├── gemini.py           # GenAI client wrapper & background generation worker
    │   └── socket_server.py    # Async Unix domain socket server (/tmp/gemini_textual.sock)
    │
    ├── widgets/
    │   ├── __init__.py
    │   ├── emacs_text_area.py  # Base TextArea with Emacs cursor, mark, and kill-ring keys
    │   ├── input_area.py       # Multi-line input area resolving snippet tokens
    │   ├── snippet_preview.py  # Floating editable snippet review box
    │   ├── feed.py             # Markdown stream renderer with snippet jumping
    │   └── history_list.py     # Interactive conversation history drawer
    │
    └── screens/
        ├── __init__.py
        ├── title_modal.py      # Modal popup for naming/renaming chat threads
        ├── frame_modal.py      # Modal picker for targeting destination Emacs windows
        └── palette.py          # Emacs-styled CommandPalette (M-x menu)
```
---

## 3. Running the Application

NOTE: Run app from installed location via terminal. ie. navigate to folder, run app execution command. ./gemini

Make gemini.py executable, or launch via python:

chmod +x gemini.py
./gemini.py

Or run through an activated virtual environment:
python gemini.py

To run in live Textual Developer Mode (for editing CSS live):
textual run --dev gemini.py

---

## 4. In-App Commands & Keybindings

The application is structured into four primary UI zones:
1. Feed Area (Top conversation stream)
2. Snippet Preview (Collapsible editor above input when snippets are inserted)
3. Input Area (Bottom multi-line prompt box)
4. History Drawer (Collapsible chat manager)

### Global Prefix & App Navigation
The app features an Emacs-style C-c (Ctrl+C) prefix table. Press Ctrl+C followed by the command letter:

| Key Chord | Action | Description |
| :--- | :--- | :--- |
| M-x / Alt+x | command_palette | Open the Emacs-style Menu / Command Palette. |
| C-c n / Ctrl+c n | new_chat | Prompt for topic and create a fresh chat session. |
| C-c b / Ctrl+c b | toggle_history | Toggle chat history drawer open/closed. |
| C-c y / Ctrl+c y | copy_last_response | Yank active snippet or model response to Emacs buffer & clipboard. |
| C-c e / Ctrl+c e | open_in_editor | Open full conversation transcript in $EDITOR or $PAGER. |
| C-c t / Ctrl+c t | rename_chat | Rename the current chat session. |
| Escape | toggle_focus | Rotate focus: Feed ↔ Snippet Preview ↔ Input Area. |
| Ctrl+q | quit | Quit application immediately. |

---

### Emacs Text-Editing Keys (Input Box & Snippet Preview)
Both the prompt area and the snippet preview implement Emacs-style navigation and editing shortcuts:

| Key | Action |
| :--- | :--- |
| Ctrl+Space / Ctrl+@ | Set Mark (begin active selection region). |
| Ctrl+f / Ctrl+b | Move cursor Forward / Backward by character. |
| Alt+f / Alt+b | Move cursor Forward / Backward by word. |
| Ctrl+a / Ctrl+e | Move to beginning / end of the current line. |
| Alt+< / Alt+> | Move to beginning / end of entire document. |
| Ctrl+k | Kill forward from cursor to end of line (copies to clipboard). |
| Ctrl+u | Kill backward from cursor to beginning of line (copies to clipboard). |
| Alt+d | Kill word forward. |
| Ctrl+w | Kill active region (or kill word backward if no selection). |
| Alt+w | Copy active region to system clipboard without deleting. |
| Ctrl+y | Yank (Paste from system clipboard). |
| Ctrl+/ / Ctrl+_ | Undo last edit. |
| Enter | Submit prompt to Gemini (Input area only). |
| Shift+Enter / Ctrl+j | Insert literal newline without submitting. |

---

### Conversation Feed (FeedArea) Navigation
When focused on the Feed (top panel):

| Key | Action |
| :--- | :--- |
| j / Down | Scroll down one line. |
| k / Up | Scroll up one line. |
| PageDown / PageUp | Scroll feed by page. |
| Home / End | Jump to very beginning / latest message. |
| Alt+n / Alt+Down | Jump to next code block (highlights and focuses snippet). |
| Alt+p / Alt+Up | Jump to previous code block. |
| Click on Code Block | Direct-select a code snippet to make it active for yanking. |
| i / Escape / Ctrl+o | Drop focus back down to Input Area. |

---

### History Drawer (HistoryList)
Toggle open using C-c b. While inside the history list:

| Key | Action |
| :--- | :--- |
| j / Ctrl+n / Down | Move selection down. |
| k / Ctrl+p / Up | Move selection up. |
| Enter | Load selected chat and return to feed. |
| r | Rename highlighted chat. |
| d / x / Delete | Delete highlighted chat from disk immediately. |
| q / Escape / Ctrl+g | Close history drawer without changing active chat. |

---

## 5. Emacs Two-Way Integration & IPC Socket

### 1. External Ingestion Socket
When the app launches, it opens a Unix Domain Socket at:
/tmp/gemini_textual.sock

You can pump code from external scripts or Emacs hooks into the running TUI by sending a JSON payload formatted as:
{
  "action": "insert",
  "text": "print('hello world')",
  "lang": "python",
  "file": "main.py",
  "start_line": 10,
  "end_line": 12
}

This triggers an inline {&snippet1} token inside the input prompt, automatically renders the code snippet preview with correct line numbers, and focuses your input box.

### 2. Emacs Yank Dispatcher (C-c y)
When yanking code out of Gemini back into your editor via C-c y:
- If 1 Emacs frame is active: Text inserts directly at point in the active buffer.
- If Multiple frames/windows are active: An Emacs Frame Selection Modal automatically prompts you to choose which window/buffer receives the snippet.