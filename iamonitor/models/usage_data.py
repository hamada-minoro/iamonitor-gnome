"""Usage data models for IAMonitor."""
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


@dataclass
class UsageEntry:
    """A single entry from ~/.claude/history.jsonl."""
    display: str
    timestamp_ms: int  # milliseconds since epoch
    project: Optional[str]
    session_id: Optional[str]


@dataclass
class RateLimitData:
    """Rate limit data from Anthropic API response headers."""
    session_utilization: float = 0.0    # 0.0–1.0
    session_reset_epoch: int = 0
    weekly_utilization: float = 0.0
    weekly_reset_epoch: int = 0
    last_updated: float = 0.0           # time.time() when last polled
    error: Optional[str] = None


@dataclass
class DailySummary:
    """Summary of activity for today."""
    prompt_count: int = 0
    session_count: int = 0
    active_minutes: int = 0
    entries: list = field(default_factory=list)  # list of UsageEntry for today


class UsageTrend(Enum):
    UP = "up"
    DOWN = "down"
    STABLE = "stable"
