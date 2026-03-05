# SovereignForge Monitoring System - Wave 6
# Production monitoring with Prometheus metrics and alerting

import asyncio
import logging
import time
from typing import Dict, Any, Optional
import os
from datetime import datetime

from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry, generate_latest
import aiohttp
import structlog

logger = logging.getLogger(__name__)

class MetricsCollector:
    """Prometheus metrics collector for SovereignForge"""

    def __init__(self):
        self.registry = CollectorRegistry()
        self.metrics_enabled = os.getenv('METRICS_ENABLED', 'true').lower() == 'true'
        self.metrics_port = int(os.getenv('METRICS_PORT', '8000'))

        if self.metrics_enabled:
            self._initialize_metrics()

    def _initialize_metrics(self):
        """Initialize Prometheus metrics"""

        # Trading metrics
        self.arbitrage_signal = Gauge(
            'sovereignforge_arbitrage_signal',
            'Current arbitrage signal strength',
            ['symbol'],
            registry=self.registry
        )

        self.detection_confidence = Gauge(
            'sovereignforge_detection_confidence',
            'Arbitrage detection confidence level',
            ['symbol'],
            registry=self.registry
        )

        self.trades_total = Counter(
            'sovereignforge_trades_total',
            'Total number of trades executed',
            ['symbol', 'status'],
            registry=self.registry
        )

        self.portfolio_value = Gauge(
            'sovereignforge_portfolio_value',
            'Current portfolio value in USD',
            registry=self.registry
        )

        self.daily_pnl = Gauge(
            'sovereignforge_daily_pnl',
            'Daily profit and loss',
            registry=self.registry
        )

        self.portfolio_drawdown_percent = Gauge(
            'sovereignforge_portfolio_drawdown_percent',
            'Portfolio drawdown percentage',
            registry=self.registry
        )

        # Risk metrics
        self.sharpe_ratio = Gauge(
            'sovereignforge_sharpe_ratio',
            'Sharpe ratio',
            registry=self.registry
        )

        self.sortino_ratio = Gauge(
            'sovereignforge_sortino_ratio',
            'Sortino ratio',
            registry=self.registry
        )

        self.max_drawdown_percent = Gauge(
            'sovereignforge_max_drawdown_percent',
            'Maximum drawdown percentage',
            registry=self.registry
        )

        self.var_95 = Gauge(
            'sovereignforge_var_95',
            'Value at Risk (95% confidence)',
            registry=self.registry
        )

        self.win_rate = Gauge(
            'sovereignforge_win_rate',
            'Win rate percentage',
            registry=self.registry
        )

        self.avg_trade_size = Gauge(
            'sovereignforge_avg_trade_size',
            'Average trade size in USD',
            registry=self.registry
        )

        # System metrics
        self.active_opportunities = Gauge(
            'sovereignforge_active_opportunities',
            'Number of active arbitrage opportunities',
            registry=self.registry
        )

        # Performance metrics
        self.detection_cycle_duration = Histogram(
            'sovereignforge_detection_cycle_duration_seconds',
            'Time taken for detection cycle',
            ['cycle_type'],
            registry=self.registry
        )

        self.request_duration = Histogram(
            'sovereignforge_request_duration_seconds',
            'Request duration in seconds',
            ['method', 'endpoint', 'status'],
            registry=self.registry
        )

        # Error metrics
        self.detection_errors_total = Counter(
            'sovereignforge_detection_errors_total',
            'Total detection errors',
            ['symbol', 'error_type'],
            registry=self.registry
        )

        self.api_errors_total = Counter(
            'sovereignforge_api_errors_total',
            'Total API errors',
            ['exchange', 'endpoint'],
            registry=self.registry
        )

        self.trade_failures_total = Counter(
            'sovereignforge_trade_failures_total',
            'Total trade failures',
            ['exchange', 'reason'],
            registry=self.registry
        )

        # Health check metrics
        self.health_check_db = Gauge(
            'sovereignforge_health_check_db',
            'Database health check status (1=healthy, 0=unhealthy)',
            ['component'],
            registry=self.registry
        )

        self.health_check_cache = Gauge(
            'sovereignforge_health_check_cache',
            'Cache health check status (1=healthy, 0=unhealthy)',
            ['component'],
            registry=self.registry
        )

        self.health_check_exchange = Gauge(
            'sovereignforge_health_check_exchange',
            'Exchange API health check status (1=healthy, 0=unhealthy)',
            ['component'],
            registry=self.registry
        )

        # System resource metrics
        self.system_cpu_percent = Gauge(
            'sovereignforge_system_cpu_percent',
            'System CPU usage percentage',
            ['hostname'],
            registry=self.registry
        )

        self.system_memory_percent = Gauge(
            'sovereignforge_system_memory_percent',
            'System memory usage percentage',
            ['hostname'],
            registry=self.registry
        )

        self.system_disk_usage_percent = Gauge(
            'sovereignforge_system_disk_usage_percent',
            'System disk usage percentage',
            ['hostname'],
            registry=self.registry
        )

        # Opportunities metrics
        self.opportunities_detected_total = Counter(
            'sovereignforge_opportunities_detected_total',
            'Total arbitrage opportunities detected',
            ['symbol'],
            registry=self.registry
        )

        self.opportunities_missed_total = Counter(
            'sovereignforge_opportunities_missed_total',
            'Total arbitrage opportunities missed',
            ['symbol', 'reason'],
            registry=self.registry
        )

    async def initialize(self):
        """Initialize the metrics collector"""
        if not self.metrics_enabled:
            logger.info("Metrics collection disabled")
            return True

        try:
            # Start metrics server
            from prometheus_client import start_http_server
            start_http_server(self.metrics_port)
            logger.info(f"Metrics server started on port {self.metrics_port}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize metrics collector: {e}")
            return False

    async def close(self):
        """Close the metrics collector"""
        # Prometheus client handles cleanup automatically
        pass

    async def record_metric(self, name: str, value: float, labels: Dict[str, str] = None):
        """Record a custom metric"""
        if not self.metrics_enabled:
            return

        try:
            if not hasattr(self, name):
                # Create dynamic metric if it doesn't exist
                if 'total' in name or 'count' in name:
                    metric = Counter(name, f'Custom counter: {name}', list(labels.keys()) if labels else [], registry=self.registry)
                else:
                    metric = Gauge(name, f'Custom gauge: {name}', list(labels.keys()) if labels else [], registry=self.registry)
                setattr(self, name, metric)

            metric = getattr(self, name)
            if labels:
                metric.labels(**labels).set(value)
            else:
                metric.set(value)

        except Exception as e:
            logger.error(f"Failed to record metric {name}: {e}")

    def get_metrics_text(self) -> str:
        """Get metrics in Prometheus text format"""
        if not self.metrics_enabled:
            return ""

        try:
            return generate_latest(self.registry).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to generate metrics text: {e}")
            return ""

    async def export_metrics(self, filepath: str):
        """Export metrics to file"""
        try:
            metrics_text = self.get_metrics_text()
            with open(filepath, 'w') as f:
                f.write(metrics_text)
            logger.info(f"Metrics exported to {filepath}")
        except Exception as e:
            logger.error(f"Failed to export metrics: {e}")


class AlertManager:
    """Alert management system for SovereignForge"""

    def __init__(self):
        self.alerts_enabled = True
        self.slack_webhook = os.getenv('SLACK_WEBHOOK_URL')
        self.slack_channel = os.getenv('SLACK_CHANNEL', '#sovereignforge-alerts')
        self.email_enabled = os.getenv('EMAIL_ALERTS_ENABLED', 'false').lower() == 'true'

        # Alert thresholds and cooldowns
        self.alert_cooldowns = {}  # alert_key -> last_alert_time
        self.cooldown_period = 300  # 5 minutes

    async def initialize(self):
        """Initialize alert manager"""
        logger.info("Alert manager initialized")
        return True

    async def close(self):
        """Close alert manager"""
        pass

    async def send_alert(self, severity: str, title: str, message: str, details: Dict[str, Any] = None):
        """Send an alert with the specified severity"""
        if not self.alerts_enabled:
            return

        alert_key = f"{severity}:{title}"
        current_time = time.time()

        # Check cooldown
        if alert_key in self.alert_cooldowns:
            if current_time - self.alert_cooldowns[alert_key] < self.cooldown_period:
                logger.debug(f"Alert {alert_key} is in cooldown")
                return

        self.alert_cooldowns[alert_key] = current_time

        try:
            # Format alert message
            alert_message = self._format_alert_message(severity, title, message, details)

            # Send to Slack
            if self.slack_webhook:
                await self._send_slack_alert(severity, title, alert_message)

            # Send email (if enabled)
            if self.email_enabled:
                await self._send_email_alert(severity, title, alert_message)

            # Log alert
            logger.warning(f"ALERT [{severity.upper()}]: {title} - {message}")

        except Exception as e:
            logger.error(f"Failed to send alert: {e}")

    def _format_alert_message(self, severity: str, title: str, message: str, details: Dict[str, Any] = None) -> str:
        """Format alert message for delivery"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')

        formatted = f"""
🚨 SovereignForge Alert 🚨

Severity: {severity.upper()}
Title: {title}
Time: {timestamp}

Message:
{message}
"""

        if details:
            formatted += "\nDetails:\n"
            for key, value in details.items():
                formatted += f"  {key}: {value}\n"

        formatted += f"\nEnvironment: {os.getenv('ENVIRONMENT', 'unknown')}"
        formatted += f"\nHostname: {os.getenv('HOSTNAME', 'unknown')}"

        return formatted.strip()

    async def _send_slack_alert(self, severity: str, title: str, message: str):
        """Send alert to Slack"""
        if not self.slack_webhook:
            return

        try:
            # Map severity to Slack colors
            color_map = {
                'critical': 'danger',
                'warning': 'warning',
                'info': 'good'
            }
            color = color_map.get(severity.lower(), 'warning')

            payload = {
                "channel": self.slack_channel,
                "username": "SovereignForge Alert",
                "icon_emoji": ":warning:",
                "attachments": [
                    {
                        "color": color,
                        "title": title,
                        "text": message,
                        "footer": "SovereignForge Trading System",
                        "ts": int(time.time())
                    }
                ]
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(self.slack_webhook, json=payload) as response:
                    if response.status != 200:
                        logger.error(f"Slack alert failed with status {response.status}")

        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")

    async def _send_email_alert(self, severity: str, title: str, message: str):
        """Send alert via email"""
        if not self.email_enabled:
            return

        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
            smtp_port = int(os.getenv('SMTP_PORT', '587'))
            smtp_username = os.getenv('SMTP_USERNAME')
            smtp_password = os.getenv('SMTP_PASSWORD')

            if not all([smtp_username, smtp_password]):
                logger.warning("Email credentials not configured")
                return

            recipients = os.getenv('ALERT_EMAIL_RECIPIENTS', '').split(',')

            msg = MIMEMultipart()
            msg['From'] = smtp_username
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = f"SovereignForge Alert: {title}"

            msg.attach(MIMEText(message, 'plain'))

            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(smtp_username, smtp_password)
            text = msg.as_string()
            server.sendmail(smtp_username, recipients, text)
            server.quit()

        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")

    async def send_heartbeat(self):
        """Send periodic heartbeat alert"""
        await self.send_alert(
            'info',
            'System Heartbeat',
            'SovereignForge is running normally',
            {'status': 'healthy', 'timestamp': datetime.now().isoformat()}
        )

    async def alert_critical_error(self, error: Exception, context: str = ""):
        """Send critical error alert"""
        await self.send_alert(
            'critical',
            'Critical System Error',
            f"A critical error occurred: {str(error)}",
            {'error_type': type(error).__name__, 'context': context, 'traceback': str(error.__traceback__)}
        )

    async def alert_trading_anomaly(self, anomaly_type: str, details: Dict[str, Any]):
        """Send trading anomaly alert"""
        await self.send_alert(
            'warning',
            f'Trading Anomaly: {anomaly_type}',
            f'A trading anomaly has been detected: {anomaly_type}',
            details
        )

    async def alert_risk_limit_breached(self, limit_type: str, current_value: float, threshold: float):
        """Send risk limit breach alert"""
        severity = 'critical' if limit_type in ['daily_loss_limit', 'drawdown_limit'] else 'warning'

        await self.send_alert(
            severity,
            f'Risk Limit Breached: {limit_type}',
            f'{limit_type} has been breached. Current: {current_value}, Threshold: {threshold}',
            {'limit_type': limit_type, 'current_value': current_value, 'threshold': threshold}
        )