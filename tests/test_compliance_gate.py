#!/usr/bin/env python3
"""
MiCA Compliance Gate Tests

Verifies that the compliance gate in the arbitrage detection and opportunity
filtering pipeline correctly rejects USDT pairs and accepts USDC pairs.

These tests are critical for MiCA Article 5 enforcement: SovereignForge must
NEVER trade USDT-denominated pairs.  Only USDC and RLUSD are permitted.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure src/ is importable
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from compliance import ComplianceViolationError, MiCAComplianceEngine, get_compliance_engine


# ---------------------------------------------------------------------------
# Direct compliance engine gate tests
# ---------------------------------------------------------------------------

class TestComplianceGateRejectsUSDT:
    """Verify the compliance gate hard-blocks every USDT pair variant."""

    def setup_method(self):
        self.engine = MiCAComplianceEngine(personal_deployment=True)

    def test_btc_usdt_rejected(self):
        """BTC/USDT must be rejected — MiCA forbids USDT stablecoin."""
        assert not self.engine.is_pair_compliant("BTC/USDT")

    def test_eth_usdt_rejected(self):
        """ETH/USDT must be rejected."""
        assert not self.engine.is_pair_compliant("ETH/USDT")

    def test_xrp_usdt_rejected(self):
        """XRP/USDT must be rejected."""
        assert not self.engine.is_pair_compliant("XRP/USDT")

    def test_ada_usdt_rejected(self):
        """ADA/USDT must be rejected."""
        assert not self.engine.is_pair_compliant("ADA/USDT")

    def test_algo_usdt_rejected(self):
        """ALGO/USDT must be rejected."""
        assert not self.engine.is_pair_compliant("ALGO/USDT")

    def test_link_usdt_rejected(self):
        """LINK/USDT must be rejected."""
        assert not self.engine.is_pair_compliant("LINK/USDT")

    def test_hbar_usdt_rejected(self):
        """HBAR/USDT must be rejected."""
        assert not self.engine.is_pair_compliant("HBAR/USDT")

    def test_xlm_usdt_rejected(self):
        """XLM/USDT must be rejected."""
        assert not self.engine.is_pair_compliant("XLM/USDT")


class TestComplianceGateAcceptsUSDC:
    """Verify that all whitelisted USDC pairs pass the compliance gate."""

    def setup_method(self):
        self.engine = MiCAComplianceEngine(personal_deployment=True)

    def test_btc_usdc_accepted(self):
        """BTC/USDC must be accepted (personal deployment)."""
        assert self.engine.is_pair_compliant("BTC/USDC")

    def test_eth_usdc_accepted(self):
        """ETH/USDC must be accepted (personal deployment)."""
        assert self.engine.is_pair_compliant("ETH/USDC")

    def test_xrp_usdc_accepted(self):
        """XRP/USDC must be accepted."""
        assert self.engine.is_pair_compliant("XRP/USDC")

    def test_ada_usdc_accepted(self):
        """ADA/USDC must be accepted."""
        assert self.engine.is_pair_compliant("ADA/USDC")

    def test_algo_usdc_accepted(self):
        """ALGO/USDC must be accepted."""
        assert self.engine.is_pair_compliant("ALGO/USDC")

    def test_link_usdc_accepted(self):
        """LINK/USDC must be accepted."""
        assert self.engine.is_pair_compliant("LINK/USDC")

    def test_hbar_usdc_accepted(self):
        """HBAR/USDC must be accepted."""
        assert self.engine.is_pair_compliant("HBAR/USDC")

    def test_xlm_usdc_accepted(self):
        """XLM/USDC must be accepted."""
        assert self.engine.is_pair_compliant("XLM/USDC")


class TestComplianceGateAcceptsRLUSD:
    """RLUSD is a MiCA-compliant stablecoin and must be accepted."""

    def setup_method(self):
        self.engine = MiCAComplianceEngine(personal_deployment=True)

    def test_xrp_rlusd_accepted(self):
        """XRP/RLUSD must be accepted."""
        assert self.engine.is_pair_compliant("XRP/RLUSD")

    def test_rlusd_in_compliant_stablecoins(self):
        """RLUSD must be listed in compliant_stablecoins."""
        assert "RLUSD" in self.engine.compliant_stablecoins


# ---------------------------------------------------------------------------
# Compliance gate in the validate_opportunity path
# ---------------------------------------------------------------------------

class TestComplianceGateValidateOpportunity:
    """Test that validate_opportunity raises on USDT and passes on USDC."""

    def setup_method(self):
        self.engine = MiCAComplianceEngine(personal_deployment=True)

    def test_usdt_opportunity_raises_violation(self):
        """validate_opportunity must raise ComplianceViolationError for USDT pair."""
        with pytest.raises(ComplianceViolationError):
            self.engine.validate_opportunity({
                "pair": "BTC/USDT",
                "exchange": "binance",
                "profit": 0.01,
            })

    def test_usdc_opportunity_passes(self):
        """validate_opportunity must return True for a USDC pair."""
        result = self.engine.validate_opportunity({
            "pair": "BTC/USDC",
            "exchange": "binance",
            "profit": 0.01,
        })
        assert result is True

    def test_non_whitelisted_usdc_pair_raises(self):
        """A non-whitelisted base asset with USDC must still be rejected."""
        with pytest.raises(ComplianceViolationError):
            self.engine.validate_opportunity({
                "pair": "SHIB/USDC",
                "exchange": "binance",
                "profit": 0.01,
            })


# ---------------------------------------------------------------------------
# Compliance gate in filter_compliant_pairs
# ---------------------------------------------------------------------------

class TestComplianceGateFilterPairs:
    """Test that filter_compliant_pairs strips USDT pairs from mixed lists."""

    def setup_method(self):
        self.engine = MiCAComplianceEngine(personal_deployment=True)

    def test_mixed_list_removes_usdt(self):
        """USDT pairs must be removed; USDC pairs must survive."""
        mixed = ["BTC/USDC", "ETH/USDT", "XRP/USDC", "ADA/USDT"]
        result = self.engine.filter_compliant_pairs(mixed)
        assert "BTC/USDC" in result
        assert "XRP/USDC" in result
        assert "ETH/USDT" not in result
        assert "ADA/USDT" not in result

    def test_all_usdt_returns_empty(self):
        """A list of only USDT pairs must return an empty list."""
        all_usdt = ["BTC/USDT", "ETH/USDT", "XRP/USDT"]
        result = self.engine.filter_compliant_pairs(all_usdt)
        assert result == []

    def test_all_usdc_returns_all(self):
        """A list of only compliant USDC pairs must all survive."""
        all_usdc = ["BTC/USDC", "ETH/USDC", "XRP/USDC"]
        result = self.engine.filter_compliant_pairs(all_usdc)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Compliance gate integration with ArbitrageDetector
# ---------------------------------------------------------------------------

class TestArbitrageDetectorComplianceGate:
    """Test that ArbitrageDetector.detect_opportunity rejects USDT at the gate."""

    @pytest.fixture(autouse=True)
    def _import_detector(self):
        """Import ArbitrageDetector, skip if heavy deps (pandas/torch) missing."""
        try:
            from arbitrage_detector import ArbitrageDetector
            self.ArbitrageDetector = ArbitrageDetector
        except ImportError as exc:
            pytest.skip(f"ArbitrageDetector import failed (missing dep): {exc}")

    def test_detect_opportunity_rejects_usdt_pair(self):
        """ArbitrageDetector must raise ComplianceViolationError for USDT pairs."""
        detector = self.ArbitrageDetector()

        with pytest.raises(ComplianceViolationError):
            detector.detect_opportunity({
                "pair": "BTC/USDT",
                "exchanges": {
                    "binance": {"bid": 50000, "ask": 50010},
                    "coinbase": {"bid": 50020, "ask": 50030},
                },
            })

    def test_detect_opportunity_accepts_usdc_pair(self):
        """ArbitrageDetector must NOT raise for a compliant USDC pair.

        The call may still fail for other reasons (no model loaded, etc.)
        but it must not raise ComplianceViolationError.
        """
        detector = self.ArbitrageDetector()

        try:
            detector.detect_opportunity({
                "pair": "BTC/USDC",
                "exchanges": {
                    "binance": {"bid": 50000, "ask": 50010},
                    "coinbase": {"bid": 50020, "ask": 50030},
                },
            })
        except ComplianceViolationError:
            pytest.fail("BTC/USDC should not trigger a ComplianceViolationError")
        except Exception:
            # Other exceptions (model not loaded, etc.) are acceptable
            pass
