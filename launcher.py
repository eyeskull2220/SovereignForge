#!/usr/bin/env python3
"""
SovereignForge Unified Launcher
================================
Single entry point to start, stop, and manage all system components.

Usage:
    python launcher.py                    # Interactive menu
    python launcher.py start              # Start API + Dashboard
    python launcher.py start --paper      # Start API + Dashboard + Paper Trading
    python launcher.py start --all        # Start everything
    python launcher.py stop               # Stop all running components
    python launcher.py status             # Show component status
    python launcher.py train              # Launch GPU training
    python launcher.py fetch              # Fetch exchange data
    python launcher.py health             # System health check
"""

import os
import sys
import time
import json
import signal
import socket
import subprocess
import platform
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# -- Project root ----------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"
LOGS_DIR = PROJECT_ROOT / "logs"
MODELS_DIR = PROJECT_ROOT / "models" / "strategies"
CONFIG_DIR = PROJECT_ROOT / "config"
PID_FILE = PROJECT_ROOT / ".launcher_pids.json"

# -- Ports -----------------------------------------------------------------
PORTS = {
    "api": 8420,
    "dashboard": 3000,
    "redis": 6379,
    "prometheus": 9090,
    "grafana": 3001,
}

# -- Colors ----------------------------------------------------------------
class C:
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    RESET = "\033[0m"

def cprint(msg: str, color: str = C.RESET):
    try:
        print(f"{color}{msg}{C.RESET}")
    except UnicodeEncodeError:
        print(f"{color}{msg.encode('ascii', 'replace').decode()}{C.RESET}")

def banner():
    cprint(r"""
    +======================================================+
    |        SovereignForge Unified Launcher                |
    |        MiCA Compliant - USDC Only - 12 Pairs          |
    +======================================================+
    """, C.CYAN)


# -- PID Management --------------------------------------------------------

def save_pids(pids: Dict[str, int]):
    with open(PID_FILE, "w") as f:
        json.dump(pids, f, indent=2)

def load_pids() -> Dict[str, int]:
    if PID_FILE.exists():
        try:
            with open(PID_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}

def is_pid_alive(pid: int) -> bool:
    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True, timeout=5
            )
            return str(pid) in result.stdout
        else:
            os.kill(pid, 0)
            return True
    except (OSError, subprocess.TimeoutExpired):
        return False

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


# -- Health Checks ---------------------------------------------------------

def check_python() -> Tuple[bool, str]:
    ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ok = sys.version_info >= (3, 10)
    return ok, f"Python {ver}" + ("" if ok else " (need 3.10+)")

def check_gpu() -> Tuple[bool, str]:
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            return True, f"GPU: {name} ({vram:.1f} GB VRAM)"
        return False, "No CUDA GPU available"
    except ImportError:
        return False, "PyTorch not installed"

def check_models() -> Tuple[bool, str]:
    if not MODELS_DIR.exists():
        return False, "No models directory"
    models = list(MODELS_DIR.glob("*.pth"))
    if len(models) == 0:
        return False, "No trained models found"
    strategies = set()
    for m in models:
        name = m.stem.split("_")[0]
        strategies.add(name)
    return True, f"{len(models)} models ({', '.join(sorted(strategies))})"

def check_node() -> Tuple[bool, str]:
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return True, f"Node.js {result.stdout.strip()}"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return False, "Node.js not found"

def check_dashboard_built() -> Tuple[bool, str]:
    build_dir = DASHBOARD_DIR / "build"
    if build_dir.exists() and (build_dir / "index.html").exists():
        return True, "Dashboard build exists"
    return False, "Dashboard not built (run: cd dashboard && npm run build)"

def check_config() -> Tuple[bool, str]:
    trading_config = CONFIG_DIR / "trading_config.json"
    if trading_config.exists():
        try:
            with open(trading_config) as f:
                cfg = json.load(f)
            pairs = cfg.get("enabled_pairs", [])
            return True, f"{len(pairs)} pairs configured"
        except (json.JSONDecodeError, IOError):
            return False, "Config file corrupt"
    return False, "trading_config.json missing"

def check_data() -> Tuple[bool, str]:
    data_dir = PROJECT_ROOT / "data"
    if not data_dir.exists():
        return False, "No data directory"
    csv_count = len(list(data_dir.rglob("*.csv")))
    if csv_count == 0:
        return False, "No CSV data files found"
    return True, f"{csv_count} data files"

def run_health_check():
    cprint("\n  System Health Check", C.BOLD)
    cprint("  " + "=" * 40, C.DIM)

    checks = [
        ("Python", check_python()),
        ("GPU/CUDA", check_gpu()),
        ("Models", check_models()),
        ("Node.js", check_node()),
        ("Dashboard", check_dashboard_built()),
        ("Config", check_config()),
        ("Data", check_data()),
    ]

    # Port checks
    for name, port in PORTS.items():
        in_use = is_port_in_use(port)
        status = f"Port {port} {'IN USE' if in_use else 'available'}"
        checks.append((f"{name.upper()} Port", (in_use if name in ["api"] else not in_use, status)))

    all_ok = True
    for name, (ok, msg) in checks:
        icon = f"{C.GREEN}OK{C.RESET}" if ok else f"{C.RED}--{C.RESET}"
        print(f"  {icon}  {name:<15} {msg}")
        if not ok and name in ["Python", "Config"]:
            all_ok = False

    # Check running components
    pids = load_pids()
    if pids:
        cprint("\n  Running Components", C.BOLD)
        cprint("  " + "-" * 40, C.DIM)
        for comp, pid in pids.items():
            alive = is_pid_alive(pid)
            icon = f"{C.GREEN}UP{C.RESET}" if alive else f"{C.RED}DN{C.RESET}"
            print(f"  {icon}  {comp:<15} PID {pid}")

    print()
    return all_ok


# -- Component Launchers ---------------------------------------------------

def start_component(name: str, cmd: List[str], log_file: Optional[str] = None,
                    cwd: Optional[Path] = None, env: Optional[dict] = None) -> Optional[int]:
    """Start a component as a background process."""
    LOGS_DIR.mkdir(exist_ok=True)

    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    log_path = LOGS_DIR / (log_file or f"{name}.log")

    try:
        with open(log_path, "a") as log_f:
            log_f.write(f"\n{'='*60}\n")
            log_f.write(f"[{datetime.now().isoformat()}] Starting {name}\n")
            log_f.write(f"Command: {' '.join(cmd)}\n")
            log_f.write(f"{'='*60}\n")

            proc = subprocess.Popen(
                cmd,
                cwd=str(cwd or PROJECT_ROOT),
                stdout=log_f,
                stderr=subprocess.STDOUT,
                env=full_env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if platform.system() == "Windows" else 0,
            )
            cprint(f"  Started {name} (PID {proc.pid}) -> logs/{log_path.name}", C.GREEN)
            return proc.pid
    except FileNotFoundError:
        cprint(f"  Failed to start {name}: command not found ({cmd[0]})", C.RED)
        return None
    except Exception as e:
        cprint(f"  Failed to start {name}: {e}", C.RED)
        return None


def start_api() -> Optional[int]:
    """Start the FastAPI dashboard API on port 8420."""
    if is_port_in_use(PORTS["api"]):
        cprint(f"  API already running on port {PORTS['api']}", C.YELLOW)
        return None
    return start_component(
        "dashboard-api",
        [sys.executable, str(SRC_DIR / "dashboard_api.py")],
        log_file="dashboard_api.log",
    )


def _find_npm() -> str:
    """Find npm executable on the system."""
    import shutil
    npm = shutil.which("npm")
    if npm:
        return npm
    # Common Windows locations
    for candidate in [
        Path(os.environ.get("APPDATA", "")) / "npm" / "npm.cmd",
        Path("C:/Program Files/nodejs/npm.cmd"),
        Path("/e/Downloads/npm"),
    ]:
        if candidate.exists():
            return str(candidate)
    return "npm"  # fallback, let it fail with clear error

def start_dashboard() -> Optional[int]:
    """Start the React dashboard dev server."""
    if is_port_in_use(PORTS["dashboard"]):
        cprint(f"  Dashboard already running on port {PORTS['dashboard']}", C.YELLOW)
        return None

    npm = _find_npm()

    node_modules = DASHBOARD_DIR / "node_modules"
    if not node_modules.exists():
        cprint("  Installing dashboard dependencies...", C.YELLOW)
        subprocess.run([npm, "install"], cwd=str(DASHBOARD_DIR), timeout=120)

    env = {"BROWSER": "none", "PORT": str(PORTS["dashboard"])}
    return start_component(
        "dashboard-ui",
        [npm, "start"],
        log_file="dashboard_ui.log",
        cwd=DASHBOARD_DIR,
        env=env,
    )


def start_paper_trading(balance: float = 300.0) -> Optional[int]:
    """Start the paper trading engine."""
    models_ok, _ = check_models()
    if not models_ok:
        cprint("  Cannot start paper trading: no trained models found", C.RED)
        cprint("  Run: python launcher.py train", C.DIM)
        return None

    return start_component(
        "paper-trading",
        [sys.executable, str(SRC_DIR / "paper_trading.py"), "--start", "--balance", str(balance)],
        log_file="paper_trading.log",
        env={"PAPER_TRADING_MODE": "true"},
    )


def start_training(args: Optional[List[str]] = None) -> Optional[int]:
    """Start GPU training."""
    gpu_ok, gpu_msg = check_gpu()
    if not gpu_ok:
        cprint(f"  GPU check: {gpu_msg}", C.RED)
        cprint("  Training requires CUDA GPU. Use cpu_train.py for CPU fallback.", C.DIM)
        return None

    train_cmd = [
        sys.executable, str(PROJECT_ROOT / "train_coin_by_coin.py"),
    ]
    if args:
        train_cmd = [sys.executable, str(PROJECT_ROOT / "gpu_train.py")] + args

    return start_component(
        "gpu-training",
        train_cmd,
        log_file="gpu_training.log",
    )


def fetch_data(exchanges: Optional[List[str]] = None, days: Optional[int] = None) -> Optional[int]:
    """Fetch historical exchange data."""
    cmd = [sys.executable, str(PROJECT_ROOT / "fetch_exchange_data.py")]
    if exchanges:
        cmd.extend(["--exchanges"] + exchanges)
    if days:
        cmd.extend(["--days", str(days)])
    return start_component("data-fetch", cmd, log_file="data_fetch.log")


# -- Stop ------------------------------------------------------------------

def stop_all():
    """Stop all running components."""
    pids = load_pids()
    if not pids:
        cprint("  No running components found.", C.DIM)
        return

    cprint("\n  Stopping components...", C.BOLD)
    for name, pid in pids.items():
        if is_pid_alive(pid):
            try:
                if platform.system() == "Windows":
                    # Graceful shutdown: try CTRL+C first, force-kill after 15s
                    subprocess.run(["taskkill", "/PID", str(pid)],
                                   capture_output=True, timeout=5)
                    # Wait up to 15s for graceful exit
                    import time as _time
                    for _ in range(15):
                        if not is_pid_alive(pid):
                            break
                        _time.sleep(1)
                    # Force-kill if still alive
                    if is_pid_alive(pid):
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                       capture_output=True, timeout=10)
                        cprint(f"  Force-stopped {name} (PID {pid})", C.YELLOW)
                    else:
                        cprint(f"  Stopped {name} (PID {pid})", C.GREEN)
                else:
                    os.kill(pid, signal.SIGTERM)
                    cprint(f"  Stopped {name} (PID {pid})", C.GREEN)
            except Exception as e:
                cprint(f"  Failed to stop {name} (PID {pid}): {e}", C.RED)
        else:
            cprint(f"  {name} (PID {pid}) already stopped", C.DIM)

    save_pids({})
    print()


# -- Status ----------------------------------------------------------------

def show_status():
    """Show status of all components."""
    cprint("\n  Component Status", C.BOLD)
    cprint("  " + "=" * 50, C.DIM)

    pids = load_pids()
    components = [
        ("Dashboard API", "api", PORTS["api"]),
        ("Dashboard UI", "dashboard", PORTS["dashboard"]),
        ("Paper Trading", None, None),
        ("GPU Training", None, None),
    ]

    for label, port_key, port in components:
        pid_name = label.lower().replace(" ", "-")
        pid = pids.get(pid_name)
        alive = is_pid_alive(pid) if pid else False
        port_up = is_port_in_use(port) if port else False

        if alive or port_up:
            status = f"{C.GREEN}RUNNING{C.RESET}"
            extra = f" (PID {pid})" if pid else ""
            if port:
                extra += f" @ http://localhost:{port}"
        else:
            status = f"{C.DIM}STOPPED{C.RESET}"
            extra = ""

        print(f"  {status}  {label:<18}{extra}")

    # Model count
    models_ok, models_msg = check_models()
    print(f"\n  {'Models:':<20}{models_msg}")

    # Training log
    train_log = LOGS_DIR / "gpu_training.log"
    if train_log.exists():
        with open(train_log, "r") as f:
            lines = f.readlines()
        last_line = lines[-1].strip() if lines else "empty"
        print(f"  {'Last train log:':<20}{last_line[:60]}")

    print()


# -- Interactive Menu ------------------------------------------------------

def interactive_menu():
    """Show interactive menu."""
    banner()
    run_health_check()

    menu_items = [
        ("1", "Start API + Dashboard",           "start"),
        ("2", "Start API + Dashboard + Paper",    "start --paper"),
        ("3", "Start Everything",                 "start --all"),
        ("4", "Stop All",                         "stop"),
        ("5", "Show Status",                      "status"),
        ("6", "Launch GPU Training",              "train"),
        ("7", "Fetch Exchange Data",              "fetch"),
        ("8", "System Health Check",              "health"),
        ("9", "Open Dashboard in Browser",        "open"),
        ("0", "Exit",                             "exit"),
    ]

    cprint("  Actions:", C.BOLD)
    for key, label, _ in menu_items:
        print(f"    {C.CYAN}{key}{C.RESET}  {label}")
    print()

    try:
        choice = input(f"  {C.BOLD}Select>{C.RESET} ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return

    action_map = {item[0]: item[2] for item in menu_items}
    action = action_map.get(choice)

    if action == "exit" or action is None:
        return
    elif action == "open":
        import webbrowser
        port = PORTS["api"]
        if is_port_in_use(PORTS["dashboard"]):
            port = PORTS["dashboard"]
        webbrowser.open(f"http://localhost:{port}")
        return
    else:
        # Re-dispatch to main with the action
        handle_command(action.split())


# -- Command Handler -------------------------------------------------------

def handle_command(args: List[str]):
    """Handle a command."""
    if not args:
        interactive_menu()
        return

    cmd = args[0]
    flags = args[1:]

    if cmd == "start":
        banner()
        pids = load_pids()

        cprint("  Starting SovereignForge...\n", C.BOLD)

        # Always start API
        pid = start_api()
        if pid:
            pids["dashboard-api"] = pid

        # Always start dashboard UI
        pid = start_dashboard()
        if pid:
            pids["dashboard-ui"] = pid

        # Paper trading
        if "--paper" in flags or "--all" in flags:
            time.sleep(2)  # Let API start first
            pid = start_paper_trading()
            if pid:
                pids["paper-trading"] = pid

        # Training
        if "--train" in flags or "--all" in flags:
            pid = start_training()
            if pid:
                pids["gpu-training"] = pid

        # Data fetch
        if "--fetch" in flags or "--all" in flags:
            pid = fetch_data()
            if pid:
                pids["data-fetch"] = pid

        save_pids(pids)

        print()
        cprint("  URLs:", C.BOLD)
        cprint(f"    Dashboard API:  http://localhost:{PORTS['api']}", C.GREEN)
        cprint(f"    Dashboard UI:   http://localhost:{PORTS['dashboard']}", C.GREEN)
        if "--paper" in flags or "--all" in flags:
            cprint(f"    Paper Trading:  Active (check logs/paper_trading.log)", C.GREEN)
        print()
        cprint("  Run 'python launcher.py status' to check components", C.DIM)
        cprint("  Run 'python launcher.py stop' to stop all", C.DIM)
        print()

    elif cmd == "stop":
        banner()
        stop_all()

    elif cmd == "status":
        banner()
        show_status()

    elif cmd == "health":
        banner()
        run_health_check()

    elif cmd == "train":
        banner()
        cprint("  Launching GPU Training...\n", C.BOLD)
        train_args = flags if flags else None
        pid = start_training(train_args)
        if pid:
            pids = load_pids()
            pids["gpu-training"] = pid
            save_pids(pids)
            cprint(f"\n  Training started. Monitor with:", C.DIM)
            cprint(f"    tail -f logs/gpu_training.log", C.DIM)
            cprint(f"    python live_monitor.py", C.DIM)

    elif cmd == "fetch":
        banner()
        cprint("  Fetching Exchange Data...\n", C.BOLD)
        exchanges = None
        days = None
        if "--exchanges" in flags:
            idx = flags.index("--exchanges")
            exchanges = []
            for f in flags[idx + 1:]:
                if f.startswith("--"):
                    break
                exchanges.append(f)
        if "--days" in flags:
            idx = flags.index("--days")
            if idx + 1 < len(flags):
                days = int(flags[idx + 1])
        pid = fetch_data(exchanges, days)
        if pid:
            pids = load_pids()
            pids["data-fetch"] = pid
            save_pids(pids)

    elif cmd == "open":
        import webbrowser
        port = PORTS["dashboard"] if is_port_in_use(PORTS["dashboard"]) else PORTS["api"]
        webbrowser.open(f"http://localhost:{port}")

    else:
        cprint(f"  Unknown command: {cmd}", C.RED)
        cprint("  Usage: python launcher.py [start|stop|status|health|train|fetch|open]", C.DIM)


# -- Main ------------------------------------------------------------------

if __name__ == "__main__":
    handle_command(sys.argv[1:])
