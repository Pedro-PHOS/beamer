"""Log uncaught worker-thread exceptions; fatal-signal logging is opt-in."""

from __future__ import annotations

import faulthandler
import logging
import sys
import threading

# Held for the life of the process: faulthandler writes to the descriptor, not the object.
_fault_file = None


def install(directory, logger=None, fatal_signals=None) -> None:
    """`directory` is where the app's log lives; `crash.log` is written there on a fatal signal.
    `fatal_signals` defaults to False: on Windows faulthandler also reports access violations
    that the code raising them goes on to handle, and would fill the file with crashes that were not."""
    global _fault_file
    logger = logger or logging.getLogger("Beamer")

    def log_thread_exception(args):
        if issubclass(args.exc_type, SystemExit):
            return
        name = args.thread.name if args.thread is not None else "unknown"
        logger.critical("thread %s ended on an uncaught exception", name,
                        exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    threading.excepthook = log_thread_exception
    if fatal_signals is None:
        fatal_signals = False
    if not fatal_signals:
        return
    try:
        _fault_file = open(f"{directory}/crash.log", "a", encoding="utf-8")
        faulthandler.enable(file=_fault_file, all_threads=True)
    except (OSError, ValueError, RuntimeError):
        logger.exception("could not set up crash.log")
