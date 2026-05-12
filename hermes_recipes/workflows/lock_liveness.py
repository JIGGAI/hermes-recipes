"""Liveness probe for stale node locks.

Port of clawrecipes/src/lib/workflows/lock-liveness.ts. Cross-host locks are
never reclaimed; only same-host pids that respond ``ESRCH`` to signal 0 count
as dead.
"""

import os
import socket
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LockOwner:
    pid: int
    host: str


def current_lock_owner() -> LockOwner:
    return LockOwner(pid=os.getpid(), host=socket.gethostname())


def is_lock_holder_dead(lock_info: dict[str, Any]) -> bool:
    host = lock_info.get("host")
    pid = lock_info.get("pid")
    same_host = isinstance(host, str) and host == socket.gethostname()
    if not same_host or not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return False
    except ProcessLookupError:
        return True
    except PermissionError:
        # Another user owns this pid — it's alive, just not signalable.
        return False
    except OSError:
        return False
