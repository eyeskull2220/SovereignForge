#!/usr/bin/env python3
"""
SovereignForge - Dashboard API

FastAPI backend serving training, portfolio, and model data
for the SovereignForge dashboard.

Usage:
    python src/dashboard_api.py
    # Starts on http://localhost:8420
"""

import asyncio
import json
import logging
import math
import os
import platform
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import traceback

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models" / "strategies"
LOGS_DIR = PROJECT_ROOT / "logs"
CONFIG_PATH = PROJECT_ROOT / "config" / "trading_config.json"
KNOWLEDGE_GRAPH_PATH = PROJECT_ROOT / "data" / "training_knowledge_graph.json"
PAPER_TRADING_STATE_PATH = PROJECT_ROOT / "reports" / "paper_trading_state.json"
DASHBOARD_DATA_PATH = PROJECT_ROOT / "reports" / "training_dashboard_data.json"
TRAINING_LOG_PATH = LOGS_DIR / "gpu_training.log"
DASHBOARD_DIST = PROJECT_ROOT / "dashboard" / "dist"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("dashboard_api")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
STRATEGIES = ["arbitrage", "fibonacci", "grid", "dca", "mean_reversion", "pairs_arbitrage", "momentum"]
EXCHANGES = ["binance", "coinbase", "kraken", "okx", "kucoin", "bybit", "gate"]
COINS = [
    "btc", "eth", "xrp", "xlm", "hbar", "algo",
    "ada", "link", "iota", "vet", "xdc", "ondo",
]
# Secrets that must never leak via /api/config
CONFIG_SECRET_KEYS = {"telegram_bot_token", "api_key", "api_secret", "passphrase", "password"}

API_KEY = os.environ.get("SOVEREIGNFORGE_API_KEY", "")

# ---------------------------------------------------------------------------
# Auth failure tracking — detect brute-force attempts
# ---------------------------------------------------------------------------
AUTH_FAILURE_WINDOW_SECONDS = 300  # 5-minute sliding window
AUTH_FAILURE_THRESHOLD = 10       # alert after this many failures per IP

_auth_failures: Dict[str, List[float]] = defaultdict(list)

# WebSocket invalid message counter (for monitoring)
_ws_invalid_message_count: int = 0


def _record_auth_failure(client_ip: str) -> None:
    """Record a failed auth attempt and warn if threshold exceeded."""
    now = time.monotonic()
    failures = _auth_failures[client_ip]
    _auth_failures[client_ip] = [
        t for t in failures if now - t < AUTH_FAILURE_WINDOW_SECONDS
    ]
    _auth_failures[client_ip].append(now)

    count = len(_auth_failures[client_ip])
    if count >= AUTH_FAILURE_THRESHOLD:
        logger.warning(
            f"AUTH ALERT: {count} failed API key attempts from {client_ip} "
            f"in the last {AUTH_FAILURE_WINDOW_SECONDS}s — possible brute-force"
        )


# ---------------------------------------------------------------------------
# Rate Limiter — sliding window, per-IP, in-memory (no external deps)
# ---------------------------------------------------------------------------
RATE_LIMIT_MAX_REQUESTS = 30   # max POST requests …
RATE_LIMIT_WINDOW_SECS = 60    # … per this many seconds


class _SlidingWindowRateLimiter:
    """Dict-based sliding window rate limiter.

    Stores a list of timestamps per IP. On each call, expired entries are
    pruned and the request is allowed only if the window is not full.
    A periodic sweep removes stale IPs so memory stays bounded.
    """

    def __init__(self, max_requests: int = RATE_LIMIT_MAX_REQUESTS,
                 window_secs: int = RATE_LIMIT_WINDOW_SECS):
        self.max_requests = max_requests
        self.window_secs = window_secs
        self._hits: Dict[str, List[float]] = defaultdict(list)
        self._last_sweep: float = time.monotonic()
        self._sweep_interval: float = 300.0  # purge stale IPs every 5 min

    def is_allowed(self, ip: str) -> bool:
        now = time.monotonic()
        self._maybe_sweep(now)
        window_start = now - self.window_secs
        timestamps = self._hits[ip]
        self._hits[ip] = timestamps = [t for t in timestamps if t > window_start]
        if len(timestamps) >= self.max_requests:
            return False
        timestamps.append(now)
        return True

    def _maybe_sweep(self, now: float) -> None:
        """Remove IPs that have no recent activity to prevent unbounded growth."""
        if now - self._last_sweep < self._sweep_interval:
            return
        self._last_sweep = now
        cutoff = now - self.window_secs
        stale = [ip for ip, ts in self._hits.items() if not ts or ts[-1] <= cutoff]
        for ip in stale:
            del self._hits[ip]


_rate_limiter = _SlidingWindowRateLimiter()


async def verify_api_key(request: Request, x_api_key: str = Header(default="")):
    """Require API key + enforce rate limit for mutation (POST) endpoints. Fail closed if no key configured."""
    if not API_KEY:
        raise HTTPException(
            status_code=503,
            detail="API key not configured. Set SOVEREIGNFORGE_API_KEY environment variable.",
        )
    if x_api_key != API_KEY:
        client_ip = request.client.host if request.client else "unknown"
        _record_auth_failure(client_ip)
        raise HTTPException(status_code=401, detail="Invalid API key")
    client_ip = request.client.host if request.client else "unknown"
    if not _rate_limiter.is_allowed(client_ip):
        logger.warning(f"Rate limit exceeded for {client_ip}")
        raise HTTPException(status_code=429, detail="Too Many Requests")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="SovereignForge Dashboard API",
    version="1.0.0",
    description="Local dashboard backend for SovereignForge crypto arbitrage system.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:8420"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

app.add_middleware(SecurityHeadersMiddleware)


# ---------------------------------------------------------------------------
# Request body size limit middleware — prevent abuse on POST endpoints
# ---------------------------------------------------------------------------
MAX_REQUEST_BODY_BYTES = 1 * 1024 * 1024  # 1 MB


class RequestBodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests with bodies exceeding MAX_REQUEST_BODY_BYTES."""

    async def dispatch(self, request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH"):
            content_length = request.headers.get("content-length")
            if content_length is not None:
                if int(content_length) > MAX_REQUEST_BODY_BYTES:
                    logger.warning(
                        f"Rejected oversized request: {int(content_length)} bytes "
                        f"from {request.client.host if request.client else 'unknown'} "
                        f"to {request.url.path}"
                    )
                    return Response(
                        content=json.dumps({
                            "detail": f"Request body too large. "
                                      f"Maximum size is {MAX_REQUEST_BODY_BYTES} bytes."
                        }),
                        status_code=413,
                        media_type="application/json",
                    )
        return await call_next(request)

app.add_middleware(RequestBodySizeLimitMiddleware)


# ---------------------------------------------------------------------------
# Global exception handlers — prevent stack trace leakage to clients
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions. Log full traceback server-side,
    return a generic message to the client so internals are never exposed."""
    logger.error(
        "Unhandled exception on %s %s:\n%s",
        request.method,
        request.url.path,
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Check server logs."},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return a generic 422 instead of echoing back the raw validation
    errors, which may reveal internal schema details."""
    logger.error(
        "Request validation error on %s %s: %s",
        request.method,
        request.url.path,
        exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content={"detail": "Validation error. Check your request parameters."},
    )


# ---------------------------------------------------------------------------
# In-memory model cache (populated on startup)
# ---------------------------------------------------------------------------
_model_cache: List[Dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_model_filename(filename: str) -> Optional[Dict[str, str]]:
    """Extract strategy, coin, quote, exchange from a .pth filename.

    Expected format: {strategy}_{coin}_usdc_{exchange}.pth
    """
    if not filename.endswith(".pth"):
        return None
    stem = filename[:-4]  # strip .pth
    # Match: strategy_coin_usdc_exchange
    m = re.match(r"^([a-z]+)_([a-z]+)_usdc_([a-z]+)$", stem)
    if not m:
        return None
    return {
        "strategy": m.group(1),
        "coin": m.group(2).upper(),
        "pair": f"{m.group(2).upper()}/USDC",
        "exchange": m.group(3),
    }


def _scan_models() -> List[Dict[str, Any]]:
    """Scan the models directory and return metadata for each model."""
    models = []
    if not MODELS_DIR.exists():
        return models

    for pth_file in sorted(MODELS_DIR.glob("*.pth")):
        parsed = _parse_model_filename(pth_file.name)
        if parsed is None:
            continue
        stat = pth_file.stat()
        models.append({
            "filename": pth_file.name,
            "strategy": parsed["strategy"],
            "coin": parsed["coin"],
            "pair": parsed["pair"],
            "exchange": parsed["exchange"],
            "file_size_kb": round(stat.st_size / 1024, 1),
            "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return models


def _enrich_models_with_knowledge_graph(models: List[Dict]) -> List[Dict]:
    """Attach val_loss / epochs from the knowledge graph where possible."""
    kg = _load_knowledge_graph_raw()
    if kg is None:
        return models

    # Build a lookup: (strategy, pair, exchange) -> best (lowest val_loss) run
    best: Dict[tuple, Dict] = {}
    for node in kg.get("nodes", []):
        if node.get("type") != "training_run":
            continue
        key = (node.get("strategy"), node.get("pair"), node.get("exchange"))
        vl = node.get("val_loss")
        if vl is None:
            continue
        if key not in best or vl < best[key].get("val_loss", float("inf")):
            best[key] = node

    for m in models:
        key = (m["strategy"], m["pair"], m["exchange"])
        run = best.get(key)
        if run:
            m["val_loss"] = round(run.get("val_loss", 0), 6)
            m["epochs"] = run.get("epochs")
            m["trained_at"] = run.get("timestamp")
    return models


def _sanitize_floats(obj: Any) -> Any:
    """Replace NaN/Infinity with None so JSON serialisation succeeds."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_floats(v) for v in obj]
    return obj

def _load_json(path: Path) -> Optional[Any]:
    """Load a JSON file, returning None on any failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return _sanitize_floats(json.load(f))
    except Exception:
        return None


async def _load_json_async(path):
    """Non-blocking JSON file read for async handlers."""
    return await asyncio.to_thread(_load_json, path)


def _load_knowledge_graph_raw() -> Optional[Dict]:
    return _load_json(KNOWLEDGE_GRAPH_PATH)


def _sanitize_config(cfg: Any) -> Any:
    """Recursively strip secret keys from config."""
    if isinstance(cfg, dict):
        return {
            k: ("***" if k in CONFIG_SECRET_KEYS else _sanitize_config(v))
            for k, v in cfg.items()
        }
    if isinstance(cfg, list):
        return [_sanitize_config(item) for item in cfg]
    return cfg


def _parse_training_log() -> Dict[str, Any]:
    """Parse gpu_training.log to extract training progress info."""
    result: Dict[str, Any] = {
        "completed": [],
        "in_progress": None,
        "skipped": [],
        "total_finished": 0,
        "current_strategy": None,
        "log_file": str(TRAINING_LOG_PATH),
        "last_updated": None,
    }
    if not TRAINING_LOG_PATH.exists():
        return result

    try:
        stat = TRAINING_LOG_PATH.stat()
        result["last_updated"] = datetime.fromtimestamp(stat.st_mtime).isoformat()
    except Exception:
        pass

    finished_re = re.compile(
        r"Finished (\w+) for (\S+)@(\w+): val_loss=([\d.]+)"
    )
    early_stop_re = re.compile(
        r"Early stopping at epoch (\d+) for (\S+) on (\w+)"
    )
    skipped_re = re.compile(
        r"Only (\d+) days for (\S+)@(\w+), below minimum"
    )
    strategy_header_re = re.compile(
        r"Training (\w+) strategy", re.IGNORECASE
    )
    epoch_re = re.compile(
        r"(\S+)@(\w+) epoch (\d+)/(\d+):.*val_loss=([\d.]+)"
    )
    wave_re = re.compile(r"STARTING SOVEREIGNFORGE GPU TRAINING - WAVE (\d+)")

    current_strategy = None
    latest_epoch_info = None
    wave = None

    try:
        with open(TRAINING_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                wm = wave_re.search(line)
                if wm:
                    wave = int(wm.group(1))

                sm = strategy_header_re.search(line)
                if sm:
                    current_strategy = sm.group(1).lower()

                fm = finished_re.search(line)
                if fm:
                    result["completed"].append({
                        "strategy": fm.group(1),
                        "pair": fm.group(2),
                        "exchange": fm.group(3),
                        "val_loss": float(fm.group(4)),
                    })
                    latest_epoch_info = None

                skm = skipped_re.search(line)
                if skm:
                    result["skipped"].append({
                        "pair": skm.group(2),
                        "exchange": skm.group(3),
                        "days_available": int(skm.group(1)),
                    })

                em = epoch_re.search(line)
                if em:
                    latest_epoch_info = {
                        "pair": em.group(1),
                        "exchange": em.group(2),
                        "epoch": int(em.group(3)),
                        "total_epochs": int(em.group(4)),
                        "val_loss": float(em.group(5)),
                        "strategy": current_strategy,
                    }
    except Exception as e:
        logger.warning(f"Error parsing training log: {e}")

    result["total_finished"] = len(result["completed"])
    result["current_strategy"] = current_strategy
    result["wave"] = wave

    # If the latest epoch entry was NOT followed by a "Finished" line, it is
    # still in progress.
    if latest_epoch_info:
        last_completed_key = None
        if result["completed"]:
            lc = result["completed"][-1]
            last_completed_key = (lc["pair"], lc["exchange"])
        epoch_key = (latest_epoch_info["pair"], latest_epoch_info["exchange"])
        if epoch_key != last_completed_key:
            result["in_progress"] = latest_epoch_info

    return result


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_scan():
    global _model_cache
    logger.info("Scanning models directory ...")
    _model_cache = _scan_models()
    _model_cache = _enrich_models_with_knowledge_graph(_model_cache)
    logger.info(f"Found {len(_model_cache)} models across {MODELS_DIR}")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    """System health: model count, config present, exchanges configured."""
    config = await _load_json_async(CONFIG_PATH)
    exchanges_configured = []
    if config:
        exchanges_configured = (
            config.get("cross_exchange", {}).get("exchanges", [])
        )
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "models_loaded": len(_model_cache),
        "models_dir_exists": MODELS_DIR.exists(),
        "config_loaded": config is not None,
        "exchanges_configured": exchanges_configured,
        "training_log_exists": TRAINING_LOG_PATH.exists(),
        "knowledge_graph_exists": KNOWLEDGE_GRAPH_PATH.exists(),
        "paper_trading_state_exists": PAPER_TRADING_STATE_PATH.exists(),
    }


@app.get("/api/models")
async def list_models():
    """List all trained models with metadata."""
    return {"models": _model_cache, "count": len(_model_cache)}


@app.get("/api/models/{strategy}")
async def list_models_by_strategy(strategy: str):
    """Filter models by strategy name."""
    strategy = strategy.lower()
    if strategy not in STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown strategy '{strategy}'. Valid: {STRATEGIES}",
        )
    filtered = [m for m in _model_cache if m["strategy"] == strategy]
    return {"strategy": strategy, "models": filtered, "count": len(filtered)}


@app.get("/api/training/status")
async def training_status():
    """Current training progress parsed from gpu_training.log."""
    if not TRAINING_LOG_PATH.exists():
        raise HTTPException(status_code=404, detail="Training log not found")
    return _parse_training_log()


@app.get("/api/training/history")
async def training_history():
    """Training run history from the knowledge graph."""
    kg = _load_knowledge_graph_raw()
    if kg is None:
        raise HTTPException(
            status_code=404, detail="Knowledge graph not found"
        )
    runs = [
        n for n in kg.get("nodes", []) if n.get("type") == "training_run"
    ]
    # Sort by timestamp descending
    runs.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return {"runs": runs, "count": len(runs)}


@app.get("/api/portfolio")
async def portfolio():
    """Paper trading portfolio state."""
    data = await _load_json_async(PAPER_TRADING_STATE_PATH)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail="Paper trading state not found at reports/paper_trading_state.json",
        )
    return data


@app.get("/api/trades")
async def trades():
    """Trade history from paper trading state."""
    data = await _load_json_async(PAPER_TRADING_STATE_PATH)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail="Paper trading state not found",
        )
    trade_list = data.get("trades", data.get("trade_history", []))
    return {"trades": trade_list, "count": len(trade_list)}


@app.get("/api/signals")
async def signals():
    """Latest signals from paper trading state."""
    data = await _load_json_async(PAPER_TRADING_STATE_PATH)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail="Paper trading state not found",
        )
    signal_list = data.get("signals", data.get("latest_signals", []))
    return {"signals": signal_list, "count": len(signal_list)}


@app.get("/api/signals/missed")
async def missed_signals():
    """Signals that were generated but not executed (skipped)."""
    data = await _load_json_async(PAPER_TRADING_STATE_PATH)
    if data is None:
        return {"missed": [], "count": 0}
    missed = data.get("skipped_signals", [])
    return {"missed": missed, "count": len(missed)}


# ---------------------------------------------------------------------------
# Paper trading control
# ---------------------------------------------------------------------------
PAPER_TRADING_PID_FILE = PROJECT_ROOT / ".paper_trading.pid"


def _pt_pid_alive() -> Optional[int]:
    """Return PID if paper trading is alive, else None."""
    if not PAPER_TRADING_PID_FILE.exists():
        return None
    try:
        pid = int(PAPER_TRADING_PID_FILE.read_text().strip())
        if platform.system() == "Windows":
            r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                               capture_output=True, text=True, timeout=5)
            if str(pid) in r.stdout:
                return pid
        else:
            os.kill(pid, 0)
            return pid
    except Exception:
        pass
    PAPER_TRADING_PID_FILE.unlink(missing_ok=True)
    return None


@app.get("/api/paper-trading/status")
async def paper_trading_status():
    pid = _pt_pid_alive()
    return {"running": pid is not None, "pid": pid}


@app.post("/api/paper-trading/start")
async def paper_trading_start(_auth=Depends(verify_api_key)):
    if _pt_pid_alive():
        return {"status": "already_running", "pid": _pt_pid_alive()}

    script = PROJECT_ROOT / "src" / "paper_trading.py"
    log_path = LOGS_DIR / "paper_trading.log"
    LOGS_DIR.mkdir(exist_ok=True)

    with open(log_path, "a") as log_f:
        log_f.write(f"\n{'='*60}\n[{datetime.now().isoformat()}] Started via dashboard API\n{'='*60}\n")
        proc = subprocess.Popen(
            [sys.executable, str(script), "--start"],
            cwd=str(PROJECT_ROOT),
            stdout=log_f,
            stderr=subprocess.STDOUT,
            env={**os.environ, "PAPER_TRADING_MODE": "true"},
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if platform.system() == "Windows" else 0,
        )
    PAPER_TRADING_PID_FILE.write_text(str(proc.pid))
    logger.info(f"Paper trading started (PID {proc.pid})")
    return {"status": "started", "pid": proc.pid}


@app.post("/api/paper-trading/stop")
async def paper_trading_stop(_auth=Depends(verify_api_key)):
    pid = _pt_pid_alive()
    if not pid:
        return {"status": "not_running"}
    try:
        if platform.system() == "Windows":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, timeout=10)
        else:
            os.kill(pid, 15)  # SIGTERM
        PAPER_TRADING_PID_FILE.unlink(missing_ok=True)
        logger.info(f"Paper trading stopped (PID {pid})")
        return {"status": "stopped", "pid": pid}
    except Exception as e:
        logger.error(f"Failed to stop: {e}")
        return {"status": "error", "detail": "Operation failed. Check server logs."}


@app.get("/api/config")
async def config():
    """Current trading config (secrets redacted)."""
    raw = await _load_json_async(CONFIG_PATH)
    if raw is None:
        raise HTTPException(status_code=404, detail="Config file not found")
    return _sanitize_config(raw)


class TogglePairRequest(BaseModel):
    pair: str
    enabled: bool

class ToggleStrategyRequest(BaseModel):
    strategy: str
    enabled: bool

class ToggleExchangeRequest(BaseModel):
    exchange: str
    enabled: bool


def _save_config(cfg: Dict) -> None:
    """Write config back to disk."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


@app.post("/api/config/toggle-pair")
async def toggle_pair(req: TogglePairRequest, _auth=Depends(verify_api_key)):
    """Enable or disable a trading pair."""
    raw = await _load_json_async(CONFIG_PATH)
    if raw is None:
        raise HTTPException(status_code=404, detail="Config file not found")

    all_pairs = [
        "BTC/USDC", "ETH/USDC", "XRP/USDC", "XLM/USDC", "HBAR/USDC",
        "ALGO/USDC", "ADA/USDC", "LINK/USDC", "IOTA/USDC", "VET/USDC",
        "XDC/USDC", "ONDO/USDC",
    ]
    if req.pair not in all_pairs:
        raise HTTPException(status_code=400, detail=f"Unknown pair: {req.pair}")

    trading = raw.setdefault("trading", {})
    enabled = trading.get("enabled_pairs", list(all_pairs))

    if req.enabled and req.pair not in enabled:
        enabled.append(req.pair)
    elif not req.enabled and req.pair in enabled:
        enabled.remove(req.pair)

    trading["enabled_pairs"] = enabled
    _save_config(raw)
    logger.info(f"Pair {req.pair} {'enabled' if req.enabled else 'disabled'}")
    return {"status": "ok", "enabled_pairs": enabled}


@app.post("/api/config/toggle-strategy")
async def toggle_strategy(req: ToggleStrategyRequest, _auth=Depends(verify_api_key)):
    """Enable or disable a strategy."""
    raw = await _load_json_async(CONFIG_PATH)
    if raw is None:
        raise HTTPException(status_code=404, detail="Config file not found")

    strategies = raw.setdefault("strategies", {})
    if req.strategy not in strategies:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {req.strategy}")

    strategies[req.strategy]["enabled"] = req.enabled
    _save_config(raw)
    logger.info(f"Strategy {req.strategy} {'enabled' if req.enabled else 'disabled'}")
    return {"status": "ok", "strategies": {k: v.get("enabled", True) for k, v in strategies.items()}}


@app.post("/api/config/toggle-exchange")
async def toggle_exchange(req: ToggleExchangeRequest, _auth=Depends(verify_api_key)):
    """Enable or disable an exchange."""
    raw = await _load_json_async(CONFIG_PATH)
    if raw is None:
        raise HTTPException(status_code=404, detail="Config file not found")

    cross = raw.setdefault("cross_exchange", {})
    enabled = cross.get("exchanges", [])

    all_exchanges = ["binance", "coinbase", "kraken", "okx"]
    if req.exchange not in all_exchanges:
        raise HTTPException(status_code=400, detail=f"Unknown exchange: {req.exchange}")

    if req.enabled and req.exchange not in enabled:
        enabled.append(req.exchange)
    elif not req.enabled and req.exchange in enabled:
        enabled.remove(req.exchange)

    cross["exchanges"] = enabled
    _save_config(raw)
    logger.info(f"Exchange {req.exchange} {'enabled' if req.enabled else 'disabled'}")
    return {"status": "ok", "exchanges": enabled}


@app.get("/api/metrics")
async def metrics():
    """Aggregate metrics across models and portfolio."""
    # --- Model metrics ---
    by_strategy: Dict[str, List[float]] = {}
    best_model = None
    worst_model = None

    for m in _model_cache:
        vl = m.get("val_loss")
        if vl is None:
            continue
        by_strategy.setdefault(m["strategy"], []).append(vl)
        if best_model is None or vl < best_model["val_loss"]:
            best_model = m
        if worst_model is None or vl > worst_model["val_loss"]:
            worst_model = m

    avg_val_loss_per_strategy = {
        s: round(sum(losses) / len(losses), 6) if losses else None
        for s, losses in by_strategy.items()
    }

    # --- Portfolio P&L ---
    portfolio_pnl = None
    pt_data = _load_json(PAPER_TRADING_STATE_PATH)
    if pt_data:
        portfolio_pnl = pt_data.get("pnl", pt_data.get("total_pnl"))

    # --- Training progress ---
    training = _parse_training_log()

    return {
        "total_models": len(_model_cache),
        "models_with_val_loss": sum(
            1 for m in _model_cache if m.get("val_loss") is not None
        ),
        "avg_val_loss_per_strategy": avg_val_loss_per_strategy,
        "best_model": (
            {
                "filename": best_model["filename"],
                "strategy": best_model["strategy"],
                "pair": best_model["pair"],
                "exchange": best_model["exchange"],
                "val_loss": best_model["val_loss"],
            }
            if best_model
            else None
        ),
        "worst_model": (
            {
                "filename": worst_model["filename"],
                "strategy": worst_model["strategy"],
                "pair": worst_model["pair"],
                "exchange": worst_model["exchange"],
                "val_loss": worst_model["val_loss"],
            }
            if worst_model
            else None
        ),
        "training_completed": training["total_finished"],
        "training_in_progress": training["in_progress"] is not None,
        "portfolio_pnl": portfolio_pnl,
    }


# ---------------------------------------------------------------------------
# WebSocket broadcast
# ---------------------------------------------------------------------------
MAX_WS_CONNECTIONS = 10


class ConnectionManager:
    """Manage WebSocket connections for real-time dashboard updates."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        if len(self.active_connections) >= MAX_WS_CONNECTIONS:
            await websocket.close(code=1008, reason="Too many connections")
            return
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected ({len(self.active_connections)} total)")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected ({len(self.active_connections)} total)")

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            if conn in self.active_connections:
                self.active_connections.remove(conn)


ws_manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(default="")):
    """WebSocket endpoint for real-time dashboard updates. Requires token auth."""
    if not API_KEY:
        await websocket.close(code=1008, reason="API key not configured on server")
        return
    if token != API_KEY:
        await websocket.close(code=1008, reason="Invalid or missing token")
        return
    await ws_manager.connect(websocket)
    try:
        await websocket.send_json({
            "type": "pipeline_status",
            "payload": {
                "connected": True,
                "models_loaded": len(_model_cache),
                "paper_trading_running": _pt_pid_alive() is not None,
            }
        })
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "payload": {"timestamp": datetime.utcnow().isoformat()}
                    })
            except json.JSONDecodeError:
                global _ws_invalid_message_count
                _ws_invalid_message_count += 1
                logger.debug(
                    f"Invalid WebSocket JSON message (total invalid: "
                    f"{_ws_invalid_message_count}): {data[:200]!r}"
                )
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


_pipeline_broadcast_task = None


async def _broadcast_pipeline_status():
    """Periodically broadcast pipeline status to all WebSocket clients."""
    while True:
        try:
            await asyncio.sleep(5)
            if not ws_manager.active_connections:
                continue

            pt_data = await _load_json_async(PAPER_TRADING_STATE_PATH)
            pipeline_state = await _load_json_async(PROJECT_ROOT / "reports" / "pipeline_state.json")

            payload: Dict[str, Any] = {
                "paper_trading_running": _pt_pid_alive() is not None,
                "models_loaded": len(_model_cache),
                "timestamp": datetime.utcnow().isoformat(),
            }

            if pt_data:
                payload["portfolio_value"] = pt_data.get("total_value", pt_data.get("portfolio_value"))
                payload["daily_pnl"] = pt_data.get("daily_pnl", pt_data.get("pnl"))
                payload["total_trades"] = len(pt_data.get("trades", pt_data.get("trade_history", [])))

            if pipeline_state:
                payload["pipeline_running"] = pipeline_state.get("is_running", False)
                payload["opportunities_detected"] = pipeline_state.get("opportunities_detected", 0)
                payload["connected_exchanges"] = pipeline_state.get("connected_exchanges", [])

            await ws_manager.broadcast({"type": "pipeline_status", "payload": payload})
        except Exception as e:
            logger.debug(f"Pipeline status broadcast error: {e}")


@app.on_event("startup")
async def start_ws_broadcast():
    global _pipeline_broadcast_task
    _pipeline_broadcast_task = asyncio.create_task(_broadcast_pipeline_status())


SHUTDOWN_GRACE_PERIOD_SECONDS = 5


@app.on_event("shutdown")
async def graceful_shutdown():
    """Clean up resources and give in-flight requests time to complete."""
    logger.info("Shutdown initiated — draining connections …")

    # 1. Cancel the background broadcast task
    global _pipeline_broadcast_task
    if _pipeline_broadcast_task is not None:
        _pipeline_broadcast_task.cancel()
        try:
            await _pipeline_broadcast_task
        except asyncio.CancelledError:
            pass
        _pipeline_broadcast_task = None
        logger.info("Pipeline broadcast task cancelled")

    # 2. Close all active WebSocket connections gracefully
    for ws in list(ws_manager.active_connections):
        try:
            await asyncio.wait_for(
                ws.close(code=1001, reason="Server shutting down"),
                timeout=2.0,
            )
        except Exception:
            pass
    ws_manager.active_connections.clear()
    logger.info("All WebSocket connections closed")

    # 3. Brief grace period so Uvicorn can finish in-flight HTTP responses
    await asyncio.sleep(SHUTDOWN_GRACE_PERIOD_SECONDS)
    logger.info("Shutdown complete")


# ---------------------------------------------------------------------------
# Pipeline control
# ---------------------------------------------------------------------------
PIPELINE_PID_FILE = PROJECT_ROOT / ".pipeline.pid"


def _pipeline_pid_alive() -> Optional[int]:
    """Return PID if pipeline is alive, else None."""
    if not PIPELINE_PID_FILE.exists():
        return None
    try:
        pid = int(PIPELINE_PID_FILE.read_text().strip())
        if platform.system() == "Windows":
            r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                               capture_output=True, text=True, timeout=5)
            if str(pid) in r.stdout:
                return pid
        else:
            os.kill(pid, 0)
            return pid
    except Exception:
        pass
    PIPELINE_PID_FILE.unlink(missing_ok=True)
    return None


@app.get("/api/pipeline/status")
async def pipeline_status():
    """Get pipeline status."""
    pid = _pipeline_pid_alive()
    state = await _load_json_async(PROJECT_ROOT / "reports" / "pipeline_state.json")
    return {"running": pid is not None, "pid": pid, "state": state}


@app.post("/api/pipeline/start")
async def pipeline_start(_auth=Depends(verify_api_key)):
    """Start the live arbitrage pipeline."""
    if _pipeline_pid_alive():
        return {"status": "already_running", "pid": _pipeline_pid_alive()}

    script = PROJECT_ROOT / "src" / "main.py"
    log_path = LOGS_DIR / "pipeline.log"
    LOGS_DIR.mkdir(exist_ok=True)

    with open(log_path, "a") as log_f:
        log_f.write(f"\n{'='*60}\n[{datetime.now().isoformat()}] Pipeline started via dashboard API\n{'='*60}\n")
        proc = subprocess.Popen(
            [sys.executable, str(script), "production", "--dry-run"],
            cwd=str(PROJECT_ROOT),
            stdout=log_f,
            stderr=subprocess.STDOUT,
            env={**os.environ, "PAPER_TRADING_MODE": "true"},
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if platform.system() == "Windows" else 0,
        )
    PIPELINE_PID_FILE.write_text(str(proc.pid))
    logger.info(f"Pipeline started (PID {proc.pid})")
    return {"status": "started", "pid": proc.pid}


@app.post("/api/pipeline/stop")
async def pipeline_stop(_auth=Depends(verify_api_key)):
    """Stop the live arbitrage pipeline."""
    pid = _pipeline_pid_alive()
    if not pid:
        return {"status": "not_running"}
    try:
        if platform.system() == "Windows":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, timeout=10)
        else:
            os.kill(pid, 15)
        PIPELINE_PID_FILE.unlink(missing_ok=True)
        logger.info(f"Pipeline stopped (PID {pid})")
        return {"status": "stopped", "pid": pid}
    except Exception as e:
        logger.error(f"Failed to stop: {e}")
        return {"status": "error", "detail": "Operation failed. Check server logs."}


CIRCUIT_BREAKER_RESET_SIGNAL = PROJECT_ROOT / ".circuit_breaker_reset"


@app.post("/api/circuit-breaker/reset")
async def reset_circuit_breaker(_auth=Depends(verify_api_key)):
    """
    Reset circuit breaker state.

    Writes a signal file that the pipeline picks up on its next cycle to
    clear both circuit_breaker_active and emergency_stop_active flags in the
    DynamicRiskAdjustment instance.  Also patches pipeline_state.json
    immediately so the dashboard reflects the change without waiting for
    the next pipeline persist cycle.
    """
    try:
        # 1. Write signal file for the running pipeline process
        CIRCUIT_BREAKER_RESET_SIGNAL.write_text(datetime.now().isoformat())
        logger.info("Circuit breaker reset signal written")

        # 2. Patch pipeline_state.json for immediate dashboard feedback
        state_path = PROJECT_ROOT / "reports" / "pipeline_state.json"
        state = await _load_json_async(state_path)
        if state is None:
            state = {}

        if 'dynamic_risk' not in state:
            state['dynamic_risk'] = {}

        state['dynamic_risk']['circuit_breaker_active'] = False
        state['dynamic_risk']['emergency_stop_active'] = False
        state['dynamic_risk']['last_reset'] = datetime.now().isoformat()
        state['dynamic_risk']['reset_by'] = 'dashboard_api'

        state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = state_path.with_suffix('.tmp')
        await asyncio.to_thread(tmp.write_text, json.dumps(state, indent=2, default=str))
        await asyncio.to_thread(tmp.replace, state_path)

        # 3. Broadcast reset event via WebSocket
        await ws_manager.broadcast({
            "type": "circuit_breaker_reset",
            "payload": {"timestamp": datetime.now().isoformat()},
        })

        return {
            "status": "reset",
            "message": "Circuit breaker reset signal sent. Pipeline will clear state on next cycle.",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Circuit breaker reset failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset circuit breaker. Check server logs.")


@app.get("/api/pipeline/opportunities")
async def pipeline_opportunities():
    """Get recent detected opportunities."""
    state = await _load_json_async(PROJECT_ROOT / "reports" / "pipeline_state.json")
    if state is None:
        return {"opportunities": [], "count": 0}
    opps = state.get("recent_opportunities", [])
    return {"opportunities": opps, "count": len(opps)}


@app.get("/api/pipeline/cointegration")
async def get_cointegration_status():
    """Get cointegration pair detection status."""
    try:
        state = await _load_json_async(PROJECT_ROOT / "reports" / "pipeline_state.json")
        if state and 'cointegration' in state:
            return state['cointegration']
        return {'cached_pairs': 0, 'pairs': [], 'statsmodels_available': False}
    except Exception:
        return {'cached_pairs': 0, 'pairs': []}


# ---------------------------------------------------------------------------
# Exchange & Capital Status Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/exchanges/status")
async def get_exchange_status():
    """Get connection status for all configured exchanges."""
    try:
        config = await _load_json_async(CONFIG_PATH)
        exchanges = config.get('cross_exchange', {}).get('exchanges', [])

        # Exchange fees from the pipeline or hardcoded
        fees = {
            'binance': 0.001, 'coinbase': 0.004, 'kraken': 0.0026,
            'kucoin': 0.001, 'okx': 0.001, 'bybit': 0.001, 'gate': 0.002,
        }

        # Pair counts per exchange
        pairs = config.get('trading', {}).get('enabled_pairs', [])

        statuses = []
        for ex in exchanges:
            statuses.append({
                'name': ex,
                'connected': True,  # Would need WebSocket status for real value
                'fee_pct': fees.get(ex, 0.001) * 100,
                'pairs': len(pairs),
            })

        return {'exchanges': statuses, 'total': len(exchanges)}
    except Exception as e:
        logger.error(f"Failed to get exchange status: {e}")
        return {'exchanges': [], 'error': 'Failed to retrieve exchange status'}


@app.get("/api/capital/status")
async def get_capital_status():
    """Get capital allocation and tier information."""
    try:
        config = await _load_json_async(CONFIG_PATH)
        cap = config.get('capital_allocation', {})
        strategies = config.get('strategies', {})

        initial = cap.get('initial_capital', 300)
        target = cap.get('target_capital', 5000)

        # Read current portfolio value if available
        portfolio_data = await _load_json_async(PAPER_TRADING_STATE_PATH)
        current = portfolio_data.get('balance', initial) if portfolio_data else initial

        # Determine tier
        if current <= 500: tier = 'micro'
        elif current <= 2000: tier = 'small'
        elif current <= 5000: tier = 'medium'
        else: tier = 'standard'

        # Strategy allocations
        allocations = {}
        for name, scfg in strategies.items():
            if isinstance(scfg, dict):
                weight = scfg.get('weight', 0)
                allocations[name] = {
                    'weight': weight,
                    'amount': round(current * weight, 2),
                    'enabled': scfg.get('enabled', True),
                }

        return {
            'current_capital': current,
            'initial_capital': initial,
            'target_capital': target,
            'growth_pct': round((current - initial) / initial * 100, 2) if initial > 0 else 0,
            'tier': tier,
            'allocations': allocations,
        }
    except Exception as e:
        logger.error(f"Failed to get capital status: {e}")
        return {'error': 'Failed to retrieve capital status'}


# ---------------------------------------------------------------------------
# Agent System Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/agents/reports")
async def get_agent_reports():
    """List all available audit reports."""
    try:
        reports_dir = Path(__file__).parent.parent / "reports" / "audits"
        if not reports_dir.exists():
            return {"reports": []}

        reports = []
        for json_file in sorted(reports_dir.glob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                reports.append({
                    "name": data.get("agent_name", json_file.stem),
                    "type": data.get("agent_type", "audit"),
                    "health_score": data.get("health_score", 0),
                    "findings_count": len(data.get("findings", [])),
                    "timestamp": data.get("timestamp", ""),
                    "file": json_file.name,
                })
            except Exception:
                continue
        return {"reports": reports}
    except Exception as e:
        logger.error(f"Error listing reports: {e}")
        return {"reports": []}


@app.get("/api/agents/reports/{agent_name}")
async def get_agent_report(agent_name: str):
    """Get a specific agent's full report."""
    try:
        reports_dir = Path(__file__).parent.parent / "reports" / "audits"
        # Try exact match and normalized name
        for name in [agent_name, agent_name.lower().replace(" ", "_")]:
            json_file = reports_dir / f"{name}.json"
            if json_file.exists():
                return json.loads(json_file.read_text(encoding="utf-8"))
        return {"error": "Report not found", "available": [f.stem for f in reports_dir.glob("*.json")]}
    except Exception as e:
        logger.error(f"Failed to get agent report '{agent_name}': {e}")
        return {"error": "Failed to retrieve agent report"}


@app.get("/api/agents/synthesis")
async def get_synthesis_report():
    """Get the consolidated synthesis report."""
    try:
        synthesis_path = Path(__file__).parent.parent / "reports" / "audits" / "synthesis.json"
        if synthesis_path.exists():
            return json.loads(synthesis_path.read_text(encoding="utf-8"))
        return {"error": "No synthesis report found. Run: python src/agents/runner.py synthesize"}
    except Exception as e:
        logger.error(f"Failed to get synthesis report: {e}")
        return {"error": "Failed to retrieve synthesis report"}


@app.get("/api/agents/health")
async def get_system_health():
    """Get overall system health score from latest synthesis."""
    try:
        synthesis_path = Path(__file__).parent.parent / "reports" / "audits" / "synthesis.json"
        if synthesis_path.exists():
            data = json.loads(synthesis_path.read_text(encoding="utf-8"))
            findings = data.get("findings", [])
            return {
                "health_score": data.get("health_score", 0),
                "critical": sum(1 for f in findings if f.get("severity") == "critical"),
                "high": sum(1 for f in findings if f.get("severity") == "high"),
                "medium": sum(1 for f in findings if f.get("severity") == "medium"),
                "total_findings": len(findings),
                "timestamp": data.get("timestamp", ""),
            }
        return {"health_score": None, "error": "No audit data available"}
    except Exception as e:
        logger.error(f"Failed to get system health: {e}")
        return {"health_score": None, "error": "Failed to retrieve system health"}


@app.get("/api/agents/research")
async def run_research_agents():
    """Run all research agents and return results."""
    results = {}
    try:
        from agents.research_sentiment import MarketSentimentAgent
        results['sentiment'] = MarketSentimentAgent().analyze()
    except Exception as e:
        logger.error(f"Sentiment agent failed: {e}")
        results['sentiment'] = {"error": "Sentiment analysis unavailable"}

    try:
        from agents.research_performance import StrategyPerformanceAgent
        results['performance'] = StrategyPerformanceAgent().analyze()
    except Exception as e:
        logger.error(f"Performance agent failed: {e}")
        results['performance'] = {"error": "Performance analysis unavailable"}

    # Technical analysis is slower (fetches from exchange) — include summary only
    try:
        from agents.research_technical import TechnicalAnalysisAgent
        ta = TechnicalAnalysisAgent().analyze()
        results['technical'] = {
            'pairs_analyzed': ta.get('pairs_analyzed', 0),
            'cross_pair_signals': ta.get('cross_pair_signals', []),
            'execution_time': ta.get('execution_time', 0),
        }
    except Exception as e:
        logger.error(f"Technical analysis agent failed: {e}")
        results['technical'] = {"error": "Technical analysis unavailable"}

    return results


# ---------------------------------------------------------------------------
# Telegram Alerts
# ---------------------------------------------------------------------------

@app.post("/api/alerts/test")
async def send_test_alert_endpoint(_auth=Depends(verify_api_key)):
    """Send a test Telegram alert."""
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "src"))
        from telegram_alerts import send_test_alert
        result = await send_test_alert()
        return result
    except ImportError as e:
        return {"success": False, "error": f"telegram_alerts module not available: {e}"}
    except Exception as e:
        logger.error(f"Test alert failed: {e}")
        return {"success": False, "error": "Failed to send test alert. Check server logs."}


@app.get("/api/alerts/status")
async def alerts_status():
    """Get Telegram alert system status."""
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "src"))
        from telegram_alerts import get_telegram_alert_system
        system = get_telegram_alert_system()
        return system.get_status()
    except ImportError:
        return {"enabled": False, "error": "telegram_alerts module not available"}


# ---------------------------------------------------------------------------
# Static file serving (dashboard SPA)
# ---------------------------------------------------------------------------
if DASHBOARD_DIST.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(DASHBOARD_DIST), html=True), name="dashboard")
    logger.info(f"Serving dashboard from {DASHBOARD_DIST}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("SOVEREIGNFORGE_DASHBOARD_PORT", "8420"))
    logger.info(f"Starting SovereignForge Dashboard API on port {port}")
    uvicorn.run(
        "dashboard_api:app",
        host="127.0.0.1",
        port=port,
        reload=False,
        log_level="info",
        ws_max_size=1 * 1024 * 1024,  # 1 MB — prevent WebSocket memory exhaustion
    )
