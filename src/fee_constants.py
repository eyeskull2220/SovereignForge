"""
SovereignForge — Single Source of Truth for Exchange Fees

All fee constants in one place. Import from here, not hardcode.
"""

# Exchange trading fees (taker fees for market orders)
EXCHANGE_FEES = {
    "binance":  {"maker": 0.001,  "taker": 0.001},
    "coinbase": {"maker": 0.004,  "taker": 0.004},
    "kraken":   {"maker": 0.0016, "taker": 0.0026},
    "kucoin":   {"maker": 0.001,  "taker": 0.001},
    "okx":      {"maker": 0.0008, "taker": 0.001},
    "bybit":    {"maker": 0.001,  "taker": 0.001},
    "gate":     {"maker": 0.002,  "taker": 0.002},
}

# Network transfer fees (USDC) for cross-exchange arbitrage
TRANSFER_FEES = {
    "binance":  1.0,
    "coinbase": 0.0,
    "kraken":   2.5,
    "kucoin":   1.0,
    "okx":      1.0,
    "bybit":    1.0,
    "gate":     1.0,
}

# Slippage range for simulation
SLIPPAGE_RANGE = (0.0005, 0.0015)  # 0.05% - 0.15%
AVG_SLIPPAGE = 0.001


def get_taker_fee(exchange: str) -> float:
    """Get taker fee for an exchange."""
    return EXCHANGE_FEES.get(exchange, {"taker": 0.001})["taker"]


def get_round_trip_cost(exchange: str, include_slippage: bool = True) -> float:
    """Get total round-trip cost (buy + sell fees + slippage)."""
    fee = get_taker_fee(exchange) * 2
    if include_slippage:
        fee += AVG_SLIPPAGE * 2
    return fee
