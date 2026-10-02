"""Простой маршрутизатор API/SPA."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from .auth import authorized
from .http import send_json

HandlerFn = Callable[..., None]

log = logging.getLogger("router")

# Клиент закрыл вкладку посреди ответа: это не ошибка сервера и отвечать уже некому.
CLIENT_GONE = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)


@dataclass
class Route:
    method: str
    path: str | None
    prefix: str | None
    fn: HandlerFn
    auth: bool = False
    catch_all: bool = False


def _fail(handler) -> None:
    """Ответить 500, если ответ ещё не начат; иначе только закрыть соединение (второй ответ испортил бы первый)."""
    if getattr(handler, "response_started", False):
        handler.close_connection = True
        return
    try:
        send_json(handler, {"error": "Внутренняя ошибка сервера"}, 500)
    except CLIENT_GONE:
        handler.close_connection = True


class Router:
    def __init__(self) -> None:
        self._routes: list[Route] = []

    def add(
        self,
        method: str,
        path: str,
        fn: HandlerFn,
        *,
        auth: bool = False,
    ) -> None:
        self._routes.append(Route(method.upper(), path, None, fn, auth=auth))

    def add_prefix(
        self,
        method: str,
        prefix: str,
        fn: HandlerFn,
        *,
        auth: bool = False,
    ) -> None:
        self._routes.append(Route(method.upper(), None, prefix, fn, auth=auth))

    def add_catch_all(self, method: str, fn: HandlerFn) -> None:
        self._routes.append(Route(method.upper(), None, None, fn, catch_all=True))

    def dispatch(self, handler, method: str, path: str) -> bool:
        method = method.upper()
        catch_alls: list[Route] = []
        for route in self._routes:
            if route.method != method:
                continue
            if route.catch_all:
                catch_alls.append(route)
                continue
            match = False
            rest = ""
            if route.path is not None and path == route.path:
                match = True
            elif route.prefix is not None and path.startswith(route.prefix):
                rest = path[len(route.prefix) :].strip("/")
                if rest:
                    match = True
            if not match:
                continue
            try:
                if route.auth and not authorized(handler):
                    send_json(handler, {"error": "Нужен вход"}, 401)
                    return True
                if route.prefix is not None:
                    route.fn(handler, rest)
                else:
                    route.fn(handler)
            except CLIENT_GONE:
                handler.close_connection = True
            except Exception:
                log.exception("%s %s", method, path)
                _fail(handler)
            return True

        for route in catch_alls:
            try:
                if route.fn(handler, path):
                    return True
            except CLIENT_GONE:
                handler.close_connection = True
                return True
            except Exception:
                log.exception("catch-all %s %s", method, path)
                _fail(handler)
                return True
        return False
