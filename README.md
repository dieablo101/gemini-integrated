# Gemini

PLEASE NOTE: THIS IS OUT OF DATE! I WILL UPDATE LATER ;-)

A terminal-based AI chat application built with **Textual** and the **Google GenAI SDK** (`gemini-3.8-flash`), featuring interactive chat branching (forking), code snippet insertion and extraction, Git tree exploration, and tight Emacs integration.

---

## Features

### 1. Interactive Chat Forking
- Branch conversations at any arbitrary point (`C-.` or `C-c .`).
- Card-based selection interface to cherry-pick turns from the conversation history.
- Automatically inserts a fork header notice and preserves hierarchy relationships without immediately re-prompting the model.
- Forked chats are assigned sub-chat hierarchy in the chat list.

### 2. File & Git Integration
- **Git Tree Explorer (`C-c g` / `Ctrl+\`)**: Browse tracked and `.gitignore`-ignored files side-by-side. Supports full or partial tree visualization insertion and toggling entire subtrees.
- **Insert File (`C-c f` / `Ctrl+f`)**: Insert any file from disk into your prompt with automatic syntax detection and line range tracking.
- **Write Snippet to Disk (`C-c r` / `Ctrl+r`)**: Save the active code block directly to disk with overwrite protection and path auto-completion.
- **Scoping**: Switch between a global working directory or chat-scoped working directories.

### 3. Snippet Management & Live Preview
- Snippets use tokens (`{&snippet1}`, `{&snippet2}`) inside the prompt input.
- Move the cursor onto a snippet token in the input box to open an editable, syntax-highlighted preview pane (`SnippetPreview`).
- Dynamic Markdown code fence renderer hooks into line numbers to reflect real source line spans accurately.

### 4. Emacs Integration & Keybindings
- **Unix Domain Socket Server** (`/tmp/gemini_textual.sock`): Allows external scripts or Emacs processes to push code selections directly into the active prompt input.
- **Emacs Yank Integration (`C-c y` / `Ctrl+y`)**: Sends active code snippets or responses directly into an active Emacs buffer/window via `emacsclient`. When multiple frames/windows exist, an interactive frame selector dialog appears.
- **Emacs Keybindings**: Full suite of readline/Emacs keybindings across input areas (`C-a`, `C-e`, `C-f`, `C-b`, `M-f`, `M-b`, `C-k`, `C-u`, `M-d`, `C-w`, `C-y`, `M-w`, `C-/`, `C-c` prefix chords).
- **Command Palette (`M-x` / `Alt+x`)**: Built-in menu palette for discovering and executing commands.

### 5. Chat History & Persistence
- Automatically saves conversations as JSON under `chats/`.
- Visual tree display for parent chats and forks.
- Renaming (`r` or `C-c t`) and deletion (`d`, `x`, `Delete`).
- Automatic orphan resolution: If a parent chat is deleted, children gracefully detach to top-level chats.

---

## Installation

### Prerequisites
- Python 3.10+
- A Google Gemini API key configured (via `GEMINI_API_KEY` environment variable).
- Optional: `emacs` / `emacsclient` running as a daemon or server if using Emacs frame-pasting features.

### Dependencies
Install the required dependencies:

```bash
pip install textual google-genai rich pyperclip
```

Ensure `gemini.py` is executable:

```bash
chmod +x gemini.py
```

---

## Usage

Set your Gemini API key and run the script:

```bash
export GEMINI_API_KEY="your-api-key-here"
./gemini.py
```

### Remote Code Insertion (from Bash / External Tools)

You can send text directly to the running application input buffer over the Unix socket:

```bash
python3 -c '
import socket, json

payload = {
    "action": "insert",
    "text": "def hello():\n    print(\"Hello world\")",
    "lang": "python",
    "file": "test.py",
    "start_line": 1,
    "end_line": 2
}
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect("/tmp/gemini_textual.sock")
s.sendall(json.dumps(payload).encode("utf-8"))
s.close()
'
```

---

## Keybindings Reference

### Global / Emacs Prefix (`C-c`)
| Key | Command | Description |
| :--- | :--- | :--- |
| `Alt+x` / `M-x` | `command_palette` | Open Command Palette / Menu |
| `C-c n` / `Ctrl+n` | `new_chat` | Start a new chat session |
| `C-c b` / `Ctrl+b` | `toggle_history` | Toggle chat history list view |
| `C-.` / `C-c .` | `fork_chat` | Enter fork mode / confirm fork |
| `C-c y` / `Ctrl+y` | `copy_last_response` | Yank active snippet/response to clipboard & Emacs |
| `C-c r` / `Ctrl+r` | `save_snippet_to_disk` | Save active snippet to disk |
| `C-c f` / `Ctrl+f` | `insert_file_from_disk`| Insert a file as a snippet into prompt |
| `C-c g` / `Ctrl+\` | `open_git_tree` | Open Git Tree modal dialog |
| `C-c e` / `Ctrl+e` | `open_in_editor` | Open current chat transcript in `$EDITOR` |
| `C-c t` / `Ctrl+t` | `rename_chat` | Rename current chat session |
| `Escape` | `toggle_focus` | Cycle focus between Feed, Preview, and Input |
| `Ctrl+q` | `quit` | Exit application |

### Input Area (`ExpandingInput` & `SnippetPreview`)
| Key | Action |
| :--- | :--- |
| `Enter` | Submit prompt to Gemini |
| `Shift+Enter` / `Ctrl+j` | Insert a newline |
| `Up` / `Ctrl+p` (line 0) | Focus Snippet Preview (when active) |
| `Alt+n` / `Alt+p` | Select next / previous snippet in feed |
| `Ctrl+Space` / `Ctrl+@` | Set selection mark |
| `Ctrl+a` / `Ctrl+e` | Beginning / End of line |
| `Alt+f` / `Alt+b` | Forward / Backward word |
| `Ctrl+k` | Kill to end of line |
| `Ctrl+u` | Kill to beginning of line |
| `Alt+d` | Kill next word |
| `Ctrl+w` | Cut selection or kill previous word |
| `Ctrl+y` | Paste from system clipboard |
| `Alt+w` | Copy selected region |
| `Ctrl+/` | Undo |

### Feed Area (`FeedArea`)
| Key | Action |
| :--- | :--- |
| `j` / `k` / `Down` / `Up` | Scroll feed down / up |
| `Alt+n` / `Alt+p` | Navigate through syntax-highlighted code fences |
| `Ctrl+r` | Save the currently highlighted code fence to disk |
| `Ctrl+f` | Insert a file into prompt |
| `Escape` / `i` / `Ctrl+o` | Return focus to prompt input |
| `.` / `f` | Initiate chat fork mode |

### Fork Mode (`ForkTurnCard`)
| Key | Action |
| :--- | :--- |
| `Space` / Click | Toggle selection of conversation turn card |
| `Alt+n` / `Alt+down` / `j` / `Down` | Move to next turn card |
| `Alt+p` / `Alt+up` / `k` / `Up` | Move to previous turn card |
| `a` | Toggle selection of all turns |
| `Enter` | Confirm turn selection and proceed to fork naming |
| `Escape` / `C-g` | Cancel fork mode |

### Chat History View (`HistoryList`)
| Key | Action |
| :--- | :--- |
| `j` / `k` / `Down` / `Up` | Navigate chat entries |
| `Enter` | Load highlighted chat session |
| `d` / `x` / `Delete` | Delete highlighted chat |
| `r` | Rename highlighted chat |
| `Escape` / `q` / `C-g` | Exit history view back to conversation |

---

## File Structure

```text
├── gemini.py             # Main application executable
└── chats/                # Conversation sessions stored as JSON
    ├── <id>.json
    └── ...
```

## Emacs Integration Setup (Optional)

To enable seamless round-trip sending between Emacs and this application:

### 1. Send selected text from Emacs to Gemini Client

Add this Elisp to your `init.el` for flawless victory.

Add the following Elisp hooks to your configuration so `C-c y` can target open Emacs windows:

```elisp
;; Turns on global line numbers
(global-display-line-numbers-mode)
;; Turns off backup files that clutter
(setq make-backup-files nil)
;; NO FILE LOCKS
(setq create-lockfiles nil)
;; Remove trailing spaces from cpy pst
(add-hook 'prog-mode-hook
  (lambda () (add-hook
'before-save-hook
'delete-trailing-whitespace nil t)))
;; Turn off autosave
(setq auto-save-default nil)
;; Fixes issues of cpy pst code into emacs
(electric-indent-mode -1)
;; Turns tabs into spaces
(setq-default indent-tabs-mode nil)
;; Auto reload files when they change on disk, ie. a buffer change automatically.
(global-auto-revert-mode 1)
(setq global-auto-revert-non-file-buffers t)
(setq auto-revert-interval 2)
(setq auto-revert-verbose nil)
;; Set python to Python3 for shell interpreter
(setq python-shell-interpreter "python3")
;; Turns on background Daemon
(when (executable-find "my-daemon")
  (start-process "my-daemon-proc" nil "my-daemon"))
;; Starts the Emacs Server
(require 'server)
(unless (server-running-p)
  (server-start))

;; Remove top menu bar
(menu-bar-mode -1)
;; Line Wrap
(setq-default truncate-lines nil)
(setq truncate-partial-width-windows nil)
(global-visual-line-mode -1)

;; EMACS && GEMINI APP CONNECTION
(require 'json)

(defun gemini--detect-language ()
  "Detect programming language identifier for Markdown syntax fences."
  (let ((mode (symbol-name major-mode))
        (ext (when buffer-file-name (file-name-extension buffer-file-name))))
    (cond
     ((and ext (string= ext "py")) "python")
     ((and ext (string= ext "el")) "elisp")
     ((and ext (string= ext "rs")) "rust")
     ((and ext (string= ext "js")) "javascript")
     ((and ext (string= ext "ts")) "typescript")
     ((and ext (string= ext "cpp")) "cpp")
     ((and ext (string= ext "c")) "c")
     ((and ext (string= ext "h")) "c")
     ((and ext (string= ext "sh")) "bash")
     ((and ext (string= ext "go")) "go")
     ((and ext (string= ext "html")) "html")
     ((and ext (string= ext "css")) "css")
     ((and ext (string= ext "json")) "json")
     ((and ext (string= ext "yaml")) "yaml")
     ((and ext (string= ext "yml")) "yaml")
     ((and ext (string= ext "md")) "markdown")
     ((string-match "^\\([a-zA-Z0-9+-]+\\)-ts-mode" mode)
      (match-string 1 mode))
     ((string-match "^\\([a-zA-Z0-9+-]+\\)-mode" mode)
      (let ((base (match-string 1 mode)))
        (cond
         ((string= base "emacs-lisp") "elisp")
         ((string= base "c++") "cpp")
         ((string= base "c") "c")
         ((string= base "js") "javascript")
         ((string= base "js2") "javascript")
         ((string= base "typescript") "typescript")
         ((string= base "python") "python")
         ((string= base "rust") "rust")
         ((string= base "sh") "bash")
         ((string= base "shell-script") "bash")
         ((string= base "ruby") "ruby")
         ((string= base "go") "go")
         ((string= base "html") "html")
         ((string= base "css") "css")
         ((string= base "sql") "sql")
         ((string= base "yaml") "yaml")
         ((string= base "json") "json")
         (t base))))
     (ext ext)
     (t ""))))

(defun gemini-chat-send-region ()
  "Send the selected region with file metadata to the Textual Gemini app."
  (interactive)
  (if (not (use-region-p))
      (message "Gemini: No region selected! Set a mark with C-SPC first.")
    (let* ((beg (region-beginning))
           (end (region-end))
           (start-line (line-number-at-pos beg))
           (end-pos (if (and (> end beg) (eq (char-before end) ?\n))
                        (max beg (1- end))
                      end))
           (end-line (line-number-at-pos end-pos))
           (file-name (if buffer-file-name
                          (file-name-nondirectory buffer-file-name)
                        (buffer-name)))
           (text (buffer-substring-no-properties beg end))
           (lang (gemini--detect-language))
           (socket-path "/tmp/gemini_textual.sock")
           (payload (json-encode `((action . "insert")
                                   (text . ,text)
                                   (lang . ,lang)
                                   (file . ,file-name)
                                   (start_line . ,start-line)
                                   (end_line . ,end-line)))))
      (if (not (file-exists-p socket-path))
          (message "Gemini: Socket %s not found. Is your chat app running?" socket-path)
        (condition-case err
            (let ((proc (make-network-process
                         :name "gemini-chat-sender"
                         :family 'local
                         :service socket-path
                         :nowait nil)))
              (process-send-string proc payload)
              (delete-process proc)
              (message "Gemini: Sent %s (Lines %d-%d) [%s]"
                       file-name start-line end-line (if (string= lang "") "code" lang)))
          (error
           (message "Gemini error: %s" (error-message-string err))))))))

(global-set-key (kbd "C-c g i") #'gemini-chat-send-region)

;; Frame and Window Query / Insertion Helpers for Gemini

(defun gemini-list-open-frames ()
  "Return JSON list of all active client terminal frames and their windows."
  (let ((result '())
        (frame-counter 1))
    (dolist (f (frame-list))
      ;; Filter out dead frames and the headless initial daemon frame
      (when (and (frame-live-p f)
                 (not (string= "Finitial" (frame-parameter f 'name)))
                 (terminal-live-p (frame-terminal f)))
        (let ((win-list '()))
          (dolist (w (window-list f 'no-minibuf))
            (let* ((b (window-buffer w))
                   (b-name (buffer-name b))
                   (file-path (or (buffer-file-name b) ""))
                   (file-disp (if (not (string= file-path ""))
                                  (file-name-nondirectory file-path)
                                b-name)))
              ;; Filter out internal star buffers
              (unless (and (string-prefix-p " *" b-name)
                           (not (string= b-name "*scratch*")))
                (push `((buf_name . ,b-name)
                        (file_name . ,file-disp)
                        (path . ,file-path))
                      win-list))))
          (when win-list
            (push `((frame_num . ,frame-counter)
                    (frame_id . ,(format "%s" f))
                    (windows . ,(apply 'vector (nreverse win-list))))
                  result)
            (setq frame-counter (1+ frame-counter))))))
    (json-encode (apply 'vector (nreverse result)))))

(defun gemini-insert-into-window (buf-name text)
  "Insert TEXT at point inside BUF-NAME without moving focus unexpectedly."
  (let ((buf (get-buffer buf-name)))
    (if buf
        (with-current-buffer buf
          (insert text))
      (with-current-buffer (window-buffer (selected-window))
        (insert text)))))
```

This program was written by the gemini API.