#!/usr/bin/env python3
"""Health check watchdog -- polls the API and restarts on failure."""

import logging
import time
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

API_URL = "http://127.0.0.1:8420/api/health"
CHECK_INTERVAL = 30  # seconds
MAX_FAILURES = 3
RESTART_COOLDOWN = 60  # seconds between restart attempts


def check_health() -> bool:
    try:
        resp = requests.get(API_URL, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


def restart_services():
    logger.warning("Restarting services...")
    try:
        subprocess.run([sys.executable, "launcher.py", "stop"], timeout=30)
        time.sleep(5)
        subprocess.run([sys.executable, "launcher.py", "start", "--paper"], timeout=30)
        logger.info("Services restarted")
    except Exception as e:
        logger.error(f"Restart failed: {e}")


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    logger.info(f"Health watchdog started. Polling {API_URL} every {CHECK_INTERVAL}s")

    consecutive_failures = 0
    last_restart = 0

    while True:
        if check_health():
            if consecutive_failures > 0:
                logger.info("Service recovered")
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            logger.warning(f"Health check failed ({consecutive_failures}/{MAX_FAILURES})")

            if consecutive_failures >= MAX_FAILURES:
                now = time.time()
                if now - last_restart > RESTART_COOLDOWN:
                    restart_services()
                    last_restart = now
                    consecutive_failures = 0
                else:
                    logger.warning(f"Restart cooldown active ({RESTART_COOLDOWN}s)")

        time.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    main()
