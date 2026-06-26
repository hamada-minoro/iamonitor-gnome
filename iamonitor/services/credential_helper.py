"""Multi-fallback OAuth credential reader for IAMonitor.

Priority order:
  1. GNOME Keyring via secretstorage
  2. File: ~/.claude/.credentials.json
  3. Manual token stored in config
"""
import json
import logging
from pathlib import Path
from typing import Optional

from iamonitor import config as cfg

__all__ = ["get_oauth_token", "save_manual_token"]

logger = logging.getLogger(__name__)

_CLAUDE_CREDENTIALS_FILE = Path.home() / ".claude" / ".credentials.json"
_KEYRING_SERVICE_NAME = "Claude Code-credentials"


def _extract_token_from_json(data: dict) -> Optional[str]:
    """Extract OAuth access token from Claude credentials JSON structure."""
    try:
        token = data.get("claudeAiOauth", {}).get("accessToken")
        if token and isinstance(token, str) and token.strip():
            return token.strip()
    except (AttributeError, TypeError):
        pass
    return None


def _try_keyring() -> Optional[str]:
    """Try to get token from GNOME Keyring via secretstorage."""
    try:
        import secretstorage  # type: ignore[import]
        connection = secretstorage.dbus_init()
        items = list(secretstorage.get_all_items(connection))
        for item in items:
            try:
                attrs = item.get_attributes()
                label = item.get_label()
                # Match by attribute 'service' or by label
                service_attr = attrs.get("service", "")
                if (
                    service_attr == _KEYRING_SERVICE_NAME
                    or label == _KEYRING_SERVICE_NAME
                    or "Claude Code" in label
                ):
                    secret_bytes = item.get_secret()
                    secret_str = secret_bytes.decode("utf-8", errors="replace")
                    data = json.loads(secret_str)
                    token = _extract_token_from_json(data)
                    if token:
                        logger.info("Loaded OAuth token from GNOME Keyring")
                        return token
            except Exception as exc:  # noqa: BLE001
                logger.debug("Error reading keyring item: %s", exc)
                continue
    except ImportError:
        logger.debug("secretstorage not available")
    except Exception as exc:  # noqa: BLE001
        logger.debug("Keyring access failed: %s", exc)
    return None


def _try_credentials_file() -> Optional[str]:
    """Try to read token from ~/.claude/.credentials.json."""
    if not _CLAUDE_CREDENTIALS_FILE.exists():
        return None
    try:
        with _CLAUDE_CREDENTIALS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        token = _extract_token_from_json(data)
        if token:
            logger.info("Loaded OAuth token from %s", _CLAUDE_CREDENTIALS_FILE)
            return token
    except (json.JSONDecodeError, OSError) as exc:
        logger.debug("Could not read credentials file: %s", exc)
    return None


def _try_config_token() -> Optional[str]:
    """Try to get token from IAMonitor's own config."""
    config = cfg.load_config()
    token = config.get("oauth_token", "").strip()
    if token:
        logger.info("Using manually configured OAuth token")
        return token
    return None


def get_oauth_token() -> tuple[Optional[str], str]:
    """Return (token, source_description).

    source is one of: 'keyring', 'file', 'config', 'none'
    """
    token = _try_keyring()
    if token:
        return token, "keyring"

    token = _try_credentials_file()
    if token:
        return token, "file"

    token = _try_config_token()
    if token:
        return token, "config"

    return None, "none"


def save_manual_token(token: str) -> None:
    """Save a manually entered OAuth token to config."""
    config = cfg.load_config()
    config["oauth_token"] = token.strip()
    cfg.save_config(config)
    logger.info("Saved manual OAuth token to config")
