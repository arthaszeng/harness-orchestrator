"""Task state enumeration for workflow phases."""

from __future__ import annotations

from enum import Enum


class TaskState(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    CONTRACTED = "contracted"
    BUILDING = "building"
    EVALUATING = "evaluating"
    SHIPPING = "shipping"
    DONE = "done"
    BLOCKED = "blocked"
