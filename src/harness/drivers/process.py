"""Process lifecycle management for agent drivers.

Provides a global child-process registry, process-group kill (Unix),
and a unified shutdown helper so that no orphan processes survive
when the harness exits — whether by normal completion, timeout,
SIGINT, or unhandled exception.

Inspired by CodeMachine-CLI's spawn.ts activeProcesses pattern.
"""

from __future__ import annotations

import atexit
import logging
import os
import signal
import subprocess
import sys
import threading

log = logging.getLogger("harness.drivers.process")

_active_processes: set[subprocess.Popen] = set()  # type: ignore[type-arg]
_lock = threading.Lock()
_shutting_down = False

# Seconds to wait after SIGTERM before escalating to SIGKILL
_SIGKILL_GRACE = 1.0


def register(proc: subprocess.Popen) -> None:  # type: ignore[type-arg]
    """Add *proc* to the global registry.  Call this right after ``Popen``."""
    with _lock:
        _active_processes.add(proc)


def unregister(proc: subprocess.Popen) -> None:  # type: ignore[type-arg]
    """Remove *proc* from the global registry.  Call after ``proc.wait()``."""
    with _lock:
        _active_processes.discard(proc)


def kill_process_tree(proc: subprocess.Popen) -> None:  # type: ignore[type-arg]
    """Kill *proc* and its children.

    On Unix, sends SIGTERM to the whole process group (``-pid``), then
    escalates to SIGKILL after ``_SIGKILL_GRACE`` seconds.
    On Windows, falls back to ``proc.kill()``.
    """
    pid = proc.pid
    if pid is None:
        return

    if sys.platform != "win32":
        try:
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            _safe_kill(proc)
            return

        def _escalate() -> None:
            try:
                os.killpg(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

        timer = threading.Timer(_SIGKILL_GRACE, _escalate)
        timer.daemon = True
        timer.start()
    else:
        _safe_kill(proc)


def kill_all_active() -> None:
    """Kill every tracked child process.  Safe to call from signal handlers."""
    global _shutting_down
    _shutting_down = True

    with _lock:
        procs = list(_active_processes)

    for proc in procs:
        kill_process_tree(proc)

    with _lock:
        _active_processes.clear()


def is_shutting_down() -> bool:
    """Return True if a global shutdown has been initiated."""
    return _shutting_down


def _safe_kill(proc: subprocess.Popen) -> None:  # type: ignore[type-arg]
    """Kill a single process, ignoring already-dead errors."""
    try:
        proc.kill()
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _start_new_process_group() -> None:
    """``preexec_fn`` for Unix Popen: create a new process group."""
    os.setpgrp()


def spawn_cursor(
    cmd: list[str],
    cwd: str,
) -> subprocess.Popen:  # type: ignore[type-arg]
    """Spawn a Cursor agent subprocess with proper process-group isolation.

    The child is placed in its own process group (Unix) so that
    ``kill_process_tree`` can cleanly terminate it and all grandchildren.
    """
    kwargs: dict = dict(
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
    )

    if sys.platform != "win32":
        kwargs["preexec_fn"] = _start_new_process_group

    proc = subprocess.Popen(cmd, **kwargs)
    register(proc)
    return proc


# Register atexit fallback so leaked processes are cleaned up
# even if nobody calls kill_all_active() explicitly.
atexit.register(kill_all_active)
