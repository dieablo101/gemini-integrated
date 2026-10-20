#!/usr/bin/env python3
import os
import pty
import select
import sys
import time

def run_pty_command(cmd, password, timeout=30):
    pid, master = pty.openpty()
    proc = os.fork()
    if proc == 0:
        # child
        os.close(master)
        os.setsid()
        # set standard file descriptors to slave
        slave = os.open(os.ttyname(pid), os.O_RDWR)
        for fd in (0, 1, 2):
            os.dup2(slave, fd)
        if slave > 2:
            os.close(slave)
        os.execvp(cmd[0], cmd)
    else:
        # parent
        output = b""
        start_time = time.time()
        password_sent = False
        try:
            while time.time() - start_time < timeout:
                r, _, _ = select.select([master], [], [], 0.5)
                if master in r:
                    try:
                        data = os.read(master, 1024)
                    except OSError:
                        break
                    if not data:
                        break
                    output += data
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()

                    lower = output.lower()
                    if b"are you sure you want to continue connecting" in lower:
                        os.write(master, b"yes\n")
                        output = b""
                    elif b"password:" in lower and not password_sent:
                        time.sleep(0.2)
                        os.write(master, (password + "\n").encode())
                        password_sent = True
                        output = b""
        finally:
            os.close(master)
            _, status = os.waitpid(proc, 0)
            return status

if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else os.getenv("TERMUX_HOST", "127.0.0.1")
    port = sys.argv[2] if len(sys.argv) > 2 else os.getenv("TERMUX_PORT", "8022")
    user = sys.argv[3] if len(sys.argv) > 3 else os.getenv("TERMUX_USER", "u0_a0")
    pwd = sys.argv[4] if len(sys.argv) > 4 else os.getenv("TERMUX_PASS", "")

    # Check ssh-copy-id or test ssh
    cmd = ["ssh", "-p", port, "-o", "StrictHostKeyChecking=no", f"{user}@{host}", "uname -a; whoami"]
    print(f"Connecting to {user}@{host}:{port}...")
    run_pty_command(cmd, pwd)
