import os
import sys
import socket
import paramiko

HOST = sys.argv[1] if len(sys.argv) > 1 else os.getenv("TERMUX_HOST", "127.0.0.1")
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else int(os.getenv("TERMUX_PORT", "8022"))
USER = sys.argv[3] if len(sys.argv) > 3 else os.getenv("TERMUX_USER", "u0_a0")
PASS = sys.argv[4] if len(sys.argv) > 4 else os.getenv("TERMUX_PASS", "")

def check_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2.0)
    try:
        return s.connect_ex((HOST, PORT)) == 0
    except Exception:
        return False
    finally:
        s.close()

if not check_port():
    print(f"[-] Port {PORT} on {HOST} is not open yet.")
    sys.exit(1)

print(f"[+] Port {PORT} open! Connecting with Paramiko...")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=10)
print("[+] SSH connection established successfully!")
stdin, stdout, stderr = ssh.exec_command("uname -a && whoami")
print("[+] Remote output:", stdout.read().decode().strip())
ssh.close()
