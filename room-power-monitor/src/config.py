"""Backward-compatible re-exports from electrifyszu.config.

Kept for existing code that does `from room_power_monitor.src.config import Config`.
New code should use `from electrifyszu.config import DormConfig`.
"""

from electrifyszu.config import DormConfig as Config  # noqa: F401
from electrifyszu.config import load_dotenv as _load_dotenv  # noqa: F401
