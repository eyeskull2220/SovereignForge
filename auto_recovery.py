#!/usr/bin/env python3
"""
SovereignForge Auto-Recovery System
Automatically handles common failure scenarios for personal use
"""

import os
import sys
import time
import json
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/auto_recovery.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class AutoRecovery:
    """Handles automatic recovery from common failure scenarios"""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = Path(project_root or Path.cwd())
        self.config_file = self.project_root / "personal_config.json"
        self.max_retries = 3
        self.retry_delay = 5  # seconds

    def load_config(self) -> Dict[str, Any]:
        """Load personal configuration"""
        try:
            with open(self.config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {}

    def check_service_health(self, service_name: str) -> bool:
        """Check if a specific service is healthy"""
        try:
            # Check if container is running
            result = subprocess.run(
                ["docker", "ps", "--filter", f"name={service_name}", "--format", "{{.Status}}"],
                capture_output=True, text=True, timeout=10
            )

            if result.returncode == 0 and "Up" in result.stdout:
                logger.info(f"Service {service_name} is running")
                return True
            else:
                logger.warning(f"Service {service_name} is not running")
                return False
        except Exception as e:
            logger.error(f"Error checking service {service_name}: {e}")
            return False

    def restart_service(self, service_name: str) -> bool:
        """Restart a specific service"""
        try:
            logger.info(f"Restarting service: {service_name}")

            # Change to project directory
            os.chdir(self.project_root)

            # Restart the service
            result = subprocess.run(
                ["docker-compose", "restart", service_name],
                capture_output=True, text=True, timeout=30
            )

            if result.returncode == 0:
                logger.info(f"Successfully restarted {service_name}")
                # Wait a moment for service to start
                time.sleep(5)
                return True
            else:
                logger.error(f"Failed to restart {service_name}: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Error restarting service {service_name}: {e}")
            return False

    def restart_all_services(self) -> bool:
        """Restart all services"""
        try:
            logger.info("Restarting all services")

            os.chdir(self.project_root)

            result = subprocess.run(
                ["docker-compose", "restart"],
                capture_output=True, text=True, timeout=60
            )

            if result.returncode == 0:
                logger.info("Successfully restarted all services")
                time.sleep(10)  # Wait for services to fully start
                return True
            else:
                logger.error(f"Failed to restart services: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Error restarting services: {e}")
            return False

    def check_api_health(self) -> bool:
        """Check if the API is responding"""
        try:
            import requests
            response = requests.get("http://localhost:8000/health", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"API health check failed: {e}")
            return False

    def check_dashboard_health(self) -> bool:
        """Check if the dashboard is accessible"""
        try:
            import requests
            response = requests.get("http://localhost:5173", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Dashboard health check failed: {e}")
            return False

    def cleanup_docker_resources(self) -> bool:
        """Clean up unused Docker resources"""
        try:
            logger.info("Cleaning up Docker resources")

            # Remove stopped containers
            subprocess.run(["docker", "container", "prune", "-f"], timeout=30)

            # Remove unused images
            subprocess.run(["docker", "image", "prune", "-f"], timeout=30)

            # Remove unused volumes
            subprocess.run(["docker", "volume", "prune", "-f"], timeout=30)

            logger.info("Docker cleanup completed")
            return True

        except Exception as e:
            logger.error(f"Docker cleanup failed: {e}")
            return False

    def recover_from_failure(self, failure_type: str = "general") -> bool:
        """Main recovery logic"""
        logger.info(f"Starting recovery process for: {failure_type}")

        config = self.load_config()
        if not config.get("personal_mode", {}).get("auto_recovery", False):
            logger.info("Auto-recovery disabled in config")
            return False

        success = False

        # Try different recovery strategies based on failure type
        if failure_type == "api_down":
            logger.info("Attempting API recovery")
            success = self.restart_service("api")

        elif failure_type == "dashboard_down":
            logger.info("Attempting dashboard recovery")
            success = self.restart_service("dashboard")

        elif failure_type == "services_down":
            logger.info("Attempting full service recovery")
            success = self.restart_all_services()

        else:
            # General recovery - try restarting all services
            logger.info("Attempting general recovery")
            success = self.restart_all_services()

        if success:
            logger.info("Recovery successful")
            # Send notification if configured
            self.send_recovery_notification(success=True, failure_type=failure_type)
        else:
            logger.error("Recovery failed")
            self.send_recovery_notification(success=False, failure_type=failure_type)

        return success

    def send_recovery_notification(self, success: bool, failure_type: str) -> None:
        """Send notification about recovery attempt"""
        try:
            config = self.load_config()
            if not config.get("monitoring", {}).get("enable_telegram", False):
                return

            # TODO: Implement Telegram notification
            # For now, just log
            status = "successful" if success else "failed"
            logger.info(f"Recovery {status} for {failure_type}")

        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

    def run_health_checks(self) -> Dict[str, bool]:
        """Run comprehensive health checks"""
        results = {}

        # Check Docker
        try:
            subprocess.run(["docker", "info"], capture_output=True, timeout=5)
            results["docker"] = True
        except:
            results["docker"] = False

        # Check services
        results["api_service"] = self.check_service_health("sovereignforge-api")
        results["dashboard_service"] = self.check_service_health("sovereignforge-dashboard")

        # Check endpoints
        results["api_health"] = self.check_api_health()
        results["dashboard_health"] = self.check_dashboard_health()

        return results

    def auto_recover_if_needed(self) -> bool:
        """Check health and recover if needed"""
        logger.info("Running auto-recovery check")

        health_results = self.run_health_checks()

        # Determine what needs recovery
        if not health_results.get("api_health", False):
            logger.warning("API health check failed, attempting recovery")
            return self.recover_from_failure("api_down")

        elif not health_results.get("dashboard_health", False):
            logger.warning("Dashboard health check failed, attempting recovery")
            return self.recover_from_failure("dashboard_down")

        elif not (health_results.get("api_service", False) and health_results.get("dashboard_service", False)):
            logger.warning("Services not running, attempting recovery")
            return self.recover_from_failure("services_down")

        else:
            logger.info("All systems healthy")
            return True

def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: python auto_recovery.py <command>")
        print("Commands: check, recover, cleanup")
        sys.exit(1)

    command = sys.argv[1]
    recovery = AutoRecovery()

    if command == "check":
        results = recovery.run_health_checks()
        print("Health Check Results:")
        for check, status in results.items():
            status_icon = "✓" if status else "✗"
            print(f"  {status_icon} {check}: {'OK' if status else 'FAILED'}")

    elif command == "recover":
        success = recovery.auto_recover_if_needed()
        sys.exit(0 if success else 1)

    elif command == "cleanup":
        success = recovery.cleanup_docker_resources()
        sys.exit(0 if success else 1)

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()