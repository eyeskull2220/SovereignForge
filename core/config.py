from __future__ import annotations
from pathlib import Path
from typing import FrozenSet, Optional
from pydantic_settings import BaseSettings
from pydantic import model_validator

class SovereignForgeConfig(BaseSettings):
    """SovereignForge v1.0.3 core config. Enforces all project rules: local-only, MiCA whitelist, Docker isolation."""

    ROOT_PATH: Path = Path(r"E:\Users\Gino\Downloads\SovereignForge")
    VERSION: str = "v1.0.3"
    WHITELIST_COINS: FrozenSet[str] = frozenset([
        "XRP", "XLM", "HBAR", "ALGO", "ADA", "Chainlink",
        "IOTA", "XDC", "ONDO", "VeChain", "USDC", "RLUSD"
    ])
    SUPPORTED_EXCHANGES: FrozenSet[str] = frozenset(["binance", "kraken", "coinbase"])  # extend locally only
    DOCKER_ISOLATED: bool = True

    DATA_DIR: Optional[Path] = None
    MODELS_DIR: Optional[Path] = None
    LOGS_DIR: Optional[Path] = None
    MEMORY_DIR: Optional[Path] = None
    OPEN_SANDBOX_DIR: Optional[Path] = None  # for MCP Knowledge Graph Docker isolation

    @model_validator(mode="after")
    def setup_paths(self):
        """Auto-create all required directories under fixed root."""
        self.DATA_DIR = self.ROOT_PATH / "data"
        self.MODELS_DIR = self.ROOT_PATH / "models"
        self.LOGS_DIR = self.ROOT_PATH / "logs"
        self.MEMORY_DIR = self.ROOT_PATH / "memory"
        self.OPEN_SANDBOX_DIR = self.ROOT_PATH / "sandbox"

        for p in (self.DATA_DIR, self.MODELS_DIR, self.LOGS_DIR,
                  self.MEMORY_DIR, self.OPEN_SANDBOX_DIR):
            p.mkdir(parents=True, exist_ok=True)
        return self

    def is_allowed_coin(self, coin: str) -> bool:
        """MiCA compliance gate. Block all non-whitelisted coins."""
        return coin.upper() in self.WHITELIST_COINS

    def get_model_path(self, exchange: str, coin: str) -> Path:
        """Per-exchange per-coin training path."""
        if not self.is_allowed_coin(coin):
            raise ValueError(f"Coin {coin} blocked. MiCA whitelist violation.")
        if exchange not in self.SUPPORTED_EXCHANGES:
            raise ValueError(f"Exchange {exchange} not supported in current build.")
        if self.MODELS_DIR is None:
            raise RuntimeError("MODELS_DIR not initialized")
        return self.MODELS_DIR / exchange / coin

config: SovereignForgeConfig = SovereignForgeConfig()