#!/usr/bin/env python3
"""
SovereignForge v1 - UI/UX Interface
PySide6-based desktop application with lightweight-charts-python
AgentCommand-style real-time monitoring dashboard
finn.no Scandinavian minimal design
"""

import sys
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget,
    QSplitter, QFrame, QProgressBar, QStatusBar, QGridLayout,
    QGroupBox, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread, QObject
from PySide6.QtGui import QFont, QPalette, QColor, QIcon

logger = logging.getLogger(__name__)

from charts import ChartContainer

class MarketDataWorker(QObject):
    """Worker thread for market data updates"""
    data_updated = Signal(dict)
    opportunities_updated = Signal(list)

    def __init__(self, trading_engine, analyzer):
        super().__init__()
        self.trading_engine = trading_engine
        self.analyzer = analyzer
        self.running = True

    def run(self):
        """Main worker loop"""
        while self.running:
            try:
                # Get market overview
                overview = self.trading_engine.get_market_overview()
                self.data_updated.emit(overview)

                # Get arbitrage opportunities
                opportunities = self.trading_engine.find_arbitrage_opportunities()
                analyses = self.analyzer.analyze_opportunities(opportunities)
                self.opportunities_updated.emit(analyses)

                # Sleep for 5 seconds
                QThread.sleep(5)
            except Exception as e:
                logger.error(f"Market data worker error: {e}")
                QThread.sleep(10)

    def stop(self):
        """Stop the worker"""
        self.running = False

class ArbitrageTable(QTableWidget):
    """Table for displaying arbitrage opportunities"""

    def __init__(self):
        super().__init__()
        self.setColumnCount(8)
        self.setHorizontalHeaderLabels([
            "Coin", "Buy Exchange", "Sell Exchange", "Net Spread %",
            "Volume", "Risk Score", "Confidence", "Session"
        ])
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.resizeColumnsToContents()

    def update_opportunities(self, analyses: List):
        """Update table with arbitrage analyses"""
        self.setRowCount(len(analyses))

        for row, analysis in enumerate(analyses):
            self.setItem(row, 0, QTableWidgetItem(analysis.coin))
            self.setItem(row, 1, QTableWidgetItem(analysis.exchanges[0]))
            self.setItem(row, 2, QTableWidgetItem(analysis.exchanges[1]))
            self.setItem(row, 3, QTableWidgetItem(f"{analysis.net_spread:.2f}%"))
            self.setItem(row, 4, QTableWidgetItem(f"{analysis.volume_opportunity:.0f}"))
            self.setItem(row, 5, QTableWidgetItem(f"{analysis.risk_score:.2f}"))
            self.setItem(row, 6, QTableWidgetItem(f"{analysis.confidence_score:.2f}"))
            self.setItem(row, 7, QTableWidgetItem(analysis.session_timing))

            # Color coding based on confidence
            if analysis.confidence_score > 0.8:
                color = QColor(34, 197, 94)  # Green
            elif analysis.confidence_score > 0.6:
                color = QColor(251, 191, 36)  # Yellow
            else:
                color = QColor(239, 68, 68)  # Red

            for col in range(8):
                self.item(row, col).setBackground(color)

class MarketOverviewWidget(QWidget):
    """Market overview display widget"""

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)

        # Title
        title = QLabel("Market Overview")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        self.layout.addWidget(title)

        # Coin grid
        self.coin_grid = QGridLayout()
        self.coin_labels = {}
        self.layout.addLayout(self.coin_grid)

        # Initialize with allowed coins
        self.allowed_coins = ["XRP", "ADA", "XLM", "HBAR", "ALGO", "LINK", "IOTA", "XDC", "ONDO", "VET"]
        self._setup_coin_display()

    def _setup_coin_display(self):
        """Setup coin price display grid"""
        exchanges = ["binance", "kraken", "coinbase", "kucoin", "gateio"]

        # Header row
        self.coin_grid.addWidget(QLabel("Coin"), 0, 0)
        for i, exchange in enumerate(exchanges):
            self.coin_grid.addWidget(QLabel(exchange.title()), 0, i+1)

        # Coin rows
        for row, coin in enumerate(self.allowed_coins, 1):
            self.coin_grid.addWidget(QLabel(coin), row, 0)
            self.coin_labels[coin] = {}

            for col, exchange in enumerate(exchanges, 1):
                label = QLabel("--")
                label.setAlignment(Qt.AlignCenter)
                self.coin_grid.addWidget(label, row, col)
                self.coin_labels[coin][exchange] = label

    def update_market_data(self, overview: Dict):
        """Update market data display"""
        for coin, exchanges in overview.items():
            if coin in self.coin_labels:
                for exchange, data in exchanges.items():
                    if exchange in self.coin_labels[coin]:
                        price = data.get('price', 0)
                        self.coin_labels[coin][exchange].setText(f"${price:.4f}")

class RiskDashboard(QWidget):
    """Risk management dashboard"""

    def __init__(self, risk_agent):
        super().__init__()
        self.risk_agent = risk_agent
        self.layout = QVBoxLayout(self)

        # Title
        title = QLabel("Risk Dashboard")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        self.layout.addWidget(title)

        # Risk metrics grid
        self.metrics_layout = QGridLayout()
        self.layout.addLayout(self.metrics_layout)

        # Initialize metrics display
        self._setup_risk_metrics()

    def _setup_risk_metrics(self):
        """Setup risk metrics display"""
        metrics = [
            ("Max Drawdown", "3.2%"),
            ("Portfolio Value", "$10,000"),
            ("Active Positions", "0"),
            ("Correlation Alert", "None"),
            ("MiCA Compliance", "✓ COMPLIANT")
        ]

        for i, (label, value) in enumerate(metrics):
            row = i // 2
            col = (i % 2) * 2

            label_widget = QLabel(f"{label}:")
            value_widget = QLabel(value)
            value_widget.setFont(QFont("Arial", 10, QFont.Bold))

            self.metrics_layout.addWidget(label_widget, row, col)
            self.metrics_layout.addWidget(value_widget, row, col + 1)

class AgentStatusWidget(QWidget):
    """Agent status monitoring widget"""

    def __init__(self, agent_system):
        super().__init__()
        self.agent_system = agent_system
        self.layout = QVBoxLayout(self)

        # Title
        title = QLabel("Agent Command Center")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        self.layout.addWidget(title)

        # Agent status grid
        self.status_layout = QGridLayout()
        self.layout.addLayout(self.status_layout)

        # Agent status indicators
        self.agent_indicators = {}
        self._setup_agent_status()

    def _setup_agent_status(self):
        """Setup agent status indicators"""
        agents = ["CEO", "Research", "Engineer", "Dev", "Tester", "UI/UX", "Risk", "Nova"]

        for i, agent in enumerate(agents):
            row = i // 4
            col = i % 4

            # Agent label
            label = QLabel(f"{agent}:")
            self.status_layout.addWidget(label, row*2, col)

            # Status indicator
            status = QLabel("ACTIVE")
            status.setStyleSheet("color: green; font-weight: bold;")
            self.status_layout.addWidget(status, row*2+1, col)

            self.agent_indicators[agent] = status

class TradingUI(QMainWindow):
    """Main trading interface window"""

    def __init__(self, trading_engine, scheduler):
        super().__init__()
        self.trading_engine = trading_engine
        self.scheduler = scheduler

        # Initialize arbitrage analyzer
        from arbitrage_analysis import ArbitrageAnalyzer
        self.analyzer = ArbitrageAnalyzer(trading_engine)

        # Initialize risk agent
        from agents import AgentSystem
        self.agent_system = AgentSystem()

        self.setWindowTitle("SovereignForge v1.0 - Personal Trading Platform")
        self.setGeometry(100, 100, 1400, 900)

        # Apply finn.no style
        self._apply_finn_no_style()

        # Setup UI
        self._setup_ui()

        # Setup market data worker
        self._setup_worker_thread()

        # Start updates
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_display)
        self.update_timer.start(1000)  # Update every second

        logger.info("TradingUI initialized")

    def _apply_finn_no_style(self):
        """Apply finn.no Scandinavian minimal design"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #ffffff;
            }
            QLabel {
                color: #2d3748;
                font-family: 'Inter', -apple-system, sans-serif;
            }
            QPushButton {
                background-color: #3182ce;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #2c5282;
            }
            QTableWidget {
                gridline-color: #e2e8f0;
                selection-background-color: #edf2f7;
            }
            QTabWidget::pane {
                border: 1px solid #e2e8f0;
                background-color: #f7fafc;
            }
            QTabBar::tab {
                background-color: #f7fafc;
                color: #4a5568;
                padding: 8px 16px;
                margin-right: 2px;
                border: 1px solid #e2e8f0;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                color: #3182ce;
                border-bottom: 2px solid #3182ce;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #e2e8f0;
                border-radius: 4px;
                margin-top: 1ex;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)

    def _setup_ui(self):
        """Setup main UI layout"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        # Top status bar
        self._setup_status_bar()

        # Main content splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left panel - Market data and opportunities
        left_panel = self._create_left_panel()
        splitter.addWidget(left_panel)

        # Right panel - Risk and agent status
        right_panel = self._create_right_panel()
        splitter.addWidget(right_panel)

        splitter.setSizes([900, 500])
        main_layout.addWidget(splitter)

    def _create_left_panel(self):
        """Create left panel with market data and opportunities"""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Tab widget for different views
        tabs = QTabWidget()

        # Market overview tab
        self.market_overview = MarketOverviewWidget()
        tabs.addTab(self.market_overview, "Market Overview")

        # Charts tab
        self.charts_container = ChartContainer()
        tabs.addTab(self.charts_container, "Charts")

        # Arbitrage opportunities tab
        arbitrage_widget = QWidget()
        arbitrage_layout = QVBoxLayout(arbitrage_widget)
        self.arbitrage_table = ArbitrageTable()
        arbitrage_layout.addWidget(self.arbitrage_table)
        tabs.addTab(arbitrage_widget, "Arbitrage Opportunities")

        layout.addWidget(tabs)
        return panel

    def _create_right_panel(self):
        """Create right panel with risk and agent status"""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Risk dashboard
        self.risk_dashboard = RiskDashboard(self.agent_system.risk)
        layout.addWidget(self.risk_dashboard)

        # Agent status
        self.agent_status = AgentStatusWidget(self.agent_system)
        layout.addWidget(self.agent_status)

        # Session timing display
        session_group = QGroupBox("Trading Sessions")
        session_layout = QVBoxLayout(session_group)

        self.session_label = QLabel("Current Session: Crypto (24/7)")
        self.session_label.setFont(QFont("Arial", 12))
        session_layout.addWidget(self.session_label)

        # Session performance
        self.session_perf_label = QLabel("Session Performance: Analyzing...")
        session_layout.addWidget(self.session_perf_label)

        layout.addWidget(session_group)

        return panel

    def _setup_status_bar(self):
        """Setup status bar"""
        self.status_bar = self.statusBar()

        # System status
        self.status_bar.addWidget(QLabel("System Status: ACTIVE"))

        # Last update time
        self.last_update_label = QLabel("Last Update: --")
        self.status_bar.addPermanentWidget(self.last_update_label)

        # Market regime
        self.regime_label = QLabel("Regime: Ranging")
        self.status_bar.addPermanentWidget(self.regime_label)

    def _setup_worker_thread(self):
        """Setup background worker thread"""
        self.worker = MarketDataWorker(self.trading_engine, self.analyzer)
        self.worker_thread = QThread()

        self.worker.moveToThread(self.worker_thread)
        self.worker.data_updated.connect(self.market_overview.update_market_data)
        self.worker.opportunities_updated.connect(self.arbitrage_table.update_opportunities)

        self.worker_thread.started.connect(self.worker.run)
        self.worker_thread.start()

    def _update_display(self):
        """Update display elements"""
        # Update last update time
        self.last_update_label.setText(f"Last Update: {datetime.now().strftime('%H:%M:%S')}")

        # Update market regime
        regime = self.analyzer.get_market_regime()
        self.regime_label.setText(f"Regime: {regime.title()}")

        # Update session info
        session = self.trading_engine._get_current_session()
        self.session_label.setText(f"Current Session: {session.title()}")

        # Update session performance
        session_comp = self.analyzer.get_session_comparison()
        if session in session_comp:
            comp = session_comp[session]
            self.session_perf_label.setText(
                f"Session Performance: {comp.opportunities_count} opps, "
                f"avg {comp.average_spread:.2f}% spread"
            )

    def closeEvent(self, event):
        """Handle application close"""
        logger.info("Shutting down TradingUI")

        # Stop worker thread
        if hasattr(self, 'worker'):
            self.worker.stop()
        if hasattr(self, 'worker_thread'):
            self.worker_thread.quit()
            self.worker_thread.wait()

        # Stop update timer
        if hasattr(self, 'update_timer'):
            self.update_timer.stop()

        event.accept()

def create_trading_ui(trading_engine, scheduler):
    """Factory function to create trading UI"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    ui = TradingUI(trading_engine, scheduler)
    return ui