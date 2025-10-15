# runtime.py
# -*- coding: utf-8 -*-
"""Coordinación de ejecución compartida (eventos de stop y logging)."""

from __future__ import annotations

import logging
import os
import select
import sys
import threading
import time


STOP_EVENT = threading.Event()


def reset_stop_event() -> None:
    """Limpia el estado del evento global antes de iniciar un flujo."""
    STOP_EVENT.clear()


def request_stop(reason: str) -> None:
    if not STOP_EVENT.is_set():
        logging.getLogger("runtime").info("Deteniendo ejecución: %s", reason)
        STOP_EVENT.set()


def ensure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )


def start_q_listener(message: str, logger: logging.Logger) -> threading.Thread:
    def _watch() -> None:
        suffix = "" if os.name == "nt" else " y Enter"
        logger.info("%s%s", message, suffix)
        while not STOP_EVENT.is_set():
            try:
                if os.name == "nt":
                    import msvcrt  # type: ignore

                    if msvcrt.kbhit():
                        ch = msvcrt.getwch()
                        if ch.lower() == "q":
                            request_stop("se presionó Q")
                            break
                else:
                    ready, _, _ = select.select([sys.stdin], [], [], 0.2)
                    if ready:
                        ch = sys.stdin.readline().strip().lower()
                        if ch == "q":
                            request_stop("se presionó Q")
                            break
            except Exception:
                time.sleep(0.3)
            time.sleep(0.1)

    listener = threading.Thread(target=_watch, daemon=True)
    listener.start()
    return listener

