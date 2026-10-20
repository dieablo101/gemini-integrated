#!/usr/bin/env python3
"""Runner script for the modular Gemini Bilateral Terminal Console.

Autonomously bootstraps virtual environment, pip dependencies,
system dependencies, and API key on first launch.
Handles subcommands (hud/monitor, satellite/node, mothership, upgrade, autostart, nodes)
cleanly without requiring heavy UI or API dependencies.
"""

from __future__ import annotations

import os
from pathlib import Path
import platform
import subprocess
import sys


def is_constrained_platform() -> bool:
    """Detects whether running on a constrained, emulated, or 32-bit platform."""
    if sys.maxsize <= 2**32:
        return True
    if os.path.exists("/proc/ish"):
        return True
    try:
        u = platform.uname()
        if "ish" in u.release.lower() or "ish" in u.version.lower():
            return True
    except Exception:
        pass
    if Path("/mnt/ipad").exists():
        return True
    if platform.machine().lower() in ("i386", "i686", "armv7l", "armv6l", "armhf", "aarch32"):
        return True
    return False


def ensure_environment() -> None:
    """Ensures a virtual environment exists with required packages and re-execs inside it if needed."""
    constrained = is_constrained_platform()

    # Check if already running in a virtualenv with required packages
    in_venv = (sys.prefix != sys.base_prefix) or ("VIRTUAL_ENV" in os.environ)
    if in_venv:
        try:
            import textual
            import rich
            import pyperclip
            if not constrained:
                import google.genai
            return  # Environment is fully operational
        except ImportError:
            pass

    script_dir = Path(__file__).resolve().parent
    venv_dir = script_dir / ".venv"
    if not venv_dir.exists():
        try:
            venv_dir.mkdir(parents=True, exist_ok=True)
            venv_dir.rmdir()
        except OSError:
            venv_dir = Path.home() / ".gemini" / "venv"

    venv_python = venv_dir / "bin" / "python3"

    if not venv_python.exists():
        sys.stdout.write("⚡ First-time launch: Initializing virtual environment (.venv)...\n")
        try:
            import venv
            venv.create(str(venv_dir), with_pip=True, clear=False)
        except Exception:
            subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

    # Check dependencies in venv
    check_code = (
        "import textual, rich, pyperclip"
        if constrained
        else "import textual, google.genai, rich, pyperclip"
    )
    req_check = subprocess.run(
        [str(venv_python), "-c", check_code],
        capture_output=True,
    )
    if req_check.returncode != 0:
        if constrained:
            sys.stdout.write("⚡ Constrained architecture detected. Installing pure-wheel UI packages...\n")
            pkg_list = ["textual>=0.50.0", "rich>=13.0.0", "pyperclip>=1.8.0"]
        else:
            sys.stdout.write("⚡ Installing required pip packages into .venv...\n")
            subprocess.run(
                [str(venv_python), "-m", "pip", "install", "--upgrade", "-q", "pip", "setuptools", "wheel"],
                check=False,
            )
            pkg_list = ["textual>=0.50.0", "google-genai>=1.0.0", "rich>=13.0.0", "pyperclip>=1.8.0"]

        try:
            subprocess.run(
                [str(venv_python), "-m", "pip", "install", "-q"] + pkg_list,
                check=True,
            )
            sys.stdout.write("✓ Virtual environment & dependencies ready.\n")
        except subprocess.CalledProcessError as exc:
            sys.stderr.write(f"Warning: pip install failed ({exc}). Continuing with available packages.\n")

    # If we are not currently running under venv_python, re-exec into venv
    if Path(sys.executable).resolve() != venv_python.resolve():
        os.execv(str(venv_python), [str(venv_python), str(Path(__file__).resolve())] + sys.argv[1:])


def print_help() -> None:
    """Displays command-line help for gemini-integrated."""
    help_text = """Gemini Integrated Bilateral Terminal Console

Usage:
  python3 gemini-integrated.py [options]
  python3 gemini-integrated.py hud [options]
  python3 gemini-integrated.py node [options]
  python3 gemini-integrated.py mothership [options]
  python3 gemini-integrated.py autostart [options]
  python3 gemini-integrated.py nodes [options]
  python3 gemini-integrated.py upgrade

Subcommands:
  hud, monitor            Run live Telemetry and AI Cognitive Monitor HUD
  node, satellite         Run as lightweight distributed satellite node
  mothership              Run fleet mothership command-and-control server
  autostart               Configure persistent boot autostart service on this device
  nodes, fleet            Inspect connected nodes or perform remote SSH rescue/reboot
  upgrade                 Perform atomic 3-stage pre-flight upgrade on local node

Autostart Options:
  --install               Install boot persistence service (systemd, openrc, launchd, or cron)
  --status                Inspect autostart daemon installation status
  --remove, --uninstall   Disable and remove boot persistence service
  --mothership HOST       Mothership IP/host (default: 192.168.1.90)

Fleet / Nodes Options:
  --list                  List active and registered nodes with SSH details
  --rescue NODE_ID        Execute remote SSH restart rescue using dieablo key
  --reboot NODE_ID        Reboot remote node machine over SSH using dieablo key
  --check NODE_ID         Check remote process vitals and iPad mount status

Node / HUD Options:
  --mothership HOST       Mothership IP/host (default: 192.168.1.90)
  --port PORT             Mothership TCP port (default: 7331)
  --interval SECONDS      Heartbeat telemetry interval in seconds (default: 15.0)
  --hud, --monitor        Enable interactive landscape-friendly HUD dashboard
  --once                  Send single registration/telemetry probe and exit
  --node-id ID            Override satellite node identifier

General Options:
  -h, --help              Show this help message and exit
  -v, --version           Show version information and exit
  --satellite             Shorthand for running in satellite node mode
  --ui                    Force local terminal UI even on constrained platforms
"""
    print(help_text.strip())


if __name__ == "__main__":
    # 1. First parse high-level flags and subcommands before touching venv or packages
    argv_set = set(sys.argv[1:])

    if "-h" in argv_set or "--help" in argv_set:
        print_help()
        sys.exit(0)

    if "-v" in argv_set or "--version" in argv_set:
        from gemini_app import __version__
        print(f"gemini-integrated v{__version__}")
        sys.exit(0)

    # 2. Check for autostart command
    if "autostart" in argv_set or "--autostart" in argv_set:
        for tok in ["autostart", "--autostart"]:
            if tok in sys.argv:
                sys.argv.remove(tok)
        from gemini_app.fleet.autostart import check_autostart_status, install_autostart, remove_autostart
        import argparse
        as_parser = argparse.ArgumentParser(description="Gemini Satellite Boot Autostart Provisioner")
        as_parser.add_argument("--install", action="store_true", help="Install boot autostart service")
        as_parser.add_argument("--remove", "--uninstall", action="store_true", help="Remove boot autostart")
        as_parser.add_argument("--status", action="store_true", help="Check autostart installation status")
        as_parser.add_argument("--mothership", default="192.168.1.90", help="Mothership host IP")
        as_parser.add_argument("--interval", type=float, default=10.0, help="Heartbeat interval")
        as_args = as_parser.parse_args(sys.argv[1:])

        if as_args.remove:
            res = remove_autostart()
            print(f"[autostart] {res.get('message')}")
        elif as_args.status:
            res = check_autostart_status()
            print(f"[autostart] Status: {res}")
        else:
            res = install_autostart(mothership=as_args.mothership, interval=as_args.interval)
            print(f"[autostart] Result: {res.get('status')} - {res.get('message', res.get('error'))}")
        sys.exit(0)

    # 3. Check for nodes / fleet management CLI
    if "nodes" in argv_set or "fleet" in argv_set:
        for tok in ["nodes", "fleet"]:
            if tok in sys.argv:
                sys.argv.remove(tok)
        from gemini_app.fleet.nodes import execute_ssh_rescue, get_fleet_snapshot
        import argparse
        node_parser = argparse.ArgumentParser(description="Gemini Fleet & Node Remote Management")
        node_parser.add_argument("--list", action="store_true", help="List active and registered nodes")
        node_parser.add_argument("--rescue", metavar="NODE_ID", help="Perform remote SSH rescue on node")
        node_parser.add_argument("--reboot", metavar="NODE_ID", help="Reboot remote node over SSH")
        node_parser.add_argument("--check", metavar="NODE_ID", help="Inspect remote node status over SSH")
        node_parser.add_argument("--action", default="restart", help="Action for rescue (restart|reboot|check)")
        n_args = node_parser.parse_args(sys.argv[1:])

        if n_args.rescue:
            res = execute_ssh_rescue(n_args.rescue, action=n_args.action)
            print(f"[rescue] Result for '{n_args.rescue}': {res.get('status')}")
            if res.get("stdout"):
                print(res["stdout"])
            if res.get("error"):
                print(f"Error: {res['error']}")
        elif n_args.reboot:
            res = execute_ssh_rescue(n_args.reboot, action="reboot")
            print(f"[reboot] Dispatched reboot to '{n_args.reboot}': {res.get('status')}")
        elif n_args.check:
            res = execute_ssh_rescue(n_args.check, action="check")
            print(f"[check] Status for '{n_args.check}':")
            print(res.get("stdout", res.get("error", "Unknown")))
        else:
            snap = get_fleet_snapshot()
            print(f"Mothership Fleet: {snap.get('active_count')} active / {snap.get('total_registered')} registered")
            for n in snap.get("nodes", []):
                st = "🟢 LIVE" if n.get("status") == "online" else "🔴 OFFLINE"
                key_name = Path(n.get("ssh_key", "")).name if n.get("ssh_key") else "dieablo101"
                print(f"  • {n.get('node_id')} ({n.get('host')}:{n.get('ssh_port', 22)}) [{st}] SSH: {n.get('ssh_user')}@{n.get('host')} [key: {key_name}]")
        sys.exit(0)

    # 4. Check for HUD / Monitor mode
    hud_tokens = {"hud", "monitor", "--hud", "--monitor"}
    matched_hud = [tok for tok in sys.argv[1:] if tok in hud_tokens]
    if matched_hud:
        for tok in matched_hud:
            sys.argv.remove(tok)
        # Ensure --hud is in sys.argv for satellite parser
        if "--hud" not in sys.argv:
            sys.argv.append("--hud")
        from gemini_app.fleet.satellite import main as satellite_main
        sys.exit(satellite_main())

    # 5. Check for upgrade command
    if "upgrade" in argv_set or "--upgrade" in argv_set:
        for tok in ["upgrade", "--upgrade"]:
            if tok in sys.argv:
                sys.argv.remove(tok)
        from gemini_app.fleet.satellite import execute_fleet_upgrade
        print("[gemini] Initiating 3-stage pre-flight node upgrade...")
        res = execute_fleet_upgrade()
        print(f"Status: {res.get('status')}")
        print(f"Message: {res.get('message', res.get('error'))}")
        sys.exit(0 if res.get("status") == "ok" else 1)

    # 6. Check for node/satellite mode anywhere in CLI arguments
    satellite_tokens = {"--node", "-n", "--satellite", "node", "satellite"}
    matched_sat = [tok for tok in sys.argv[1:] if tok in satellite_tokens]
    if matched_sat:
        for tok in matched_sat:
            sys.argv.remove(tok)
        from gemini_app.fleet.satellite import main as satellite_main
        sys.exit(satellite_main())

    # 7. Check for mothership server mode
    mothership_tokens = {"--mothership-server", "--fleet-server", "mothership"}
    matched_mother = [tok for tok in sys.argv[1:] if tok in mothership_tokens]
    if matched_mother:
        for tok in matched_mother:
            sys.argv.remove(tok)
        from gemini_app.fleet.mothership import main as mothership_main
        sys.exit(mothership_main())

    # 8. If on a constrained platform without google-genai, auto-route gracefully
    if is_constrained_platform():
        try:
            import google.genai
        except ImportError:
            # Check if user specified --ui explicitly
            if "--ui" not in sys.argv:
                sys.stdout.write(
                    "⚡ Constrained mobile platform detected (iPad iSH / 32-bit musl).\n"
                    "   Local Google GenAI SDK requires Rust wheels not supported on this device.\n"
                    "   Auto-launching Live Telemetry HUD to connect with Mothership...\n"
                    "   (Pass --ui to force local terminal UI)\n\n"
                )
                if "--hud" not in sys.argv:
                    sys.argv.append("--hud")
                from gemini_app.fleet.satellite import main as satellite_main
                sys.exit(satellite_main())

    ensure_environment()
    from gemini_app.main import main
    main()
