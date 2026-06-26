"""Task budget models for IAMonitor."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import uuid
from datetime import datetime


class PlanType(Enum):
    PRO = "pro"
    MAX_5X = "max_5x"
    MAX_20X = "max_20x"


@dataclass
class TaskBudget:
    """A task with an allocated time budget."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    allocated_minutes: int = 60
    used_minutes: int = 0
    is_active: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        """Serialize to a plain dict for JSON storage."""
        return {
            "id": self.id,
            "name": self.name,
            "allocated_minutes": self.allocated_minutes,
            "used_minutes": self.used_minutes,
            "is_active": self.is_active,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaskBudget":
        """Deserialize from a plain dict."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            allocated_minutes=data.get("allocated_minutes", 60),
            used_minutes=data.get("used_minutes", 0),
            is_active=data.get("is_active", False),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )
