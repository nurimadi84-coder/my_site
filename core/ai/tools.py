"""Реестр AI-tools: контекст в system prompt + опциональные действия."""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

log = logging.getLogger("ai.tools")


@runtime_checkable
class Tool(Protocol):
    name: str
    description: str

    def context(self, products: list, history: list) -> str: ...

    def maybe_act(self, message: str, history: list) -> dict | None: ...


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: list[Tool] = []

    def register(self, tool: Tool) -> None:
        self._tools = [t for t in self._tools if getattr(t, "name", None) != tool.name]
        self._tools.append(tool)

    def all(self) -> list[Tool]:
        return list(self._tools)

    def build_context(self, products: list, history: list) -> str:
        parts = []
        for tool in self._tools:
            try:
                chunk = tool.context(products, history)
            except Exception:
                # Один сломанный инструмент не должен валить весь чат, но сбой обязан быть виден в логе.
                log.exception("tool %s: context() упал, контекст инструмента пропущен", getattr(tool, "name", tool))
                continue
            if chunk and str(chunk).strip():
                parts.append(str(chunk).strip())
        return "\n\n".join(parts)

    def run_actions(self, message: str, history: list) -> dict | None:
        for tool in self._tools:
            try:
                result = tool.maybe_act(message, history)
            except Exception:
                log.exception("tool %s: maybe_act() упал", getattr(tool, "name", tool))
                continue
            if result:
                return result
        return None
