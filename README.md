# Gemini Textual TUI Client

A keyboard-centric, feature-rich Terminal User Interface (TUI) chat client for the Google Gemini API built with [Textual](https://textual.textualize.io/) and Python. Designed specifically for power users, developers, and Emacs enthusiasts who want fluid code-snippet staging, deep Git/filesystem awareness, and bidirectional editor integration.

---

## Features

- **Emacs-Inspired Navigation & Ergonomics:**
  - Standard keybindings throughout text inputs (`C-a`, `C-e`, `C-p`, `C-n`, `C-f`, `C-b`, `M-f`, `M-b`, `C-k`, `C-u`, `M-d`, `C-w`, `M-w`, `C-y`, etc.).
  - Two-key `C-c` leader prefixes for primary app actions.
  - Interactive command palette bound to `M-x` (`Alt+x`).

- **Bidirectional Emacs Integration & IPC:**
  - Unix Domain Socket (`/tmp/gemini_textual.sock`) listener allowing external tools (like Emacs) to insert snippets directly into your prompt buffer.
  - Frame & window introspection via `emacsclient`: yank responses or active snippets directly into active or selected Emacs buffers.

- **Dynamic Snippet Staging System:**
  - Insert code snippets using references like `{&snippet1}` inside your prompt.
  - Automatic floating preview box displays and allows real-time edits to the snippet at the cursor.
  - Accurate file-relative start and end line numbering in code fence headers.

- **Git & Filesystem Intelligence:**
  - **Interactive Git Tree Explorer (`C-c g` / `Ctrl+\`):** Dual-tree explorer displaying both Git-tracked files and `.gitignore`-ignored files. Select files individually or whole directories to inject ASCII project trees and staged file snippets directly into the prompt.
  - **Insert File (`C-c f` / `Ctrl+f`):** Path auto-completion with language detection from file extensions.
  - **Write to Disk (`C-c r` / `Ctrl+r`):** Save any selected code snippet from the chat feed directly to disk, with conflict detection and overwrite confirmation.
  - Chat-scoped vs. global working directory tracking.

- **Chat Persistence & History Management:**
  - Automatic JSON persistence under `chats/`.
  - Full history drawer (`C-c b` / `Ctrl+b`) with live chat search, renaming (`r`), and deletion (`d` / `x`).
  - Open full chat transcripts directly into your favorite editor/pager via `$EDITOR` (`C-c e`).

---

## Requirements

- Python 3.10+
- A Google Gemini API Key (`GEMINI_API_KEY` set in your environment)
- Optional: `git` and `emacsclient` for repository browsing and Emacs integration

### Python Dependencies

- `textual`
- `google-genai`
- `pyperclip`
- `rich`

---

## Installation & Setup

1. **Clone the repository or save `gemini.py` locally:**

   ```bash
   git clone <repo-url>
   cd <repo-folder>
   ```

2. **Set up a virtual environment and install dependencies:**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install textual google-genai pyperclip rich
   ```

3. **Export your Gemini API Key:**

   ```bash
   export GEMINI_API_KEY="your-gemini-api-key-here"
   ```

4. **Run the application:**

   ```bash
   python gemini.py
   ```

---

## Keyboard Shortcuts

### Global / Application Actions

| Keybinding | Emacs Prefix | Action |
|---|---|---|
| `Alt+x` | — | Open Menu / Command Palette (`M-x`) |
| `Ctrl+n` | `C-c n` | Start a new chat session |
| `Ctrl+b` | `C-c b` | Toggle Chat History sidebar |
| `Ctrl+t` | `C-c t` | Rename active chat session |
| `Ctrl+f` | `C-c f` | Insert file from disk as a snippet |
| `Ctrl+\` | `C-c g` | Open Interactive Git Tree Explorer |
| `Ctrl+r` | `C-c r` | Save active snippet from feed to disk |
| `Ctrl+y` | `C-c y` | Yank active snippet / response (copies to clipboard & Emacs) |
| `Ctrl+e` | `C-c e` | Open conversation in `$EDITOR` / `$PAGER` |
| `Escape` | — | Cycle focus (Feed Area ↔ Snippet Preview ↔ Prompt Input) |
| `Ctrl+q` | — | Quit application |

---

### Text Input & Snippet Preview (Emacs Navigation)

| Key | Description |
|---|---|
| `Ctrl+a` / `Ctrl+e` | Move to start / end of line |
| `Ctrl+f` / `Ctrl+b` | Move cursor character forward / backward |
| `Alt+f` / `Alt+b` | Move cursor word forward / backward |
| `Ctrl+p` / `Ctrl+n` | Move cursor line up / down (or jump into snippet preview) |
| `Ctrl+Space` | Set selection mark |
| `Ctrl+k` | Kill from cursor to end of line |
| `Ctrl+u` | Kill from cursor to beginning of line |
| `Alt+d` | Kill word forward |
| `Ctrl+w` | Kill region (or kill word backward if no mark set) |
| `Alt+w` | Copy selected region |
| `Ctrl+y` | Paste / Yank from clipboard |
| `Ctrl+/` | Undo |
| `Enter` | Submit prompt |
| `Shift+Enter` / `Ctrl+j` | Insert newline |

---

### Feed Navigation

| Key | Description |
|---|---|
| `j` / `k` or `Down` / `Up` | Scroll conversation up / down |
| `PageUp` / `PageDown` | Scroll page up / down |
| `Home` / `End` | Jump to conversation start / end |
| `Alt+n` / `Alt+Down` | Focus / cycle to next code snippet block |
| `Alt+p` / `Alt+Up` | Focus / cycle to previous code snippet block |
| `i` / `Ctrl+o` / `Escape` | Return focus to prompt input |

---

### History Drawer Navigation

| Key | Description |
|---|---|
| `j` / `k` or `Down` / `Up` | Select chat session |
| `Enter` | Load highlighted chat session |
| `r` | Rename highlighted chat session |
| `d` / `x` / `Delete` | Delete highlighted chat session |
| `Escape` / `q` / `Ctrl+g` | Close history drawer |

---

### Path & Directory Completion Inputs

- **Tab (1x):** Auto-completes directory or file path inline.
- **Tab (2x quickly):** Navigates focus to the next UI element.

---

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