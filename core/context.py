"""Общий контекст приложения для feature-модулей."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .ai.tools import ToolRegistry
from .config import CHAT_DIR, DB_FILE, DIST, ROOT, UPLOAD_DIR
from .router import Router


@dataclass
class AppContext:
    root: Path = ROOT
    dist: Path = DIST
    db_file: Path = DB_FILE
    upload_dir: Path = UPLOAD_DIR
    chat_dir: Path = CHAT_DIR
    router: Router = field(default_factory=Router)
    tools: ToolRegistry = field(default_factory=ToolRegistry)
