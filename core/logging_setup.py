"""Единое логирование: консоль + logs/server.log (всё) + logs/error.log (ошибки со стеком)."""

from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

from .config import LOG_DIR

FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def setup_logging(level: int = logging.INFO) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(FORMAT)

    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        # Консоль Windows (cp866) не знает ₸ и эмодзи: без замены логгер сыплет «--- Logging error ---».
        reconfigure(errors="replace")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)

    everything = RotatingFileHandler(LOG_DIR / "server.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    everything.setFormatter(formatter)

    errors = RotatingFileHandler(LOG_DIR / "error.log", maxBytes=5_000_000, backupCount=10, encoding="utf-8")
    errors.setLevel(logging.ERROR)
    errors.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for handler in (console, everything, errors):
        root.addHandler(handler)

    def log_uncaught(exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        logging.getLogger("uncaught").critical("необработанное исключение", exc_info=(exc_type, exc, tb))

    def log_thread(args) -> None:
        logging.getLogger("uncaught").critical(
            "необработанное исключение в потоке %s",
            getattr(args.thread, "name", "?"),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = log_uncaught
    threading.excepthook = log_thread
