#!/usr/bin/env python3
"""
SovereignForge v1 - Chart Components
Lightweight-charts-python integration for clean financial charts
"""

import sys
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer

logger = logging.getLogger(__name__)

try:
    from lightweight_charts import Chart
    LIGHTWEIGHT_CHARTS_AVAILABLE = True
except ImportError:
    logger.warning("lightweight-charts-python not available, using placeholder")
    LIGHTWEIGHT_CHARTS_AVAILABLE = False

    class Chart:
        """Placeholder Chart class"""
        def __init__(self, widget):
            self.widget = widget

        def set(self, data):
            pass

        def update(self, data):
            pass

class PriceChartWidget(QWidget):
    """Price chart widget using lightweight-charts-python"""

    def __init__(self, coin: str = "XRP"):
        super().__init__()
        self.coin = coin
        self.layout = QVBoxLayout(self)

        # Chart title
        self.title = QLabel(f"{coin} Price Chart")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 10px;")
        self.layout.addWidget(self.title)

        # Chart widget
        self.chart_widget = QWidget()
        self.layout.addWidget(self.chart_widget)

        # Initialize chart
        self.chart = None
        self._setup_chart()

        # Price data storage
        self.price_data = []

    def _setup_chart(self):
        """Setup the lightweight chart"""
        if not LIGHTWEIGHT_CHARTS_AVAILABLE:
            # Fallback placeholder
            placeholder = QLabel("Chart not available - install lightweight-charts-python")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("color: #666; padding: 20px;")
            self.layout.addWidget(placeholder)
            return

        try:
            self.chart = Chart(self.chart_widget)

            # Configure chart appearance (finn.no style)
            self.chart.layout(
                background_color='#ffffff',
                text_color='#2d3748',
                font_family='Inter, -apple-system, sans-serif'
            )

            # Set up candlestick chart
            self.chart.candlestick()

            # Configure grid and axes
            self.chart.grid(
                color='#e2e8f0',
                style='solid'
            )

            logger.info(f"Chart initialized for {self.coin}")

        except Exception as e:
            logger.error(f"Failed to initialize chart: {e}")
            placeholder = QLabel(f"Chart initialization failed: {str(e)}")
            placeholder.setAlignment(Qt.AlignCenter)
            self.layout.addWidget(placeholder)

    def update_price_data(self, price_data: List[Dict[str, Any]]):
        """Update chart with new price data"""
        if not self.chart or not LIGHTWEIGHT_CHARTS_AVAILABLE:
            return

        try:
            # Convert data to chart format
            chart_data = []
            for data_point in price_data[-100:]:  # Last 100 points
                chart_data.append({
                    'time': data_point.get('timestamp', datetime.now()),
                    'open': data_point.get('open', data_point.get('price', 0)),
                    'high': data_point.get('high', data_point.get('price', 0)),
                    'low': data_point.get('low', data_point.get('price', 0)),
                    'close': data_point.get('close', data_point.get('price', 0)),
                    'volume': data_point.get('volume', 0)
                })

            # Update chart
            self.chart.set(chart_data)

        except Exception as e:
            logger.error(f"Failed to update chart data: {e}")

    def add_price_point(self, price: float, volume: float = 0):
        """Add a single price point to the chart"""
        if not self.chart or not LIGHTWEIGHT_CHARTS_AVAILABLE:
            return

        try:
            data_point = {
                'time': datetime.now(),
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'volume': volume
            }

            self.price_data.append(data_point)

            # Keep only recent data
            if len(self.price_data) > 100:
                self.price_data = self.price_data[-100:]

            # Update chart
            self.chart.update(data_point)

        except Exception as e:
            logger.error(f"Failed to add price point: {e}")

class ArbitrageChartWidget(QWidget):
    """Chart showing arbitrage spread over time"""

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)

        # Chart title
        self.title = QLabel("Arbitrage Spread Analysis")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 10px;")
        self.layout.addWidget(self.title)

        # Chart widget
        self.chart_widget = QWidget()
        self.layout.addWidget(self.chart_widget)

        # Initialize chart
        self.chart = None
        self._setup_chart()

        # Spread data storage
        self.spread_data = []

    def _setup_chart(self):
        """Setup the arbitrage spread chart"""
        if not LIGHTWEIGHT_CHARTS_AVAILABLE:
            placeholder = QLabel("Chart not available - install lightweight-charts-python")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("color: #666; padding: 20px;")
            self.layout.addWidget(placeholder)
            return

        try:
            self.chart = Chart(self.chart_widget)

            # Configure chart appearance
            self.chart.layout(
                background_color='#ffffff',
                text_color='#2d3748',
                font_family='Inter, -apple-system, sans-serif'
            )

            # Set up line chart for spread
            self.chart.line(
                color='#3182ce',
                width=2
            )

            # Configure grid
            self.chart.grid(
                color='#e2e8f0',
                style='solid'
            )

            logger.info("Arbitrage spread chart initialized")

        except Exception as e:
            logger.error(f"Failed to initialize arbitrage chart: {e}")

    def update_spread_data(self, spread_data: List[Dict[str, Any]]):
        """Update chart with arbitrage spread data"""
        if not self.chart or not LIGHTWEIGHT_CHARTS_AVAILABLE:
            return

        try:
            # Convert data to chart format
            chart_data = []
            for data_point in spread_data[-50:]:  # Last 50 points
                chart_data.append({
                    'time': data_point.get('timestamp', datetime.now()),
                    'value': data_point.get('spread', 0)
                })

            # Update chart
            self.chart.set(chart_data)

        except Exception as e:
            logger.error(f"Failed to update spread chart: {e}")

    def add_spread_point(self, spread: float):
        """Add a spread point to the chart"""
        if not self.chart or not LIGHTWEIGHT_CHARTS_AVAILABLE:
            return

        try:
            data_point = {
                'time': datetime.now(),
                'value': spread
            }

            self.spread_data.append(data_point)

            # Keep only recent data
            if len(self.spread_data) > 50:
                self.spread_data = self.spread_data[-50:]

            # Update chart
            self.chart.update(data_point)

        except Exception as e:
            logger.error(f"Failed to add spread point: {e}")

class VolumeChartWidget(QWidget):
    """Volume analysis chart"""

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)

        # Chart title
        self.title = QLabel("Volume Analysis")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 10px;")
        self.layout.addWidget(self.title)

        # Chart widget
        self.chart_widget = QWidget()
        self.layout.addWidget(self.chart_widget)

        # Initialize chart
        self.chart = None
        self._setup_chart()

        # Volume data storage
        self.volume_data = []

    def _setup_chart(self):
        """Setup the volume chart"""
        if not LIGHTWEIGHT_CHARTS_AVAILABLE:
            placeholder = QLabel("Chart not available - install lightweight-charts-python")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("color: #666; padding: 20px;")
            self.layout.addWidget(placeholder)
            return

        try:
            self.chart = Chart(self.chart_widget)

            # Configure chart appearance
            self.chart.layout(
                background_color='#ffffff',
                text_color='#2d3748',
                font_family='Inter, -apple-system, sans-serif'
            )

            # Set up histogram for volume
            self.chart.histogram(
                color='#48bb78',
                price_format='volume'
            )

            logger.info("Volume chart initialized")

        except Exception as e:
            logger.error(f"Failed to initialize volume chart: {e}")

    def update_volume_data(self, volume_data: List[Dict[str, Any]]):
        """Update chart with volume data"""
        if not self.chart or not LIGHTWEIGHT_CHARTS_AVAILABLE:
            return

        try:
            # Convert data to chart format
            chart_data = []
            for data_point in volume_data[-50:]:  # Last 50 points
                chart_data.append({
                    'time': data_point.get('timestamp', datetime.now()),
                    'value': data_point.get('volume', 0)
                })

            # Update chart
            self.chart.set(chart_data)

        except Exception as e:
            logger.error(f"Failed to update volume chart: {e}")

class RiskChartWidget(QWidget):
    """Risk metrics visualization"""

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)

        # Chart title
        self.title = QLabel("Risk Metrics")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 10px;")
        self.layout.addWidget(self.title)

        # Chart widget
        self.chart_widget = QWidget()
        self.layout.addWidget(self.chart_widget)

        # Initialize chart
        self.chart = None
        self._setup_chart()

        # Risk data storage
        self.risk_data = []

    def _setup_chart(self):
        """Setup the risk metrics chart"""
        if not LIGHTWEIGHT_CHARTS_AVAILABLE:
            placeholder = QLabel("Chart not available - install lightweight-charts-python")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("color: #666; padding: 20px;")
            self.layout.addWidget(placeholder)
            return

        try:
            self.chart = Chart(self.chart_widget)

            # Configure chart appearance
            self.chart.layout(
                background_color='#ffffff',
                text_color='#2d3748',
                font_family='Inter, -apple-system, sans-serif'
            )

            # Set up area chart for risk score
            self.chart.area(
                color='#e53e3e',
                opacity=0.3
            )

            # Add line overlay
            self.chart.line(
                color='#e53e3e',
                width=2
            )

            logger.info("Risk chart initialized")

        except Exception as e:
            logger.error(f"Failed to initialize risk chart: {e}")

    def update_risk_data(self, risk_data: List[Dict[str, Any]]):
        """Update chart with risk metrics data"""
        if not self.chart or not LIGHTWEIGHT_CHARTS_AVAILABLE:
            return

        try:
            # Convert data to chart format
            chart_data = []
            for data_point in risk_data[-30:]:  # Last 30 points
                chart_data.append({
                    'time': data_point.get('timestamp', datetime.now()),
                    'value': data_point.get('risk_score', 0)
                })

            # Update chart
            self.chart.set(chart_data)

        except Exception as e:
            logger.error(f"Failed to update risk chart: {e}")

    def add_risk_point(self, risk_score: float):
        """Add a risk score point to the chart"""
        if not self.chart or not LIGHTWEIGHT_CHARTS_AVAILABLE:
            return

        try:
            data_point = {
                'time': datetime.now(),
                'value': risk_score
            }

            self.risk_data.append(data_point)

            # Keep only recent data
            if len(self.risk_data) > 30:
                self.risk_data = self.risk_data[-30:]

            # Update chart
            self.chart.update(data_point)

        except Exception as e:
            logger.error(f"Failed to add risk point: {e}")

class ChartContainer(QWidget):
    """Container for multiple charts with tabs"""

    def __init__(self):
        super().__init__()
        from PySide6.QtWidgets import QTabWidget

        self.layout = QVBoxLayout(self)

        # Tab widget for different charts
        self.tabs = QTabWidget()

        # Initialize chart widgets
        self.price_chart = PriceChartWidget("XRP")
        self.arbitrage_chart = ArbitrageChartWidget()
        self.volume_chart = VolumeChartWidget()
        self.risk_chart = RiskChartWidget()

        # Add tabs
        self.tabs.addTab(self.price_chart, "Price Chart")
        self.tabs.addTab(self.arbitrage_chart, "Arbitrage Spread")
        self.tabs.addTab(self.volume_chart, "Volume Analysis")
        self.tabs.addTab(self.risk_chart, "Risk Metrics")

        self.layout.addWidget(self.tabs)

    def update_price_data(self, coin: str, data: List[Dict[str, Any]]):
        """Update price chart for specific coin"""
        if coin == "XRP":  # Update main chart
            self.price_chart.update_price_data(data)

    def update_arbitrage_data(self, spread_data: List[Dict[str, Any]]):
        """Update arbitrage spread chart"""
        self.arbitrage_chart.update_spread_data(spread_data)

    def update_volume_data(self, volume_data: List[Dict[str, Any]]):
        """Update volume chart"""
        self.volume_chart.update_volume_data(volume_data)

    def update_risk_data(self, risk_data: List[Dict[str, Any]]):
        """Update risk chart"""
        self.risk_chart.update_risk_data(risk_data)