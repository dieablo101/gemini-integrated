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
           (socket-path (expand-file-name "~/.gemini/gemini_textual.sock"))
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

(defun gemini-insert-file-into-window (buf-name file-path)
  "Insert FILE-PATH contents at point inside BUF-NAME without blocking or buffer limits."
  (let ((buf (get-buffer buf-name)))
    (if buf
        (with-current-buffer buf
          (insert-file-contents file-path))
      (with-current-buffer (window-buffer (selected-window))
        (insert-file-contents file-path)))))

(defun gemini-insert-into-window (buf-name text)
  "Insert TEXT at point inside BUF-NAME without moving focus unexpectedly."
  (let ((buf (get-buffer buf-name)))
    (if buf
        (with-current-buffer buf
          (insert text))
      (with-current-buffer (window-buffer (selected-window))
        (insert text)))))