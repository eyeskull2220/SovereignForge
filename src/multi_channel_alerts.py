#!/usr/bin/env python3
"""
SovereignForge - Multi-Channel Alert System
Wave 2 - Category 3: SMS/Email backup alerts + alert prioritization router.

Channels supported:
- Telegram (primary, uses existing TelegramAlertSystem)
- Email via SMTP (backup)
- SMS via Twilio (backup, optional dependency)

Alert priority levels (highest → lowest):
    CRITICAL  → all channels in parallel
    HIGH      → Telegram + Email
    MEDIUM    → Telegram only
    LOW       → Telegram only (rate-limited)
    DEBUG     → log only

Configuration via environment variables:
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_TO
    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM, TWILIO_TO
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS, TELEGRAM_ENABLED
"""

from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import ssl
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Priority levels
# ---------------------------------------------------------------------------

class AlertPriority(Enum):
    DEBUG = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Alert:
    title: str
    message: str
    priority: AlertPriority
    category: str = "system"         # e.g. 'arbitrage', 'risk', 'system'
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    alert_id: str = field(default_factory=lambda: f"ALT-{int(time.time()*1000)}")


@dataclass
class DeliveryResult:
    channel: str
    success: bool
    error: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class AlertDeliveryReport:
    alert: Alert
    results: List[DeliveryResult]
    sent_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def any_success(self) -> bool:
        return any(r.success for r in self.results)

    @property
    def all_failed(self) -> bool:
        return all(not r.success for r in self.results)


# ---------------------------------------------------------------------------
# Channel interfaces
# ---------------------------------------------------------------------------

class BaseAlertChannel:
    name: str = "base"

    async def send(self, alert: Alert) -> DeliveryResult:
        raise NotImplementedError

    def is_configured(self) -> bool:
        return False


class TelegramChannel(BaseAlertChannel):
    name = "telegram"

    def __init__(self):
        self._system = None

    def is_configured(self) -> bool:
        return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_IDS"))

    async def send(self, alert: Alert) -> DeliveryResult:
        start = time.monotonic()
        try:
            from telegram_alerts import get_telegram_alert_system
            system = get_telegram_alert_system()
            if not system.is_running:
                await system.initialize()
            level_map = {
                AlertPriority.CRITICAL: "error",
                AlertPriority.HIGH: "warning",
                AlertPriority.MEDIUM: "info",
                AlertPriority.LOW: "info",
                AlertPriority.DEBUG: "info",
            }
            await system.send_system_alert(
                alert.title, alert.message, level=level_map[alert.priority]
            )
            return DeliveryResult(
                channel=self.name,
                success=True,
                duration_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as e:
            return DeliveryResult(
                channel=self.name,
                success=False,
                error=str(e),
                duration_ms=(time.monotonic() - start) * 1000,
            )


class EmailChannel(BaseAlertChannel):
    name = "email"

    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.from_addr = os.getenv("SMTP_FROM", self.smtp_user)
        self.to_addrs: List[str] = [
            a.strip()
            for a in os.getenv("SMTP_TO", "").split(",")
            if a.strip()
        ]

    def is_configured(self) -> bool:
        return bool(self.smtp_user and self.smtp_password and self.to_addrs)

    async def send(self, alert: Alert) -> DeliveryResult:
        start = time.monotonic()
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._send_sync, alert)
            return DeliveryResult(
                channel=self.name,
                success=True,
                duration_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return DeliveryResult(
                channel=self.name,
                success=False,
                error=str(e),
                duration_ms=(time.monotonic() - start) * 1000,
            )

    def _send_sync(self, alert: Alert) -> None:
        subject = f"[SovereignForge {alert.priority.name}] {alert.title}"
        body = self._build_html_body(alert)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(self.to_addrs)
        msg.attach(MIMEText(alert.message, "plain"))
        msg.attach(MIMEText(body, "html"))

        context = ssl.create_default_context()
        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.login(self.smtp_user, self.smtp_password)
            smtp.sendmail(self.from_addr, self.to_addrs, msg.as_string())

    @staticmethod
    def _build_html_body(alert: Alert) -> str:
        color_map = {
            AlertPriority.CRITICAL: "#c0392b",
            AlertPriority.HIGH:     "#e67e22",
            AlertPriority.MEDIUM:   "#2980b9",
            AlertPriority.LOW:      "#27ae60",
            AlertPriority.DEBUG:    "#7f8c8d",
        }
        color = color_map.get(alert.priority, "#333")
        ts = datetime.fromtimestamp(alert.timestamp).strftime("%Y-%m-%d %H:%M:%S UTC")
        return f"""
        <html><body style="font-family:Arial,sans-serif;max-width:600px;">
          <div style="background:{color};color:white;padding:12px 20px;border-radius:4px 4px 0 0;">
            <h2 style="margin:0">{alert.priority.name}: {alert.title}</h2>
          </div>
          <div style="border:1px solid {color};padding:20px;border-radius:0 0 4px 4px;">
            <p style="white-space:pre-wrap">{alert.message}</p>
            <hr/>
            <small style="color:#999">
              Category: {alert.category} | ID: {alert.alert_id} | Time: {ts}
            </small>
          </div>
        </body></html>
        """


class SMSChannel(BaseAlertChannel):
    name = "sms"

    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.from_number = os.getenv("TWILIO_FROM", "")
        self.to_numbers: List[str] = [
            n.strip()
            for n in os.getenv("TWILIO_TO", "").split(",")
            if n.strip()
        ]
        self._twilio_available = False
        try:
            from twilio.rest import Client  # type: ignore  # noqa: F401
            self._twilio_available = True
        except ImportError:
            pass

    def is_configured(self) -> bool:
        return bool(
            self._twilio_available
            and self.account_sid
            and self.auth_token
            and self.from_number
            and self.to_numbers
        )

    async def send(self, alert: Alert) -> DeliveryResult:
        start = time.monotonic()
        if not self._twilio_available:
            return DeliveryResult(
                channel=self.name,
                success=False,
                error="twilio not installed",
            )
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._send_sync, alert)
            return DeliveryResult(
                channel=self.name,
                success=True,
                duration_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as e:
            return DeliveryResult(
                channel=self.name,
                success=False,
                error=str(e),
                duration_ms=(time.monotonic() - start) * 1000,
            )

    def _send_sync(self, alert: Alert) -> None:
        from twilio.rest import Client  # type: ignore
        client = Client(self.account_sid, self.auth_token)
        body = f"[SovereignForge {alert.priority.name}] {alert.title}\n{alert.message[:140]}"
        for number in self.to_numbers:
            client.messages.create(body=body, from_=self.from_number, to=number)


# ---------------------------------------------------------------------------
# Rate limiter (per-priority token bucket)
# ---------------------------------------------------------------------------

class AlertRateLimiter:
    """
    Simple sliding-window rate limiter per (priority, category).
    Prevents alert floods for lower-priority events.
    """
    # Max alerts per window_seconds per priority
    _limits: Dict[AlertPriority, int] = {
        AlertPriority.CRITICAL: 100,  # essentially unlimited
        AlertPriority.HIGH:      20,
        AlertPriority.MEDIUM:    10,
        AlertPriority.LOW:        5,
        AlertPriority.DEBUG:      2,
    }
    _window_seconds = 60

    def __init__(self):
        self._history: Dict[AlertPriority, Deque[float]] = {
            p: deque() for p in AlertPriority
        }

    def allow(self, priority: AlertPriority) -> bool:
        now = time.monotonic()
        window_start = now - self._window_seconds
        q = self._history[priority]
        while q and q[0] < window_start:
            q.popleft()
        limit = self._limits[priority]
        if len(q) < limit:
            q.append(now)
            return True
        return False


# ---------------------------------------------------------------------------
# Channel router
# ---------------------------------------------------------------------------

class AlertRouter:
    """
    Routes alerts to the appropriate channels based on priority.

    Priority → channels:
        CRITICAL  → telegram + email + sms (parallel)
        HIGH      → telegram + email
        MEDIUM    → telegram
        LOW       → telegram (rate-limited)
        DEBUG     → log only
    """

    _ROUTING: Dict[AlertPriority, List[str]] = {
        AlertPriority.CRITICAL: ["telegram", "email", "sms"],
        AlertPriority.HIGH:     ["telegram", "email"],
        AlertPriority.MEDIUM:   ["telegram"],
        AlertPriority.LOW:      ["telegram"],
        AlertPriority.DEBUG:    [],
    }

    def __init__(self, custom_routing: Optional[Dict[AlertPriority, List[str]]] = None):
        self._channels: Dict[str, BaseAlertChannel] = {
            "telegram": TelegramChannel(),
            "email": EmailChannel(),
            "sms": SMSChannel(),
        }
        self._rate_limiter = AlertRateLimiter()
        self._routing = custom_routing or self._ROUTING
        self._callbacks: List[Callable[[AlertDeliveryReport], None]] = []

    def add_channel(self, channel: BaseAlertChannel) -> None:
        """Register a custom channel."""
        self._channels[channel.name] = channel

    def add_delivery_callback(self, cb: Callable[[AlertDeliveryReport], None]) -> None:
        """Called after every alert delivery attempt."""
        self._callbacks.append(cb)

    async def send(self, alert: Alert) -> AlertDeliveryReport:
        """Route and send an alert. Returns a DeliveryReport."""
        if not self._rate_limiter.allow(alert.priority):
            logger.debug(
                f"Rate limited alert [{alert.priority.name}]: {alert.title}"
            )
            return AlertDeliveryReport(alert=alert, results=[])

        target_channels = self._routing.get(alert.priority, [])
        if not target_channels:
            logger.debug(f"[{alert.priority.name}] {alert.title}: log only")
            return AlertDeliveryReport(alert=alert, results=[])

        # Only send to configured channels
        active = [
            self._channels[ch]
            for ch in target_channels
            if ch in self._channels and self._channels[ch].is_configured()
        ]

        if not active:
            logger.warning(
                f"No configured channels for {alert.priority.name} alert '{alert.title}'"
            )
            # Log the alert content so it's not lost
            logger.warning(f"ALERT: [{alert.priority.name}] {alert.title} — {alert.message}")
            return AlertDeliveryReport(alert=alert, results=[])

        # Send in parallel for CRITICAL; sequential for others
        if alert.priority == AlertPriority.CRITICAL:
            results = await asyncio.gather(
                *[ch.send(alert) for ch in active], return_exceptions=False
            )
        else:
            results = []
            for ch in active:
                results.append(await ch.send(alert))

        report = AlertDeliveryReport(alert=alert, results=list(results))

        for cb in self._callbacks:
            try:
                cb(report)
            except Exception:
                pass

        if report.all_failed:
            logger.error(
                f"All channels failed for alert '{alert.title}' "
                f"[{alert.priority.name}]: "
                + "; ".join(r.error or "" for r in results)
            )
        else:
            success_channels = [r.channel for r in results if r.success]
            logger.info(
                f"Alert '{alert.title}' [{alert.priority.name}] "
                f"delivered via: {', '.join(success_channels)}"
            )

        return report

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    async def critical(self, title: str, message: str, **kw) -> AlertDeliveryReport:
        return await self.send(Alert(title, message, AlertPriority.CRITICAL, **kw))

    async def high(self, title: str, message: str, **kw) -> AlertDeliveryReport:
        return await self.send(Alert(title, message, AlertPriority.HIGH, **kw))

    async def medium(self, title: str, message: str, **kw) -> AlertDeliveryReport:
        return await self.send(Alert(title, message, AlertPriority.MEDIUM, **kw))

    async def low(self, title: str, message: str, **kw) -> AlertDeliveryReport:
        return await self.send(Alert(title, message, AlertPriority.LOW, **kw))


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_router: Optional[AlertRouter] = None


def get_alert_router() -> AlertRouter:
    global _router
    if _router is None:
        _router = AlertRouter()
    return _router


# Convenience functions
async def send_critical_alert(title: str, message: str, **kw) -> AlertDeliveryReport:
    return await get_alert_router().critical(title, message, **kw)


async def send_high_alert(title: str, message: str, **kw) -> AlertDeliveryReport:
    return await get_alert_router().high(title, message, **kw)


async def send_medium_alert(title: str, message: str, **kw) -> AlertDeliveryReport:
    return await get_alert_router().medium(title, message, **kw)


async def send_low_alert(title: str, message: str, **kw) -> AlertDeliveryReport:
    return await get_alert_router().low(title, message, **kw)


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    async def _smoke():
        router = AlertRouter()
        report = await router.medium(
            "Smoke Test",
            "Multi-channel alert system operational.",
            category="system",
        )
        print(f"Delivered: {report.any_success} | Channels tried: {[r.channel for r in report.results]}")

    asyncio.run(_smoke())
