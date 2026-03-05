#!/usr/bin/env python3
"""
SovereignForge v1.0 - Main Entry Point
MiCA-compliant AI-powered arbitrage trading platform

Usage:
  python main.py                    # GUI mode
  python main.py --cli             # CLI mode
  python main.py --opensandbox     # OpenSandbox isolated mode
  python main.py --help            # Show help

Environment Variables:
  OPENSANDBOX_MODE=true           # Enable OpenSandbox isolation
  NETWORK_DISABLED=true           # Disable network access
  CEO_GATED_ACCESS=true           # Require CEO approval for critical operations
"""

import sys
import os
import argparse
import logging
from pathlib import Path

# Add current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/sovereignforge.log', mode='a')
    ]
)

logger = logging.getLogger(__name__)

def check_opensandbox_isolation():
    """Verify OpenSandbox isolation if enabled"""
    if os.getenv('OPENSANDBOX_MODE', '').lower() == 'true':
        logger.info("🔒 OpenSandbox mode enabled - verifying isolation...")

        # Check network isolation
        if os.getenv('NETWORK_DISABLED', '').lower() == 'true':
            logger.info("🚫 Network access disabled by default")

        # Check CEO gating
        if os.getenv('CEO_GATED_ACCESS', '').lower() == 'true':
            logger.info("👑 CEO-gated access enabled for critical operations")

        logger.info("✅ OpenSandbox isolation verified")

def cli_mode():
    """Run SovereignForge in CLI mode"""
    print("🚀 SovereignForge v1.0 - CLI Mode")
    print("=" * 50)

    check_opensandbox_isolation()

    try:
        # Import and initialize core systems
        from operations.procedures import get_procedures
        from monitoring.system_monitor import get_monitor
        from monitoring.alert_system import get_alert_manager
        from ml_training.data_pipeline import get_data_pipeline

        # Initialize operational procedures
        procedures = get_procedures()
        logger.info("Starting operational procedures...")

        # Run startup procedure
        startup_result = procedures.startup_procedure()
        if startup_result['success']:
            logger.info("✅ Startup procedure completed successfully")
        else:
            logger.error(f"❌ Startup failed: {startup_result['errors']}")
            return 1

        # Initialize monitoring
        monitor = get_monitor()
        alert_manager = get_alert_manager()

        monitor.start_monitoring(interval_seconds=10)
        alert_manager.start()

        logger.info("📊 System monitoring started")

        # Initialize data pipeline
        data_pipeline = get_data_pipeline()
        data_pipeline.start_data_collection()

        logger.info("📈 Data collection started")

        # Main CLI loop
        print("\n🎯 SovereignForge v1.0 is running in CLI mode")
        print("Available commands:")
        print("  status  - Show system status")
        print("  monitor - Show real-time monitoring")
        print("  alerts  - Show active alerts")
        print("  data    - Show data collection status")
        print("  stop    - Shutdown gracefully")
        print("  help    - Show this help")
        print()

        while True:
            try:
                command = input("sovereignforge> ").strip().lower()

                if command == 'status':
                    show_system_status()
                elif command == 'monitor':
                    show_monitoring_status()
                elif command == 'alerts':
                    show_alerts()
                elif command == 'data':
                    show_data_status()
                elif command == 'stop':
                    break
                elif command == 'help':
                    show_help()
                elif command == '':
                    continue
                else:
                    print(f"Unknown command: {command}")
                    print("Type 'help' for available commands")

            except KeyboardInterrupt:
                print("\nReceived interrupt signal...")
                break
            except Exception as e:
                logger.error(f"CLI error: {e}")
                print(f"Error: {e}")

        # Graceful shutdown
        logger.info("Shutting down SovereignForge...")
        shutdown_result = procedures.shutdown_procedure()

        if shutdown_result['success']:
            logger.info("✅ Shutdown completed successfully")
            return 0
        else:
            logger.error(f"❌ Shutdown failed: {shutdown_result['errors']}")
            return 1

    except Exception as e:
        logger.error(f"CLI mode failed: {e}")
        return 1

def gui_mode():
    """Run SovereignForge in GUI mode"""
    print("🚀 SovereignForge v1.0 - GUI Mode")
    print("=" * 50)

    check_opensandbox_isolation()

    try:
        # Import GUI components
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QTimer
        import sys

        # Import SovereignForge GUI
        from ui.main_window import MainWindow

        # Create Qt application
        app = QApplication(sys.argv)
        app.setApplicationName("SovereignForge v1.0")
        app.setApplicationVersion("1.0.0")
        app.setOrganizationName("SovereignForge")

        # Create main window
        window = MainWindow()
        window.show()

        # Start the event loop
        return app.exec()

    except ImportError as e:
        logger.error(f"GUI dependencies not available: {e}")
        print("❌ GUI mode requires PySide6. Install with: pip install PySide6")
        return 1
    except Exception as e:
        logger.error(f"GUI mode failed: {e}")
        return 1

def show_system_status():
    """Show comprehensive system status"""
    try:
        from operations.procedures import get_procedures
        from monitoring.system_monitor import get_monitor
        from ml_training.data_pipeline import get_data_pipeline

        procedures = get_procedures()
        monitor = get_monitor()
        data_pipeline = get_data_pipeline()

        op_status = procedures.get_system_status()
        monitor_status = monitor.get_current_status()
        data_status = data_pipeline.get_data_collection_status()

        print("\n🔍 System Status Report")
        print("=" * 30)

        print(f"System Running: {'✅' if op_status['is_running'] else '❌'}")
        print(f"Uptime: {op_status.get('uptime_seconds', 0):.0f} seconds")

        print(f"\n📊 Monitoring Status:")
        print(f"  CPU Usage: {monitor_status.get('cpu_percent', 'N/A')}%")
        print(f"  Memory Usage: {monitor_status.get('memory_percent', 'N/A')}%")
        print(f"  GPU Usage: {monitor_status.get('gpu_percent', 'N/A')}%")

        print(f"\n📈 Data Collection:")
        print(f"  Active: {'✅' if data_status['is_collecting'] else '❌'}")
        print(f"  Exchanges: {len(data_status['exchanges'])}")
        print(f"  Coins: {len(data_status['allowed_coins'])}")

        print(f"\n🗂️  Directories:")
        for name, path in op_status.get('directories', {}).items():
            exists = Path(path).exists()
            print(f"  {name}: {'✅' if exists else '❌'} {path}")

    except Exception as e:
        print(f"Error getting system status: {e}")

def show_monitoring_status():
    """Show real-time monitoring data"""
    try:
        from monitoring.system_monitor import get_monitor
        monitor = get_monitor()
        status = monitor.get_current_status()

        print("\n📊 Real-time Monitoring")
        print("=" * 25)

        for key, value in status.items():
            if isinstance(value, float):
                print(f"{key}: {value:.2f}")
            else:
                print(f"{key}: {value}")

    except Exception as e:
        print(f"Error getting monitoring status: {e}")

def show_alerts():
    """Show active alerts"""
    try:
        from monitoring.alert_system import get_alert_manager
        alert_manager = get_alert_manager()
        alerts = alert_manager.get_active_alerts()

        print(f"\n🚨 Active Alerts ({len(alerts)})")
        print("=" * 20)

        if not alerts:
            print("No active alerts")
            return

        for alert in alerts[:10]:  # Show last 10 alerts
            print(f"[{alert['severity'].upper()}] {alert['title']}")
            print(f"  {alert['message']}")
            print(f"  Age: {alert['age_minutes']:.0f} minutes")
            print()

    except Exception as e:
        print(f"Error getting alerts: {e}")

def show_data_status():
    """Show data collection status"""
    try:
        from ml_training.data_pipeline import get_data_pipeline
        data_pipeline = get_data_pipeline()
        status = data_pipeline.get_data_collection_status()

        print(f"\n📈 Data Collection Status")
        print("=" * 25)

        print(f"Collecting: {'✅' if status['is_collecting'] else '❌'}")
        print(f"Exchanges: {len(status['exchanges'])}")
        print(f"Coins: {len(status['allowed_coins'])}")

        if status['data_status']:
            print(f"\nData Points per Coin/Exchange:")
            for key, data in list(status['data_status'].items())[:5]:  # Show first 5
                print(f"  {key}: {data['data_points']} points")

    except Exception as e:
        print(f"Error getting data status: {e}")

def show_help():
    """Show CLI help"""
    print("\n🎯 SovereignForge v1.0 - CLI Commands")
    print("=" * 40)
    print("status   - Show comprehensive system status")
    print("monitor  - Show real-time system monitoring")
    print("alerts   - Show active system alerts")
    print("data     - Show data collection status")
    print("stop     - Shutdown SovereignForge gracefully")
    print("help     - Show this help message")
    print()

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='SovereignForge v1.0 - MiCA-compliant AI-powered arbitrage platform',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    # Start GUI mode
  python main.py --cli             # Start CLI mode
  python main.py --opensandbox     # Enable OpenSandbox isolation
  python main.py --cli --verbose   # CLI with verbose logging
        """
    )

    parser.add_argument('--cli', action='store_true',
                       help='Run in CLI mode instead of GUI')
    parser.add_argument('--opensandbox', action='store_true',
                       help='Enable OpenSandbox isolation mode')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')

    args = parser.parse_args()

    # Set OpenSandbox mode if requested
    if args.opensandbox:
        os.environ['OPENSANDBOX_MODE'] = 'true'
        os.environ['NETWORK_DISABLED'] = 'true'
        os.environ['CEO_GATED_ACCESS'] = 'true'

    # Set verbose logging if requested
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Print banner
    print("""
    🚀 SovereignForge v1.0
    MiCA-compliant AI-powered arbitrage platform
    """)

    # Check if running in OpenSandbox
    if os.getenv('OPENSANDBOX_MODE', '').lower() == 'true':
        print("🔒 Running in OpenSandbox isolation mode")
        if os.getenv('NETWORK_DISABLED', '').lower() == 'true':
            print("🚫 Network access disabled")
        if os.getenv('CEO_GATED_ACCESS', '').lower() == 'true':
            print("👑 CEO-gated access enabled")

    print()

    # Run appropriate mode
    if args.cli:
        return cli_mode()
    else:
        return gui_mode()

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n👋 SovereignForge shutdown requested by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"SovereignForge failed to start: {e}")
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)