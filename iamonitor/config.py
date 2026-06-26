"""Configuration management for IAMonitor."""
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".config" / "iamonitor"
CONFIG_FILE = CONFIG_DIR / "config.json"
TASKS_FILE = CONFIG_DIR / "tasks.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "polling_interval": 120,
    "plan_type": "pro",
    "daily_budget_minutes": 480,
    "reset_hour": 0,
    "alert_at_percentage": 80,
    "oauth_token": "",
}


def _ensure_config_dir() -> None:
    """Create config directory if it doesn't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    """Load config from disk, filling in defaults for any missing keys."""
    _ensure_config_dir()
    config = dict(DEFAULT_CONFIG)  # start with defaults
    if CONFIG_FILE.exists():
        try:
            with CONFIG_FILE.open("r", encoding="utf-8") as f:
                stored = json.load(f)
            config.update(stored)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read config file, using defaults: %s", exc)
    return config


def save_config(config: dict) -> None:
    """Persist config to disk."""
    _ensure_config_dir()
    try:
        with CONFIG_FILE.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except OSError as exc:
        logger.error("Failed to save config: %s", exc)


def load_tasks() -> list:
    """Load task list from disk. Returns empty list if file missing/invalid."""
    _ensure_config_dir()
    if not TASKS_FILE.exists():
        return []
    try:
        with TASKS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        logger.warning("tasks.json did not contain a list, resetting")
        return []
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read tasks file: %s", exc)
        return []


def save_tasks(tasks: list) -> None:
    """Persist task list to disk."""
    _ensure_config_dir()
    try:
        with TASKS_FILE.open("w", encoding="utf-8") as f:
            json.dump(tasks, f, indent=2)
    except OSError as exc:
        logger.error("Failed to save tasks: %s", exc)
