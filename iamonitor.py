#!/usr/bin/env python3
"""IAMonitor — Claude Pro/Max usage monitor for GNOME/Linux."""
import sys
import logging
from iamonitor.app import IAMonitorApp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

if __name__ == "__main__":
    app = IAMonitorApp()
    sys.exit(app.run())
